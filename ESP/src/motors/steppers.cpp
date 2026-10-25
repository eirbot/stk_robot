#include "steppers.h"

#include <FastAccelStepper.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <initializer_list>

#include "config.h"
#include "kinematics.h"

namespace {

FastAccelStepperEngine engine;

// mm/s (ou mm/s²) de roue -> pas/s (ou pas/s²), au moins 1 : FastAccelStepper refuse 0
uint32_t toStepsRate(float mm) {
  const float steps = std::fabs(kinematics::mmToSteps(mm));
  return steps < 1.0f ? 1u : static_cast<uint32_t>(std::lround(steps));
}

FastAccelStepper* attach(uint8_t step_pin, uint8_t dir_pin, bool dir_high_forward) {
  FastAccelStepper* s = engine.stepperConnectToPin(step_pin);
  if (s != nullptr) s->setDirectionPin(dir_pin, dir_high_forward);
  return s;
}

// Mouvement relatif d'une roue ; `ratio` = part de sa distance par rapport à la roue la plus longue
bool moveWheel(FastAccelStepper* s, int32_t steps, float ratio, float speed_mm_s, float accel_mm_s2) {
  if (steps == 0) return true;
  s->setSpeedInHz(toStepsRate(speed_mm_s * ratio));
  s->setAcceleration(static_cast<int32_t>(toStepsRate(accel_mm_s2 * ratio)));
  return s->move(steps) == MOVE_OK;
}

void runWheel(FastAccelStepper* s, float speed_mm_s, float accel_mm_s2) {
  s->setAcceleration(static_cast<int32_t>(toStepsRate(accel_mm_s2)));
  if (std::fabs(speed_mm_s) < 0.5f) {  // moins d'un pas toutes les ~0,1 s : arrêt
    s->stopMove();
    return;
  }
  s->setSpeedInHz(toStepsRate(speed_mm_s));
  if (speed_mm_s > 0.0f) s->runForward();
  else s->runBackward();
}

}  // namespace

bool Steppers::begin() {
  engine.init();
  right_ = attach(config::PIN_STEP_RIGHT, config::PIN_DIR_RIGHT, config::DIR_HIGH_FORWARD_RIGHT);
  left_ = attach(config::PIN_STEP_LEFT, config::PIN_DIR_LEFT, config::DIR_HIGH_FORWARD_LEFT);
  return left_ != nullptr && right_ != nullptr;
}

int32_t Steppers::leftSteps() const { return left_->getCurrentPosition(); }

int32_t Steppers::rightSteps() const { return right_->getCurrentPosition(); }

bool Steppers::move(int32_t left_steps, int32_t right_steps, float speed_mm_s, float accel_mm_s2) {
  const int32_t longest = std::max(std::abs(left_steps), std::abs(right_steps));
  if (longest == 0) return true;
  const float ratio_left = static_cast<float>(std::abs(left_steps)) / longest;
  const float ratio_right = static_cast<float>(std::abs(right_steps)) / longest;
  const bool ok_left = moveWheel(left_, left_steps, ratio_left, speed_mm_s, accel_mm_s2);
  const bool ok_right = moveWheel(right_, right_steps, ratio_right, speed_mm_s, accel_mm_s2);
  if (!ok_left || !ok_right) {
    stop();
    return false;
  }
  return true;
}

void Steppers::run(float left_mm_s, float right_mm_s, float accel_mm_s2) {
  runWheel(left_, left_mm_s, accel_mm_s2);
  runWheel(right_, right_mm_s, accel_mm_s2);
}

void Steppers::stop() {
  const int32_t decel = static_cast<int32_t>(toStepsRate(config::STOP_DECEL_MM_S2));
  for (FastAccelStepper* s : {left_, right_}) {
    // La nouvelle décélération doit être appliquée au mouvement en cours avant stopMove
    s->setAcceleration(decel);
    s->applySpeedAcceleration();
    s->stopMove();
  }
}

bool Steppers::isRunning() const { return left_->isRunning() || right_->isRunning(); }
