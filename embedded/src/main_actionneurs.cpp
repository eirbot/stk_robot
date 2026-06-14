#include "ActuatorThread.hpp"
#include "Arm_ActuatorVTask.hpp"
#include "Communicator.hpp"

#define INCLUDE_vTaskDelay 1

void setup() {

  Arm_ActuatorManager arm_actuator_manager{};

  static ComWithRasp comRasp{std::vector<ActuatorManager *>{&arm_actuator_manager}};
  Serial.begin(115200);

  Wire.begin(21, 22);
  Wire.setClock(100000);

  // TODO: uncomment before match
  if (!pcf.begin()) {
    Serial.println("PCF8575 introuvable");
    while (1)
      ;
  }

  pinMode(IntEXT, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(IntEXT), IntEXTfct, FALLING);

  comRasp.StartCom();
}

void loop() {}
