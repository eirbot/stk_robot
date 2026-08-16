#include "Stepper.hpp"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"

// First stepper
int pwmGPIOPin = 21;
gpio_num_t dirGPIOPin = GPIO_NUM_32;

static const char *TAG = "STEPPER_DEBUG";

#define DEG_PER_STEP 1.8

unsigned int frequencies[7] {100, 500, 1000, 1500, 2000, 2500, 3000};

void test_stepper_limit() {
  Stepper stepper(0, 1, pwmGPIOPin, dirGPIOPin, DEG_PER_STEP, 1000);
  while (true) {
    for (int k=0; k < 7; k++) {
      ESP_LOGI(TAG, "Frequency: %u Hz", frequencies[k]);
      assert(stepper.set_frequency(frequencies[k]) == 0);
      unsigned int time_to_wait;
      assert(stepper.set_steps(360, time_to_wait) == 0);
      ESP_LOGI(TAG, "Time to wait in: %u ms", time_to_wait);
      vTaskDelay(pdMS_TO_TICKS(time_to_wait + 500));
    }
  }
}
