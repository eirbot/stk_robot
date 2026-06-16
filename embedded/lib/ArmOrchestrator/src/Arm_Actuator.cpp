#include "Arm_Actuator.hpp"

PCF8575 pcf(0x20, &Wire);
volatile bool IntDetected = false;

Arm_Actuator act1 = {ServoE, ServoF, Verin31EXT, Verin32EXT, asc1_stp, asc1_dirEXT, sns_asc_1EXT, true};
Arm_Actuator act2 = {ServoA, ServoB, Verin11EXT, Verin12EXT, asc2_stp, asc2_dirEXT, sns_asc_2EXT, false};
Arm_Actuator act3 = {ServoC, ServoD, Verin21EXT, Verin22EXT, asc3_stp, asc3_dirEXT, sns_asc_3EXT, false};
Arm_Actuator act4 = {ServoG, ServoH, Verin41EXT, Verin42EXT, asc4_stp, asc4_dirEXT, sns_asc_4EXT, false};

TaskHandle_t Handle_TaskActionneurs = NULL;

void ARDUINO_ISR_ATTR IntEXTfct() {
  IntDetected = true;
  BaseType_t xHigherPriorityTaskWoken = pdFALSE;
  vTaskNotifyGiveFromISR(Handle_TaskActionneurs, &xHigherPriorityTaskWoken);
  if (xHigherPriorityTaskWoken) {
    portYIELD_FROM_ISR();
  }
}
