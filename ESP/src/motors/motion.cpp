#include "motion.h"

#include "config.h"
#include "kinematics.h"

using kinematics::mmToStepsRounded;
using kinematics::rotationDegToWheelMm;

MotionController::MotionController(WheelDriver& wheels, MotionListener& listener)
    : wheels_(wheels), listener_(listener) {}

void MotionController::begin(const Pose& pose) {
  odometry_.reset(pose, wheels_.leftSteps(), wheels_.rightSteps());
}

// --- Commandes ---------------------------------------------------------------------

void MotionController::handle(const Command& cmd, uint32_t now_ms) {
  switch (cmd.type) {
    case Command::Type::GoTo:
      if (gotoActive()) abortGoto();
      if (state_ == State::Velocity) wheels_.stop();
      startGoto(cmd);
      break;

    case Command::Type::Velocity:
      if (gotoActive()) abortGoto();
      state_ = State::Velocity;
      v_mm_s_ = cmd.v_mm_s;
      omega_deg_s_ = cmd.omega_deg_s;
      last_velocity_ms_ = now_ms;
      applyVelocity();
      break;

    case Command::Type::SetPose:
      // Un GoTo en cours a été calculé dans l'ancien repère : on l'annule
      if (gotoActive()) abortGoto();
      odometry_.reset(cmd.pose, wheels_.leftSteps(), wheels_.rightSteps());
      break;

    case Command::Type::Lidar:
      obstacle_ = cmd.obstacle;
      if (state_ == State::Velocity) applyVelocity();
      // GoTo : vérifié dans update(), qui connaît le segment en cours
      break;

    case Command::Type::Halt:
      if (gotoActive()) abortGoto();
      wheels_.stop();
      state_ = State::Idle;
      break;

    case Command::Type::Heartbeat:
    case Command::Type::Invalid:
      break;
  }
}

// --- Boucle ---------------------------------------------------------------------------

void MotionController::update(uint32_t now_ms) {
  odometry_.update(wheels_.leftSteps(), wheels_.rightSteps());

  switch (state_) {
    case State::Idle:
      break;

    case State::Goto:
      if (segment_.type != Segment::Type::None) {
        if (blocked(segment_)) {
          // Obstacle sur le chemin : arrêt, le segment sera recalculé à la reprise
          wheels_.stop();
          planner_.restartSegment();
          segment_ = {};
          state_ = State::GotoPaused;
          pause_since_ms_ = now_ms;
        } else if (segmentFinished(now_ms)) {
          segment_ = {};
        }
      }
      // Segment suivant une fois les roues arrêtées (fin de segment, ou freinage
      // après un nouveau G)
      if (state_ == State::Goto && segment_.type == Segment::Type::None && !wheels_.isRunning()) {
        startNextSegment(now_ms);
      }
      break;

    case State::GotoPaused:
      if (now_ms - pause_since_ms_ >= config::OBSTACLE_ABORT_MS) {
        abortGoto();
      } else if (!wheels_.isRunning()) {
        // Reste en pause (même chronomètre) tant que le segment est bloqué
        startNextSegment(now_ms);
      }
      break;

    case State::Velocity:
      if (now_ms - last_velocity_ms_ > config::VELOCITY_TIMEOUT_MS) {
        wheels_.stop();
        state_ = State::Idle;
      }
      break;
  }
}

// --- GoTo -------------------------------------------------------------------------------

void MotionController::startGoto(const Command& cmd) {
  goto_id_ = cmd.id;
  speed_factor_ = cmd.speed_factor;
  planner_.start(cmd.pose);
  segment_ = {};
  state_ = State::Goto;  // le premier segment part au prochain update(), roues arrêtées
}

void MotionController::startNextSegment(uint32_t now_ms) {
  const Segment seg = planner_.next(odometry_.pose());
  if (seg.type == Segment::Type::None) {
    finishGoto();
    return;
  }
  if (blocked(seg)) {
    planner_.restartSegment();
    if (state_ != State::GotoPaused) {
      state_ = State::GotoPaused;
      pause_since_ms_ = now_ms;
    }
    return;
  }
  state_ = State::Goto;
  if (!launch(seg)) abortGoto();
}

bool MotionController::launch(const Segment& seg) {
  int32_t left = 0, right = 0;
  float speed = 0.0f, accel = 0.0f;
  if (seg.type == Segment::Type::Rotate) {
    // Sens + : roue droite en avant, gauche en arrière
    right = mmToStepsRounded(rotationDegToWheelMm(seg.amount));
    left = -right;
    speed = rotationDegToWheelMm(config::ROTATE_SPEED_DEG_S);
    accel = rotationDegToWheelMm(config::ROTATE_ACCEL_DEG_S2);
  } else {
    left = right = mmToStepsRounded(seg.amount);
    speed = config::DRIVE_SPEED_MM_S;
    accel = config::DRIVE_ACCEL_MM_S2;
  }
  speed *= speed_factor_;
  accel *= speed_factor_;
  segment_ = seg;
  target_left_ = wheels_.leftSteps() + left;
  target_right_ = wheels_.rightSteps() + right;
  idle_seen_ = false;
  return wheels_.move(left, right, speed, accel);
}

bool MotionController::segmentFinished(uint32_t now_ms) {
  if (wheels_.isRunning()) {
    idle_seen_ = false;
    return false;
  }
  if (wheels_.leftSteps() == target_left_ && wheels_.rightSteps() == target_right_) return true;
  // Roues arrêtées avant la cible (ne devrait pas arriver) : on n'attend pas indéfiniment
  if (!idle_seen_) {
    idle_seen_ = true;
    idle_since_ms_ = now_ms;
  }
  return now_ms - idle_since_ms_ >= config::SEGMENT_SETTLE_MS;
}

bool MotionController::blocked(const Segment& seg) const {
  switch (obstacle_) {
    case Obstacle::Clear: return false;
    case Obstacle::Stop: return true;
    case Obstacle::Front: return seg.type == Segment::Type::Drive && seg.amount > 0.0f;
    case Obstacle::Back: return seg.type == Segment::Type::Drive && seg.amount < 0.0f;
  }
  return true;
}

void MotionController::finishGoto() {
  state_ = State::Idle;
  segment_ = {};
  listener_.onGotoDone(goto_id_, odometry_.pose());
}

void MotionController::abortGoto() {
  wheels_.stop();
  state_ = State::Idle;
  segment_ = {};
  listener_.onGotoAborted(goto_id_, odometry_.pose());
}

// --- Vitesse ------------------------------------------------------------------------------

void MotionController::applyVelocity() {
  if (obstacle_ == Obstacle::Stop) {
    wheels_.stop();
    return;
  }
  float v = v_mm_s_;
  if ((obstacle_ == Obstacle::Front && v > 0.0f) || (obstacle_ == Obstacle::Back && v < 0.0f)) v = 0.0f;
  const kinematics::WheelSpeeds s = kinematics::wheelSpeedsFromTwist(v, omega_deg_s_);
  wheels_.run(s.left_mm_s, s.right_mm_s, config::VELOCITY_ACCEL_MM_S2);
}
