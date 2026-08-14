#include "ActiveObjectCreator.hpp"
#include "AppState.hpp"
#include "Arm.hpp"
#include "ArmCreator.hpp"
#include "Arms.hpp"
#include "Arduino.h"
#include "Arm_Actuator.hpp"
#include "freertos/projdefs.h"

#define INCLUDE_vTaskDelay 1

// The setup that we do not care a lot in this test
void espSetup() {
  Wire.begin(21, 22);
  Wire.setClock(100000);
  // TODO: uncomment before match
  if (!get_static_pcf().begin()) {
    Serial.println("PCF8575 introuvable");
    while (1) {
      vTaskDelay(pdMS_TO_TICKS(1000));
    };
  }
}

void my_arm_task(void *pvParameters) {
  Arm_Actuator my_arm{ArmActuator1, get_static_pcf(),
                      armInterruptionStateRef(ArmActuator1)};
  Serial.println("Orchestrator task started! Waiting 3 seconds");
  vTaskDelay(pdMS_TO_TICKS(3000));
  Serial.println("Homming...");
  my_arm.homming();
  vTaskDelay(pdMS_TO_TICKS(3000));
  Serial.println("Elevate the arm...");
  my_arm.setElevatorPosition(100);
  vTaskDelay(pdMS_TO_TICKS(3000));
  Serial.println("Timeout! Every task will be stopped.");
  appState.timeout = true;
}

void setup() {
    Serial.begin(115200);
    Serial.println("Waiting 2 seconds...");
    attachSensorInterruptSignals();
    espSetup();
    FreeRTOSTaskStaticBuffers task_buffer = {armUxCreatorTaskStackBuffer +
                                                 (0 * ARM_TASK_STACK_SIZE),
                                             armXCreatorTaskTCBBuffer + 0};
    xTaskCreateStatic(my_arm_task, "arm1", ARM_TASK_STACK_SIZE, NULL,
                      ARM_TASK_PRIORITY, task_buffer.puxStackBuffer,
                      task_buffer.pxTaskBuffer);
    delay(2000); // service delay
    Serial.println("Start orchestrator task!");
}

void loop() {}
