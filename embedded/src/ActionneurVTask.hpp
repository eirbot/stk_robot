#pragma once

#include "Actionneurs.hpp"
#include <stdint.h>

#define idlog(act, msg) { \
    Serial.print("[Task|Act"); \
    char buf[8]; \
    Serial.print(itoa(act->_actId, buf, 10)); \
    Serial.println("]" msg); \
}

extern QueueHandle_t qActVtask1, qActVtask2, qActVtask3, qActVtask4;

 /**
 * G: None
 * R: None
 * T: Inversion of current state, no param needed
 * P: Angle flag, one value or the other
 * A: PID controller factor ??? TODO: CHECK
 * I: None
 */
class TaskParams {
    public:
      TaskParams(char cmd, uint8_t P_angleFlag, int A_param1): _cmd(cmd), _P_angleFlag(P_angleFlag), _A_param1(A_param1) {}
        const char _cmd;
        const uint8_t _P_angleFlag;
        const int _A_param1;
    private:
};

class ActionneurVTask {
public:
    ActionneurVTask(Actionneur& act, uint8_t actId, QueueHandle_t& queue);
    void processCommand(TaskParams params);
    QueueHandle_t& _queue;
    bool flagInit;
    const uint8_t _actId;
private:
    Actionneur& _act;
    uint16_t pAngle0, pAngle1;
};

extern ActionneurVTask actVTask1;
extern ActionneurVTask actVTask2;
extern ActionneurVTask actVTask3;
extern ActionneurVTask actVTask4;

void ActVTaskRunner(void *pvParameter);
