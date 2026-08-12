#include <Arduino.h>
#include <unity.h>
#include "ActiveObject.hpp"
#include "AppState.hpp"
#include "Arm.hpp"
#include "Arms.hpp"
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
    if (!get_static_pcf().begin()) {
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

void test_small_communication(void) {
    
    Serial.println("Waiting 5 seconds...");
    vTaskDelay(pdMS_TO_TICKS(5000));

    Serial.println("Scheduling Commands...");

    // TODO: add a command to the queue and test

    ArmTaskParam command1{NO_COMMAND+1,'I',0,0};
    xQueueSendToBack(armInterfaces[ArmActuator1].queue_into_object, &command1, 0);
    Serial.println("Scheduled!");
    Serial.println("Waiting 5 seconds before ends the test...");
    vTaskDelay(pdMS_TO_TICKS(2000));
    xTaskNotifyGive(armInterfaces[ArmActuator1].task_id);
    // TODO: Set true params for an ascending arm command 
    // ArmTaskParam command2{NO_COMMAND+2,'A',0,2};
    // xQueueSendToBack(armInterfaces[ArmActuator1].queue_into_object, &command2, 0);

    vTaskDelay(pdMS_TO_TICKS(3000));
    
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
    Serial.println("Start arm1 task!");

    init_arm(ArmActuator1);

    Serial.println("Arm task started! Waiting 2seconds");
    vTaskDelay(pdMS_TO_TICKS(2000));

    RUN_TEST(test_small_communication);

    UNITY_END(); // stop unit testing
}

void loop()
{
}
