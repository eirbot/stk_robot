#include <Arduino.h>
#include <unity.h>
#include "AppState.hpp"
#include "Arm_Actuator.hpp"
#include "Communicator.hpp"

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

void setup()
{
    delay(2000); // service delay
    UNITY_BEGIN();

    espSetup();

    ComWithRasp comRasp;
    comRasp.StartCom();
    comRasp.StartWorkers(); 

    vTaskDelay(pdMS_TO_TICKS(5000));
    appState.timeout = true;

    RUN_TEST(test_small_communication);

    UNITY_END(); // stop unit testing
}

void loop()
{
}
