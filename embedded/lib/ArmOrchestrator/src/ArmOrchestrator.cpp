#include "ArmOrchestrator.hpp"
#include "Arduino.h"
#include "Arm.hpp"
#include "freertos/projdefs.h"

void ArmOrchestrator::forwardCommandToArms(Command &cmd) {
  if (cmd.cmd == 'I') {
    ArmTaskParam taskParams {cmd.cmd, 0, 0};

    _synchronized_arm_nb = 0;

    for (ArmInterface arm: _arms)
       arm.scheduleArmCommand(taskParams);

    return;
  }

  if (cmd.params.size() == 0) {
    Serial.println(
        "No parameters for other actions, thus not valid ! Ignoring...");
    return;
  }

  int actioStatus = 0;
  int actId = cmd.params[0];
  int A_param1 = 0;
  uint8_t P_angleFlag = 0;
  if (cmd.cmd == 'P') {
    if (cmd.params.size() != 2) {
      Serial.println("Invalid number of parameters for command P");
      return;
    }
    P_angleFlag = cmd.params[1];
  } else if (cmd.cmd == 'A') {
    if (cmd.params.size() != 2) {
      Serial.println("Invalid number of parameters for command A");
      return;
    }
    A_param1 = cmd.params[1];
  }
  char buf[8];
  Serial.print(itoa(actId, buf, 10));
  Serial.println(" id");
  ArmTaskParam taskParams {cmd.cmd, P_angleFlag, A_param1};

  if (0 <= actId && actId < 4)
     _arms[actId].scheduleArmCommand(taskParams); 
}

void ArmOrchestratorInterface::scheduleCommand(Command &cmd) {
  xQueueSendToBack(queue_into_object(), &cmd, 0);
}

bool ArmOrchestratorInterface::getNextTerminatedCommand(Command *opt) {
  std::vector<int> dummy_params{};
  Command cmd {'~', dummy_params};
  if (xQueueReceive(queue_out_from_object(), &cmd, 0) == pdTRUE) {
     *opt = cmd;
     return true;
  }
  return false;
}

void ArmOrchestrator::loop() {
  // Check the queue and forward the commands to the arms
  Command cmd;
  if (xQueueReceive(queue_into_object(), &cmd, 0) == pdTRUE) forwardCommandToArms(cmd);
  // Check the arms finished missions
  for (ArmInterface arm: _arms) {
    ArmTaskParam finished_arm_cmd;
    bool maybe_finished_cmd = arm.getNextEndedCommand(&finished_arm_cmd);
    if (maybe_finished_cmd) {
      // Dispatch the terminated command 
      // TODO: set a param, e.g. a cmd id
      Command cmd {finished_arm_cmd.cmd, std::vector<int>{}};
      xQueueSendToBack(queue_out_from_object(), &cmd, 0);

      // If it an arm has finished initating, then increment the number of
      // synchronized arms
      if (finished_arm_cmd.cmd == 'I') {
        _synchronized_arm_nb++;
        // If all the arms are synchronized, then notify their FreeRTOS tasks
        // so they will stop suspending
        if (_synchronized_arm_nb == 4) {
          for (ArmInterface arm_to_be_notified : _arms) 
            xTaskNotifyGive(arm_to_be_notified.getRelatedFreeRTOSTask());
        }
      }
    }
  }
}
