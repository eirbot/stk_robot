#include "Arm.hpp"
#include "AppState.hpp"
#include "Arduino.h"

void Arm::scheduleArmCommand(ArmTaskParam &command) {
   xQueueSendToBack(queue_into_object(), &command, 0);
}

std::optional<ArmTaskParam> Arm::getNextEndedCommand() {
   ArmTaskParam pvBuffer {};
   if (xQueueReceive(queue_out_from_object(), &pvBuffer, 0) == pdTRUE)
     return std::optional<ArmTaskParam>{pvBuffer};
   return std::nullopt;
}


void Arm::triggerFirmwareForCommand(ArmTaskParam command) {
      switch (command.cmd) {
        case 'G':
            idlog(this, "Closing piston !");
            _actuator->closePiston();
            break;
        case 'R':
            idlog(this, "Opening piston !");
            _actuator->openPiston();
            break;
        case 'T':
            {
                idlog(this, "Command T inversing");
                int angle = _actuator->p9G_status == 0 ? 180 : 0;
                _actuator->servo_9G(angle);
                _actuator->p9G_status = angle;
            }
            break;
        case 'P':
            idlog(this, "Command P soft servo");
            _actuator->soft_servo(command.P_angleFlag ? *_pAngle0 : 90);
            break;
        case 'A':
            {
                idlog(this, "SetPos");
                int mmToStep = 80;
                int asked_height = command.A_param1* mmToStep;
                if(asked_height >= _actuator->asc_height) {
                  _actuator->goUp(asked_height - this->_actuator->asc_height);
                } else {
                  _actuator->goDown(_actuator->asc_height - asked_height);
                };
                _actuator->asc_height = asked_height;
            }
            break;
        case 'I':
            idlog(this, "Homming");
            _actuator->homming();
        default:
            break;
    }
}

void Arm::loop() {
  ArmTaskParam params{'~', 255, -1}; // empty buffer

  if (xQueueReceive(queue_into_object(), &params, 0) != pdTRUE)
    return;

  if (params.cmd == '~') {
    Serial.println("Warning: invalid value parsed from queue");
    return;
  }

  triggerFirmwareForCommand(params);
  // Notify that the command is finished
  xQueueSendToBack(queue_out_from_object(), &params, 0);

  if (params.cmd == 'I') {
    const TickType_t xMaxBlockTime = pdMS_TO_TICKS( 5000 );
    uint32_t notify_result;
    BaseType_t xResult = xTaskNotifyWait(pdFALSE, UINT32_MAX, &notify_result, xMaxBlockTime);
  }
}

void Arm::setRelatedFreeRTOSTask(TaskHandle_t task) {
  _relatedFreeRTOSTask = task;
}

TaskHandle_t Arm::getRelatedFreeRTOSTask() {
  return _relatedFreeRTOSTask;
}

void arm_task(void *pvParameters) {
   Arm *arm = (Arm*) pvParameters;
   while (!appState.timeout) {
     arm->loop();
     vTaskDelay(pdMS_TO_TICKS(ARM_TASK_DELAY_MS));
   };
}

std::array<Arm, 4> init_4_arms_rtos_tasks() {
  std::array<char const[5], 4> armPcNames{"arm1","arm2","arm3","arm4"};
  std::array<Arm, 4> arms{
    Arm{&act1, 0}, Arm{&act2, 1}, Arm{&act3, 2}, Arm{&act4, 3}
  };
  for (uint8_t arm_id = 0; arm_id < 4; arm_id++) {
    Arm arm = arms[arm_id];
    char const *armPcName = armPcNames[arm_id];
    TaskHandle_t relatedTask;
    xTaskCreatePinnedToCore(arm_task, armPcName, 4000, &arm, 1, &relatedTask, tskNO_AFFINITY);
    arm.setRelatedFreeRTOSTask(relatedTask);
  }
  return arms;
}
