#pragma once

#include "ActiveObject.hpp"
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
  command_id cmd_id;
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

#define ARM_MAX_NB 4

class Arm: public ActiveObject {
public:
  Arm(Arm_Actuator &actuator, ArmActuatorId actId,
      ActiveObjectStaticInterface &interface)
      : _actuator(actuator), _actId(actId),
        ActiveObject(interface){};

  void loop() override;

private:
  Arm_Actuator& _actuator;
  uint8_t _actId;
 
  /** Carry out the blocking interactions with the firmware to process the
command.

    For this operation to not block those in other actuators, be sure to run
    this in a FreeRTOS task.
   */
  void triggerFirmwareForCommand(ArmTaskParam command);
};
