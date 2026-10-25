#include "goto_planner.h"

#include <cmath>

#include "config.h"

namespace {
constexpr float RAD_TO_DEG_F = 180.0f / config::PI_F;
constexpr float DEG_TO_RAD_F = config::PI_F / 180.0f;
}  // namespace

void GotoPlanner::start(const Pose& target) {
  target_ = target;
  target_.theta_deg = normalizeDeg(target.theta_deg);
  phase_ = Phase::RotateToPath;
  last_phase_ = Phase::RotateToPath;
}

void GotoPlanner::restartSegment() {
  if (phase_ != last_phase_) phase_ = last_phase_;
}

Segment GotoPlanner::next(const Pose& current) {
  const float dx = target_.x_mm - current.x_mm;
  const float dy = target_.y_mm - current.y_mm;

  // Les phases s'enchaînent ; une phase dont le segment est trop petit passe à la suivante
  while (phase_ != Phase::Done) {
    last_phase_ = phase_;
    switch (phase_) {
      case Phase::RotateToPath: {
        phase_ = Phase::Drive;
        if (std::hypot(dx, dy) < config::MIN_DRIVE_MM) break;
        // Face à la cible, ou dos à elle si c'est le plus court (la ligne droite sera
        // alors en marche arrière) : jamais plus de 90° à tourner
        const float heading = std::atan2(dy, dx) * RAD_TO_DEG_F;
        float turn = angleDiffDeg(heading, current.theta_deg);
        if (std::fabs(turn) > 90.0f) turn = angleDiffDeg(heading + 180.0f, current.theta_deg);
        if (std::fabs(turn) >= config::MIN_ROTATE_DEG) return {Segment::Type::Rotate, turn};
        break;
      }
      case Phase::Drive: {
        phase_ = Phase::RotateFinal;
        // Distance projetée sur le cap actuel : signe = sens de marche, et si la rotation
        // n'est pas parfaite on s'arrête au point le plus proche de la cible
        const float theta = current.theta_deg * DEG_TO_RAD_F;
        const float distance = dx * std::cos(theta) + dy * std::sin(theta);
        if (std::fabs(distance) >= config::MIN_DRIVE_MM) return {Segment::Type::Drive, distance};
        break;
      }
      case Phase::RotateFinal: {
        phase_ = Phase::Done;
        const float turn = angleDiffDeg(target_.theta_deg, current.theta_deg);
        if (std::fabs(turn) >= config::MIN_ROTATE_DEG) return {Segment::Type::Rotate, turn};
        break;
      }
      case Phase::Done:
        break;
    }
  }
  return {};
}
