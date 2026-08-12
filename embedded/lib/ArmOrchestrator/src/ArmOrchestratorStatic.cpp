#include "ArmOrchestratorStatic.hpp"
#include "ArmOrchestrator.hpp"
#include "ArmOrchestratorCreator.hpp"

ArmOrchestrator
init_orchestrator(std::array<ActiveObjectStaticInterface, 4> &arms) {
  return ArmOrchestratorCreator{}.init_arm_orchestrator(
      orchestrator_interface, arms,
      FreeRTOSQueueStaticBuffers{&armOrchestratorInStaticQueueStruct,
                                 armOrchestratorUcInQueuesStorageArea},
      FreeRTOSQueueStaticBuffers{&armOrchestratorOutStaticQueueStruct,
                                 armOrchestratorUcOutQueuesStorageArea});
}
