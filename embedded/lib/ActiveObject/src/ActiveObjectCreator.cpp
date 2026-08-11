#include "ActiveObjectCreator.hpp"
#include "Arduino.h"

TaskHandle_t ActiveObjectCreator::_start_task(
    TaskFunction_t pvTaskCode, const char *const pcName,
    const uint32_t ulStackDepth, void *const pvParameters,
    UBaseType_t uxPriority, FreeRTOSTaskStaticBuffers task_static_buffers) {
  return xTaskCreateStatic(pvTaskCode, pcName, ulStackDepth, pvParameters,
                           uxPriority, task_static_buffers.puxStackBuffer,
                           task_static_buffers.pxTaskBuffer);
}

QueueHandle_t ActiveObjectCreator::_create_queue(
    const UBaseType_t uxQueueLength, const UBaseType_t uxItemSize,
    FreeRTOSQueueStaticBuffers queue_static_buffers) {
  return xQueueCreateStatic(uxQueueLength, uxItemSize,
                            queue_static_buffers.pucQueueStorage,
                            queue_static_buffers.pxStaticQueue);
}
