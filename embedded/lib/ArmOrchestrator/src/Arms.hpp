#pragma once

#include "ActiveObject.hpp"
#include "Arduino.h"
#include "Arm.hpp"
#include "ArmCreator.hpp"
#include "freertos/FreeRTOS.h"

// Queue buffers
static StaticQueue_t armInStaticQueueStructs[ARM_MAX_NB];
static StaticQueue_t armOutStaticQueueStructs[ARM_MAX_NB];
static uint8_t armUcInQueuesStorageAreas[ARM_MAX_NB * ARM_QUEUE_MAX_ITEM_NB * ARM_IN_QUEUE_ITEM_SIZE];
static uint8_t armUcOutQueuesStorageAreas[ARM_MAX_NB * ARM_QUEUE_MAX_ITEM_NB * ARM_OUT_QUEUE_ITEM_SIZE];

// Task buffers
static StaticTask_t armXCreatorTaskTCBBuffer[ARM_MAX_NB];
static StackType_t armUxCreatorTaskStackBuffer[ ARM_MAX_NB * ARM_TASK_STACK_SIZE ];

// ActiveObjects
static QueueHandle_t armInStaticQueues[ARM_MAX_NB];
static QueueHandle_t armOutStaticQueues[ARM_MAX_NB];
static TaskHandle_t armStaticTasks[ARM_MAX_NB];
static struct ActiveObjectStaticInterface armInterfaces[ARM_MAX_NB] = {
    {armInStaticQueues[0], armOutStaticQueues[0], armStaticTasks[0]},
    {armInStaticQueues[1], armOutStaticQueues[1], armStaticTasks[1]},
    {armInStaticQueues[2], armOutStaticQueues[2], armStaticTasks[2]},
    {armInStaticQueues[3], armOutStaticQueues[3], armStaticTasks[3]}
};

/* Start the FreeRTOS task of the k-th arm from the relevant static buffers,
   which are edited.
*/
void init_arm(ArmActuatorId k);
/* Start the tasks of all the arms. */
void init_arms();
