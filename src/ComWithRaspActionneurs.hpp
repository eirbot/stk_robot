#ifndef COM_WITH_RASP_HPP
#define COM_WITH_RASP_HPP

// #include "main_robot.h"
#include <Arduino.h>
#include <vector>

class ComWithRasp {
public:
  ComWithRasp();
  void StartCom(); // Lance la tâche FreeRTOS
  void Send();     // Envoie la commande (debug/test)

  volatile bool flagInit = false;

private:
  void Receive();     // Lecture UART dans une boucle
  void Execute();     // Exécute les commandes de cmdQueue une par une
  void TelemetryLoop(); // Envoi périodique de la télémétrie
  void processLine(); // Découpe et traite la commande
  void processCommand(const String &cmd, const std::vector<int> &params);
  void asyncGoTo(float x, float y, float angle);
  static void GoToTask(void* pvParameters);

  String commande;
  char rcv;
  static constexpr int MAX_COMMAND_LENGTH = 64;
  volatile bool isMoving = false;
  // Lignes reçues en attente d'exécution : la lecture reste réactive pendant
  // qu'une commande bloquante (ascenseur, servo) s'exécute
  QueueHandle_t cmdQueue = NULL;
};

#endif