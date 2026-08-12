#include "Arms.hpp"
#include "ActiveObjectCreator.hpp"
#include "ArmCreator.hpp"
#include "Arm_Actuator.hpp"

void init_arm(ArmActuatorId k) {
  FreeRTOSTaskStaticBuffers task_buffer = {armUxCreatorTaskStackBuffer +
                                               (k * ARM_TASK_STACK_SIZE),
                                           armXCreatorTaskTCBBuffer + k};
  FreeRTOSQueueStaticBuffers in_queue_buffer = {
      armInStaticQueueStructs + k,
      armUcInQueuesStorageAreas +
          (k * ARM_QUEUE_MAX_ITEM_NB * ARM_IN_QUEUE_ITEM_SIZE)};
  FreeRTOSQueueStaticBuffers out_queue_buffer = {
      armOutStaticQueueStructs + k,
      armUcInQueuesStorageAreas +
          (k * ARM_QUEUE_MAX_ITEM_NB * ARM_OUT_QUEUE_ITEM_SIZE)};
  char arm_process_name[5] = "arm1";
  arm_process_name[3] = k + 1;
  ArmCreator().init_active_object(armInterfaces[k], arm_process_name, task_buffer, in_queue_buffer, out_queue_buffer);
}

void init_arms() {
  init_arm(ArmActuator1);
  init_arm(ArmActuator2);
  init_arm(ArmActuator3);
  init_arm(ArmActuator4);
}
