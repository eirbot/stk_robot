// Tests sur PC de src/motors/kinematics : pio test -e native
#include <unity.h>

#include "motors/config.h"
#include "motors/kinematics.h"

using namespace kinematics;

void setUp() {}
void tearDown() {}

// Un tour de roue = STEPS_PER_REV pas = pi x diamètre
void test_un_tour_de_roue() {
  const float circonference = config::PI_F * config::WHEEL_DIAMETER_MM;
  TEST_ASSERT_FLOAT_WITHIN(0.01f, config::STEPS_PER_REV, mmToSteps(circonference));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, circonference, stepsToMm(config::STEPS_PER_REV));
}

void test_aller_retour_mm_pas() {
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 1234.5f, stepsToMm(mmToSteps(1234.5f)));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -80.0f, stepsToMm(mmToSteps(-80.0f)));
}

void test_arrondi_au_pas_le_plus_proche() {
  // 1 m = 14147,5 pas avec les valeurs actuelles : arrondi, pas tronqué
  const float exact = mmToSteps(1000.0f);
  TEST_ASSERT_INT32_WITHIN(1, static_cast<int32_t>(exact + 0.5f), mmToStepsRounded(1000.0f));
  TEST_ASSERT_EQUAL_INT32(-mmToStepsRounded(1000.0f), mmToStepsRounded(-1000.0f));
  TEST_ASSERT_EQUAL_INT32(0, mmToStepsRounded(0.0f));
}

// Un tour complet sur place : chaque roue parcourt pi x entraxe
void test_tour_sur_place() {
  TEST_ASSERT_FLOAT_WITHIN(0.01f, config::PI_F * config::WHEEL_BASE_MM, rotationDegToWheelMm(360.0f));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 90.0f, wheelMmToRotationDeg(rotationDegToWheelMm(90.0f)));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -45.0f, wheelMmToRotationDeg(rotationDegToWheelMm(-45.0f)));
}

void test_ligne_droite() {
  WheelSpeeds s = wheelSpeedsFromTwist(300.0f, 0.0f);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 300.0f, s.left_mm_s);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 300.0f, s.right_mm_s);
}

// Rotation dans le sens + : roue droite en avant, gauche en arrière, même vitesse
void test_rotation_sens_trigo() {
  WheelSpeeds s = wheelSpeedsFromTwist(0.0f, 90.0f);
  TEST_ASSERT_TRUE(s.right_mm_s > 0.0f);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -s.right_mm_s, s.left_mm_s);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, rotationDegToWheelMm(90.0f), s.right_mm_s);
}

// Saturation : les deux roues réduites dans la même proportion (même courbure)
void test_saturation_garde_la_courbure() {
  const float v = 1000.0f, omega = 180.0f;
  WheelSpeeds brut{v - rotationDegToWheelMm(omega), v + rotationDegToWheelMm(omega)};
  WheelSpeeds s = wheelSpeedsFromTwist(v, omega);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, config::WHEEL_SPEED_MAX_MM_S, s.right_mm_s);
  TEST_ASSERT_FLOAT_WITHIN(0.0001f, brut.left_mm_s / brut.right_mm_s, s.left_mm_s / s.right_mm_s);
}

void test_saturation_marche_arriere() {
  WheelSpeeds s = wheelSpeedsFromTwist(-5000.0f, 0.0f);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, -config::WHEEL_SPEED_MAX_MM_S, s.left_mm_s);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, -config::WHEEL_SPEED_MAX_MM_S, s.right_mm_s);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_un_tour_de_roue);
  RUN_TEST(test_aller_retour_mm_pas);
  RUN_TEST(test_arrondi_au_pas_le_plus_proche);
  RUN_TEST(test_tour_sur_place);
  RUN_TEST(test_ligne_droite);
  RUN_TEST(test_rotation_sens_trigo);
  RUN_TEST(test_saturation_garde_la_courbure);
  RUN_TEST(test_saturation_marche_arriere);
  return UNITY_END();
}
