#include "ArmOrchestratorCreator.hpp"
#include "ActiveObject.hpp"
#include "Arm.hpp"
#include "ArmOrchestrator.hpp"

void ArmOrchestratorCreator::init_active_object(
    ActiveObjectStaticInterface &interface, const char *const pcName,
    const FreeRTOSTaskStaticBuffers &task_static_buffers,
    const FreeRTOSQueueStaticBuffers &queue_in_static_buffers,
    const FreeRTOSQueueStaticBuffers &queue_out_static_buffers) {}

ArmOrchestrator ArmOrchestratorCreator::init_arm_orchestrator(
    ActiveObjectStaticInterface &interface,
    std::array<ActiveObjectStaticInterface, ARM_MAX_NB> &arms,
    const FreeRTOSQueueStaticBuffers &queue_in_static_buffers,
    const FreeRTOSQueueStaticBuffers &queue_out_static_buffers) {
  interface.queue_into_object = _create_queue(
      ARM_ORCHESTRATOR_QUEUE_MAX_ITEM_NB, ARM_ORCHESTRATOR_IN_QUEUE_ITEM_SIZE,
      queue_in_static_buffers);
  interface.queue_out_from_object = _create_queue(
      ARM_ORCHESTRATOR_QUEUE_MAX_ITEM_NB, ARM_ORCHESTRATOR_OUT_QUEUE_ITEM_SIZE,
      queue_out_static_buffers);
  // INFO: no freertos task is initiated for this active object, so no task is
  // assigned to the interface
  return ArmOrchestrator{arms, interface};
}
