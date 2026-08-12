#pragma once

#include "ActiveObject.hpp"
#include "Arduino.h"
#include "freertos/FreeRTOS.h"

struct FreeRTOSTaskStaticBuffers {
  /* This is the stack that will be used by the prvStaticallyAllocatedCreator()
  task, which is itself created using statically allocated buffers (so without any
  dynamic memory allocation).

  Declare it externally like this:
    static StackType_t uxCreatorTaskStackBuffer[ TASK_STACK_SIZE ];
  */
  StackType_t *const puxStackBuffer;

  /* StaticTask_t is a publicly accessible structure that has the same size and
  alignment requirements as the real TCB structure.  It is provided as a mechanism
  for applications to know the size of the TCB (which is dependent on the
  architecture and configuration file settings) without breaking the strict data
  hiding policy by exposing the real TCB.  This StaticTask_t variable is passed
  into the xTaskCreateStatic() function that creates the
  prvStaticallyAllocatedCreator() task, and will hold the TCB of the created
  tasks.

  Declare it externally like this:
    static StaticTask_t xCreatorTaskTCBBuffer;
  */
  StaticTask_t *const pxTaskBuffer;
};

struct FreeRTOSQueueStaticBuffers {
  /** Declare it externally like this:
    static StaticQueue_t pxStaticQueue;
  */
  StaticQueue_t *pxStaticQueue;

  /** Declare it externally like this:
    static uint8_t pucQueueStorage[ QUEUE_LENGTH_IN_ITEMS * sizeof( StructOfQueueElement ) ];
  */
  uint8_t *pucQueueStorage;
};

/** Simple wrapper to the FreeRTOS static task creation function. 
  * Override it to create your specialized ActiveObject. 
  */
class ActiveObjectCreator {
  public:
    ActiveObjectCreator() {};
    /** Set the queues and the task id of the active object's interface.   
      */
    virtual void
    init_active_object(ActiveObjectStaticInterface &interface,
                       const char *const pcName,
                       const FreeRTOSTaskStaticBuffers &task_static_buffers,
                       const FreeRTOSQueueStaticBuffers &queue_in_static_buffers,
                       const FreeRTOSQueueStaticBuffers &queue_out_static_buffers) = 0;

  protected:
    TaskHandle_t _start_task(TaskFunction_t pvTaskCode, const char *const pcName, const uint32_t ulStackDepth, void *const pvParameters, UBaseType_t uxPriority,FreeRTOSTaskStaticBuffers task_static_buffers);
    QueueHandle_t _create_queue(const UBaseType_t uxQueueLength, const UBaseType_t uxItemSize, FreeRTOSQueueStaticBuffers queue_static_buffers);
};
