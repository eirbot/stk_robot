#ifndef ACTUATOR_THREAD_HPP
#define ACTUATOR_THREAD_HPP

#include <Arduino.h>
#include <vector>

class TaskParams {
    public:
      TaskParams(char cmd, uint8_t P_angleFlag, int A_param1): _cmd(cmd), _P_angleFlag(P_angleFlag), _A_param1(A_param1) {}
        const char _cmd;
        const uint8_t _P_angleFlag;
        const int _A_param1;
    private:
};

template <typename Actuator, typename PvParametersType>
class ActuatorThread {
public:
    ActuatorThread(Actuator& act, uint8_t actId, const char *const threadName, QueueHandle_t& queue_to_thread, QueueHandle_t& queue_from_thread)
        : _act(act), _actId(actId), _threadName(threadName), _queue_to_thread(_queue_to_thread), _queue_from_thread(queue_from_thread) {}

    virtual ~ActuatorThread() = default;

    /** Send data to the queue related to the thread to init a command
     *  processing.
     */
    void sendToThreadQueue(TaskParams& params);

    /** Implement the FreeRTOS vTask related to the ActuatorThread.
     *
     *  Implement the vTask as usual in FreeRTOS. Don't forget to call the
     *  vTaskDelete function inside to correctly free the task.
     */
    virtual void vTask(PvParametersType *pvParameter) = 0;

    /** Call this method once to init the FreeRTOS vTask.
     */
    void initVTask(PvParametersType *pvParameters);


protected:
    QueueHandle_t& _queue_to_thread;
    QueueHandle_t& _queue_from_thread;
    bool flagInit = false;
    const uint8_t _actId;
    const char *const _threadName;

    Actuator& _act;
    uint16_t pAngle0, pAngle1;

    /** Code to process a given command.
     */
    virtual void processCommand(TaskParams params) = 0;

};

class ActuatorManager {
public:
  virtual void processCommand(const String &cmd,
                              const std::vector<int> &params) = 0;
};

template <typename Actuator, typename PvParametersType>
struct TaskContext {
  ActuatorThread<Actuator, PvParametersType> *instance;
  PvParametersType *pvParameters;
};


// Template functions/methods implementation in the hpp 
// (cf. c++ templating engine)

template <typename Actuator, typename PvParametersType> void vTaskOnInstance(void *pvParameters) {
   TaskContext<Actuator, PvParametersType> *ctx = (TaskContext<Actuator, PvParametersType> *)pvParameters;
   ctx->instance->vTask(ctx->pvParameters);
}

template <typename Actuator, typename PvParametersType> void ActuatorThread<Actuator, PvParametersType>::initVTask(PvParametersType *pvParameters) {
  TaskContext<Actuator, PvParametersType> taskCtx{this, pvParameters};
  xTaskCreatePinnedToCore(vTaskOnInstance<Actuator, PvParametersType>,
                          _threadName, 4000, &taskCtx, 1, NULL, tskNO_AFFINITY);
}

template <typename Actuator, typename PvParametersType> void ActuatorThread<Actuator, PvParametersType>::sendToThreadQueue(TaskParams& params) {
    xQueueSendToBack(_queue_to_thread, &params, 0);
}

class Promise {
  /** Carry out a promise lifecycle loop.
   *
   *  Returns the success state of the Promise.
   *
   *  If it is not a success, consider yielding to the other async loops.
   *  Else, consider processing the next instructions/promises of your async
   *  loop.
   *
   *  If the promise has not started yet, then the first loop call will be carry
   *  out the start action.
   */
  bool loop();

protected:
  bool _started = false;
  bool _finished = false;

  /** Carry out a custom action when the promise is initiated.
   *
   *  For instance, send a command to another thread through a FreeRTOS Queue.
   */
  virtual void on_start();

  /** Carry out a custom action when the promise has ended with success.
   *
   *  For instance, ask the communication module to notify the Raspberry Pi on
   *  the success of a command.
   */
  virtual void on_success();

  /** Carry out custom checking to figure out if the promise has succedded.
   *
   */
  virtual bool check_promise_success();
};
#endif // ACTUATOR_THREAD_HPP
