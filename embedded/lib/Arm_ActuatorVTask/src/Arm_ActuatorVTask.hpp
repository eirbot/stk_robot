#pragma once

#include "ActuatorThread.hpp"
#include "Arduino.h"
#include "Arm_Actuator.hpp"
#include <array>

#define idlog(act, msg) { \
    Serial.print("[Task|Act"); \
    char buf[8]; \
    Serial.print(itoa(act->_actId, buf, 10)); \
    Serial.println("]" msg); \
}

class Arm_ActuatorVTask: public ActuatorThread<Arm_Actuator, void> {
public:
    Arm_ActuatorVTask(Arm_Actuator& act, uint8_t actId, const char *const threadName, QueueHandle_t& queue);
 
    void vTask(void *const pvParameter) override;

    bool is_arm_initiated();

protected:
    void processCommand(TaskParams params) override;

    bool _arm_initiated = false;
};

#define ARM_TASK_QUEUE_SIZE 25

class Arm_ActuatorManager: public ActuatorManager {

public:
  /** Init all the thread related to the 4 actuators
    */
  Arm_ActuatorManager();

  /**
   * G: None
   * R: None
   * T: Inversion of current state, no param needed
   * P: Angle flag, one value or the other
   * A: PID controller factor ??? TODO: CHECK
   * I: None
   */
  void processCommand(const String &cmd,
                      const std::vector<int> &params) override;

private:
    std::array<QueueHandle_t, 4> _arm_queues = {
      xQueueCreate(ARM_TASK_QUEUE_SIZE, sizeof(TaskParams)),
      xQueueCreate(ARM_TASK_QUEUE_SIZE, sizeof(TaskParams)),
      xQueueCreate(ARM_TASK_QUEUE_SIZE, sizeof(TaskParams)),
      xQueueCreate(ARM_TASK_QUEUE_SIZE, sizeof(TaskParams)),
    };

    std::array<Arm_ActuatorVTask, 4> _arm_threads = {
        Arm_ActuatorVTask {act1, 0, "Arm_Actuator1_Thread", _arm_queues[0]},
        Arm_ActuatorVTask {act2, 1, "Arm_Actuator2_Thread", _arm_queues[1]},
        Arm_ActuatorVTask {act3, 2, "Arm_Actuator3_Thread", _arm_queues[2]},
        Arm_ActuatorVTask {act4, 3, "Arm_Actuator4_Thread", _arm_queues[3]},
    };

};
