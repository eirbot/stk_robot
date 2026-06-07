#include "main_robot.h"

TaskHandle_t vstratHandle = NULL;
TaskHandle_t vterminal_bluetoothHandle = NULL;

unsigned long startMillis;

TaskParams Parameters = {0, 0, 0, 0};

GoToPosition serialGoto{X_POS_INIT, Y_POS_INIT, ANGLE_INIT, 1000, 1000, 0};

void setup() {
  esp_task_wdt_init(10, true);
  static ComWithRasp comRasp;

  // Config des vitesses max et accélérations
  engine.init();

  moteurGauche = engine.stepperConnectToPin(STEPG);
  if (moteurGauche) {
    moteurGauche->setDirectionPin(DIRG);
    moteurGauche->setAutoEnable(
        true); // Gère le pin Enable si tu l'as câblé un jour
  }

  moteurDroit = engine.stepperConnectToPin(STEPD);
  if (moteurDroit) {
    moteurDroit->setDirectionPin(DIRD);
    moteurDroit->setAutoEnable(true);
  }

  // Config des vitesses max et accélérations par défaut
  moteurGauche->setSpeedInHz(SPEEDMAX);
  moteurGauche->setAcceleration(ACCELMAX);
  moteurDroit->setSpeedInHz(SPEEDMAX);
  moteurDroit->setAcceleration(ACCELMAX);

  xPositionMutex = xSemaphoreCreateMutex();
  if (xPositionMutex == NULL) {
    // Serial.println("Erreur : mutex non créé");
  }

  Serial.begin(115200);
  startMillis = millis();

  Serial.println("Démarrage du robot...");
  mot.StartMotors();

  Serial.println("Démarrage de la communication avec la Raspberry Pi...");

  comRasp.StartCom();
  comRasp.StartTelemetry();
}

void loop() {}
