#ifndef ACTIONNEURS_HPP
#define ACTIONNEURS_HPP

#include "Arduino.h"
#include "PCF8575.h"  // Bibliothèque de Rob Tillaart
#include "GpioActionneurs.hpp"
#include <ESP32Servo.h>
#include <cstdint>

extern volatile bool IntDetected;

PCF8575& get_static_pcf();

struct ArmVars {
  uint8_t p9G;
  uint8_t p17G;
  uint8_t v1;
  uint8_t v2;
  uint8_t stp;
  uint8_t dir;
  uint8_t sns;
  bool dir_elevator;
};

enum ArmActuatorId {
  ArmActuator1,
  ArmActuator2,
  ArmActuator3,
  ArmActuator4
};

ArmVars per_arm_vars(ArmActuatorId arm_id);

#define ELEVATOR_MM_HEIGHT_TO_STEP 80

class Arm_Actuator {
public:
  // Init all the vars and init the servos.
  Arm_Actuator(ArmActuatorId arm_id, PCF8575 &pcf)
      : _pcf(pcf), _armVars(per_arm_vars(arm_id)) {
    initialize_status_and_servos();
  };

  // Set the status vars and servos to their initial states.
  void initialize_status_and_servos() {
    _pcf.setButtonMask(bit(_armVars.sns));

    pinMode(_armVars.stp, OUTPUT);
    _servo9G.attach(_armVars.p9G);
    _servo17G.attach(_armVars.p17G);

    _canMove = true;
    _sns_status = 0;
    _p17G_status = 89;
    _p9G_status = 0;
    _asc_height = 0;
  }


  // Invert the angle of the servo9G (switch between 0° and 180°)
  void invert_servo9G() {
    int degree_angle = _p9G_status == 0 ? 180 : 0;
    _set_servo9G_angle(degree_angle);
  }

  // TODO: set the spec
  void soft_servo(int objectif) {
    while (abs(objectif - _p17G_status) >= 1) {
      if (objectif - _p17G_status >= 0) {
        _p17G_status += 1;
      } else {
        _p17G_status -= 1;
      }
      _servo17G.write(_p17G_status);
      // delay(10)
      vTaskDelay(10 / portTICK_PERIOD_MS);
    }
  }

  // Set both servo motors and the elevator to their initial synchronization values.  
  // TODO: review the spec.
  void homming() {
    _pcf.write(_armVars.dir, _armVars.dir_elevator ? HIGH : LOW);
    soft_servo(90);
    _set_servo9G_angle(0);
    this->goDown(20000);

    _pcf.write(_armVars.dir, _armVars.dir_elevator ? LOW : HIGH);
    _canMove = true;
    this->goUp(200);

    _asc_height = 0;
  }

  // Close the piston.
  void closePiston() {
    _pcf.write(_armVars.v1, HIGH);
    _pcf.write(_armVars.v2, LOW);
  }

  // Open the piston.
  void openPiston() {
    _pcf.write(_armVars.v1, LOW);
    _pcf.write(_armVars.v2, HIGH);
  }

  // Make the elevator go up with the given step number.
  void goUp(int steps) {
    _pcf.write(_armVars.dir, _armVars.dir_elevator ? LOW : HIGH);
    _canMove = true;
    for (int k = 0; k < steps; k++) {
      _makeStep();
      // TODO: transform into vTaskDelay
      delayMicroseconds(100);
    }
  }

  // Make the elevator go down with the given step number.
  void goDown(int steps) {
    _pcf.write(_armVars.dir, _armVars.dir_elevator ? HIGH : LOW);
    _canMove = true;
    _sns_read();
    if (_sns_status == LOW) {
      for (int k = 0; k < steps; k++) {
        _makeStep();
        // TODO: transform into vTaskDelay
        delayMicroseconds(50);
        if (IntDetected) {
          _sns_read();
          IntDetected = false;
        }
        if (_sns_status == HIGH) {
          break;
        }
      }
    }
  }

  // Set the elevator absolute height to the asked one in milimeters.
  void setElevatorPosition(int milimeter_height) {
    int step_height = milimeter_height * ELEVATOR_MM_HEIGHT_TO_STEP;
    if (step_height >= _asc_height) {
      goUp(step_height - _asc_height);
    } else {
      goDown(_asc_height - step_height);
    };
    _asc_height = step_height;
  }

private:
  ArmVars _armVars;

  Servo _servo9G, _servo17G;
  bool _canMove;
  int _sns_status;
  int _p17G_status;
  int _p9G_status;
  int _asc_height;

  PCF8575& _pcf;

  // Achieve one step with the actuator in its current state.  
  void _makeStep() {
    if (_canMove) {
      digitalWrite(_armVars.stp, !digitalRead(_armVars.stp));
    }
  }

  // Read the sns and update the status and the actuator locking state.
  void _sns_read() {
    _sns_status = _pcf.read(_armVars.sns);
    _canMove = (_sns_status == LOW);
  }

  // Set the angle of the servo9G and update the status.
  void _set_servo9G_angle(int degree_angle) {
    _servo9G.write(degree_angle);
    _p9G_status = degree_angle;
  }
};

void ARDUINO_ISR_ATTR IntEXTfct();

#endif
