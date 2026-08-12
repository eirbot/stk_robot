#include "ArmOrchestrator.hpp"
#include "Arms.hpp"
#include "ArmOrchestratorStatic.hpp"
#include "Communicator.hpp"
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

    // TODO: start the arm orchestrator and communication in a freertos task
    init_arms();
    ArmOrchestrator arm_orchestrator = init_orchestrator(armInterfaces);
    ComWithRasp com_object{orchestrator_interface, arm_orchestrator};
    com_object.task();

    // TODO: keep this in the main task
    // Serial.println("Orchestrator task started! Waiting 2seconds");
    // vTaskDelay(pdMS_TO_TICKS(2000));

    // test_small_communication();

    // appState.timeout = true;
}

void loop() {}
