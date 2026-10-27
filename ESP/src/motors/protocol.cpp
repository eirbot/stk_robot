#include "protocol.h"

#include <cctype>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>

namespace protocol {

namespace {

constexpr int MAX_FIELDS = 5;

// Découpe les champs numériques qui suivent la lettre de commande. Renvoie le nombre
// de champs lus, ou -1 si l'un d'eux n'est pas un nombre fini ou s'il y en a trop.
int parseNumbers(const char* p, float* out) {
  int n = 0;
  while (true) {
    while (*p == ' ') p++;
    if (*p == '\0') return n;
    if (n == MAX_FIELDS) return -1;
    char* end = nullptr;
    const float value = std::strtof(p, &end);
    // Rien lu, caractère collé au nombre (« 12abc »), nan ou inf : refusé
    if (end == p || (*end != ' ' && *end != '\0') || !std::isfinite(value)) return -1;
    out[n++] = value;
    p = end;
  }
}

Command invalid(const char* reason) {
  Command c;
  c.error = reason;
  return c;
}

size_t format(char* buf, size_t size, const char* fmt, ...) {
  va_list args;
  va_start(args, fmt);
  const int n = std::vsnprintf(buf, size, fmt, args);
  va_end(args);
  return (n < 0 || static_cast<size_t>(n) >= size) ? 0 : static_cast<size_t>(n);
}

}  // namespace

Command parse(const char* line) {
  while (*line == ' ') line++;
  const char letter = line[0];
  if (letter == '\0') return invalid("ligne vide");
  if (line[1] != ' ' && line[1] != '\0') return invalid("commande inconnue");

  float f[MAX_FIELDS];
  const int n = parseNumbers(line + 1, f);
  if (n < 0) return invalid("nombre illisible");

  Command c;
  switch (letter) {
    case 'G':
      if (n != 4 && n != 5) return invalid("G attend : id x y theta [facteur]");
      // L'id doit être un entier positif (strtof lit aussi « 3.5 » ou « -1 »)
      if (f[0] < 0.0f || f[0] > 16777216.0f || f[0] != std::floor(f[0])) return invalid("id de GoTo invalide");
      c.type = Command::Type::GoTo;
      c.id = static_cast<uint32_t>(f[0]);
      c.pose = {f[1], f[2], normalizeDeg(f[3])};
      if (n == 5) {
        if (!(f[4] > 0.0f && f[4] <= 1.0f)) return invalid("facteur de vitesse hors ]0, 1]");
        c.speed_factor = f[4];
      }
      return c;
    case 'V':
      if (n != 2) return invalid("V attend : vx omega");
      c.type = Command::Type::Velocity;
      c.v_mm_s = f[0];
      c.omega_deg_s = f[1];
      return c;
    case 'S':
      if (n != 3) return invalid("S attend : x y theta");
      c.type = Command::Type::SetPose;
      c.pose = {f[0], f[1], normalizeDeg(f[2])};
      return c;
    case 'L':
      if (n != 1) return invalid("L attend : etat");
      if (f[0] != 0.0f && f[0] != 1.0f && f[0] != 2.0f && f[0] != 3.0f) return invalid("etat LiDAR invalide (0 a 3)");
      c.type = Command::Type::Lidar;
      c.obstacle = static_cast<Obstacle>(static_cast<int>(f[0]));
      return c;
    case 'H':
      if (n != 0) return invalid("H sans parametre");
      c.type = Command::Type::Halt;
      return c;
    case 'K':
      if (n != 0) return invalid("K sans parametre");
      c.type = Command::Type::Heartbeat;
      return c;
    default:
      return invalid("commande inconnue");
  }
}

size_t formatPose(char* buf, size_t size, const Pose& pose) {
  return format(buf, size, "T %.2f %.2f %.2f\n", pose.x_mm, pose.y_mm, pose.theta_deg);
}

size_t formatDone(char* buf, size_t size, uint32_t id) {
  return format(buf, size, "D %lu\n", static_cast<unsigned long>(id));
}

size_t formatAborted(char* buf, size_t size, uint32_t id) {
  return format(buf, size, "A %lu\n", static_cast<unsigned long>(id));
}

size_t formatWatchdog(char* buf, size_t size) { return format(buf, size, "W\n"); }

size_t formatError(char* buf, size_t size, const char* message) {
  return format(buf, size, "E %s\n", message);
}

LineReader::Result LineReader::push(char c) {
  if (c == '\n' || c == '\r') {
    const bool was_overflow = overflow_;
    const size_t len = len_;
    overflow_ = false;
    len_ = 0;
    if (was_overflow) return Result::Overflow;
    if (len == 0) return Result::None;  // ligne vide, ou '\n' d'un "\r\n"
    buf_[len] = '\0';
    return Result::Line;
  }
  if (overflow_) return Result::None;
  if (len_ < config::LINE_MAX_CHARS) {
    buf_[len_++] = c;
  } else {
    overflow_ = true;
  }
  return Result::None;
}

void RaspWatchdog::onActivity(uint32_t now_ms) {
  last_ms_ = now_ms;
  seen_ = true;
  tripped_ = false;
}

bool RaspWatchdog::expired(uint32_t now_ms) {
  if (!seen_ || tripped_ || now_ms - last_ms_ <= config::RASP_TIMEOUT_MS) return false;
  tripped_ = true;
  return true;
}

}  // namespace protocol
