// Tests sur PC de src/motors/goto_planner : pio test -e native
#include <unity.h>

#include <cmath>

#include "motors/config.h"
#include "motors/goto_planner.h"

using Type = Segment::Type;

void setUp() {}
void tearDown() {}

// Exécute un segment sur une pose, avec une erreur relative (0 = parfait)
static Pose apply(Pose p, const Segment& s, float error = 0.0f) {
  const float k = 1.0f + error;
  if (s.type == Type::Rotate) {
    p.theta_deg = normalizeDeg(p.theta_deg + s.amount * k);
  } else if (s.type == Type::Drive) {
    const float t = p.theta_deg * config::PI_F / 180.0f;
    p.x_mm += s.amount * k * std::cos(t);
    p.y_mm += s.amount * k * std::sin(t);
  }
  return p;
}

// Déroule tout le GoTo ; renvoie la pose finale et le nombre de segments
static Pose run(GotoPlanner& g, Pose p, int* count = nullptr, float error = 0.0f) {
  int n = 0;
  for (Segment s = g.next(p); s.type != Type::None; s = g.next(p)) {
    p = apply(p, s, error);
    n++;
    TEST_ASSERT_TRUE_MESSAGE(n <= 3, "plus de 3 segments");
  }
  if (count) *count = n;
  return p;
}

static void assertSegment(Type type, float amount, const Segment& s, float tol = 0.01f) {
  TEST_ASSERT_EQUAL_INT(static_cast<int>(type), static_cast<int>(s.type));
  TEST_ASSERT_FLOAT_WITHIN(tol, amount, s.amount);
}

static void assertPose(const Pose& expected, const Pose& p, float tol_mm = 0.05f, float tol_deg = 0.01f) {
  TEST_ASSERT_FLOAT_WITHIN(tol_mm, expected.x_mm, p.x_mm);
  TEST_ASSERT_FLOAT_WITHIN(tol_mm, expected.y_mm, p.y_mm);
  TEST_ASSERT_FLOAT_WITHIN(tol_deg, 0.0f, angleDiffDeg(expected.theta_deg, p.theta_deg));
}

void test_cible_devant_une_seule_ligne_droite() {
  GotoPlanner g;
  Pose p{0, 0, 0};
  g.start({500, 0, 0});
  assertSegment(Type::Drive, 500.0f, g.next(p));
  p = apply(p, {Type::Drive, 500.0f});
  assertSegment(Type::None, 0.0f, g.next(p));
  TEST_ASSERT_TRUE(g.done());
}

// Cible derrière : pas de demi-tour, marche arrière
void test_cible_derriere_marche_arriere() {
  GotoPlanner g;
  g.start({0, 0, 0});
  assertSegment(Type::Drive, -400.0f, g.next({400, 0, 0}));
}

void test_cible_sur_le_cote() {
  GotoPlanner g;
  Pose p{1000, 0, 0};
  g.start({1000, 500, 0});
  assertSegment(Type::Rotate, 90.0f, g.next(p));
  p = apply(p, {Type::Rotate, 90.0f});
  assertSegment(Type::Drive, 500.0f, g.next(p));
  p = apply(p, {Type::Drive, 500.0f});
  assertSegment(Type::Rotate, -90.0f, g.next(p));
}

// Cible derrière à gauche (135°) : on tourne de -45° et on recule
void test_jamais_plus_de_90_degres_vers_la_trajectoire() {
  GotoPlanner g;
  g.start({-100, 100, 0});
  Segment s = g.next({0, 0, 0});
  assertSegment(Type::Rotate, -45.0f, s);
  Pose p = apply({0, 0, 0}, s);
  TEST_ASSERT_TRUE(g.next(p).amount < 0.0f);
}

void test_rotation_seule_sur_place() {
  GotoPlanner g;
  g.start({300, 200, 90});
  assertSegment(Type::Rotate, 90.0f, g.next({300, 200, 0}));
  assertSegment(Type::None, 0.0f, g.next({300, 200, 90}));
}

void test_deja_sur_la_cible() {
  GotoPlanner g;
  g.start({300, 200, 45});
  assertSegment(Type::None, 0.0f, g.next({300.5f, 200, 45.1f}));
}

// Passage par ±180° : le plus court chemin
void test_rotation_par_le_plus_court() {
  GotoPlanner g;
  g.start({0, 0, -170});
  assertSegment(Type::Rotate, 20.0f, g.next({0, 0, 170}));
}

// Arrondi : 45,9° restent 45,9° (l'ancien firmware tronquait à 45°)
void test_pas_de_troncature() {
  GotoPlanner g;
  g.start({0, 0, 45.9f});
  assertSegment(Type::Rotate, 45.9f, g.next({0, 0, 0}), 0.001f);
}

// Chaque segment repart de la pose mesurée : rotation 2 % trop courte, la ligne
// droite est raccourcie à la projection et la rotation finale rattrape le cap
void test_segments_calcules_depuis_la_pose_mesuree() {
  GotoPlanner g;
  g.start({1000, 1000, 0});
  Pose p{0, 0, 0};
  Segment rot = g.next(p);
  p = apply(p, rot, -0.02f);  // 44,1° au lieu de 45°
  Segment drive = g.next(p);
  TEST_ASSERT_FLOAT_WITHIN(0.5f, std::hypot(1000.0f, 1000.0f) * std::cos(0.9f * config::PI_F / 180.0f),
                           drive.amount);
  p = apply(p, drive);
  Segment fin = g.next(p);
  p = apply(p, fin);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, angleDiffDeg(0.0f, p.theta_deg));
}

// Erreur systématique de 1 % : le GoTo suivant repart de la vraie pose, rien ne s'accumule
void test_pas_d_accumulation_entre_goto() {
  const Pose cibles[] = {{1500, 500, 90}, {500, 500, 180}, {500, -500, -90}, {1000, 0, 0}};
  auto tours = [&](int n) {
    GotoPlanner g;
    Pose p{1000, 0, 0};
    for (int tour = 0; tour < n; tour++) {
      for (const Pose& c : cibles) {
        g.start(c);
        p = run(g, p, nullptr, 0.01f);
      }
    }
    return p;
  };
  // L'erreur finale ne dépend que du dernier GoTo : la même après 1 tour et après 10
  const Pose un = tours(1), dix = tours(10);
  assertPose(un, dix, 0.5f, 0.01f);
}

void test_goto_complet_exact() {
  GotoPlanner g;
  int n = 0;
  g.start({1200, -800, 30});
  Pose p = run(g, {200, -1200, 0}, &n);
  TEST_ASSERT_EQUAL_INT(3, n);
  assertPose({1200, -800, 30}, p);
}

// Obstacle au milieu de la ligne droite : on recalcule la distance restante
void test_reprise_apres_interruption() {
  GotoPlanner g;
  g.start({1000, 0, 0});
  Pose p{0, 0, 0};
  assertSegment(Type::Drive, 1000.0f, g.next(p));
  p = apply(p, {Type::Drive, 350.0f});  // arrêté à 350 mm
  g.restartSegment();
  assertSegment(Type::Drive, 650.0f, g.next(p));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_cible_devant_une_seule_ligne_droite);
  RUN_TEST(test_cible_derriere_marche_arriere);
  RUN_TEST(test_cible_sur_le_cote);
  RUN_TEST(test_jamais_plus_de_90_degres_vers_la_trajectoire);
  RUN_TEST(test_rotation_seule_sur_place);
  RUN_TEST(test_deja_sur_la_cible);
  RUN_TEST(test_rotation_par_le_plus_court);
  RUN_TEST(test_pas_de_troncature);
  RUN_TEST(test_segments_calcules_depuis_la_pose_mesuree);
  RUN_TEST(test_pas_d_accumulation_entre_goto);
  RUN_TEST(test_goto_complet_exact);
  RUN_TEST(test_reprise_apres_interruption);
  return UNITY_END();
}
