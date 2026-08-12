#pragma once

#include "ActiveObject.hpp"
#include "Arduino.h"
#include "ArmOrchestrator.hpp"
#include "freertos/FreeRTOS.h"

// Queue buffers
static StaticQueue_t armOrchestratorInStaticQueueStruct;
static StaticQueue_t armOrchestratorOutStaticQueueStruct;
static uint8_t
    armOrchestratorUcInQueuesStorageArea[ARM_ORCHESTRATOR_QUEUE_MAX_ITEM_NB *
                                          ARM_ORCHESTRATOR_IN_QUEUE_ITEM_SIZE];
static uint8_t armOrchestratorUcOutQueuesStorageArea
    [ARM_ORCHESTRATOR_QUEUE_MAX_ITEM_NB * ARM_ORCHESTRATOR_OUT_QUEUE_ITEM_SIZE];

static QueueHandle_t armOrchestratorInStaticQueue;
static QueueHandle_t armOrchestratorOutStaticQueue;
static TaskHandle_t armOrchestratorDummyTask;

static struct ActiveObjectStaticInterface orchestrator_interface {
  armOrchestratorInStaticQueue, armOrchestratorOutStaticQueue,
      armOrchestratorDummyTask
};

// Init the arm orchestrator in the vtask from the static buffers 
ArmOrchestrator init_orchestrator(std::array<ActiveObjectStaticInterface, 4> &arms);
