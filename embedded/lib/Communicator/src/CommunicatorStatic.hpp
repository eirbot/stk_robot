#include "Arduino.h"
#include "CommunicatorConstructor.hpp"

// Task buffers
static StaticTask_t orchestratorXCreatorTaskTCBBuffer;
static StackType_t orchestratorUxCreatorTaskStackBuffer[ ORCHESTRATOR_TASK_STACK_SIZE ];
static TaskHandle_t orchestratorTask;

// Start the communicator task from the static stack buffers
void start_communicator_task();
