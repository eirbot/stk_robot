#include "Arm_Actuator.hpp"

static PCF8575 static_pcf{0x20, &Wire};
volatile bool IntDetected = false;

PCF8575& get_static_pcf() {
  return static_pcf;  
}

ArmVars per_arm_vars(ArmActuatorId arm_id) {
  switch (arm_id) {
  case ArmActuator1:
    return ArmVars{ServoE,      ServoF,       Verin31EXT, Verin32EXT, asc1_stp,
                   asc1_dirEXT, sns_asc_1EXT, true,       40};
    break;
  case ArmActuator2:
    return ArmVars{ServoA,      ServoB,       Verin11EXT, Verin12EXT, asc2_stp,
                   asc2_dirEXT, sns_asc_2EXT, false,      60};
    break;
  case ArmActuator3:
    return ArmVars{ServoC,      ServoD,       Verin21EXT, Verin22EXT, asc3_stp,
                   asc3_dirEXT, sns_asc_3EXT, false,      120};
    break;
  case ArmActuator4:
    return ArmVars{ServoG,      ServoH,       Verin41EXT, Verin42EXT, asc4_stp,
                   asc4_dirEXT, sns_asc_4EXT, false,      140};
    break;
  // WARN: this case should not happen
  default:
    return ArmVars{ServoE,      ServoF,       Verin31EXT, Verin32EXT, asc1_stp,
                   asc1_dirEXT, sns_asc_1EXT, true,       40};
    break;
  }
}

TaskHandle_t Handle_TaskActionneurs = NULL;

void ARDUINO_ISR_ATTR IntEXTfct() {
  // IntDetected = true;
  // BaseType_t xHigherPriorityTaskWoken = pdFALSE;
  // TODO: send interrupt notification to each freertos task
  // vTaskNotifyGiveFromISR(Handle_TaskActionneurs, &xHigherPriorityTaskWoken);
  // if (xHigherPriorityTaskWoken) {
  //   portYIELD_FROM_ISR();
  // }
}
