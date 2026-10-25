// Driver LiDAR RPLiDAR C1 (protocole : docu/RPLiDAR_C1M1_protocole_com.pdf).
//
// Lit les mesures sur /dev/lidar et, à chaque tour, envoie en UDP (127.0.0.1:8080) la
// distance minimale vue dans chaque secteur de SECTOR_DEG degrés. La décision
// (obstacle devant / derrière / tout près) est prise côté Python : Rasp/core/obstacles.py,
// qui définit aussi le format du paquet (à garder identique des deux côtés).
//
// Compilé sur la Rasp par main_robot.py (g++ -O3).

#include <arpa/inet.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>

using namespace std;

// --- Paramètres --------------------------------------------------------------------------
constexpr int SECTOR_DEG = 5;
constexpr int SECTORS = 360 / SECTOR_DEG;
constexpr float MIN_DIST_MM = 80.0f;     // en dessous : le robot lui-même / bruit
constexpr float MIN_QUALITY = 10.0f;
// Un point ne compte que s'il fait partie d'un groupe d'au moins COHERENT_POINTS points
// voisins (distance et angle proches) : élimine les mesures isolées aberrantes
constexpr int COHERENT_POINTS = 3;
constexpr float COHERENT_DIST_MM = 50.0f;
constexpr float COHERENT_ANGLE_DEG = 5.0f;

// --- Paquet UDP (little-endian, cf. Rasp/core/obstacles.py) ----------------------------------
#pragma pack(push, 1)
struct LidarScan {
  char magic[4];               // "LDR2"
  float closest_angle_deg;     // point le plus proche du tour (affichage sur la carte)
  float closest_dist_mm;       // 0 : aucun point
  float sector_min_mm[SECTORS];  // secteur i = angles [i*SECTOR_DEG, (i+1)*SECTOR_DEG[ ; 0 = rien vu
};
#pragma pack(pop)

int global_serial_fd = -1;
const unsigned char STOP_CMD[] = {0xA5, 0x25};
const unsigned char SCAN_CMD[] = {0xA5, 0x20};

void sig_handler(int signo) {
  if (signo == SIGTERM || signo == SIGINT) {
    cout << "\n[LIDAR C++] 🛑 Signal recu, arret du moteur LiDAR..." << endl;
    if (global_serial_fd >= 0) {
      write(global_serial_fd, STOP_CMD, 2);
      usleep(50000);
      close(global_serial_fd);
      global_serial_fd = -1;
    }
    exit(0);
  }
}

void read_exactly(int fd, unsigned char *buf, int n) {
  int total = 0;
  while (total < n) {
    int r = read(fd, buf + total, n - total);
    if (r > 0) total += r;
  }
}

float normalize_angle(float angle) {
  angle = fmod(angle, 360.0f);
  return angle < 0 ? angle + 360.0f : angle;
}

float angle_gap(float a, float b) {
  float d = a - b;
  if (d < -180.0f) d += 360.0f;
  else if (d > 180.0f) d -= 360.0f;
  return fabs(d);
}

// Accumule les mesures d'un tour
struct ScanBuilder {
  LidarScan scan;
  float last_dist = 0.0f, last_angle = 0.0f;
  int coherent = 0;

  ScanBuilder() { reset(); }

  void reset() {
    memset(&scan, 0, sizeof scan);
    memcpy(scan.magic, "LDR2", 4);
    coherent = 0;
  }

  void add(float angle, float dist, float quality) {
    if (dist <= MIN_DIST_MM || quality <= MIN_QUALITY) return;
    if (fabs(dist - last_dist) < COHERENT_DIST_MM && angle_gap(angle, last_angle) < COHERENT_ANGLE_DEG) coherent++;
    else coherent = 1;
    last_dist = dist;
    last_angle = angle;
    if (coherent < COHERENT_POINTS) return;

    float &sector = scan.sector_min_mm[static_cast<int>(angle / SECTOR_DEG) % SECTORS];
    if (sector == 0.0f || dist < sector) sector = dist;
    if (scan.closest_dist_mm == 0.0f || dist < scan.closest_dist_mm) {
      scan.closest_dist_mm = dist;
      scan.closest_angle_deg = angle;
    }
  }
};

int open_lidar(const char *port, termios *tty, bool configure) {
  int fd = open(port, O_RDWR | O_NOCTTY | O_SYNC);
  if (fd < 0) return fd;
  if (configure) {
    tcgetattr(fd, tty);
    cfsetospeed(tty, B460800);
    cfsetispeed(tty, B460800);
    tty->c_cflag = (tty->c_cflag & ~CSIZE) | CS8;
    tty->c_iflag &= ~IGNBRK;
    tty->c_lflag = 0;
    tty->c_oflag = 0;
    tty->c_cc[VMIN] = 1;
    tty->c_cc[VTIME] = 1;
    tty->c_iflag &= ~(IXON | IXOFF | IXANY);
    tty->c_cflag |= (CLOCAL | CREAD);
  }
  tcsetattr(fd, TCSANOW, tty);
  return fd;
}

int main() {
  signal(SIGINT, sig_handler);
  signal(SIGTERM, sig_handler);

  int sock = socket(AF_INET, SOCK_DGRAM, 0);
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(8080);
  inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

  const char *port = "/dev/lidar";
  termios tty{};
  int serial_fd = open_lidar(port, &tty, true);
  global_serial_fd = serial_fd;
  if (serial_fd < 0) {
    cout << "[LIDAR C++] ❌ ERREUR: Impossible d'ouvrir " << port << endl;
    return 1;
  }
  cout << "[LIDAR C++] ✅ Connecté sur " << port << endl;

  write(serial_fd, STOP_CMD, 2);
  usleep(50000);
  write(serial_fd, SCAN_CMD, 2);
  unsigned char desc[7];
  read_exactly(serial_fd, desc, 7);

  unsigned char chunk[1024];
  unsigned char buf[5] = {0};
  float last_angle_sync = -1.0f;
  int points_since_send = 0;
  ScanBuilder builder;

  cout << "[LIDAR C++] Prêt : secteurs de " << SECTOR_DEG << "°" << endl;

  while (true) {
    int n = read(serial_fd, chunk, sizeof(chunk));
    if (n <= 0) {
      cout << "[LIDAR C++] ❌ ERREUR DE LECTURE (Lidar débranché ou chute de tension ?)" << endl;
      close(serial_fd);
      usleep(1000000);
      serial_fd = open_lidar(port, &tty, false);
      global_serial_fd = serial_fd;
      if (serial_fd >= 0) {
        write(serial_fd, SCAN_CMD, 2);
        cout << "[LIDAR C++] ✅ Reconnexion USB réussie !" << endl;
      }
      continue;
    }

    for (int i = 0; i < n; i++) {
      // Fenêtre glissante de 5 octets = une mesure
      memmove(buf, buf + 1, 4);
      buf[4] = chunk[i];
      // Octet 0 : bits S et !S complémentaires ; octet 1 : bit de contrôle à 1
      if (!(((buf[0] & 0x01) ^ ((buf[0] >> 1) & 0x01)) == 1 && (buf[1] & 0x01) == 1)) continue;

      const int S = buf[0] & 0x01;  // 1 = première mesure d'un nouveau tour
      const float angle = normalize_angle(((buf[2] << 7) | (buf[1] >> 1)) / 64.0f);
      const float dist = ((buf[4] << 8) | buf[3]) / 4.0f;
      const float quality = static_cast<float>((buf[0] >> 2) & 0x3F);

      // Faux départ de trame (angle qui saute) : on se resynchronise
      if (last_angle_sync >= 0.0f && S == 0) {
        float diff = angle - last_angle_sync;
        if (diff < -180.0f) diff += 360.0f;
        else if (diff > 180.0f) diff -= 360.0f;
        if (diff < -2.0f || diff > 20.0f) {
          last_angle_sync = -1.0f;
          continue;
        }
      }
      last_angle_sync = angle;
      points_since_send++;

      // Fin de tour (ou LiDAR bloqué) : envoi du tour terminé, puis on repart à zéro
      if (S == 1 || points_since_send > 2000) {
        sendto(sock, &builder.scan, sizeof builder.scan, 0, reinterpret_cast<sockaddr *>(&addr), sizeof addr);
        builder.reset();
        points_since_send = 0;
      }
      builder.add(angle, dist, quality);
      memset(buf, 0, sizeof buf);
    }
  }
  return 0;
}
