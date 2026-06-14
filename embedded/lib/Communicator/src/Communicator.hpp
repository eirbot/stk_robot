#ifndef COM_WITH_RASP_HPP
#define COM_WITH_RASP_HPP

// #include "main_robot.h"
#include "ActuatorThread.hpp"
#include <Arduino.h>
#include <vector>

class ComWithRasp {
public:
  ComWithRasp(std::vector<ActuatorManager *> actuator_managers): _actuator_managers(actuator_managers) {};
  void StartCom(); // Lance la tâche FreeRTOS
  void Send();     // Envoie la commande (debug/test)

  volatile bool flagInit = false;

private:
  void Receive();     // Lecture UART dans une boucle
  void TelemetryLoop(); // Envoi périodique de la télémétrie
  void processLine(); // Découpe et traite la commande
  void processCommand(const String &cmd, const std::vector<int> &params);
  void asyncGoTo(float x, float y, float angle);
  static void GoToTask(void* pvParameters);

  std::vector<ActuatorManager *> _actuator_managers;
  String commande;
  char rcv;
  static constexpr int MAX_COMMAND_LENGTH = 64;
  volatile bool isMoving = false;
};

#endif
