#ifndef COMMON_H
#define COMMON_H

#define STEPG 16
#define DIRG 4
#define STEPD 19
#define DIRD 18

#define SPEEDMAX 1000
#define ACCELMAX 2000

#define dRoues 72.0
#define stepPerRev 3200
#define ecartRoues 345.0

#define vitesse_nominale 100
#define STOP_DISTANCE 300

extern float X_POS_INIT;
extern float Y_POS_INIT;
extern float ANGLE_INIT;

#include "ClassMotors.hpp"
#include "FastAccelStepper.h"
#include "GoToPosition.hpp"
#include "esp_task_wdt.h"

typedef struct {
  int distance;
  int angle;
  int direction;
  int vitesse;
} TaskParams;

// Déclaration des deux moteurs (type DRIVER = step/dir)
extern FastAccelStepperEngine engine;
extern FastAccelStepper *moteurGauche;
extern FastAccelStepper *moteurDroit;

extern TaskHandle_t vMotorsHandle;
extern TaskHandle_t handleDoStrat;

extern SemaphoreHandle_t xPositionMutex;

extern bool FLAG_STOP; // Valeur initiale (1 = stop, 0 = continue)

extern volatile int LiDAR_state; // 0: Libre, 1: Stop, 2: Front, 3: Back
#endif