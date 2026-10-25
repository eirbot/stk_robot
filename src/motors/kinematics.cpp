#include "kinematics.h"

#include <cmath>

#include "config.h"

namespace kinematics {

namespace {
constexpr float DEG_TO_RAD_F = config::PI_F / 180.0f;
constexpr float WHEEL_CIRCUMFERENCE_MM = config::PI_F * config::WHEEL_DIAMETER_MM;
constexpr float STEPS_PER_MM = config::STEPS_PER_REV / WHEEL_CIRCUMFERENCE_MM;
constexpr float HALF_WHEEL_BASE_MM = config::WHEEL_BASE_MM / 2.0f;
}  // namespace

float mmToSteps(float mm) { return mm * STEPS_PER_MM; }

float stepsToMm(float steps) { return steps / STEPS_PER_MM; }

int32_t mmToStepsRounded(float mm) { return static_cast<int32_t>(std::lround(mmToSteps(mm))); }

float rotationDegToWheelMm(float deg) { return deg * DEG_TO_RAD_F * HALF_WHEEL_BASE_MM; }

float wheelMmToRotationDeg(float mm) { return mm / HALF_WHEEL_BASE_MM / DEG_TO_RAD_F; }

WheelSpeeds wheelSpeedsFromTwist(float v_mm_s, float omega_deg_s) {
  const float arc_mm_s = rotationDegToWheelMm(omega_deg_s);
  WheelSpeeds s{v_mm_s - arc_mm_s, v_mm_s + arc_mm_s};

  const float fastest = std::fmax(std::fabs(s.left_mm_s), std::fabs(s.right_mm_s));
  if (fastest > config::WHEEL_SPEED_MAX_MM_S) {
    const float scale = config::WHEEL_SPEED_MAX_MM_S / fastest;
    s.left_mm_s *= scale;
    s.right_mm_s *= scale;
  }
  return s;
}

}  // namespace kinematics
