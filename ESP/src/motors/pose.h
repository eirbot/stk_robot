// Pose du robot et calculs d'angles, partagés par l'odométrie, le GoTo et le protocole.
// Repère table (cf. CLAUDE.md) : x, y en mm ; theta en degrés, sens trigonométrique,
// normalisé dans ]-180, 180].
#pragma once

#include <cmath>

struct Pose {
  float x_mm = 0.0f;
  float y_mm = 0.0f;
  float theta_deg = 0.0f;
};

// Angle ramené dans ]-180, 180]
inline float normalizeDeg(float deg) {
  float d = std::fmod(deg, 360.0f);
  if (d <= -180.0f) d += 360.0f;
  else if (d > 180.0f) d -= 360.0f;
  return d;
}

// Plus petit angle pour aller de `from` à `to` (to - from ramené dans ]-180, 180])
inline float angleDiffDeg(float to, float from) { return normalizeDeg(to - from); }
