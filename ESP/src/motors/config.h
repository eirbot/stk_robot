// Constantes du firmware moteurs : tout ce qu'on règle se trouve ici.
//
// Règle : l'unité est dans le nom (MM, DEG, MS, HZ...). Pas de #define, des
// constexpr typés : le compilateur vérifie les types et le débogueur voit les noms.
// Ce fichier ne dépend ni d'Arduino ni d'ESP-IDF : les tests sur PC l'incluent aussi.
#pragma once

#include <cstdint>

namespace config {

// --- Mécanique ---------------------------------------------------------------
constexpr float WHEEL_DIAMETER_MM = 72.0f;
// Distance entre les points de contact des deux roues. Mesurée le 2026-10-19 :
// 10 tours demandés -> 10 tours + 60° avec 345 mm, d'où 345 x 3600 / 3660.
constexpr float WHEEL_BASE_MM = 339.3f;
// Drivers MKS SERVO42D en boucle fermée (mode CR_CLOSE ; CR_vFOC donne des à-coups).
// Le micro-pas doit être le MÊME que celui réglé dans le menu des drivers (MStep).
// En boucle fermée il ne fixe que la finesse des consignes : à 16, un pas = 0,07 mm
// de roue, bien plus fin que ce que le robot sait faire. Monter (256) n'apporte rien
// et multiplie la fréquence des pas (cf. MAX_STEP_RATE_HZ plus bas).
constexpr int32_t MICROSTEPS = 16;
constexpr int32_t MOTOR_FULL_STEPS_PER_REV = 200;  // moteur 1,8°, pas de réducteur
constexpr int32_t STEPS_PER_REV = MOTOR_FULL_STEPS_PER_REV * MICROSTEPS;

// --- Câblage (numéros de GPIO) -----------------------------------------------
// Gauche / droite au sens du repère table (direct, theta trigonométrique) : la roue
// DROITE est celle qui, en avançant seule, fait augmenter theta. L'ancien code
// appelait « gauche » le moteur des broches 16/4 et inversait la formule
// d'odométrie (« Inversion L/R ») ; ici les noms sont justes et la formule standard.
// Sur les deux moteurs, pas > 0 = la roue fait avancer le robot.
constexpr uint8_t PIN_STEP_RIGHT = 16;
constexpr uint8_t PIN_DIR_RIGHT = 4;
constexpr uint8_t PIN_STEP_LEFT = 19;
constexpr uint8_t PIN_DIR_LEFT = 18;
// Sens : true = la broche DIR à l'état haut fait avancer la roue (comme l'ancien
// firmware). Une roue qui part à l'envers se corrige ici, sans toucher aux drivers.
constexpr bool DIR_HIGH_FORWARD_RIGHT = true;
constexpr bool DIR_HIGH_FORWARD_LEFT = true;

// --- GoTo : vitesses et accélérations (profil trapèze de FastAccelStepper) ----
// Valeurs reprises de l'ancien firmware, exprimées dans leurs vraies unités.
constexpr float DRIVE_SPEED_MM_S = 1000.0f;     // ligne droite
constexpr float DRIVE_ACCEL_MM_S2 = 750.0f;
constexpr float ROTATE_SPEED_DEG_S = 236.0f;    // rotation sur place (700 mm/s par roue)
constexpr float ROTATE_ACCEL_DEG_S2 = 177.0f;

// Décélération des arrêts (H, obstacle, fin de consigne de vitesse). Plus fort que
// l'accélération pour s'arrêter court, sans faire patiner les roues : à régler sur la table.
constexpr float STOP_DECEL_MM_S2 = 1000.0f;

// En dessous de ces valeurs, un segment du GoTo est sauté (déjà sur place)
constexpr float MIN_DRIVE_MM = 1.0f;
constexpr float MIN_ROTATE_DEG = 0.2f;

// --- Joystick (consigne de vitesse « V ») -------------------------------------
constexpr float VELOCITY_ACCEL_MM_S2 = 1400.0f;  // par roue
constexpr float WHEEL_SPEED_MAX_MM_S = 1130.0f;  // saturation par roue (16 000 pas/s)
constexpr uint32_t VELOCITY_TIMEOUT_MS = 500;    // sans nouvelle consigne : arrêt

// Fréquence de pas à ne pas dépasser. Marge large sous les limites de FastAccelStepper
// sur ESP32 et de l'entrée STEP des SERVO42D (valeurs exactes à vérifier dans leurs docs).
constexpr float MAX_STEP_RATE_HZ = 100000.0f;
constexpr float PI_F = 3.14159265f;
static_assert(WHEEL_SPEED_MAX_MM_S / (PI_F * WHEEL_DIAMETER_MM) * STEPS_PER_REV < MAX_STEP_RATE_HZ,
              "Vitesse max trop haute pour ce micro-pas : baisser MICROSTEPS ou WHEEL_SPEED_MAX_MM_S");
static_assert(DRIVE_SPEED_MM_S <= WHEEL_SPEED_MAX_MM_S, "DRIVE_SPEED_MM_S au-delà de la vitesse max des roues");

// --- Pose au démarrage (la Rasp envoie « S » avant le match) ---------------------
constexpr float INITIAL_X_MM = 200.0f;      // zone de départ bleue, comme l'ancien firmware
constexpr float INITIAL_Y_MM = -1200.0f;
constexpr float INITIAL_THETA_DEG = 0.0f;

// --- Évitement (état LiDAR « L » envoyé par la Rasp) ---------------------------
// Obstacle qui ne part pas pendant ce délai : le GoTo est abandonné (« A »)
constexpr uint32_t OBSTACLE_ABORT_MS = 5000;

// --- Liaison avec la Rasp ---------------------------------------------------------
constexpr uint32_t UART_BAUDRATE = 115200;
constexpr int UART_RX_BUFFER_BYTES = 1024;
// Tampon d'envoi : une écriture ne bloque pas la tâche de mouvement (D / A)
constexpr int UART_TX_BUFFER_BYTES = 1024;
// Lecture série : la tâche se réveille au moins à cette période pour vérifier le watchdog
constexpr uint32_t UART_READ_TIMEOUT_MS = 10;
constexpr uint32_t LINE_MAX_CHARS = 64;              // une commande = une ligne
// Rasp muette pendant ce délai (plantée, câble coupé) : tout s'arrête (« W »)
constexpr uint32_t RASP_TIMEOUT_MS = 300;
constexpr uint32_t TELEMETRY_PERIOD_MS = 100;    // trame « T x y theta » à 10 Hz

// --- Boucle de mouvement -------------------------------------------------------------
// Odométrie, fin de segment et obstacles vérifiés toutes les MOTION_PERIOD_MS (200 Hz) ;
// une commande de la Rasp réveille la tâche immédiatement, sans attendre ce délai.
constexpr uint32_t MOTION_PERIOD_MS = 5;
// Roues arrêtées sans avoir atteint la cible depuis ce délai : segment considéré fini
// (le segment suivant repart de la pose mesurée, donc rien n'est perdu)
constexpr uint32_t SEGMENT_SETTLE_MS = 100;

// --- Tâches FreeRTOS (cœur 1 : celui d'Arduino ; le cœur 0 garde le Wi-Fi/BT) -----
constexpr int CORE_APP = 1;
constexpr uint32_t MOTION_TASK_PRIORITY = 5;     // la plus haute : réagit en premier
constexpr uint32_t LINK_RX_TASK_PRIORITY = 4;
constexpr uint32_t TELEMETRY_TASK_PRIORITY = 3;
constexpr uint32_t MOTION_TASK_STACK = 4096;
constexpr uint32_t LINK_RX_TASK_STACK = 4096;
constexpr uint32_t TELEMETRY_TASK_STACK = 3072;
constexpr int COMMAND_QUEUE_LENGTH = 8;

}  // namespace config
