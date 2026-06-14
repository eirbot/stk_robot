#include "Arm_ActuatorVTask.hpp"
#include "AppState.hpp"
#include "Arduino.h"
#include "Arm_Actuator.hpp"
#include <cstdint>

#define TASK_QUEUE_SIZE 25

const uint16_t pangles0[4] = {40, 60, 120, 140};

Arm_ActuatorVTask::Arm_ActuatorVTask(Arm_Actuator &act, uint8_t actId,
                                     const char *const threadName,
                                     QueueHandle_t &queue)
    : ActuatorThread<Arm_Actuator, void>::ActuatorThread(act, actId, threadName,
                                                         queue) {
  // assign possible p angles
  if (actId < 4)
    this->pAngle0 = pangles0[actId];
}

bool Arm_ActuatorVTask::is_arm_initiated() {
    return _arm_initiated;
}

void Arm_ActuatorVTask::processCommand(TaskParams params) {
    switch (params._cmd) {
        case 'G':
            idlog(this, "Closing piston !");
            this->_act.closePiston();
            break;
        case 'R':
            idlog(this, "Opening piston !");
            this->_act.openPiston();
            break;
        case 'T':
            {
                idlog(this, "Command T inversing");
                int angle = this->_act.p9G_status == 0 ? 180 : 0;
                this->_act.servo_9G(angle);
                this->_act.p9G_status = angle;
            }
            break;
        case 'P':
            idlog(this, "Command P soft servo");
            this->_act.soft_servo(params._P_angleFlag ? this->pAngle0 : 90);
            break;
        case 'A':
            {
                idlog(this, "SetPos");
                int mmToStep = 80;
                int asked_height = params._A_param1* mmToStep;
                if(asked_height >= this->_act.asc_height) {
                  this->_act.goUp(asked_height - this->_act.asc_height);
                } else {
                  this->_act.goDown(this->_act.asc_height - asked_height);
                };
                this->_act.asc_height = asked_height;
            }
            break;
        case 'I':
            idlog(this, "Homming");
            this->_act.homming();
        default:
            break;
    }
}

void Arm_ActuatorVTask::vTask(void *const pvParameter) {
     while (!appState.timeout) {
        TaskParams params{'~', 255, -1}; // empty buffer

        // temporary shit polling
        // TODO: enable INCLUDE_vTaskSuspend to enable blocking call on time portMAX_DELAY
        int to_wait_ms = 10;  // the maximal blocking waiting time of millisecond
        const TickType_t xTicksToWait = pdMS_TO_TICKS(to_wait_ms);

        if (xQueueReceive(_queue, (void *) &params, 0) == pdTRUE) {
            if (params._cmd == '~') {
                Serial.println("Warning: invalid value parsed from queue");
            }
            processCommand(params);
        } else {
            vTaskDelay(xTicksToWait);
            idlog(this, "Queue empty, yield...");
        }

        vTaskDelay(0);
    }   
    vTaskDelete(NULL);
}

Arm_ActuatorManager::Arm_ActuatorManager() {
  act1.initialiser();
  act2.initialiser();
  act3.initialiser();
  act4.initialiser();

  for (Arm_ActuatorVTask arm_thread : _arm_threads)
    arm_thread.initVTask(NULL);
}

void Arm_ActuatorManager::processCommand(const String &cmd,
                                         const std::vector<int> &params) {

  // wait for all inits
  if (cmd == "I") {
    TaskParams taskParams = TaskParams(cmd.charAt(0), 0, 0);
    for (Arm_ActuatorVTask arm_thread: _arm_threads)
       arm_thread.sendToThreadQueue(taskParams);

    bool all_arms_initiated = true;
    for (Arm_ActuatorVTask arm_thread : _arm_threads) {
        if (!arm_thread.is_arm_initiated()) {
            all_arms_initiated = false;
            break;
        }
    }

    if (!all_arms_initiated)
        vTaskDelay(0);
    return;
  }

  if (params.size() == 0) {
    Serial.println(
        "No parameters for other actions, thus not valid ! Ignoring...");
    return;
  }

  int actioStatus = 0;
  int actId = (int)params[0];
  int A_param1 = 0;
  uint8_t P_angleFlag = 0;
  if (cmd == "P") {
    if (params.size() != 2) {
      Serial.println("Invalid number of parameters for command P");
      return;
    }
    P_angleFlag = params[1];
  } else if (cmd == "A") {
    if (params.size() != 2) {
      Serial.println("Invalid number of parameters for command A");
      return;
    }
    A_param1 = params[1];
  }
  char buf[8];
  Serial.print(itoa(actId, buf, 10));
  Serial.println(" id");
  TaskParams taskParams = TaskParams(cmd.charAt(0), P_angleFlag, A_param1);

  if (0 <= actId && actId < 4)
     _arm_threads[actId].sendToThreadQueue(taskParams); 
}
