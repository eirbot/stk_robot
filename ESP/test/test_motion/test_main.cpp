// Tests sur PC de src/motors/motion (machine d'états) : pio test -e native
#include <unity.h>

#include <cmath>
#include <cstdlib>
#include <vector>

#include "motors/config.h"
#include "motors/kinematics.h"
#include "motors/motion.h"

using State = MotionController::State;
using kinematics::mmToSteps;

// --- Fausses roues : vitesse constante (pas d'accélération), arrêt immédiat ---------------
struct FakeWheel {
  double pos = 0.0;
  double target = 0.0;
  double rate = 0.0;      // pas/s, > 0
  bool continuous = false;
  int dir = 0;            // continu : +1 / -1 / 0
  bool running() const { return continuous ? dir != 0 : std::fabs(target - pos) > 1e-9; }
  void advance(double dt_s) {
    if (continuous) {
      pos += dir * rate * dt_s;
    } else if (running()) {
      const double step = rate * dt_s, left = target - pos;
      pos = std::fabs(left) <= step ? target : pos + (left > 0 ? step : -step);
    }
  }
};

struct FakeWheels : WheelDriver {
  FakeWheel l, r;
  int moves = 0, runs = 0, stops = 0;
  int32_t last_left = 0, last_right = 0;
  float last_run_left = 0, last_run_right = 0;
  float last_speed = 0, last_accel = 0;

  int32_t leftSteps() const override { return static_cast<int32_t>(std::lround(l.pos)); }
  int32_t rightSteps() const override { return static_cast<int32_t>(std::lround(r.pos)); }
  bool move(int32_t left, int32_t right, float speed, float accel) override {
    moves++;
    last_speed = speed;
    last_accel = accel;
    last_left = left;
    last_right = right;
    const int32_t longest = std::max(std::abs(left), std::abs(right));
    setMove(l, left, speed * std::abs(left) / std::max(longest, 1));
    setMove(r, right, speed * std::abs(right) / std::max(longest, 1));
    return true;
  }
  void run(float left, float right, float) override {
    runs++;
    last_run_left = left;
    last_run_right = right;
    setRun(l, left);
    setRun(r, right);
  }
  void stop() override {
    stops++;
    for (FakeWheel* w : {&l, &r}) {
      w->continuous = false;
      w->dir = 0;
      w->target = w->pos = std::round(w->pos);
    }
  }
  bool isRunning() const override { return l.running() || r.running(); }

  static void setMove(FakeWheel& w, int32_t steps, float speed_mm_s) {
    w.continuous = false;
    w.target = std::round(w.pos) + steps;
    w.rate = mmToSteps(speed_mm_s);
  }
  static void setRun(FakeWheel& w, float speed_mm_s) {
    w.continuous = true;
    w.dir = speed_mm_s > 0.5f ? 1 : (speed_mm_s < -0.5f ? -1 : 0);
    w.rate = std::fabs(mmToSteps(speed_mm_s));
  }
};

struct Event {
  bool done;
  uint32_t id;
  Pose pose;
};

struct Recorder : MotionListener {
  std::vector<Event> events;
  void onGotoDone(uint32_t id, const Pose& p) override { events.push_back({true, id, p}); }
  void onGotoAborted(uint32_t id, const Pose& p) override { events.push_back({false, id, p}); }
};

// Banc de test : roues + contrôleur + horloge simulée
struct Bench {
  FakeWheels wheels;
  Recorder rec;
  MotionController mc{wheels, rec};
  uint32_t now = 0;

  explicit Bench(Pose start = {0, 0, 0}) { mc.begin(start); }

  void send(const Command& c) { mc.handle(c, now); }
  void tick() {
    now += config::MOTION_PERIOD_MS;
    wheels.l.advance(config::MOTION_PERIOD_MS / 1000.0);
    wheels.r.advance(config::MOTION_PERIOD_MS / 1000.0);
    mc.update(now);
  }
  void wait(uint32_t ms) {
    for (uint32_t t = 0; t < ms; t += config::MOTION_PERIOD_MS) tick();
  }
  // Avance jusqu'à la fin du GoTo (ou max_ms)
  void runUntilIdle(uint32_t max_ms = 20000) {
    for (uint32_t t = 0; t < max_ms && mc.state() != State::Idle; t += config::MOTION_PERIOD_MS) tick();
  }
};

static Command gotoCmd(uint32_t id, float x, float y, float theta) {
  Command c;
  c.type = Command::Type::GoTo;
  c.id = id;
  c.pose = {x, y, theta};
  return c;
}
static Command simple(Command::Type t) {
  Command c;
  c.type = t;
  return c;
}
static Command lidar(Obstacle o) {
  Command c;
  c.type = Command::Type::Lidar;
  c.obstacle = o;
  return c;
}
static Command velocity(float v, float omega) {
  Command c;
  c.type = Command::Type::Velocity;
  c.v_mm_s = v;
  c.omega_deg_s = omega;
  return c;
}

static void assertPose(float x, float y, float theta, const Pose& p) {
  TEST_ASSERT_FLOAT_WITHIN(0.5f, x, p.x_mm);
  TEST_ASSERT_FLOAT_WITHIN(0.5f, y, p.y_mm);
  TEST_ASSERT_FLOAT_WITHIN(0.1f, 0.0f, angleDiffDeg(theta, p.theta_deg));
}

static void assertEvent(bool done, uint32_t id, const Event& e) {
  TEST_ASSERT_EQUAL_MESSAGE(done, e.done, done ? "D attendu" : "A attendu");
  TEST_ASSERT_EQUAL_UINT32(id, e.id);
}

void setUp() {}
void tearDown() {}

// --- GoTo ---------------------------------------------------------------------------------

void test_goto_complet() {
  Bench b({200, -1200, 0});
  b.send(gotoCmd(1, 1200, -800, 30));
  b.runUntilIdle();
  TEST_ASSERT_EQUAL_size_t(1, b.rec.events.size());
  assertEvent(true, 1, b.rec.events[0]);
  assertPose(1200, -800, 30, b.mc.pose());
  assertPose(1200, -800, 30, b.rec.events[0].pose);  // pose jointe au D = pose finale
  TEST_ASSERT_EQUAL_INT(3, b.wheels.moves);
}

// Rotation sens + : roue droite en avant, gauche en arrière
void test_rotation_sens_des_roues() {
  Bench b;
  b.send(gotoCmd(1, 0, 0, 90));
  b.tick();
  TEST_ASSERT_TRUE(b.wheels.last_right > 0);
  TEST_ASSERT_EQUAL_INT32(-b.wheels.last_right, b.wheels.last_left);
}

// Facteur de vitesse du G : vitesse et accélération des segments réduites d'autant
void test_goto_facteur_vitesse() {
  Bench b;
  b.send(gotoCmd(1, 500, 0, 0));
  b.tick();
  const float pleine_v = b.wheels.last_speed, pleine_a = b.wheels.last_accel;
  b.runUntilIdle();
  Command lent = gotoCmd(2, 1000, 0, 0);
  lent.speed_factor = 0.3f;
  b.send(lent);
  b.tick();
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.3f * pleine_v, b.wheels.last_speed);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.3f * pleine_a, b.wheels.last_accel);
  b.runUntilIdle();
  assertPose(1000, 0, 0, b.mc.pose());
}

void test_goto_deja_sur_place() {
  Bench b({500, 500, 45});
  b.send(gotoCmd(9, 500, 500, 45));
  b.tick();
  TEST_ASSERT_EQUAL_size_t(1, b.rec.events.size());
  assertEvent(true, 9, b.rec.events[0]);
  TEST_ASSERT_EQUAL_INT(0, b.wheels.moves);
}

void test_nouveau_goto_remplace_le_precedent() {
  Bench b;
  b.send(gotoCmd(1, 1000, 0, 0));
  b.wait(300);
  b.send(gotoCmd(2, 0, 500, 90));
  TEST_ASSERT_EQUAL_size_t(1, b.rec.events.size());
  assertEvent(false, 1, b.rec.events[0]);
  b.runUntilIdle();
  TEST_ASSERT_EQUAL_size_t(2, b.rec.events.size());
  assertEvent(true, 2, b.rec.events[1]);
  assertPose(0, 500, 90, b.mc.pose());
}

void test_halt_annule_le_goto() {
  Bench b;
  b.send(gotoCmd(5, 1000, 0, 0));
  b.wait(300);
  b.send(simple(Command::Type::Halt));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(State::Idle), static_cast<int>(b.mc.state()));
  TEST_ASSERT_FALSE(b.wheels.isRunning());
  b.wait(3000);
  TEST_ASSERT_EQUAL_size_t(1, b.rec.events.size());
  assertEvent(false, 5, b.rec.events[0]);
}

// --- Obstacles -------------------------------------------------------------------------------

void test_obstacle_devant_pause_puis_reprise() {
  Bench b;
  b.send(gotoCmd(1, 1000, 0, 0));
  b.wait(300);
  b.send(lidar(Obstacle::Front));
  b.tick();
  TEST_ASSERT_EQUAL_INT(static_cast<int>(State::GotoPaused), static_cast<int>(b.mc.state()));
  const float x_pause = b.mc.pose().x_mm;
  b.wait(1000);
  TEST_ASSERT_FLOAT_WITHIN(0.1f, x_pause, b.mc.pose().x_mm);  // immobile pendant la pause
  b.send(lidar(Obstacle::Clear));
  b.runUntilIdle();
  TEST_ASSERT_EQUAL_size_t(1, b.rec.events.size());
  assertEvent(true, 1, b.rec.events[0]);
  assertPose(1000, 0, 0, b.mc.pose());
}

void test_obstacle_persistant_abandon() {
  Bench b;
  b.send(gotoCmd(3, 1000, 0, 0));
  b.wait(300);
  b.send(lidar(Obstacle::Front));
  b.wait(config::OBSTACLE_ABORT_MS - 100);
  TEST_ASSERT_EQUAL_size_t(0, b.rec.events.size());
  b.wait(200);
  TEST_ASSERT_EQUAL_size_t(1, b.rec.events.size());
  assertEvent(false, 3, b.rec.events[0]);
}

// Obstacle devant : la marche arrière reste permise ; derrière : elle est bloquée
void test_obstacle_selon_le_sens() {
  Bench b({1000, 0, 0});
  b.send(lidar(Obstacle::Front));
  b.send(gotoCmd(1, 500, 0, 0));  // cible derrière : marche arrière
  b.runUntilIdle();
  assertEvent(true, 1, b.rec.events.at(0));

  b.send(lidar(Obstacle::Back));
  b.send(gotoCmd(2, 0, 0, 0));
  b.wait(500);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(State::GotoPaused), static_cast<int>(b.mc.state()));
}

// Obstacle tout près : les rotations aussi sont bloquées
void test_obstacle_stop_bloque_les_rotations() {
  Bench b;
  b.send(lidar(Obstacle::Stop));
  b.send(gotoCmd(1, 0, 0, 90));
  b.wait(500);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(State::GotoPaused), static_cast<int>(b.mc.state()));
  TEST_ASSERT_EQUAL_INT(0, b.wheels.moves);
  b.send(lidar(Obstacle::Clear));
  b.runUntilIdle();
  assertPose(0, 0, 90, b.mc.pose());
}

// --- Vitesse (joystick) ------------------------------------------------------------------------

void test_vitesse_puis_arret_sans_consigne() {
  Bench b;
  b.send(velocity(200, 0));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 200.0f, b.wheels.last_run_left);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 200.0f, b.wheels.last_run_right);
  b.wait(config::VELOCITY_TIMEOUT_MS - 50);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(State::Velocity), static_cast<int>(b.mc.state()));
  b.wait(100);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(State::Idle), static_cast<int>(b.mc.state()));
  TEST_ASSERT_FALSE(b.wheels.isRunning());
  // ~0,5 s à 200 mm/s
  TEST_ASSERT_FLOAT_WITHIN(15.0f, 100.0f, b.mc.pose().x_mm);
}

void test_vitesse_annule_le_goto() {
  Bench b;
  b.send(gotoCmd(4, 1000, 0, 0));
  b.wait(200);
  b.send(velocity(0, 30));
  assertEvent(false, 4, b.rec.events.at(0));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(State::Velocity), static_cast<int>(b.mc.state()));
}

// Obstacle devant : on ne peut plus avancer, mais on peut tourner
void test_vitesse_avec_obstacle_devant() {
  Bench b;
  b.send(lidar(Obstacle::Front));
  b.send(velocity(300, 45));
  const float arc = kinematics::rotationDegToWheelMm(45);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, -arc, b.wheels.last_run_left);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, arc, b.wheels.last_run_right);
  b.send(lidar(Obstacle::Clear));  // voie libre : la consigne complète repart
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 300 - arc, b.wheels.last_run_left);
}

// --- Pose connue ------------------------------------------------------------------------------

void test_set_pose() {
  Bench b;
  Command s;
  s.type = Command::Type::SetPose;
  s.pose = {200, -1200, 90};
  b.send(s);
  assertPose(200, -1200, 90, b.mc.pose());
  b.send(gotoCmd(1, 200, -1000, 90));
  b.runUntilIdle();
  assertPose(200, -1000, 90, b.mc.pose());
  TEST_ASSERT_EQUAL_INT(1, b.wheels.moves);  // déjà dans l'axe : une seule ligne droite
}

void test_set_pose_annule_le_goto() {
  Bench b;
  b.send(gotoCmd(6, 1000, 0, 0));
  b.wait(200);
  Command s;
  s.type = Command::Type::SetPose;
  s.pose = {0, 0, 0};
  b.send(s);
  assertEvent(false, 6, b.rec.events.at(0));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_goto_complet);
  RUN_TEST(test_rotation_sens_des_roues);
  RUN_TEST(test_goto_facteur_vitesse);
  RUN_TEST(test_goto_deja_sur_place);
  RUN_TEST(test_nouveau_goto_remplace_le_precedent);
  RUN_TEST(test_halt_annule_le_goto);
  RUN_TEST(test_obstacle_devant_pause_puis_reprise);
  RUN_TEST(test_obstacle_persistant_abandon);
  RUN_TEST(test_obstacle_selon_le_sens);
  RUN_TEST(test_obstacle_stop_bloque_les_rotations);
  RUN_TEST(test_vitesse_puis_arret_sans_consigne);
  RUN_TEST(test_vitesse_annule_le_goto);
  RUN_TEST(test_vitesse_avec_obstacle_devant);
  RUN_TEST(test_set_pose);
  RUN_TEST(test_set_pose_annule_le_goto);
  return UNITY_END();
}
