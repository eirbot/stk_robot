// Tests sur PC de src/motors/odometry : pio test -e native
#include <unity.h>

#include <cmath>

#include "motors/config.h"
#include "motors/kinematics.h"
#include "motors/odometry.h"

using kinematics::mmToStepsRounded;
using kinematics::rotationDegToWheelMm;

// Robot simulé : compteurs de pas des deux roues + odométrie mise à jour par petits pas,
// comme la tâche de mouvement le fera à 50 Hz
struct Robot {
  int32_t left = 0, right = 0;
  Odometry odo;

  void start(Pose p) { odo.reset(p, left, right); }

  // Déplace chaque roue de (d_left, d_right) pas, découpés en `slices` mises à jour
  void move(int32_t d_left, int32_t d_right, int slices = 50) {
    const int32_t l0 = left, r0 = right;
    for (int i = 1; i <= slices; i++) {
      left = l0 + static_cast<int32_t>(std::lround(static_cast<double>(d_left) * i / slices));
      right = r0 + static_cast<int32_t>(std::lround(static_cast<double>(d_right) * i / slices));
      odo.update(left, right);
    }
  }
  void drive(float mm) { move(mmToStepsRounded(mm), mmToStepsRounded(mm)); }
  void rotate(float deg) {
    const int32_t s = mmToStepsRounded(rotationDegToWheelMm(deg));
    move(-s, s);
  }
};

void setUp() {}
void tearDown() {}

static void assertPose(float x, float y, float theta, const Pose& p, float tol_mm = 0.1f, float tol_deg = 0.01f) {
  TEST_ASSERT_FLOAT_WITHIN(tol_mm, x, p.x_mm);
  TEST_ASSERT_FLOAT_WITHIN(tol_mm, y, p.y_mm);
  TEST_ASSERT_FLOAT_WITHIN(tol_deg, 0.0f, angleDiffDeg(theta, p.theta_deg));
}

void test_normalisation_angles() {
  TEST_ASSERT_FLOAT_WITHIN(1e-4f, 180.0f, normalizeDeg(-180.0f));
  TEST_ASSERT_FLOAT_WITHIN(1e-4f, 180.0f, normalizeDeg(540.0f));
  TEST_ASSERT_FLOAT_WITHIN(1e-4f, -90.0f, normalizeDeg(270.0f));
  TEST_ASSERT_FLOAT_WITHIN(1e-4f, -20.0f, angleDiffDeg(170.0f, -170.0f));
}

void test_reset_donne_la_pose() {
  Robot r;
  r.left = 1234;
  r.right = -99;
  r.start({200.0f, -1200.0f, 370.0f});
  assertPose(200.0f, -1200.0f, 10.0f, r.odo.pose());
}

void test_ligne_droite_vers_x() {
  Robot r;
  r.start({0.0f, 0.0f, 0.0f});
  r.drive(1000.0f);
  assertPose(1000.0f, 0.0f, 0.0f, r.odo.pose());
}

void test_marche_arriere() {
  Robot r;
  r.start({1000.0f, 0.0f, 90.0f});
  r.drive(-500.0f);
  assertPose(1000.0f, -500.0f, 90.0f, r.odo.pose());
}

// Rotation sens + : roue droite en avant ; la position ne bouge pas
void test_rotation_sur_place() {
  Robot r;
  r.start({500.0f, 300.0f, 0.0f});
  r.rotate(90.0f);
  assertPose(500.0f, 300.0f, 90.0f, r.odo.pose(), 0.1f, 0.02f);
}

void test_rotation_puis_avance_vers_y() {
  Robot r;
  r.start({0.0f, 0.0f, 0.0f});
  r.rotate(90.0f);
  r.drive(500.0f);
  assertPose(0.0f, 500.0f, 90.0f, r.odo.pose(), 0.5f, 0.02f);
}

// Le cap vient directement des compteurs : 10 tours aller puis retour, aucune dérive
void test_dix_tours_sans_derive() {
  Robot r;
  r.start({0.0f, 0.0f, 30.0f});
  for (int i = 0; i < 40; i++) r.rotate(90.0f);
  for (int i = 0; i < 40; i++) r.rotate(-90.0f);
  assertPose(0.0f, 0.0f, 30.0f, r.odo.pose(), 0.01f, 0.0001f);
}

void test_carre_revient_au_depart() {
  Robot r;
  r.start({1000.0f, 0.0f, 0.0f});
  for (int i = 0; i < 4; i++) {
    r.drive(500.0f);
    r.rotate(90.0f);
  }
  assertPose(1000.0f, 0.0f, 0.0f, r.odo.pose(), 1.0f, 0.05f);
}

// Une seule roue (droite) avance : arc de cercle autour de la roue gauche, rayon = entraxe / 2
// pour le centre. Après un quart de tour, le centre est à (R, R) du point de départ
void test_arc_une_seule_roue() {
  Robot r;
  r.start({0.0f, 0.0f, 0.0f});
  const float R = config::WHEEL_BASE_MM / 2.0f;
  // Quart de tour du robot : la roue droite parcourt un quart de cercle de rayon entraxe
  r.move(0, mmToStepsRounded(config::PI_F * config::WHEEL_BASE_MM / 2.0f), 200);
  assertPose(R, R, 90.0f, r.odo.pose(), 0.5f, 0.02f);
}

void test_pas_de_mouvement_pas_de_changement() {
  Robot r;
  r.start({10.0f, 20.0f, 30.0f});
  r.odo.update(r.left, r.right);
  assertPose(10.0f, 20.0f, 30.0f, r.odo.pose(), 1e-4f, 1e-4f);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_normalisation_angles);
  RUN_TEST(test_reset_donne_la_pose);
  RUN_TEST(test_ligne_droite_vers_x);
  RUN_TEST(test_marche_arriere);
  RUN_TEST(test_rotation_sur_place);
  RUN_TEST(test_rotation_puis_avance_vers_y);
  RUN_TEST(test_dix_tours_sans_derive);
  RUN_TEST(test_carre_revient_au_depart);
  RUN_TEST(test_arc_une_seule_roue);
  RUN_TEST(test_pas_de_mouvement_pas_de_changement);
  return UNITY_END();
}
