#include "CommunicatorStatic.hpp"
#include "ActiveObjectCreator.hpp"
#include "CommunicatorConstructor.hpp"

void start_communicator_task() {
  orchestratorTask = CommunicatorConstuctor{}.start_task(
      "orchestrator",
      FreeRTOSTaskStaticBuffers{orchestratorUxCreatorTaskStackBuffer,
                                &orchestratorXCreatorTaskTCBBuffer});
}
