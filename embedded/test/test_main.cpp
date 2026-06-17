#include <Arduino.h>
#include <unity.h>
#include "AppState.hpp"
#include "Arm.hpp"
#include "ArmOrchestrator.hpp"
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

void test_small_communication(void) {
    
    vTaskDelay(pdMS_TO_TICKS(5000));

    for (int arm_id; arm_id < 4; arm_id++) {
        Command init_cmd {'I', std::vector<int>{arm_id}};
        Command ascend {'A', std::vector<int>{arm_id, arm_id < 2 ? 10 : -10}};
        Command descend {'A', std::vector<int>{arm_id, arm_id < 2 ? -10 : 10}};
        arm_orchestrator.scheduleCommand(init_cmd);
        arm_orchestrator.scheduleCommand(ascend);
        arm_orchestrator.scheduleCommand(descend);
    }

    vTaskDelay(pdMS_TO_TICKS(7000));
    
    appState.timeout = true;

    TEST_ASSERT_EQUAL(1, 1);
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

void arm_orchestrator_life(void *pvParameters) {
    while (!appState.timeout) {
       arm_orchestrator.loop(); 
       vTaskDelay(pdMS_TO_TICKS(ARM_TASK_DELAY_MS));
    }
}

void setup()
{
    delay(2000); // service delay

    UNITY_BEGIN();

    espSetup();
    xTaskCreatePinnedToCore(arm_orchestrator_life, "armOrchestratorPc", 4000, NULL, 1, NULL, tskNO_AFFINITY);

    vTaskDelay(pdMS_TO_TICKS(2000));

    RUN_TEST(test_small_communication);

    UNITY_END(); // stop unit testing
}

void loop()
{
}
