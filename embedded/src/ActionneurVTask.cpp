#include "ActionneurVTask.hpp"
#include "Arduino.h"
#include <cstdint>

#define TASK_QUEUE_SIZE 25

QueueHandle_t
    qActVtask1 = xQueueCreate(TASK_QUEUE_SIZE, sizeof(TaskParams)),
    qActVtask2 = xQueueCreate(TASK_QUEUE_SIZE, sizeof(TaskParams)),
    qActVtask3 = xQueueCreate(TASK_QUEUE_SIZE, sizeof(TaskParams)),
    qActVtask4 = xQueueCreate(TASK_QUEUE_SIZE, sizeof(TaskParams));

ActionneurVTask actVTask1 = ActionneurVTask{act1, 1, qActVtask1};
ActionneurVTask actVTask2 = ActionneurVTask{act2, 2, qActVtask2};
ActionneurVTask actVTask3 = ActionneurVTask{act3, 3, qActVtask3};
ActionneurVTask actVTask4 = ActionneurVTask{act4, 4, qActVtask4};

void ActionneurVTask::processCommand(TaskParams params) {
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

const uint16_t pangles0[4] = {40, 60, 120, 140};

ActionneurVTask::ActionneurVTask(Actionneur &act, uint8_t actId, QueueHandle_t &queue): _act(act), _queue(queue), _actId(actId) {
    this->flagInit = false;
    // assign possible p angles
    if (actId < 4)
      this->pAngle0 = pangles0[actId];
}

void ActVTaskRunner(void *pvParameter) {
    ActionneurVTask* myObject = static_cast<ActionneurVTask*>(pvParameter);

    for (;;) {
        TaskParams params{'~', 255, -1}; // empty buffer

        // temporary shit polling
        // TODO: enable INCLUDE_vTaskSuspend to enable blocking call on time portMAX_DELAY
        int to_wait_ms = 10;  // the maximal blocking waiting time of millisecond
        const TickType_t xTicksToWait = pdMS_TO_TICKS(to_wait_ms);

        if (xQueueReceive(myObject->_queue, (void *) &params, 0) == pdTRUE) {
            if (params._cmd == '~') {
                Serial.println("Warning: invalid value parsed from queue");
            }
            myObject->processCommand(params);
        } else {
            vTaskDelay(xTicksToWait);
            idlog(myObject, "Queue empty, yield...");
        }

        vTaskDelay(0);
    }
    vTaskDelete(NULL);
}
