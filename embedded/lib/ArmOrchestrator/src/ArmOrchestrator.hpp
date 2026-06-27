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
  ArmOrchestrator(std::array<Arm, 4> &arms, QueueHandle_t &queue_into_object, QueueHandle_t &queue_out_from_object): _arms(arms), ActiveObject(queue_into_object, queue_out_from_object) {};

  void loop() override;

  void scheduleCommand(Command &cmd);
  bool getNextTerminatedCommand(Command *opt);

private:
  std::array<Arm, 4> &_arms;
  int _synchronized_arm_nb = 0; // 4 => send signal

  void forwardCommandToArms(Command &cmd);
};
