// Contrôleur de mouvement : SEUL code qui commande les roues. Machine d'états pure
// (pas de FreeRTOS, temps passé en paramètre), testée sur PC avec de fausses roues.
// motion_task.cpp la fait tourner dans une tâche FreeRTOS.
//
// États
//   Idle        rien en cours
//   Goto        un segment du GoTo s'exécute, ou le suivant va être lancé
//   GotoPaused  GoTo suspendu par un obstacle ; reprend quand la voie est libre,
//               abandonné (« A ») si l'obstacle reste OBSTACLE_ABORT_MS
//   Velocity    consigne de vitesse (joystick) ; arrêt sans nouvelle consigne pendant
//               VELOCITY_TIMEOUT_MS
//
// Règles
//   - G pendant un GoTo : « A ancien » puis départ vers la nouvelle cible.
//   - V, H ou S pendant un GoTo : « A ».
//   - Obstacle Stop : bloque tout (rotations comprises) ; Front : la marche avant ;
//     Back : la marche arrière.
#pragma once

#include <cstdint>

#include "goto_planner.h"
#include "odometry.h"
#include "protocol.h"
#include "wheel_driver.h"

// Fin d'un GoTo, à transmettre à la Rasp (pose envoyée juste avant D / A)
class MotionListener {
 public:
  virtual ~MotionListener() = default;
  virtual void onGotoDone(uint32_t id, const Pose& pose) = 0;
  virtual void onGotoAborted(uint32_t id, const Pose& pose) = 0;
};

class MotionController {
 public:
  enum class State { Idle, Goto, GotoPaused, Velocity };

  MotionController(WheelDriver& wheels, MotionListener& listener);

  // Pose de départ (avant tout mouvement)
  void begin(const Pose& pose);

  // Commande de la Rasp (Heartbeat et Invalid sont ignorés)
  void handle(const Command& cmd, uint32_t now_ms);

  // À appeler toutes les MOTION_PERIOD_MS : odométrie, fin de segment, obstacles, délais
  void update(uint32_t now_ms);

  Pose pose() const { return odometry_.pose(); }
  State state() const { return state_; }

 private:
  void startGoto(const Command& cmd);
  void startNextSegment(uint32_t now_ms);
  bool launch(const Segment& seg);
  bool segmentFinished(uint32_t now_ms);
  bool blocked(const Segment& seg) const;
  void finishGoto();
  void abortGoto();
  void applyVelocity();
  bool gotoActive() const { return state_ == State::Goto || state_ == State::GotoPaused; }

  WheelDriver& wheels_;
  MotionListener& listener_;
  Odometry odometry_;
  GotoPlanner planner_;
  State state_ = State::Idle;
  Obstacle obstacle_ = Obstacle::Clear;

  // GoTo
  uint32_t goto_id_ = 0;
  Segment segment_;                 // segment en cours (type None : aucun, le suivant est à lancer)
  int32_t target_left_ = 0;         // compteurs de pas visés par le segment
  int32_t target_right_ = 0;
  bool idle_seen_ = false;          // roues arrêtées avant la cible...
  uint32_t idle_since_ms_ = 0;      // ... depuis cet instant
  uint32_t pause_since_ms_ = 0;

  // Vitesse
  float v_mm_s_ = 0.0f;
  float omega_deg_s_ = 0.0f;
  uint32_t last_velocity_ms_ = 0;
};
