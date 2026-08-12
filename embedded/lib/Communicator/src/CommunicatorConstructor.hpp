#pragma once

#include "ActiveObjectCreator.hpp"
#include "Arduino.h"

// include this for the macro to work everywhere
#include "Communicator.hpp"
#include "ArmOrchestrator.hpp"

#define ORCHESTRATOR_TASK_STACK_SIZE (sizeof( ComWithRasp ) + sizeof( ArmOrchestrator )) * 2
#ifndef ORCHESTRATOR_TASK_PRIORITY
#define ORCHESTRATOR_TASK_PRIORITY ( tskIDLE_PRIORITY + 2 )
#endif // ORCHESTRATOR_TASK_PRIORITY

class CommunicatorConstuctor {
public:
  CommunicatorConstuctor() {};
  static TaskHandle_t
  start_task(const char *const pcName,
             const FreeRTOSTaskStaticBuffers &task_static_buffers);
};
