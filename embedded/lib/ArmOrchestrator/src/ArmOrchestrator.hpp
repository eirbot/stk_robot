#pragma once

#include "ActiveObject.hpp"

#include <Arduino.h>
#include <vector>

#include "Arm.hpp"

struct Command {
  command_id cmd_id;
  // the function name
  char cmd;
  // the parmas encoded in a vector of int
  std::vector<int> params;
};

#define ARM_ORCHESTRATOR_QUEUE_MAX_ITEM_NB 25
#define ARM_ORCHESTRATOR_IN_QUEUE_ITEM_SIZE sizeof( Command )
#define ARM_ORCHESTRATOR_OUT_QUEUE_ITEM_SIZE sizeof( command_id )
#define ARM_ORCHESTRATOR_TASK_STACK_SIZE sizeof(ArmOrchestrator) * 5
#ifndef ARM_ORCHESTRATOR_TASK_PRIORITY
#define ARM_ORCHESTRATOR_TASK_PRIORITY ( tskIDLE_PRIORITY + 2 )
#endif // ARM_ORCHESTRATOR_TASK_PRIORITY

class ArmOrchestrator: public ActiveObject {
public:
  ArmOrchestrator(std::array<ActiveObjectStaticInterface, ARM_MAX_NB> &arms, ActiveObjectStaticInterface &interface): _arms(arms), ActiveObject(interface) {};

  void loop() override;
private:
  std::array<ActiveObjectStaticInterface, ARM_MAX_NB> &_arms;
  command_id _pending_sync_arm_cmd_id = NO_COMMAND;
  int _synchronized_arm_nb = 0; // 4 => send signal

  void forwardCommandToArms(Command &cmd);
};
