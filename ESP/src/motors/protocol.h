// Protocole série Rasp <-> ESP moteurs : une commande par ligne, champs séparés par
// des espaces, nombres décimaux avec un point. Fonctions pures, testées sur PC.
//
// Rasp -> ESP
//   G id x y theta [f]  GoTo vers (x, y) en mm puis cap theta en degrés, repère odométrie.
//                    id : entier choisi par la Rasp, renvoyé dans D / A. f (optionnel, ]0, 1]) :
//                    facteur sur les vitesses et accélérations du GoTo (calibration lente sans glissement).
//   V vx omega       Vitesse (joystick) : vx en mm/s, omega en deg/s. Arrêt si aucune
//                    nouvelle consigne pendant VELOCITY_TIMEOUT_MS.
//   S x y theta      Pose connue : remet l'odométrie à cette pose.
//   L etat           Évitement LiDAR : 0 libre, 1 obstacle tout près (tout s'arrête),
//                    2 obstacle devant (pas de marche avant), 3 derrière (pas de marche arrière).
//   H                Arrêt : annule le GoTo ou la vitesse en cours.
//   K                Battement de cœur (tout octet reçu compte comme signe de vie).
//
// ESP -> Rasp
//   T x y theta      Pose odométrie (10 Hz, et juste avant chaque D / A).
//   D id             GoTo id terminé.
//   A id             GoTo id annulé (H, V, nouveau G, obstacle persistant, watchdog).
//   W                Watchdog : rien reçu de la Rasp depuis RASP_TIMEOUT_MS, tout est arrêté.
//   E message        Erreur (commande illisible...), pour les journaux de la Rasp.
#pragma once

#include <cstddef>
#include <cstdint>

#include "config.h"
#include "pose.h"

enum class Obstacle : uint8_t { Clear = 0, Stop = 1, Front = 2, Back = 3 };

struct Command {
  enum class Type { Invalid, GoTo, Velocity, SetPose, Lidar, Halt, Heartbeat };
  Type type = Type::Invalid;
  uint32_t id = 0;              // GoTo
  Pose pose;                    // GoTo (cible), SetPose
  float speed_factor = 1.0f;    // GoTo : facteur ]0, 1] sur vitesses et accélérations
  float v_mm_s = 0.0f;          // Velocity
  float omega_deg_s = 0.0f;     // Velocity
  Obstacle obstacle = Obstacle::Clear;  // Lidar
  const char* error = nullptr;  // Invalid : raison, à renvoyer dans une trame E
};

namespace protocol {

// Lit une ligne (sans le '\n'). Toute ligne mal formée donne Type::Invalid + error.
Command parse(const char* line);

// Écrivent une trame terminée par '\n' dans buf ; renvoient sa longueur (0 si buf trop petit)
size_t formatPose(char* buf, size_t size, const Pose& pose);
size_t formatDone(char* buf, size_t size, uint32_t id);
size_t formatAborted(char* buf, size_t size, uint32_t id);
size_t formatWatchdog(char* buf, size_t size);
size_t formatError(char* buf, size_t size, const char* message);

// Rassemble les octets reçus en lignes ('\n' ou '\r' terminent une ligne, lignes vides
// ignorées). Une ligne trop longue est jetée en entier, jusqu'au prochain retour à la ligne.
class LineReader {
 public:
  enum class Result { None, Line, Overflow };
  Result push(char c);
  // Ligne complète après Result::Line ; valable jusqu'au push() suivant
  const char* line() const { return buf_; }

 private:
  char buf_[config::LINE_MAX_CHARS + 1] = {};
  size_t len_ = 0;
  bool overflow_ = false;
};

// Watchdog de la liaison : expire une fois si rien n'est reçu pendant RASP_TIMEOUT_MS.
// Ne s'arme qu'au premier octet reçu (sinon l'ESP s'arrêterait avant que la Rasp parle).
class RaspWatchdog {
 public:
  void onActivity(uint32_t now_ms);
  // true UNE fois au moment où le délai est dépassé ; se réarme au prochain octet
  bool expired(uint32_t now_ms);

 private:
  uint32_t last_ms_ = 0;
  bool seen_ = false;
  bool tripped_ = false;
};

}  // namespace protocol
