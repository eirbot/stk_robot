// Tests sur PC de src/motors/protocol : pio test -e native
#include <unity.h>

#include <cstring>

#include "motors/protocol.h"

using Type = Command::Type;

void setUp() {}
void tearDown() {}

static void assertType(Type expected, const Command& c) {
  TEST_ASSERT_EQUAL_INT(static_cast<int>(expected), static_cast<int>(c.type));
}

static void assertInvalid(const char* line) {
  const Command c = protocol::parse(line);
  TEST_ASSERT_EQUAL_INT_MESSAGE(static_cast<int>(Type::Invalid), static_cast<int>(c.type), line);
  TEST_ASSERT_NOT_NULL_MESSAGE(c.error, line);
}

void test_goto() {
  const Command c = protocol::parse("G 7 1000.5 -500 90");
  assertType(Type::GoTo, c);
  TEST_ASSERT_EQUAL_UINT32(7, c.id);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 1000.5f, c.pose.x_mm);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, -500.0f, c.pose.y_mm);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 90.0f, c.pose.theta_deg);
}

void test_goto_cap_normalise() {
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, -90.0f, protocol::parse("G 1 0 0 270").pose.theta_deg);
}

void test_goto_facteur_vitesse() {
  TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1.0f, protocol::parse("G 1 0 0 0").speed_factor);  // absent : pleine vitesse
  const Command c = protocol::parse("G 2 100 0 0 0.3");
  assertType(Type::GoTo, c);
  TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.3f, c.speed_factor);
  TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1.0f, protocol::parse("G 3 0 0 0 1").speed_factor);
  assertInvalid("G 4 0 0 0 0");
  assertInvalid("G 5 0 0 0 1.5");
  assertInvalid("G 6 0 0 0 -0.5");
}

void test_goto_id_invalide() {
  assertInvalid("G -1 0 0 0");
  assertInvalid("G 3.5 0 0 0");
}

void test_vitesse() {
  const Command c = protocol::parse("V -250 45.5");
  assertType(Type::Velocity, c);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, -250.0f, c.v_mm_s);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 45.5f, c.omega_deg_s);
}

void test_set_pose() {
  const Command c = protocol::parse("S 200 -1200 0");
  assertType(Type::SetPose, c);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 200.0f, c.pose.x_mm);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, -1200.0f, c.pose.y_mm);
}

void test_lidar() {
  assertType(Type::Lidar, protocol::parse("L 2"));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(Obstacle::Front), static_cast<int>(protocol::parse("L 2").obstacle));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(Obstacle::Clear), static_cast<int>(protocol::parse("L 0").obstacle));
  assertInvalid("L 4");
  assertInvalid("L 1.5");
  assertInvalid("L");  // l'ancien « L » seul (bascule) n'existe plus
}

void test_arret_et_battement() {
  assertType(Type::Halt, protocol::parse("H"));
  assertType(Type::Heartbeat, protocol::parse("K"));
  assertInvalid("H 1");
}

void test_espaces_multiples() {
  const Command c = protocol::parse("  G  3   10  20   30  ");
  assertType(Type::GoTo, c);
  TEST_ASSERT_EQUAL_UINT32(3, c.id);
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, 30.0f, c.pose.theta_deg);
}

void test_mauvais_nombre_de_champs() {
  assertInvalid("G 1 2 3");      // ancien format sans id
  assertInvalid("G 1 2 3 4 0.5 6");
  assertInvalid("V 100");
  assertInvalid("S 1 2");
}

void test_nombres_illisibles() {
  assertInvalid("G 1 12abc 0 0");
  assertInvalid("V nan 0");
  assertInvalid("V inf 0");
  assertInvalid("S 1,5 2 3");    // virgule décimale
}

void test_commandes_inconnues() {
  assertInvalid("");
  assertInvalid("   ");
  assertInvalid("X 1");
  assertInvalid("GO 1 2 3 4");
  assertInvalid("g 1 2 3 4");
}

void test_trames_sortantes() {
  char buf[64];
  TEST_ASSERT_EQUAL_size_t(std::strlen("T 1000.50 -12.25 -90.00\n"),
                           protocol::formatPose(buf, sizeof buf, {1000.5f, -12.25f, -90.0f}));
  TEST_ASSERT_EQUAL_STRING("T 1000.50 -12.25 -90.00\n", buf);
  protocol::formatDone(buf, sizeof buf, 42);
  TEST_ASSERT_EQUAL_STRING("D 42\n", buf);
  protocol::formatAborted(buf, sizeof buf, 43);
  TEST_ASSERT_EQUAL_STRING("A 43\n", buf);
  protocol::formatWatchdog(buf, sizeof buf);
  TEST_ASSERT_EQUAL_STRING("W\n", buf);
  protocol::formatError(buf, sizeof buf, "commande inconnue");
  TEST_ASSERT_EQUAL_STRING("E commande inconnue\n", buf);
}

void test_tampon_trop_petit() {
  char buf[8];
  TEST_ASSERT_EQUAL_size_t(0, protocol::formatPose(buf, sizeof buf, {1000.0f, 1000.0f, 0.0f}));
}

using protocol::LineReader;
using LineResult = LineReader::Result;

// Pousse une chaîne ; renvoie le dernier résultat non None (ou None)
static LineResult pushAll(LineReader& r, const char* s) {
  LineResult last = LineResult::None;
  for (; *s; s++) {
    const LineResult res = r.push(*s);
    if (res != LineResult::None) last = res;
  }
  return last;
}

void test_lignes_lf_et_crlf() {
  LineReader r;
  TEST_ASSERT_EQUAL_INT(static_cast<int>(LineResult::Line), static_cast<int>(pushAll(r, "G 1 2 3 4\n")));
  TEST_ASSERT_EQUAL_STRING("G 1 2 3 4", r.line());
  TEST_ASSERT_EQUAL_INT(static_cast<int>(LineResult::Line), static_cast<int>(pushAll(r, "K\r\n")));
  TEST_ASSERT_EQUAL_STRING("K", r.line());
  TEST_ASSERT_EQUAL_INT(static_cast<int>(LineResult::None), static_cast<int>(pushAll(r, "\n\n\r")));
}

void test_ligne_en_plusieurs_morceaux() {
  LineReader r;
  TEST_ASSERT_EQUAL_INT(static_cast<int>(LineResult::None), static_cast<int>(pushAll(r, "V 10")));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(LineResult::Line), static_cast<int>(pushAll(r, "0 5\n")));
  TEST_ASSERT_EQUAL_STRING("V 100 5", r.line());
}

// Ligne trop longue : jetée en entier, la suivante est lue normalement
void test_ligne_trop_longue() {
  LineReader r;
  char longue[config::LINE_MAX_CHARS + 20];
  for (size_t i = 0; i < sizeof longue - 1; i++) longue[i] = 'X';
  longue[sizeof longue - 1] = '\0';
  TEST_ASSERT_EQUAL_INT(static_cast<int>(LineResult::None), static_cast<int>(pushAll(r, longue)));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(LineResult::Overflow), static_cast<int>(r.push('\n')));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(LineResult::Line), static_cast<int>(pushAll(r, "H\n")));
  TEST_ASSERT_EQUAL_STRING("H", r.line());
}

void test_watchdog() {
  protocol::RaspWatchdog w;
  TEST_ASSERT_FALSE(w.expired(100000));  // pas armé tant que rien n'est reçu
  w.onActivity(1000);
  TEST_ASSERT_FALSE(w.expired(1000 + config::RASP_TIMEOUT_MS));
  TEST_ASSERT_TRUE(w.expired(1001 + config::RASP_TIMEOUT_MS));
  TEST_ASSERT_FALSE(w.expired(5000));    // une seule fois
  w.onActivity(6000);                    // la Rasp revient : réarmé
  TEST_ASSERT_TRUE(w.expired(6001 + config::RASP_TIMEOUT_MS));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_goto);
  RUN_TEST(test_goto_cap_normalise);
  RUN_TEST(test_goto_facteur_vitesse);
  RUN_TEST(test_goto_id_invalide);
  RUN_TEST(test_vitesse);
  RUN_TEST(test_set_pose);
  RUN_TEST(test_lidar);
  RUN_TEST(test_arret_et_battement);
  RUN_TEST(test_espaces_multiples);
  RUN_TEST(test_mauvais_nombre_de_champs);
  RUN_TEST(test_nombres_illisibles);
  RUN_TEST(test_commandes_inconnues);
  RUN_TEST(test_trames_sortantes);
  RUN_TEST(test_tampon_trop_petit);
  RUN_TEST(test_lignes_lf_et_crlf);
  RUN_TEST(test_ligne_en_plusieurs_morceaux);
  RUN_TEST(test_ligne_trop_longue);
  RUN_TEST(test_watchdog);
  return UNITY_END();
}
