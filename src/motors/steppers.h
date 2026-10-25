// Les deux moteurs des roues : seul fichier qui parle à FastAccelStepper.
//
// Unités : distances et vitesses en mm (roue) côté appelant, converties en pas ici.
// Convention : pas > 0 = la roue fait avancer le robot (sens réglé dans config.h).
// Les pas sont générés par un périphérique de l'ESP32 : ces fonctions ne font que
// programmer le mouvement et rendent la main tout de suite.
//
// Pas thread-safe : un seul propriétaire, la tâche de mouvement.
#pragma once

#include <cstdint>

#include "wheel_driver.h"

class FastAccelStepper;

class Steppers : public WheelDriver {
 public:
  // Démarre le générateur de pas et branche les deux moteurs. false si un moteur
  // n'a pas pu être attaché (broche invalide, plus de canal libre).
  bool begin();

  // Compteurs de pas depuis le démarrage (pour l'odométrie)
  int32_t leftSteps() const override;
  int32_t rightSteps() const override;

  // Déplacement relatif des deux roues, profil trapèze. La roue qui a le plus de chemin
  // va à speed / accel ; l'autre est réduite dans la même proportion : les deux
  // démarrent et s'arrêtent ensemble. Renvoie false si FastAccelStepper refuse.
  bool move(int32_t left_steps, int32_t right_steps, float speed_mm_s, float accel_mm_s2) override;

  // Rotation continue de chaque roue à sa vitesse (joystick), avec cette accélération.
  // Une vitesse nulle arrête la roue en douceur.
  void run(float left_mm_s, float right_mm_s, float accel_mm_s2) override;

  // Arrêt des deux roues avec la décélération STOP_DECEL_MM_S2 (rend la main tout de suite)
  void stop() override;

  bool isRunning() const override;

 private:
  FastAccelStepper* left_ = nullptr;
  FastAccelStepper* right_ = nullptr;
};
