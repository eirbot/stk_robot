#include "Arm.hpp"
#include "ActiveObject.hpp"
#include "Arduino.h"

void Arm::triggerFirmwareForCommand(ArmTaskParam command) {
  switch (command.cmd) {
    case 'G':
      idlog(this, "Closing piston !");
      _actuator.closePiston();
      break;
    case 'R':
      idlog(this, "Opening piston !");
      _actuator.openPiston();
      break;
    case 'T':
      idlog(this, "Command T inversing");
      _actuator.invert_finger_angle();
      break;
    case 'P':
      idlog(this, "Command P soft servo");
      _actuator.set_elevator_horizontal_angle(command.P_angleFlag ? *_pAngle0 : 90);
      break;
    case 'A':
      idlog(this, "SetPos");
      _actuator.setElevatorPosition(command.A_param1);
      break;
    case 'I':
      idlog(this, "Homming");
      _actuator.homming();
      break;
    default:
      break;
  }
}

void Arm::loop() {
  ArmTaskParam params{NO_COMMAND, '~', 255, -1}; // empty buffer

  if (xQueueReceive(_interface.queue_into_object, &params, 0) != pdTRUE)
    return;

  if (params.cmd == '~') {
    Serial.println("Warning: invalid value parsed from queue");
    return;
  }

  triggerFirmwareForCommand(params);
  // Notify that the command is finished
  xQueueSendToBack(_interface.queue_out_from_object, &params.cmd_id, 0);

  if (params.cmd == 'I') {
    // If the command was homing, wait a sync notification from the orchestrator
    const TickType_t xMaxBlockTime = pdMS_TO_TICKS( 5000 );
    uint32_t notify_result;
    BaseType_t xResult = xTaskNotifyWait(pdFALSE, UINT32_MAX, &notify_result, xMaxBlockTime);
  }
}
