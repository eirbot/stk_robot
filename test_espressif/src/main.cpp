#include <esp_log.h>
#include "Stepper.hpp"
#include "freertos/FreeRTOS.h"
// int group_id,
// int intr_priority,
// int pwmGPIO,
// gpio_num_t dirGPIO
// float gain_step,
// mcpwm_timer_handle_t timer,
// mcpwm_oper_handle_t oper,
// mcpwm_cmpr_handle_t comparator,
// mcpwm_gen_handle_t generator,
// pcnt_unit_config_t unit_config,
// pcnt_chan_config_t chan_config,
// pcnt_unit_handle_t pcnt_unit,
// pcnt_channel_handle_t pcnt_chan,
// int max_pcnt

// First stepper
mcpwm_timer_handle_t timer;
mcpwm_oper_handle_t oper;
mcpwm_cmpr_handle_t comparator;
mcpwm_gen_handle_t generator;
pcnt_unit_config_t unit_config;
pcnt_chan_config_t chan_config;
pcnt_unit_handle_t pcnt_unit;
pcnt_channel_handle_t pcnt_chan;

int pwmGPIO = 25;
gpio_num_t dirGPIO = GPIO_NUM_18;

Stepper stepper1(0, 1, pwmGPIO, dirGPIO, 1.0, timer, oper, comparator,
                 generator, unit_config, chan_config, pcnt_unit, pcnt_chan,
                 1000);

// Second stepper
mcpwm_timer_handle_t timer_2;
mcpwm_oper_handle_t oper_2;
mcpwm_cmpr_handle_t comparator_2;
mcpwm_gen_handle_t generator_2;
pcnt_unit_config_t unit_config_2;
pcnt_chan_config_t chan_config_2;
pcnt_unit_handle_t pcnt_unit_2;
pcnt_channel_handle_t pcnt_chan_2;

int pwmGPIO_2 = 23;
gpio_num_t dirGPIO_2 = GPIO_NUM_17;

Stepper stepper2(0, 1, pwmGPIO_2, dirGPIO_2, 1.0, timer_2, oper_2, comparator_2,
                 generator_2, unit_config_2, chan_config_2, pcnt_unit_2,
                 pcnt_chan_2, 1000);

unsigned int time_to_wait;

// FreeRTOS tasks
// #define STEPPER_NUMBER 2
// #define STEPPER_TASK_STACK_SIZE (sizeof(Stepper)) * 4
// #define STEPPER_TASK_PRIORITY (tskIDLE_PRIORITY + 2)
// static StaticTask_t xCreatorTaskTCBBuffers[STEPPER_NUMBER];
// static StackType_t uxCreatorTaskStackBuffers[STEPPER_TASK_STACK_SIZE * STEPPER_NUMBER];
// static TaskHandle_t tasks[STEPPER_NUMBER];

static const char *TAG = "Stepper";

extern "C" void app_main() {
    /*SETUP*/
    stepper1.init();
    ESP_LOGI(TAG, "Stepper initialized");
    
    /*LOOP*/
    while (true)
    {
        stepper1.set_frequency(2000);
        stepper2.set_frequency(2000);
        stepper1.set_steps(100, time_to_wait);
        stepper2.set_steps(100, time_to_wait);
        vTaskDelay(pdMS_TO_TICKS(500));

        stepper1.set_frequency(1000);
        stepper2.set_frequency(1000);
        stepper1.set_steps(-200, time_to_wait);
        stepper2.set_steps(-200, time_to_wait);
        vTaskDelay(pdMS_TO_TICKS(500));

    }
}
