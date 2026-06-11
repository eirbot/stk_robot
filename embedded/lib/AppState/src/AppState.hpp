#ifndef APP_STATE_HPP
#define APP_STATE_HPP

class AppState {
public:
   bool timeout = false; // Set to true will stop all the FreeRTOS vTasks
};

extern AppState appState;

#endif // APP_STATE_HPP
