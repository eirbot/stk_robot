#pragma once

#include "ActiveObject.hpp"

#include <Arduino.h>
#include <optional>

#include "Arm.hpp"

struct Command {
  const char cmd;
  const std::vector<int> &params;
};

class ArmOrchestrator: public ActiveObject {
public:
  ArmOrchestrator(std::array<Arm, 4> &arms): _arms(arms), ActiveObject(xQueueCreate(ARM__MAX_PENDING_CMD_NB, sizeof(Command)), xQueueCreate(ARM__MAX_PENDING_CMD_NB, sizeof(Command))) {};

  void loop() override;

  void scheduleCommand(Command &cmd);
  std::optional<Command> getNextTerminatedCommand();

private:
  std::array<Arm, 4> &_arms;
  int _synchronized_arm_nb = 0; // 4 => send signal

  void forwardCommandToArms(Command &cmd);
};

extern ArmOrchestrator arm_orchestrator;
