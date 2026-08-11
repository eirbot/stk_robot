#pragma once

/** Imitation with FreeRTOS tasks of the ActiveObject design pattern inside an
    Abstract Class. */

#include <Arduino.h>

/** Contains 2 queues and a task id variables. All those elements must be
  * statically initialized once so the interface can be shared accross several
  * FreeRTOS tasks. A struct like this must also be initialized statically to
  * be shared.
  */
struct ActiveObjectInterface {
  QueueHandle_t& queue_into_object; 
  QueueHandle_t& queue_out_from_object; 
  TaskHandle_t& task_id;
};


class ActiveObject {
public:
  ActiveObject(const ActiveObjectInterface& staticInterface): _interface(staticInterface) {}; 

  ~ActiveObject() = default;

  virtual void loop() = 0;

protected:
  const ActiveObjectInterface& _interface;
};
