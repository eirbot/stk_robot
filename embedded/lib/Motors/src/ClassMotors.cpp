#include "ClassMotors.hpp"

ClassMotors::ClassMotors() {
  xQueue = xQueueCreate(30, sizeof(MotorTaskParams));
  xQueueBuffer = xQueueCreate(30, sizeof(MotorTaskParams));
}

void ClassMotors::vMotors(void *pvParameters) {
  ClassMotors *instance = (ClassMotors *)pvParameters;
  MotorTaskParams taskParams;

  const TickType_t maxIdleTime = pdMS_TO_TICKS(5000);

  while (1) {
    if (xQueueReceive(instance->xQueue, &taskParams, portMAX_DELAY) == pdPASS) {
      TickType_t lastOdoUpdate = xTaskGetTickCount();

      // Vitesse en Hz (pas/sec)
      uint32_t speedHz = (taskParams.vitesse * stepPerRev) / ((M_PI * dRoues));
      uint32_t accelHz = speedHz * 0.75;

      moteurGauche->setSpeedInHz(speedHz);
      moteurGauche->setAcceleration(accelHz);
      moteurDroit->setSpeedInHz(speedHz);
      moteurDroit->setAcceleration(accelHz);

      instance->currentStep = moteurGauche->getCurrentPosition();

      // Variables d'état réinitialisées à chaque mouvement
      bool wasStopped = false;
      TickType_t stopStartTime = 0;
      bool movementFinished = false;
      int steps = 0;

      if (taskParams.angle == 0 && taskParams.distance == 0) {
        // Commande vide, on ignore
      } else if (taskParams.angle ==
                 0) { // === POUR AVANCER (AVEC SÉCURITÉ) ===
        steps = (int)((taskParams.distance / (M_PI * dRoues)) * stepPerRev);
        instance->stepDid = 0;

        moteurGauche->move(steps);
        moteurDroit->move(steps);

        while (!movementFinished) {

          bool stopReq = false;
          if (LiDAR_state == 1)
            stopReq = true;
          else if (LiDAR_state == 2 && steps > 0)
            stopReq = true;
          else if (LiDAR_state == 3 && steps < 0)
            stopReq = true;

          // --- GESTION DE L'ARRÊT ---
          if (stopReq) {
            if (!wasStopped) {
              StopStepper(moteurGauche, moteurDroit, instance);
              stopStartTime = xTaskGetTickCount();
              wasStopped = true;
            } else if ((xTaskGetTickCount() - stopStartTime) > maxIdleTime) {
              wasStopped = false;
              FLAG_STOP = true;

              instance->stepDid = moteurGauche->getCurrentPosition() -
                                  instance->GetCurrentStep();
              instance->distanceDid =
                  (instance->GetStepDid() * M_PI * dRoues) / stepPerRev;
              instance->TransferQueueBuffer();
              break;
            }
          }
          // --- GESTION DE LA RELANCE ---
          else {
            if (wasStopped) {
              wasStopped = false;
              instance->stepDid = moteurGauche->getCurrentPosition() -
                                  instance->GetCurrentStep();
              int32_t remainingSteps = steps - instance->stepDid;

              moteurGauche->move(remainingSteps);
              moteurDroit->move(remainingSteps);
            } else {
              if (!moteurGauche->isRunning() && !moteurDroit->isRunning()) {
                movementFinished = true;
              }
            }
          }

          // --- ODOMÉTRIE ---
          if ((xTaskGetTickCount() - lastOdoUpdate) >= odoInterval) {
            instance->UpdateOdometry();
            lastOdoUpdate = xTaskGetTickCount();
          }
          vTaskDelay(pdMS_TO_TICKS(5));
        }
        instance->UpdateOdometry();
      } else if (taskParams.distance ==
                 0) { // === POUR TOURNER (SANS SÉCURITÉ) ===
        steps = (int)((std::abs(taskParams.angle) / 360.0) *
                      (M_PI * ecartRoues) * stepPerRev / (M_PI * dRoues));
        instance->stepDid = steps;

        if (taskParams.direction == 0) {
          moteurGauche->move(steps);
          moteurDroit->move(-steps);
        } else {
          moteurGauche->move(-steps);
          moteurDroit->move(steps);
        }

        // Boucle ultra-simple : il tourne jusqu'à la fin, quoi qu'il arrive
        // autour de lui
        while (moteurGauche->isRunning() || moteurDroit->isRunning()) {
          if ((xTaskGetTickCount() - lastOdoUpdate) >= odoInterval) {
            instance->UpdateOdometry();
            lastOdoUpdate = xTaskGetTickCount();
          }
          vTaskDelay(pdMS_TO_TICKS(5));
        }
        instance->UpdateOdometry();
      }

      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

void ClassMotors::StartMotors() {
  xTaskCreatePinnedToCore(vMotors, "vMotors", 10000, this, 1, &vMotorsHandle,
                          1);
}

void ClassMotors::EnvoyerDonnees(void *Params) {
  MotorTaskParams *ptaskParams =
      (MotorTaskParams *)(Params); // Merci au patron de l'année derrnière en dépit
                              // de ses maigres performances concernant la coupe
  xQueueSend(xQueue, ptaskParams, portMAX_DELAY);
}

void ClassMotors::TransferQueueBuffer() {
  MotorTaskParams tmp;
  while (xQueueReceive(xQueue, &tmp, 0) == pdTRUE) {
    xQueueSend(xQueueBuffer, &tmp, 0); // Sauvegarde dans le tampon
  }
}

void ClassMotors::RestoreQueueBuffer() {
  MotorTaskParams tmp;
  while (xQueueReceive(xQueueBuffer, &tmp, 0) == pdTRUE) {
    xQueueSend(xQueue, &tmp, 0); // Recharge
  }
}

void ClassMotors::WaitUntilDone() {
  while (uxQueueMessagesWaiting(xQueue) > 0 || moteurGauche->isRunning() ||
         moteurDroit->isRunning()) {
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void ClassMotors::Stop() {
  StopStepper(moteurGauche, moteurDroit, this);
  if (GetCurrentStep() != 0) {
    stepDid = moteurGauche->getCurrentPosition() - GetCurrentStep();
    distanceDid = (stepDid * M_PI * dRoues) / stepPerRev;
  } else {
    stepDid = 0;
    distanceDid = 0.0;
  }
  if (vMotorsHandle != NULL)
    vTaskSuspend(vMotorsHandle);

  UBaseType_t nbMessages = uxQueueMessagesWaiting(xQueue);
  MotorTaskParams tmp;
  for (UBaseType_t i = 0; i < nbMessages; ++i)
    xQueueReceive(xQueue, &tmp, 0);

  if (vMotorsHandle != NULL)
    vTaskResume(vMotorsHandle);
}

void ClassMotors::RestartMotors() {
  if (vMotorsHandle != NULL) {
    vTaskResume(vMotorsHandle);
  }
}

void StopStepper(FastAccelStepper *moteur1, FastAccelStepper *moteur2,
                 ClassMotors *instance) {
  // Déclenche une décélération matérielle propre jusqu'à l'arrêt
  moteur1->stopMove();
  moteur2->stopMove();

  TickType_t lastOdoUpdate = xTaskGetTickCount();

  while (moteur1->isRunning() || moteur2->isRunning()) {
    if (instance != nullptr &&
        (xTaskGetTickCount() - lastOdoUpdate) >= odoInterval) {
      instance->UpdateOdometry();
      lastOdoUpdate = xTaskGetTickCount();
    }
    vTaskDelay(pdMS_TO_TICKS(5)); // Attente propre
  }

  if (instance != nullptr) {
    instance->UpdateOdometry();
  }
}

void ClassMotors::GetPosition(float &x, float &y, float &angle) {
  if (xSemaphoreTake(xPositionMutex, portMAX_DELAY) == pdTRUE) {
    x = x_pos;
    y = y_pos;
    angle = orientation;
    xSemaphoreGive(xPositionMutex);
  }
}

void ClassMotors::SetPosition(float x, float y, float angle) {
  if (xSemaphoreTake(xPositionMutex, portMAX_DELAY) == pdTRUE) {
    x_pos = x;
    y_pos = y;
    orientation = angle;
    xSemaphoreGive(xPositionMutex);
  }
}

void ClassMotors::UpdateOdometry() {
  long currentStepGauche = moteurGauche->getCurrentPosition();
  long currentStepDroit = moteurDroit->getCurrentPosition();
  long deltaStepGauche = currentStepGauche - lastStepGauche;
  long deltaStepDroit = currentStepDroit - lastStepDroit;

  if (deltaStepGauche == 0 && deltaStepDroit == 0)
    return;

  lastStepGauche = currentStepGauche;
  lastStepDroit = currentStepDroit;

  float distanceParStep = (M_PI * dRoues) / stepPerRev;
  float s_L = deltaStepGauche * distanceParStep;
  float s_R = deltaStepDroit * distanceParStep;
  float delta_s = (s_R + s_L) / 2.0;
  float delta_theta = (s_L - s_R) / ecartRoues; // Inversion L/R

  if (xSemaphoreTake(xPositionMutex, portMAX_DELAY) == pdTRUE) {
    orientation += delta_theta;
    if (orientation > M_PI)
      orientation -= 2 * M_PI;
    if (orientation < -M_PI)
      orientation += 2 * M_PI;

    // Repère Direct : X devant, Y gauche, Theta trigo (CCW+)
    x_pos += delta_s * cos(orientation);
    y_pos += delta_s * sin(orientation);

    xSemaphoreGive(xPositionMutex);
  }
}
