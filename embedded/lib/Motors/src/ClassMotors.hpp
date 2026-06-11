#ifndef CLASSMOTORS_H
#define CLASSMOTORS_H

#include "Arduino.h"
#include "FastAccelStepper.h"
#include <cmath>

#include "common.h"

#define DECCEL 30000.0

const TickType_t odoInterval = pdMS_TO_TICKS(20); // 20 ms = 50 Hz

class ClassMotors {
public:
  ClassMotors();
  static void vMotors(void *pvParameters);

  void WaitUntilDone();
  void StartMotors();
  void EnvoyerDonnees(void *Params);
  void TransferQueueBuffer();
  void RestoreQueueBuffer();
  void Stop();
  void RestartMotors();

  long GetStepDid() const { return stepDid; }
  long GetCurrentStep() const { return currentStep; }
  float GetDistanceDid() const { return distanceDid; }
  void UpdateOdometry();

  void GetPosition(float &x, float &y, float &angle);
  void SetPosition(float x, float y, float angle);

private:
  QueueHandle_t xQueue;
  QueueHandle_t xQueueBuffer;

  long stepDid;
  long currentStep;
  float distanceDid;

  float x_pos = X_POS_INIT;
  float y_pos = Y_POS_INIT;
  float orientation = ANGLE_INIT; // radians

  long lastStepGauche = 0;
  long lastStepDroit = 0;
};
void StopStepper(FastAccelStepper *moteur1, FastAccelStepper *moteur2,
                 ClassMotors *instance = nullptr);

extern ClassMotors mot;

#endif
