#include "ArmOrchestrator.hpp"
#include "ActiveObject.hpp"
#include "Arduino.h"
#include "Arm.hpp"
#include "freertos/projdefs.h"

bool getNextEndedCommand(ActiveObjectStaticInterface &arm, command_id &cmd_id) {
  command_id finished_cmd;
  if (xQueueReceive(arm.queue_out_from_object, &finished_cmd, 0) == pdTRUE) {
    cmd_id = finished_cmd;
    return true;
  }
  return false;
}

void ArmOrchestrator::forwardCommandToArms(Command &cmd) {
  if (cmd.cmd == 'I') {
    ArmTaskParam taskParams {cmd.cmd_id, cmd.cmd, 0, 0};

    _pending_sync_arm_cmd_id = cmd.cmd_id;
    _synchronized_arm_nb = 0;

    for (ActiveObjectStaticInterface arm: _arms)
       xQueueSendToBack(arm.queue_into_object, &taskParams, 0);

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
  ArmTaskParam taskParams {cmd.cmd_id, cmd.cmd, P_angleFlag, A_param1};

  if (0 <= actId && actId < 4)
     xQueueSendToBack(_arms[actId].queue_into_object, &taskParams, 0);
}

void ArmOrchestrator::loop() {
  // Check the queue and forward the commands to the arms
  Command cmd;
  if (xQueueReceive(_interface.queue_into_object, &cmd, 0) == pdTRUE) forwardCommandToArms(cmd);
  // Check the arms finished missions
  for (ActiveObjectStaticInterface arm: _arms) {
    command_id finished_arm_cmd;
    bool maybe_finished_cmd = getNextEndedCommand(arm, finished_arm_cmd);
    if (maybe_finished_cmd) {
      // Dispatch the terminated command 
      xQueueSendToBack(_interface.queue_out_from_object, &finished_arm_cmd, 0);

      // If it an arm has finished initating, then increment the number of
      // synchronized arms
      if (finished_arm_cmd == _pending_sync_arm_cmd_id) {
        _synchronized_arm_nb++;
        // If all the arms are synchronized, then notify their FreeRTOS tasks
        // so they will stop suspending
        if (_synchronized_arm_nb == 4) {
          for (ActiveObjectStaticInterface arm_to_be_notified : _arms) 
            xTaskNotifyGive(arm_to_be_notified.task_id);
          _pending_sync_arm_cmd_id = NO_COMMAND;
        }
      }
    }
  }
}
