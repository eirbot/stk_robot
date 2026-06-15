#include "ActuatorThread.hpp"

bool Promise::loop() {
  if (!_started) {
    on_start();
    _started = true;
  }

  if (_finished)
    return true;

  if (check_promise_success()) {
    on_success();
    _finished = true;
    return true; 
  } 

  return false;
}
