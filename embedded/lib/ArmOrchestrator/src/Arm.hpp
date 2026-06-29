#pragma once

#include "ActiveObject.hpp"
#include "Arduino.h"
#include "Arm_Actuator.hpp"

#define idlog(act, msg) { \
    Serial.print("[Task|Act"); \
    char buf[8]; \
    Serial.print(itoa(act->_actId, buf, 10)); \
    Serial.println("]" msg); \
}

/**
 * G: None
 * R: None
 * T: Inversion of current state, no param needed
 * P: Angle flag, one value or the other
 * A: PID controller factor ??? TODO: CHECK
 * I: None
 */
struct ArmTaskParam {
  char cmd;
  uint8_t P_angleFlag;
  int A_param1;
};

#ifndef ARM__MAX_PENDING_CMD_NB
#define ARM__MAX_PENDING_CMD_NB 25
#endif

#ifndef ARM_TASK_DELAY_MS
#define ARM_TASK_DELAY_MS 25
#endif

const uint16_t pangles0[4] = {40, 60, 120, 140};

class Arm: public ActiveObject {
public:
  Arm(Arm_Actuator& actuator, ArmActuatorId actId, QueueHandle_t &queue_into_object, QueueHandle_t &queue_out_from_object): _actuator(actuator), _actId(actId), _pAngle0(&(pangles0[actId])), ActiveObject(queue_into_object, queue_out_from_object) {};

  ~Arm() = default;

  void loop() override;

  void setRelatedFreeRTOSTask(TaskHandle_t task);
  TaskHandle_t getRelatedFreeRTOSTask();

private:
  Arm_Actuator& _actuator;
  uint8_t _actId;
  const uint16_t *_pAngle0;
  TaskHandle_t _relatedFreeRTOSTask;
 
  /** Carry out the blocking interactions with the firmware to process the
command.

    For this operation to not block those in other actuators, be sure to run
    this in a FreeRTOS task.
   */
  void triggerFirmwareForCommand(ArmTaskParam command);
};


void arm_task(void *pvParameters);

struct ArmTaskContext {
    ArmActuatorId act_id;
    PCF8575& pcf;
    QueueHandle_t& queue_into;
    QueueHandle_t& queue_out_of;
};

class ArmInterface: public ActiveObjectInterface {
public:
  ArmInterface(QueueHandle_t &queue_into_object, QueueHandle_t &queue_out_from_object): ActiveObjectInterface(queue_into_object, queue_out_from_object) {};

  ~ArmInterface() = default;

  void scheduleArmCommand(ArmTaskParam &command);

  /** Retrun true if something is returned (then opt has been edited).
   */
  bool getNextEndedCommand(ArmTaskParam *opt);
};
