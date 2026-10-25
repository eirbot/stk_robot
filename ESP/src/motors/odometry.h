// Odométrie : pose du robot calculée à partir des compteurs de pas des deux roues.
//
// Les drivers sont en boucle fermée : les pas demandés sont les pas faits (tant que le
// driver ne se met pas en protection). Les compteurs de FastAccelStepper donnent donc
// le déplacement réel des roues, au glissement près.
//
// Pas thread-safe : un seul propriétaire (la tâche de mouvement), qui publie des copies.
#pragma once

#include <cstdint>

#include "pose.h"

class Odometry {
 public:
  // Pose connue (« S » de la Rasp, démarrage) avec les compteurs de pas à cet instant
  void reset(const Pose& pose, int32_t left_steps, int32_t right_steps);

  // Nouvelles valeurs (absolues) des compteurs de pas ; à appeler souvent (≥ 50 Hz)
  // pour que l'approximation des petits arcs reste exacte
  void update(int32_t left_steps, int32_t right_steps);

  Pose pose() const { return pose_; }

 private:
  Pose pose_;
  // Cap = cap de référence + (pas droite - pas gauche depuis la référence) : calculé
  // directement depuis les compteurs entiers, il ne dérive pas par accumulation.
  float ref_theta_deg_ = 0.0f;
  int32_t ref_left_ = 0;
  int32_t ref_right_ = 0;
  int32_t last_left_ = 0;
  int32_t last_right_ = 0;
};
