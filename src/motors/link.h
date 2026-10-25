// Liaison série avec la Rasp (protocole : protocol.h), sur l'UART0 (port USB de l'ESP32).
//
// Deux tâches :
//   réception  lit les octets (pilote UART d'ESP-IDF, lecture bloquante), découpe les
//              lignes, transmet les commandes à la tâche de mouvement, et surveille le
//              watchdog : Rasp muette RASP_TIMEOUT_MS -> « W » puis arrêt (H).
//   télémétrie envoie la pose « T » toutes les TELEMETRY_PERIOD_MS.
// Link est aussi le MotionListener : fin de GoTo -> « T » puis « D id » / « A id ».
//
// Chaque trame part en UN seul appel d'écriture, sous verrou : deux tâches qui écrivent
// en même temps ne mélangent jamais leurs caractères.
#pragma once

#include "motion.h"

class Link : public MotionListener {
 public:
  // Installe le pilote UART et crée les deux tâches. À appeler après motion_task::start().
  bool start();

  // Trame « E message » (erreurs, y compris au démarrage)
  void sendError(const char* message);

  void onGotoDone(uint32_t id, const Pose& pose) override;
  void onGotoAborted(uint32_t id, const Pose& pose) override;
};
