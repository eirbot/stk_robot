#include "motion_task.h"

#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

#include "config.h"

namespace motion_task {

namespace {

QueueHandle_t queue = nullptr;
MotionController* controller = nullptr;

// Copie de la pose pour les autres tâches. Section critique courte (12 octets copiés) :
// un spinlock suffit, et il marche entre les deux cœurs.
portMUX_TYPE pose_lock = portMUX_INITIALIZER_UNLOCKED;
Pose published_pose;

uint32_t nowMs() { return static_cast<uint32_t>(esp_timer_get_time() / 1000); }

void publishPose() {
  const Pose p = controller->pose();
  portENTER_CRITICAL(&pose_lock);
  published_pose = p;
  portEXIT_CRITICAL(&pose_lock);
}

void taskLoop(void*) {
  const TickType_t period = pdMS_TO_TICKS(config::MOTION_PERIOD_MS);
  TickType_t last_update = xTaskGetTickCount();
  for (;;) {
    const TickType_t elapsed = xTaskGetTickCount() - last_update;
    if (elapsed >= period) {
      controller->update(nowMs());
      last_update += period;
      // Retard de plus d'une période (ne devrait pas arriver) : on repart de maintenant
      if (xTaskGetTickCount() - last_update >= period) last_update = xTaskGetTickCount();
      publishPose();
      continue;
    }
    Command cmd;
    if (xQueueReceive(queue, &cmd, period - elapsed) == pdTRUE) {
      controller->handle(cmd, nowMs());
      publishPose();
    }
  }
}

}  // namespace

bool start(WheelDriver& wheels, MotionListener& listener, const Pose& initial_pose) {
  queue = xQueueCreate(config::COMMAND_QUEUE_LENGTH, sizeof(Command));
  if (queue == nullptr) return false;
  // Vit jusqu'à l'arrêt de l'ESP : jamais libéré
  controller = new MotionController(wheels, listener);
  controller->begin(initial_pose);
  publishPose();
  return xTaskCreatePinnedToCore(taskLoop, "motion", config::MOTION_TASK_STACK, nullptr,
                                 config::MOTION_TASK_PRIORITY, nullptr, config::CORE_APP) == pdPASS;
}

bool send(const Command& cmd) { return queue != nullptr && xQueueSend(queue, &cmd, 0) == pdTRUE; }

Pose pose() {
  portENTER_CRITICAL(&pose_lock);
  const Pose p = published_pose;
  portEXIT_CRITICAL(&pose_lock);
  return p;
}

}  // namespace motion_task
