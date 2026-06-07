#include "Actionneurs.hpp"

PCF8575 pcf(0x20, &Wire);
volatile bool IntDetected = false;

Actionneur act1 = {ServoE, ServoF, Verin31EXT, Verin32EXT, asc1_stp, asc1_dirEXT, sns_asc_1EXT, true};
Actionneur act2 = {ServoA, ServoB, Verin11EXT, Verin12EXT, asc2_stp, asc2_dirEXT, sns_asc_2EXT, false};
Actionneur act3 = {ServoC, ServoD, Verin21EXT, Verin22EXT, asc3_stp, asc3_dirEXT, sns_asc_3EXT, false};
Actionneur act4 = {ServoG, ServoH, Verin41EXT, Verin42EXT, asc4_stp, asc4_dirEXT, sns_asc_4EXT, false};

void ARDUINO_ISR_ATTR IntEXTfct() {
  IntDetected = true;
}