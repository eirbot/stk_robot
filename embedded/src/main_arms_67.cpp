#include "AppState.hpp"
#include "Arduino.h"
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

    Arm_Actuator my_arm{ArmActuator1, get_static_pcf()};

    Serial.println("Orchestrator task started! Waiting 3 seconds");

    vTaskDelay(pdMS_TO_TICKS(3000));

    my_arm.homming();

    vTaskDelay(pdMS_TO_TICKS(3000));

    my_arm.setElevatorPosition(50);

    Serial.println("Timeout! Every task will be stopped.");
    appState.timeout = true;
}

void loop() {}
