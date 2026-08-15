#include "Stepper.hpp"

bool on_reach_function(pcnt_unit_handle_t unit, const pcnt_watch_event_data_t *edata, void *user_ctx){
    // TODO: pass the Stepper and call a public method to stop the stepper, the counter and
    Stepper *stepper = (Stepper *)user_ctx;
    stepper->interrupt();
    return 0;
}

Stepper::Stepper(   int group_id,
                    int intr_priority,
                    int GPIO,
                    mcpwm_timer_handle_t timer,
                    mcpwm_oper_handle_t oper,
                    mcpwm_cmpr_handle_t comparator,
                    mcpwm_gen_handle_t generator,
                    float gain_step){
    
    _timer_config = {
        .group_id = group_id,
        .clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = PWM_RESOLUTION,
        .count_mode = MCPWM_TIMER_COUNT_MODE_UP,
        .period_ticks = PWM_RESOLUTION/DEFAULT_FREQ,
    };
    _operator_config = {
        .group_id = group_id,
        .intr_priority = intr_priority
    };
    _comparator_config = {
        .intr_priority = intr_priority
    };
    _generator_config = {
        .gen_gpio_num = GPIO
    };
    
    _timer = timer;
    _oper = oper;
    _comparator = comparator;
    _generator = generator;

    _GPIO = GPIO;
    _gain_step = gain_step;
}

bool Stepper::init(){
    ESP_ERROR_CHECK(mcpwm_new_timer(&_timer_config,&_timer));
    ESP_ERROR_CHECK(mcpwm_new_operator(&_operator_config,&_oper));
    ESP_ERROR_CHECK(mcpwm_operator_connect_timer(_oper, _timer));
    ESP_ERROR_CHECK(mcpwm_new_comparator(_oper,&_comparator_config,&_comparator));
    ESP_ERROR_CHECK(mcpwm_new_generator(_oper,&_generator_config,&_generator));
    ESP_ERROR_CHECK(mcpwm_generator_set_action_on_timer_event(_generator,{.direction = MCPWM_TIMER_DIRECTION_UP,.event = MCPWM_TIMER_EVENT_EMPTY,.action = MCPWM_GEN_ACTION_HIGH,}));
    ESP_ERROR_CHECK(mcpwm_generator_set_action_on_compare_event(_generator,{.direction = MCPWM_TIMER_DIRECTION_UP,.comparator = _comparator,.action = MCPWM_GEN_ACTION_LOW,}));
    ESP_ERROR_CHECK(mcpwm_comparator_set_compare_value(_comparator,_timer_config.period_ticks / 2));
    
    pcnt_unit_config_t unit_config = {.clk_src = PCNT_CLK_SRC_DEFAULT, .low_limit = -1, .high_limit = 1000, .intr_priority = 0, .flags = {.accum_count = 1}};
    ESP_ERROR_CHECK(pcnt_new_unit(&unit_config,&_pcnt));
    pcnt_chan_config_t chan_config = {.edge_gpio_num = _GPIO, .level_gpio_num = -1, .flags = {.invert_edge_input = 0, .invert_level_input = 0, .virt_edge_io_level = 0, .virt_level_io_level = 0}};
    ESP_ERROR_CHECK(pcnt_new_channel(_pcnt,&chan_config,&_pcnt_chan));

    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(_pcnt_chan,PCNT_CHANNEL_EDGE_ACTION_INCREASE,PCNT_CHANNEL_EDGE_ACTION_HOLD));

    pcnt_event_callbacks_t my_callbacks{.on_reach = on_reach_function};

    ESP_ERROR_CHECK(pcnt_unit_register_event_callbacks(_pcnt, &my_callbacks, this));
    ESP_ERROR_CHECK(pcnt_unit_enable(_pcnt));
    return 0;
}

bool Stepper::set_frequency(int frequency){
    uint32_t new_preriod = PWM_RESOLUTION / frequency;
    ESP_ERROR_CHECK(mcpwm_timer_set_period(_timer, new_preriod));
    // TODO: fix the error code
    return 0;
}

int Stepper::set_steps(int steps){
    if (_is_busy)
        return 0;

    _is_busy = true;
    ESP_ERROR_CHECK(pcnt_unit_add_watch_point(_pcnt,steps));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(_pcnt));
    ESP_ERROR_CHECK(pcnt_unit_start(_pcnt));

    // TODO: start the steps

    // TODO: return the correct time to be awaited
    return 42;
}

bool Stepper::interrupt() {
    // TODO: stop the stepper
    // TODO: stop the counter
    _is_busy = false;
    return true;
}

bool Stepper::is_available() {
    return !_is_busy;
}
