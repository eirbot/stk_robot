#include "odometry.h"

#include <cmath>

#include "config.h"
#include "kinematics.h"

namespace {
constexpr float DEG_TO_RAD_F = config::PI_F / 180.0f;
}

void Odometry::reset(const Pose& pose, int32_t left_steps, int32_t right_steps) {
  pose_ = pose;
  pose_.theta_deg = normalizeDeg(pose.theta_deg);
  ref_theta_deg_ = pose_.theta_deg;
  ref_left_ = last_left_ = left_steps;
  ref_right_ = last_right_ = right_steps;
}

void Odometry::update(int32_t left_steps, int32_t right_steps) {
  const int32_t d_left = left_steps - last_left_;
  const int32_t d_right = right_steps - last_right_;
  if (d_left == 0 && d_right == 0) return;
  last_left_ = left_steps;
  last_right_ = right_steps;

  // Cap : la différence de chemin entre les roues, divisée par l'entraxe. Moitié de
  // l'écart pour chaque roue : wheelMmToRotationDeg attend l'arc d'UNE roue.
  const float theta_before = pose_.theta_deg;
  const int32_t diff_steps = (right_steps - ref_right_) - (left_steps - ref_left_);
  const float theta_after =
      ref_theta_deg_ + kinematics::wheelMmToRotationDeg(kinematics::stepsToMm(diff_steps) / 2.0f);

  // Position : avance du centre du robot, dans la direction du cap au MILIEU du petit
  // arc (plus juste que le cap de début ou de fin quand le robot tourne en avançant)
  const float ds_mm = kinematics::stepsToMm((d_left + d_right) / 2.0f);
  const float theta_mid_rad = (theta_before + angleDiffDeg(theta_after, theta_before) / 2.0f) * DEG_TO_RAD_F;
  pose_.x_mm += ds_mm * std::cos(theta_mid_rad);
  pose_.y_mm += ds_mm * std::sin(theta_mid_rad);
  pose_.theta_deg = normalizeDeg(theta_after);
}
