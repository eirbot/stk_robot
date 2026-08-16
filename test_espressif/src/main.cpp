#include <esp_log.h>
#include "Stepper.hpp"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"

// First stepper
int pwmGPIO = 18;
gpio_num_t dirGPIO = GPIO_NUM_25;

// Second stepper
int pwmGPIO_2 = 23;
gpio_num_t dirGPIO_2 = GPIO_NUM_17;

unsigned int time_to_wait;

// FreeRTOS tasks
#define STEPPER_NUMBER 2
#define STEPPER_TASK_STACK_SIZE 4096
#define STEPPER_TASK_PRIORITY (tskIDLE_PRIORITY + 2)
static StaticTask_t xCreatorTaskTCBBuffers[STEPPER_NUMBER];
static StackType_t uxCreatorTaskStackBuffers[STEPPER_TASK_STACK_SIZE * STEPPER_NUMBER];
static TaskHandle_t tasks[STEPPER_NUMBER];

static const char *TAG = "Stepper";

void stepper_one_task(void *pvParameters) {
    Stepper stepper1(0, 1, pwmGPIO, dirGPIO, 1.0,1000);

    stepper1.set_frequency(500);
    
    while (1) {
        stepper1.set_steps(500, time_to_wait);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

void stepper_two_task(void *pvParameters) {
    Stepper stepper2(0, 1, pwmGPIO_2, dirGPIO_2, 1.0, 1000);

    stepper2.set_frequency(500);
    
    while (1) {
        stepper2.set_steps(200, time_to_wait);
        vTaskDelay(pdMS_TO_TICKS(1000));
        stepper2.set_steps(-200, time_to_wait);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    
}
extern "C" void app_main() {
    /*SETUP*/
    tasks[0] =
        xTaskCreateStatic(stepper_one_task, "stepper1", STEPPER_TASK_STACK_SIZE,
                          NULL, STEPPER_TASK_PRIORITY,
                          uxCreatorTaskStackBuffers, xCreatorTaskTCBBuffers);
    tasks[1] =
        xTaskCreateStatic(stepper_two_task, "stepper2", STEPPER_TASK_STACK_SIZE,
                          NULL, STEPPER_TASK_PRIORITY,
                          uxCreatorTaskStackBuffers + STEPPER_TASK_STACK_SIZE,
                          xCreatorTaskTCBBuffers + 1);
    ESP_LOGI(TAG, "Steppers initialized");

    /*LOOP*/
    while (1) {
        ESP_LOGI(TAG, "TIC");
        vTaskDelay(pdMS_TO_TICKS(1000));
        ESP_LOGI(TAG, "TAC");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }

}
