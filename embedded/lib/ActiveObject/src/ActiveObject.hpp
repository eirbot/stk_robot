#pragma once

/** Imitation with FreeRTOS tasks of the ActiveObject design pattern inside an
    Abstract Class. */

#include <Arduino.h>

class ActiveObjectInterface {
public:
  ActiveObjectInterface(QueueHandle_t &queue_into_object, QueueHandle_t &queue_out_from_object): _queue_into_object(queue_into_object), _queue_out_from_object(queue_out_from_object) {}; 

  ~ActiveObjectInterface() = default;

protected:
  // The access to the queues is restricted to the inherited classes. 
  // So, to enqueue a command or get a result, those classes will have to
  // implement other methods that internally enqueue suitable data
  QueueHandle_t& queue_into_object();
  QueueHandle_t& queue_out_from_object();

private:
  QueueHandle_t& _queue_into_object; 
  QueueHandle_t& _queue_out_from_object; 

};


class ActiveObject: public ActiveObjectInterface {
public:
  ActiveObject(QueueHandle_t &queue_into_object, QueueHandle_t &queue_out_from_object): ActiveObjectInterface(queue_into_object, queue_out_from_object) {}; 

  ~ActiveObject() = default;
  
  virtual void loop() = 0;
};
