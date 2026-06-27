#include "ActiveObject.hpp"

#include <Arduino.h>

QueueHandle_t& ActiveObject::queue_into_object() {
  return _queue_into_object;
}

QueueHandle_t& ActiveObject::queue_out_from_object() {
  return _queue_out_from_object;
}
