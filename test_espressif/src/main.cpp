#include <esp_log.h>
#include "Stepper.hpp"
#include "freertos/FreeRTOS.h"
// int group_id,
// int intr_priority,
// int GPIO,
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

mcpwm_timer_handle_t timer;
mcpwm_oper_handle_t oper;
mcpwm_cmpr_handle_t comparator;
mcpwm_gen_handle_t generator;
pcnt_unit_config_t unit_config;
pcnt_chan_config_t chan_config;
pcnt_unit_handle_t pcnt_unit;
pcnt_channel_handle_t pcnt_chan;

Stepper stepper1(0, 1, 25, 1.0, timer, oper, comparator, generator, unit_config, chan_config, pcnt_unit, pcnt_chan, 1000);
unsigned int time_to_wait;

static const char *TAG = "Stepper";

extern "C" void app_main() {
    /*SETUP*/
    stepper1.init();
    ESP_LOGI(TAG, "Stepper initialized");
    
    /*LOOP*/
    while (true)
    {
        stepper1.set_frequency(2000);
        stepper1.set_steps(500, time_to_wait);
        vTaskDelay(pdMS_TO_TICKS(500));
        ESP_LOGI(TAG, "loop completed : freq = 2kHz");
        stepper1.set_frequency(1000);
        stepper1.set_steps(500, time_to_wait);
        vTaskDelay(pdMS_TO_TICKS(500));
        ESP_LOGI(TAG, "loop completed : freq = 1kHz");
    }
    
}