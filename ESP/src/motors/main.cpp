// Firmware de l'ESP32 moteurs : démarrage. Tout le reste tourne dans des tâches FreeRTOS
// (motion_task : roues + odométrie ; link : série avec la Rasp).
#include <Arduino.h>

#include "config.h"
#include "link.h"
#include "motion_task.h"
#include "steppers.h"

namespace {

Steppers steppers;
Link rasp_link;

// Démarrage impossible : on le dit à la Rasp chaque seconde, sans jamais bouger
[[noreturn]] void fail(const char* message) {
  for (;;) {
    rasp_link.sendError(message);
    delay(1000);
  }
}

}  // namespace

void setup() {
  // La liaison d'abord : elle sert à signaler un échec des étapes suivantes
  if (!rasp_link.start()) {
    for (;;) delay(1000);  // pas d'UART : personne à qui le dire
  }
  if (!steppers.begin()) fail("demarrage : moteurs non branches");
  const Pose initial{config::INITIAL_X_MM, config::INITIAL_Y_MM, config::INITIAL_THETA_DEG};
  if (!motion_task::start(steppers, rasp_link, initial)) fail("demarrage : tache de mouvement");
}

// Tout tourne dans les tâches : la tâche loop() d'Arduino est supprimée
void loop() { vTaskDelete(nullptr); }
