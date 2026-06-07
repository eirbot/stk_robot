#include "common.h"

TaskHandle_t vMotorsHandle;
TaskHandle_t handleDoStrat = NULL;

FastAccelStepperEngine engine = FastAccelStepperEngine();
FastAccelStepper *moteurGauche = NULL;
FastAccelStepper *moteurDroit = NULL;

ClassMotors mot;

bool FLAG_STOP = false; // Valeur initiale (1 = stop, 0 = continue)

SemaphoreHandle_t xPositionMutex;

bool jaune = true;
volatile int LiDAR_state = 0; // 0: Libre, 1: Stop, 2: Front, 3: Back

// position bleu par default
float X_POS_INIT = 200;
float Y_POS_INIT = -1200;
float ANGLE_INIT = 0;
