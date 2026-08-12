#include "CommunicatorConstructor.hpp"
#include "Arduino.h"
#include "ArmOrchestrator.hpp"
#include "ArmOrchestratorStatic.hpp"
#include "Arms.hpp"
#include "Communicator.hpp"

void communicator_task(void *pvParameters) {
    init_arms();
    ArmOrchestrator arm_orchestrator = init_orchestrator(armInterfaces);
    ComWithRasp com_object{orchestrator_interface, arm_orchestrator};
    com_object.task();
};

TaskHandle_t CommunicatorConstuctor::start_task(
    const char *const pcName,
    const FreeRTOSTaskStaticBuffers &task_static_buffers) {
  return xTaskCreateStatic(
      communicator_task, pcName, ORCHESTRATOR_TASK_STACK_SIZE, NULL,
      ORCHESTRATOR_TASK_PRIORITY, task_static_buffers.puxStackBuffer,
      task_static_buffers.pxTaskBuffer);
}
