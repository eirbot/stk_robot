#ifndef COM_WITH_RASP_HPP
#define COM_WITH_RASP_HPP

// #include "main_robot.h"
#include <Arduino.h>
#include <vector>

#include "ActiveObject.hpp"
#include "ArmOrchestrator.hpp"

class ComWithRasp {
public:
  ComWithRasp(ActiveObjectStaticInterface &armOrchestratorInterface,
              ArmOrchestrator &taskLocalArmOrchestrator)
      : _armOrchestratorInterface(armOrchestratorInterface),
        _taskLocalArmOrchestrator(taskLocalArmOrchestrator){};
  void Send();     // Envoie la commande (debug/test)
  void task();     // com lifecycle: loop UART readings and yields until timeout

  volatile bool flagInit = false;

private:
  // TODO: write in serial the id of the ended commands 
  void receive(char rx_buffer[64], int &rx_index); // One UART reading
  void TelemetryLoop(); // Envoi périodique de la télémétrie
  void processLine(); // Découpe et traite la commande
  void processCommand(const String &cmd, const std::vector<int> &params);
  void asyncGoTo(float x, float y, float angle);
  static void GoToTask(void* pvParameters);

  ActiveObjectStaticInterface &_armOrchestratorInterface;
  ArmOrchestrator &_taskLocalArmOrchestrator;
  command_id _next_command_id = NO_COMMAND + 1;
  String commande;
  char rcv;
  static constexpr int MAX_COMMAND_LENGTH = 64;
  volatile bool isMoving = false;
};

#endif
