#include "link.h"

#include <driver/uart.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#include "config.h"
#include "motion_task.h"
#include "protocol.h"

namespace {

constexpr uart_port_t PORT = UART_NUM_0;
constexpr size_t FRAME_MAX = 96;  // « T x y theta » + « D id » dans une seule écriture

SemaphoreHandle_t tx_lock = nullptr;

uint32_t nowMs() { return static_cast<uint32_t>(esp_timer_get_time() / 1000); }

void write(const char* data, size_t len) {
  if (len == 0) return;
  xSemaphoreTake(tx_lock, portMAX_DELAY);
  uart_write_bytes(PORT, data, len);
  xSemaphoreGive(tx_lock);
}

void sendError(const char* message) {
  char buf[FRAME_MAX];
  write(buf, protocol::formatError(buf, sizeof buf, message));
}

// Pose puis D / A dans la même écriture : la Rasp lit une pose à jour avant la fin du GoTo
void sendPoseThen(const Pose& pose, size_t (*format_end)(char*, size_t, uint32_t), uint32_t id) {
  char buf[FRAME_MAX];
  const size_t n = protocol::formatPose(buf, sizeof buf, pose);
  const size_t m = n > 0 ? format_end(buf + n, sizeof buf - n, id) : 0;
  write(buf, m > 0 ? n + m : 0);
}

void handleLine(const char* line) {
  const Command cmd = protocol::parse(line);
  if (cmd.type == Command::Type::Invalid) {
    sendError(cmd.error);
    return;
  }
  // Le battement de cœur n'a servi qu'à nourrir le watchdog (fait à la réception des octets)
  if (cmd.type == Command::Type::Heartbeat) return;
  if (!motion_task::send(cmd)) sendError("file de commandes pleine");
}

void rxTask(void*) {
  protocol::LineReader reader;
  protocol::RaspWatchdog watchdog;
  uint8_t chunk[64];
  for (;;) {
    const int n = uart_read_bytes(PORT, chunk, sizeof chunk, pdMS_TO_TICKS(config::UART_READ_TIMEOUT_MS));
    const uint32_t now = nowMs();
    if (n > 0) watchdog.onActivity(now);  // tout octet reçu est un signe de vie
    for (int i = 0; i < n; i++) {
      switch (reader.push(static_cast<char>(chunk[i]))) {
        case protocol::LineReader::Result::Line: handleLine(reader.line()); break;
        case protocol::LineReader::Result::Overflow: sendError("ligne trop longue"); break;
        case protocol::LineReader::Result::None: break;
      }
    }
    if (watchdog.expired(now)) {
      // Rasp plantée ou câble coupé : plus d'arrêt à 100 s ni d'évitement côté Rasp.
      // « W » d'abord : le « A » du GoTo annulé arrive juste après.
      char buf[8];
      write(buf, protocol::formatWatchdog(buf, sizeof buf));
      Command halt;
      halt.type = Command::Type::Halt;
      motion_task::send(halt);
    }
  }
}

void telemetryTask(void*) {
  TickType_t last_wake = xTaskGetTickCount();
  for (;;) {
    vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(config::TELEMETRY_PERIOD_MS));
    char buf[FRAME_MAX];
    write(buf, protocol::formatPose(buf, sizeof buf, motion_task::pose()));
  }
}

}  // namespace

bool Link::start() {
  tx_lock = xSemaphoreCreateMutex();
  if (tx_lock == nullptr) return false;

  uart_config_t cfg = {};
  cfg.baud_rate = static_cast<int>(config::UART_BAUDRATE);
  cfg.data_bits = UART_DATA_8_BITS;
  cfg.parity = UART_PARITY_DISABLE;
  cfg.stop_bits = UART_STOP_BITS_1;
  cfg.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
  cfg.source_clk = UART_SCLK_APB;
  if (uart_driver_install(PORT, config::UART_RX_BUFFER_BYTES, config::UART_TX_BUFFER_BYTES, 0, nullptr, 0) != ESP_OK ||
      uart_param_config(PORT, &cfg) != ESP_OK) {
    return false;
  }

  return xTaskCreatePinnedToCore(rxTask, "link_rx", config::LINK_RX_TASK_STACK, nullptr,
                                 config::LINK_RX_TASK_PRIORITY, nullptr, config::CORE_APP) == pdPASS &&
         xTaskCreatePinnedToCore(telemetryTask, "telemetry", config::TELEMETRY_TASK_STACK, nullptr,
                                 config::TELEMETRY_TASK_PRIORITY, nullptr, config::CORE_APP) == pdPASS;
}

void Link::sendError(const char* message) { ::sendError(message); }

void Link::onGotoDone(uint32_t id, const Pose& pose) { sendPoseThen(pose, protocol::formatDone, id); }

void Link::onGotoAborted(uint32_t id, const Pose& pose) { sendPoseThen(pose, protocol::formatAborted, id); }
