#pragma once

#include "ActiveObject.hpp"

#include <Arduino.h>
#include <vector>

#include "Arm.hpp"

struct Command {
  char cmd;
  std::vector<int> params;
};

class ArmOrchestrator: public ActiveObject {
public:
  ArmOrchestrator(std::array<Arm, 4> &arms): _arms(arms), ActiveObject(xQueueCreate(ARM__MAX_PENDING_CMD_NB, sizeof(Command)), xQueueCreate(ARM__MAX_PENDING_CMD_NB, sizeof(Command))) {};

  void loop() override;

  void scheduleCommand(Command &cmd);
  bool getNextTerminatedCommand(Command *opt);

private:
  std::array<Arm, 4> &_arms;
  int _synchronized_arm_nb = 0; // 4 => send signal

  void forwardCommandToArms(Command &cmd);
};
