#include "ArmCreator.hpp"
#include "ActiveObjectCreator.hpp"
#include "Arm_Actuator.hpp"
#include "Arm.hpp"
#include "AppState.hpp"
#include "ActiveObject.hpp"
#include "PCF8575.h"

struct ArmTaskContext {
    ArmActuatorId act_id;
    PCF8575& pcf;
    ActiveObjectStaticInterface& arm_interface;
};

void arm_task(void *pvParameters) {
   ArmTaskContext *ctx = (ArmTaskContext *) pvParameters; 
   Arm_Actuator arm_actuator{ctx->act_id, ctx->pcf, armInterruptionStateRef(ctx->act_id)};
   Arm arm{arm_actuator, ctx->act_id, ctx->arm_interface};
   while (!appState.timeout) {
     arm.loop();
     vTaskDelay(pdMS_TO_TICKS(ARM_TASK_DELAY_MS));
   };
}

void ArmCreator::init_active_object(
    ActiveObjectStaticInterface &interface, const char *const pcName,
    const FreeRTOSTaskStaticBuffers &task_static_buffers,
    const FreeRTOSQueueStaticBuffers &queue_in_static_buffers,
    const FreeRTOSQueueStaticBuffers &queue_out_static_buffers
) {
  interface.queue_into_object = _create_queue(
      ARM_QUEUE_MAX_ITEM_NB, ARM_IN_QUEUE_ITEM_SIZE, queue_in_static_buffers);
  interface.queue_out_from_object = _create_queue(ARM_QUEUE_MAX_ITEM_NB, ARM_OUT_QUEUE_ITEM_SIZE, queue_out_static_buffers);
  ArmTaskContext ctx {
      _arm_id, get_static_pcf(), interface
  };
  interface.task_id = _start_task(arm_task, pcName, ARM_TASK_STACK_SIZE, &ctx, ARM_TASK_PRIORITY, task_static_buffers);
}
