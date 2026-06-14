#include "GoToPosition.hpp"

#include <cmath>
#include "common.h"
#include "ClassMotors.hpp"

GoToPosition::GoToPosition(const float &x_i, const float &y_i,
                           const float &cangle_i, const float &x_f,
                           const float &y_f, const float &cangle_f) {
  x_initial = x_i;
  y_initial = y_i;
  cangle_initial = cangle_i;
  x_final = x_f;
  y_final = y_f;
  cangle_final = cangle_f;
}

void GoToPosition::CalculPolar() {
  float delta_x = x_final - x_initial;
  float delta_y = y_final - y_initial; // Système direct

  r = sqrt(delta_x * delta_x + delta_y * delta_y);
  float sigma = atan2(delta_y, delta_x) * RAD_TO_DEG;

  pangle = sigma - cangle_initial;
  pangleFin = cangle_final - sigma;

  if (pangle > 180)
    pangle -= 360;
  if (pangle < -180)
    pangle += 360;
  if (pangleFin > 180)
    pangleFin -= 360;
  if (pangleFin < -180)
    pangleFin += 360;

  if (abs(pangle) > 90) {
    pangle += 180.0;
    pangleFin += 180.0;
    r = -r;

    if (pangle > 180)
      pangle -= 360;
    if (pangle < -180)
      pangle += 360;
    if (pangleFin > 180)
      pangleFin -= 360;
    if (pangleFin < -180)
      pangleFin += 360;
  }
}

bool GoToPosition::Go(float x_f, float y_f, float cangle_f) {
  static int retryCount = 0;

  MotorTaskParams Params;
  x_final = x_f;
  y_final = y_f;
  cangle_final = cangle_f;

  CalculPolar();

  Params = {0, (int)(abs(pangle)), (pangle > 0) ? 0 : 1, (int)(SPEEDMAX * 0.7)};
  mot.EnvoyerDonnees(&Params);

  Params = {(int)r, 0, 0, SPEEDMAX};
  mot.EnvoyerDonnees(&Params);

  Params = {0, (int)(abs(pangleFin)), (pangleFin > 0) ? 0 : 1,
            (int)(SPEEDMAX * 0.7)};
  mot.EnvoyerDonnees(&Params);

  mot.WaitUntilDone();

  if (FLAG_STOP) {
    UpdateFinalPoseAfterStop(mot.GetDistanceDid());

    float x, y, angle;
    mot.GetPosition(x, y, angle);
    FLAG_STOP = false;

    return false; // Mouvement annulé

  } else {
    float x, y, angle;
    mot.GetPosition(x, y, angle);

    x_initial = x;
    y_initial = y;
    cangle_initial = cangle_final;

    return true; // Mouvement terminé
  }
}

void GoToPosition::AllerEtSet(float x_f, float y_f, float cangle_f, float x_set,
                              float y_set, float cangle_set) {
  Go(x_f, y_f, cangle_f);

  x_initial = x_set;
  y_initial = y_set;
  cangle_initial = cangle_set;

  // Mettre à jour la position finale après l'arrêt
  mot.SetPosition(x_initial, y_initial, cangle_initial * DEG_TO_RAD);
  mot.UpdateOdometry();
}

void GoToPosition::SetPos(float x, float y, float cangle) {
  x_initial = x;
  y_initial = y;
  cangle_initial = cangle;

  mot.SetPosition(x_initial, y_initial, cangle_initial * DEG_TO_RAD);
  mot.UpdateOdometry();
}

void GoToPosition::UpdateFinalPoseAfterStop(float distanceDid) {
  cangle_initial += pangle;

  float dx = distanceDid * cos(cangle_initial * DEG_TO_RAD);
  float dy = distanceDid * sin(cangle_initial * DEG_TO_RAD);

  x_initial += dx;
  y_initial += dy;
}
