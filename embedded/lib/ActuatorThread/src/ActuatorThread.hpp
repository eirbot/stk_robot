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
    ActuatorThread(Actuator& act, uint8_t actId, const char *const threadName,QueueHandle_t& queue)
        : _act(act), _actId(actId), _threadName(threadName), _queue(queue) {}

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
    QueueHandle_t& _queue;
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
    xQueueSendToBack(_queue, &params, 0);
}
#endif // ACTUATOR_THREAD_HPP
