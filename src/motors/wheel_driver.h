// Ce dont le contrôleur de mouvement a besoin pour piloter les roues. Steppers
// (FastAccelStepper) l'implémente sur le robot ; les tests PC utilisent de fausses roues.
// Unités : pas (compteurs, déplacements) et mm de roue (vitesses), pas > 0 = en avant.
#pragma once

#include <cstdint>

class WheelDriver {
 public:
  virtual ~WheelDriver() = default;
  virtual int32_t leftSteps() const = 0;
  virtual int32_t rightSteps() const = 0;
  virtual bool move(int32_t left_steps, int32_t right_steps, float speed_mm_s, float accel_mm_s2) = 0;
  virtual void run(float left_mm_s, float right_mm_s, float accel_mm_s2) = 0;
  virtual void stop() = 0;
  virtual bool isRunning() const = 0;
};
