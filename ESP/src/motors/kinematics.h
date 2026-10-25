// Cinématique du robot différentiel : conversions entre le mouvement du robot
// (mm, degrés) et celui des roues (mm, pas). Fonctions pures, testées sur PC.
//
// Conventions (repère table, cf. CLAUDE.md) : theta en degrés, sens trigonométrique.
// Pour tourner dans le sens + (vers la gauche), la roue droite avance et la gauche recule.
#pragma once

#include <cstdint>

namespace kinematics {

// --- Roue : millimètres <-> pas ---------------------------------------------------
float mmToSteps(float mm);
float stepsToMm(float steps);
// Nombre entier de pas le plus proche (consigne de déplacement d'une roue)
int32_t mmToStepsRounded(float mm);

// --- Rotation sur place : angle du robot <-> distance parcourue par chaque roue -------
// Chaque roue décrit un arc de rayon WHEEL_BASE_MM / 2 : la droite de +arc, la gauche de -arc.
float rotationDegToWheelMm(float deg);
float wheelMmToRotationDeg(float mm);

// --- Vitesses ------------------------------------------------------------------------
struct WheelSpeeds {
  float left_mm_s;
  float right_mm_s;
};

// Consigne robot (v en mm/s, omega en deg/s) -> vitesses des roues. Si une roue dépasse
// WHEEL_SPEED_MAX_MM_S, les deux sont réduites dans la même proportion : le robot
// garde la même trajectoire (même courbure), il va juste moins vite.
WheelSpeeds wheelSpeedsFromTwist(float v_mm_s, float omega_deg_s);

}  // namespace kinematics
