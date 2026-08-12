#pragma once

#include "ActiveObject.hpp"
#include "ActiveObjectCreator.hpp"

// included for the macro to works
#include "Arduino.h"
#include "Arm.hpp"
#include "Arm_Actuator.hpp"

#define ARM_QUEUE_MAX_ITEM_NB 25
#define ARM_IN_QUEUE_ITEM_SIZE sizeof( ArmTaskParam )
#define ARM_OUT_QUEUE_ITEM_SIZE sizeof( uint8_t )
#define ARM_TASK_STACK_SIZE (sizeof(Arm) + sizeof(Arm_Actuator)) * 5
#ifndef ARM_TASK_PRIORITY
#define ARM_TASK_PRIORITY ( tskIDLE_PRIORITY + 2 )
#endif // ARM_TASK_PRIORITY

class ArmCreator : public ActiveObjectCreator {
public:
  ArmCreator() {};
  ~ArmCreator();
  void init_active_object(
      ActiveObjectStaticInterface &interface, const char *const pcName,
      const FreeRTOSTaskStaticBuffers &task_static_buffers,
      const FreeRTOSQueueStaticBuffers &queue_in_static_buffers,
      const FreeRTOSQueueStaticBuffers &queue_out_static_buffers) override;

private:
};
