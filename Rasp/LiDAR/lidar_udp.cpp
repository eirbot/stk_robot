#include <algorithm>
#include <arpa/inet.h>
#include <cmath>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>

using namespace std;

#include <signal.h>

int global_serial_fd = -1;

void sig_handler(int signo) {
  if (signo == SIGTERM || signo == SIGINT) {
    cout << "\n[LIDAR C++] 🛑 Signal recu, arret du moteur LiDAR..." << endl;
    if (global_serial_fd >= 0) {
      unsigned char stop_cmd[] = {0xA5, 0x25};
      write(global_serial_fd, stop_cmd, 2);
      usleep(50000);
      close(global_serial_fd);
      global_serial_fd = -1;
    }
    exit(0);
  }
}

#pragma pack(push, 1)
struct LidarPoint {
  float angle;
  float distance;
  float intensity;
};

struct LidarState {
  LidarPoint closest_obstacle;
  int num_beacons;
  LidarPoint beacons[4];
};
#pragma pack(pop)

void read_exactly(int fd, unsigned char *buf, int n) {
  int total = 0;
  while (total < n) {
    int r = read(fd, buf + total, n - total);
    if (r > 0)
      total += r;
  }
}

float normalize_angle(float angle) {
  angle = fmod(angle, 360.0f);
  if (angle < 0)
    angle += 360.0f;
  return angle;
}

int main() {
  signal(SIGINT, sig_handler);
  signal(SIGTERM, sig_handler);

  int sock = socket(AF_INET, SOCK_DGRAM, 0);
  sockaddr_in addr;
  addr.sin_family = AF_INET;
  addr.sin_port = htons(8080);
  inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

  const char *port = "/dev/lidar";
  int serial_fd = open(port, O_RDWR | O_NOCTTY | O_SYNC);
  global_serial_fd = serial_fd;
  if (serial_fd < 0) {
    cout << "[LIDAR C++] ❌ ERREUR: Impossible d'ouvrir " << port << endl;
    return 1;
  }
  cout << "[LIDAR C++] ✅ Connecté sur " << port << endl;

  struct termios tty;
  tcgetattr(serial_fd, &tty);
  cfsetospeed(&tty, B460800);
  cfsetispeed(&tty, B460800);
  tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;
  tty.c_iflag &= ~IGNBRK;
  tty.c_lflag = 0;
  tty.c_oflag = 0;
  tty.c_cc[VMIN] = 1;
  tty.c_cc[VTIME] = 1;
  tty.c_iflag &= ~(IXON | IXOFF | IXANY);
  tty.c_cflag |= (CLOCAL | CREAD);
  tcsetattr(serial_fd, TCSANOW, &tty);

  unsigned char stop_cmd[] = {0xA5, 0x25};
  write(serial_fd, stop_cmd, 2);
  usleep(50000);
  unsigned char start_cmd[] = {0xA5, 0x20};
  write(serial_fd, start_cmd, 2);
  unsigned char desc[7];
  read_exactly(serial_fd, desc, 7);

  unsigned char chunk[1024];
  unsigned char buf[5] = {0};

  float min_dist = 99999.0f, min_angle = 0.0f, min_qual = 0.0f;
  bool has_points = false;
  float last_angle_sync = -1.0f;
  float last_obj_dist = 0.0f;
  float last_obj_angle = 0.0f;
  int coherent_points = 0;
  int points_since_last_send = 0;

  LidarPoint detected_beacons[10];
  int beacon_count = 0;
  bool in_beacon_cluster = false;
  int cur_beacon_pts = 0;
  float cur_beacon_min_dist = 99999.0f;
  float cur_beacon_angle = 0.0f;
  float cur_beacon_qual = 0.0f;
  float last_beacon_dist = 0.0f;
  float last_beacon_angle = 0.0f;

  // --- PARAMÈTRES BALISES ---
  const int MIN_BEACON_POINTS = 2;
  const int MAX_BEACON_POINTS = 15; // Un humain fera souvent + de 20 points

  cout << "[LIDAR] C++ Prêt ! Filtre anti-humain (taille max: "
       << MAX_BEACON_POINTS << " pts) activé." << endl;

  while (true) {
    int n = read(serial_fd, chunk, sizeof(chunk));

    if (n <= 0) {
      cout << "[LIDAR C++] ❌ ERREUR DE LECTURE (Lidar débranché ou chute de "
              "tension ?)"
           << endl;
      close(serial_fd);
      usleep(1000000); // Wait 1 second
      serial_fd = open(port, O_RDWR | O_NOCTTY | O_SYNC);
      global_serial_fd = serial_fd;
      if (serial_fd >= 0) {
        tcsetattr(serial_fd, TCSANOW, &tty);
        write(serial_fd, start_cmd, 2);
        cout << "[LIDAR C++] ✅ Reconnexion USB réussie !" << endl;
      }
      continue;
    }

    for (int i = 0; i < n; i++) {
      buf[0] = buf[1];
      buf[1] = buf[2];
      buf[2] = buf[3];
      buf[3] = buf[4];
      buf[4] = chunk[i];

      if (((buf[0] & 0x01) ^ ((buf[0] >> 1) & 0x01)) == 1 &&
          (buf[1] & 0x01) == 1) {

        int S = buf[0] & 0x01;
        float angle = normalize_angle(((buf[2] << 7) | (buf[1] >> 1)) / 64.0f);
        float dist = ((buf[4] << 8) | buf[3]) / 4.0f;
        float qual = (float)((buf[0] >> 2) & 0x3F);

        bool angle_ok = true;
        if (last_angle_sync >= 0.0f && S == 0) {
          float diff = angle - last_angle_sync;
          if (diff < -180.0f)
            diff += 360.0f;
          else if (diff > 180.0f)
            diff -= 360.0f;
          if (diff < -2.0f || diff > 20.0f)
            angle_ok = false;
        }

        if (!angle_ok) {
          last_angle_sync = -1.0f;
          continue;
        }

        last_angle_sync = angle;
        points_since_last_send++;

        if (S == 1 || points_since_last_send > 2000) {
          // Fermer un cluster à la fin du tour ou en cas de blocage physique
          if (in_beacon_cluster && cur_beacon_pts >= MIN_BEACON_POINTS &&
              cur_beacon_pts <= MAX_BEACON_POINTS && beacon_count < 10) {
            detected_beacons[beacon_count++] = {
                cur_beacon_angle, cur_beacon_min_dist, cur_beacon_qual};
          }

          LidarState state;
          state.closest_obstacle =
              has_points ? LidarPoint{min_angle, min_dist, min_qual}
                         : LidarPoint{0.0f, 99999.0f, 0.0f};
          state.num_beacons = std::min(beacon_count, 4);

          for (int b = 0; b < 4; b++) {
            if (b < beacon_count)
              state.beacons[b] = detected_beacons[b];
            else
              state.beacons[b] = {0.0f, 0.0f, 0.0f};
          }

          sendto(sock, &state, sizeof(state), 0, (struct sockaddr *)&addr,
                 sizeof(addr));

          min_dist = 99999.0f;
          has_points = false;
          coherent_points = 0;
          beacon_count = 0;
          in_beacon_cluster = false;
          cur_beacon_pts = 0;
          points_since_last_send = 0;
        }

        // LOGIQUE BALISES
        if (dist > 80.0f && qual >= 48.0f) {
          float angle_diff = angle - last_beacon_angle;
          if (angle_diff < -180.0f)
            angle_diff += 360.0f;
          else if (angle_diff > 180.0f)
            angle_diff -= 360.0f;

          if (!in_beacon_cluster) {
            in_beacon_cluster = true;
            cur_beacon_pts = 1;
            cur_beacon_min_dist = dist;
            cur_beacon_angle = angle;
            cur_beacon_qual = qual;
          } else if (fabs(dist - last_beacon_dist) < 150.0f &&
                     fabs(angle_diff) < 5.0f) {
            cur_beacon_pts++;
            if (dist < cur_beacon_min_dist) {
              cur_beacon_min_dist = dist;
              cur_beacon_angle = angle;
              cur_beacon_qual = qual;
            }
          } else {
            // LE FILTRE ANTI-HUMAIN EST ICI
            if (cur_beacon_pts >= MIN_BEACON_POINTS &&
                cur_beacon_pts <= MAX_BEACON_POINTS && beacon_count < 10) {
              detected_beacons[beacon_count++] = {
                  cur_beacon_angle, cur_beacon_min_dist, cur_beacon_qual};
            }
            cur_beacon_pts = 1;
            cur_beacon_min_dist = dist;
            cur_beacon_angle = angle;
            cur_beacon_qual = qual;
          }
          last_beacon_dist = dist;
          last_beacon_angle = angle;
        } else {
          if (in_beacon_cluster) {
            // LE FILTRE ANTI-HUMAIN EST ICI AUSSI
            if (cur_beacon_pts >= MIN_BEACON_POINTS &&
                cur_beacon_pts <= MAX_BEACON_POINTS && beacon_count < 10) {
              detected_beacons[beacon_count++] = {
                  cur_beacon_angle, cur_beacon_min_dist, cur_beacon_qual};
            }
            in_beacon_cluster = false;
            cur_beacon_pts = 0;
          }
        }

        // LOGIQUE ANTI-COLLISION
        if (dist > 80.0f && qual > 10.0f) {
          float angle_diff = angle - last_obj_angle;
          if (angle_diff < -180.0f)
            angle_diff += 360.0f;
          else if (angle_diff > 180.0f)
            angle_diff -= 360.0f;

          if (fabs(dist - last_obj_dist) < 50.0f && fabs(angle_diff) < 5.0f)
            coherent_points++;
          else
            coherent_points = 1;

          last_obj_dist = dist;
          last_obj_angle = angle;

          if (coherent_points >= 3 && dist < min_dist) {
            min_dist = dist;
            min_angle = angle;
            min_qual = qual;
            has_points = true;
          }
        }

        buf[0] = 0;
        buf[1] = 0;
        buf[2] = 0;
        buf[3] = 0;
        buf[4] = 0;
      }
    }
  }
  return 0;
}