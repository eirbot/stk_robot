#include "CommunicatorStatic.hpp"
#include "AppState.hpp"
#include "Arm_Actuator.hpp"

#define INCLUDE_vTaskDelay 1

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

void setup()
{
    Serial.println("Waiting 2 seconds...");
    delay(2000); // service delay

    Serial.println("Tests started!");

    espSetup();
    Serial.println("Start orchestrator task!");

    start_communicator_task();

    Serial.println("Orchestrator task started! Waiting 10 seconds");

    vTaskDelay(pdMS_TO_TICKS(10000));

    Serial.println("Timeout! Every task will be stopped.");
    appState.timeout = true;
}

void loop() {}
