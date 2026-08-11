#pragma once

#include "ActiveObject.hpp"
#include "ActiveObjectCreator.hpp"

class ArmCreator : public ActiveObjectCreator {
public:
  ArmCreator() {};
  ~ArmCreator();
  void init_active_object(
      ActiveObjectStaticInterface &interface, const char *const pcName,
      FreeRTOSTaskStaticBuffers task_static_buffers,
      FreeRTOSQueueStaticBuffers queue_in_static_buffers,
      FreeRTOSQueueStaticBuffers queue_out_static_buffers) override;

private:
};
