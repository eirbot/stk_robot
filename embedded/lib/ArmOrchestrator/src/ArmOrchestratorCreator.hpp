#pragma once

#include "ActiveObjectCreator.hpp"
#include "ArmOrchestrator.hpp"

class ArmOrchestratorCreator : public ActiveObjectCreator {
public:
  ArmOrchestratorCreator() : ActiveObjectCreator() {};  

  /* Do not implement this function. */
  void init_active_object(ActiveObjectStaticInterface &interface,
                       const char *const pcName,
                       const FreeRTOSTaskStaticBuffers &task_static_buffers,
                       const FreeRTOSQueueStaticBuffers &queue_in_static_buffers,
                       const FreeRTOSQueueStaticBuffers &queue_out_static_buffers) override;

  ArmOrchestrator init_arm_orchestrator(
      ActiveObjectStaticInterface &interface,
      std::array<ActiveObjectStaticInterface, ARM_MAX_NB> &arms,
      const FreeRTOSQueueStaticBuffers &queue_in_static_buffers,
      const FreeRTOSQueueStaticBuffers &queue_out_static_buffers);
};
