#ifndef ACTIONNEURS_HPP
#define ACTIONNEURS_HPP

#include "Arduino.h"
#include "PCF8575.h"  // Bibliothèque de Rob Tillaart
#include "GpioActionneurs.hpp"
#include <ESP32Servo.h>
#include <cstdint>

extern volatile bool IntDetected;

PCF8575& get_static_pcf();

class Arm_Actuator {
public:
  Arm_Actuator(uint8_t p9G, uint8_t p17G, uint8_t v1, uint8_t v2, uint8_t stp, uint8_t dir, uint8_t sns, bool dir_elevator, PCF8575 &pcf): p9G(p9G), p17G(p17G), v1(v1), v2(v2), stp(stp), dir(dir), sns(sns), dir_elevator(dir_elevator), pcf_(pcf) {};

  uint8_t p9G, p17G, v1, v2, stp, dir, sns;
  bool dir_elevator;
  Servo servo9G, servo17G;
  bool canMove;
  int sns_status;
  int p17G_status;
  int p9G_status;
  int asc_height;

  void initialiser() {
    pcf_.setButtonMask(bit(sns));

    pinMode(stp, OUTPUT);
    servo9G.attach(p9G);
    servo17G.attach(p17G);

    canMove = true;
    sns_status = 0;
    p17G_status = 89;
    p9G_status = 0;
    asc_height = 0;
  }

  void sns_read() {
    sns_status = pcf_.read(sns);
    canMove = (sns_status == LOW);
  }

  void servo_9G(int angle) { servo9G.write(angle); }

  void soft_servo(int objectif) {
    while (abs(objectif - p17G_status) >= 1) {
      if (objectif - p17G_status >= 0) {
        p17G_status += 1;
      } else {
        p17G_status -= 1;
      }
      servo17G.write(p17G_status);
      // delay(10)
      vTaskDelay(10 / portTICK_PERIOD_MS);
    }
  }

  void homming() {
    pcf_.write(dir, dir_elevator ? HIGH : LOW);
    soft_servo(90);
    servo_9G(0);
    this->goDown(20000);

    pcf_.write(dir, dir_elevator ? LOW : HIGH);
    canMove = true;
    this->goUp(200);

    asc_height = 0;
  }

  void fairePas() {
    if (canMove) {
      digitalWrite(stp, !digitalRead(stp));
    }
  }

  void closePiston() {
    pcf_.write(v1, HIGH);
    pcf_.write(v2, LOW);
  }

  void openPiston() {
    pcf_.write(v1, LOW);
    pcf_.write(v2, HIGH);
  }

  void goUp(int steps) {
    pcf_.write(dir, dir_elevator ? LOW : HIGH);
    canMove = true;
    for (int k = 0; k < steps; k++) {
      this->fairePas();
      delayMicroseconds(100);
    }
  }

  void goDown(int steps) {
    pcf_.write(dir, dir_elevator ? HIGH : LOW);
    canMove = true;
    sns_read();
    if (sns_status == LOW) {
      for (int k = 0; k < steps; k++) {
        this->fairePas();
        delayMicroseconds(50);
        if (IntDetected) {
          sns_read();
          IntDetected = false;
        }
        if (sns_status == HIGH) {
          break;
        }
      }
    }
  }
private:
  PCF8575& pcf_;
};

enum ArmActuatorId {
  ArmActuator1,
  ArmActuator2,
  ArmActuator3,
  ArmActuator4
};

Arm_Actuator init_arm_actuator(ArmActuatorId act_id, PCF8575 &pcf); 

void ARDUINO_ISR_ATTR IntEXTfct();

#endif
