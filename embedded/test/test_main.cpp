#include <Arduino.h>
#include <unity.h>
#include "AppState.hpp"
#include "Arm.hpp"
#include "Arm_Actuator.hpp"
#include "freertos/projdefs.h"

String STR_TO_TEST;

static int timeout;

void setUp(void) {
    // set stuff up here
    STR_TO_TEST = "Hello, world!";
}

void tearDown(void) {
    // clean stuff up here
    STR_TO_TEST = "";
}

// The setup that we do not care a lot in this test
void espSetup() {
    Wire.begin(21, 22); 
    Wire.setClock(100000);
    // TODO: uncomment before match
    if (!pcf.begin()) {
      Serial.println("PCF8575 introuvable");
      while (1);
    }
    pinMode(IntEXT, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(IntEXT), IntEXTfct, FALLING);
}

// TODO: put those links in a documentation
// https://sourceforge.net/p/freertos/code/HEAD/tree/trunk/FreeRTOS/Demo/Common/Minimal/StaticAllocation.c#l53
// https://freertos.org/Documentation/02-Kernel/02-Kernel-features/09-Memory-management/03-Static-vs-Dynamic-memory-allocation
// https://freertos.org/Documentation/02-Kernel/02-Kernel-features/09-Memory-management/01-Memory-management#heap_4c
// https://www.youtube.com/watch?v=Qske3yZRW5I&list=PLEBQazB0HUyQ4hAPU1cJED6t3DU0h34bz&index=4
#define QUEUE_LENGTH_IN_ITEMS 25
#define TASK_STACK_SIZE (sizeof(Arm) + sizeof(Arm_Actuator)) * 5
#define TASK_PRIORITY	( tskIDLE_PRIORITY + 2 )

static StaticQueue_t staticQueueIntoArm;
static StaticQueue_t staticQueueOutOfArm;
static uint8_t ucQueueStorageAreaInto[ QUEUE_LENGTH_IN_ITEMS * sizeof( ArmTaskParam ) ];
static uint8_t ucQueueStorageAreaOutOf[ QUEUE_LENGTH_IN_ITEMS * sizeof( ArmTaskParam ) ];

/*-----------------------------------------------------------*/

/* StaticTask_t is a publicly accessible structure that has the same size and
alignment requirements as the real TCB structure.  It is provided as a mechanism
for applications to know the size of the TCB (which is dependent on the
architecture and configuration file settings) without breaking the strict data
hiding policy by exposing the real TCB.  This StaticTask_t variable is passed
into the xTaskCreateStatic() function that creates the
prvStaticallyAllocatedCreator() task, and will hold the TCB of the created
tasks. */
static StaticTask_t xCreatorTaskTCBBuffer;

/* This is the stack that will be used by the prvStaticallyAllocatedCreator()
task, which is itself created using statically allocated buffers (so without any
dynamic memory allocation). */
static StackType_t uxCreatorTaskStackBuffer[ TASK_STACK_SIZE ];

/*-----------------------------------------------------------*/

// ----------- SETUP ------------
QueueHandle_t queue_into = xQueueCreateStatic(QUEUE_LENGTH_IN_ITEMS, sizeof(ArmTaskParam), ucQueueStorageAreaInto, &staticQueueIntoArm);    
QueueHandle_t queue_out_of = xQueueCreateStatic(QUEUE_LENGTH_IN_ITEMS, sizeof(ArmTaskParam), ucQueueStorageAreaOutOf, &staticQueueOutOfArm);    
ArmTaskContext ctx {
    ArmActuator1, get_static_pcf(), queue_into, queue_out_of
};


void vStartStaticallyAllocatedTasks( void  )
{
    /* Create a single task, which then repeatedly creates and deletes the other
    RTOS objects using both statically and dynamically allocated RAM. */
    xTaskCreateStatic( arm_task,		/* The function that implements the task being created. */
    			   "Arm1StatCreate",						/* Text name for the task - not used by the RTOS, its just to assist debugging. */
    			   TASK_STACK_SIZE,		/* Size of the buffer passed in as the stack - in words, not bytes! */
    			   &ctx,								/* Parameter passed into the task - not used in this case. */
    			   TASK_PRIORITY,					/* Priority of the task. */
    			   &( uxCreatorTaskStackBuffer[ 0 ] ),  /* The buffer to use as the task's stack. */
    			   &xCreatorTaskTCBBuffer );			/* The variable that will hold the task's TCB. */
}
// ----------- SETUP ------------



void test_small_communication(void) {
    
    Serial.println("Waiting 5 seconds...");
    vTaskDelay(pdMS_TO_TICKS(5000));

    Serial.println("Scheduling Commands...");
    // TODO: add a command to the queue and test
    Serial.println("Scheduled!");

    Serial.println("Waiting 5 seconds before ends the test...");
    vTaskDelay(pdMS_TO_TICKS(7000));
    
    appState.timeout = true;

    TEST_ASSERT_EQUAL(1, 1);
}

void setup()
{
    Serial.println("Waiting 2 seconds...");
    delay(2000); // service delay

    UNITY_BEGIN();
    Serial.println("Tests started!");

    espSetup();
    Serial.println("Start orchestrator task!");

    vStartStaticallyAllocatedTasks();

    Serial.println("Orchestrator task started! Waiting 2seconds");
    vTaskDelay(pdMS_TO_TICKS(2000));

    RUN_TEST(test_small_communication);

    UNITY_END(); // stop unit testing
}

void loop()
{
}
