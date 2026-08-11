#include "ArmCreator.hpp"
#include "ActiveObjectCreator.hpp"
#include "Arm_Actuator.hpp"
#include "Arm.hpp"
#include "AppState.hpp"
#include "ActiveObject.hpp"
#include "PCF8575.h"
#include <cstdint>

struct ArmTaskContext {
    ArmActuatorId act_id;
    PCF8575& pcf;
    ActiveObjectStaticInterface& arm_interface;
};

void arm_task(void *pvParameters) {
   ArmTaskContext *ctx = (ArmTaskContext *) pvParameters; 
   Arm_Actuator arm_actuator = init_arm_actuator(ctx->act_id, ctx->pcf);
   Arm arm{arm_actuator, ctx->act_id, ctx->arm_interface};
   while (!appState.timeout) {
     arm.loop();
     vTaskDelay(pdMS_TO_TICKS(ARM_TASK_DELAY_MS));
   };
}

#define QUEUE_LENGTH_IN_ITEMS 25
#define TASK_STACK_SIZE (sizeof(Arm) + sizeof(Arm_Actuator)) * 5
#define TASK_PRIORITY	( tskIDLE_PRIORITY + 2 )

void ArmCreator::init_active_object(
    ActiveObjectStaticInterface &interface, const char *const pcName,
    FreeRTOSTaskStaticBuffers task_static_buffers,
    FreeRTOSQueueStaticBuffers queue_in_static_buffers,
    FreeRTOSQueueStaticBuffers queue_out_static_buffers
) {
  interface.queue_into_object = _create_queue(
      QUEUE_LENGTH_IN_ITEMS, sizeof(ArmTaskParam), queue_in_static_buffers);
  interface.queue_out_from_object = _create_queue(QUEUE_LENGTH_IN_ITEMS, sizeof(uint8_t), queue_out_static_buffers);
  ArmTaskContext ctx {
      ArmActuator1, pcf, interface
  };
  interface.task_id = _start_task(arm_task, pcName, TASK_STACK_SIZE, &ctx, TASK_PRIORITY, task_static_buffers);
}
