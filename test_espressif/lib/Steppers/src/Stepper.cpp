#include "Stepper.hpp"

bool interrupt_stepper_when_steps_reached(pcnt_unit_handle_t unit, const pcnt_watch_event_data_t *edata, void *user_ctx){
    Stepper *stepper = (Stepper *)user_ctx;
    stepper->interrupt();
    return false;
}

Stepper::Stepper(int group_id,
                int intr_priority,
                int pwmGPIO,
                gpio_num_t dirGPIO,
                float gain_step,
                int max_pcnt){
    
    /* GPIO assignement and stepper gain */                
    _pwmGPIO = pwmGPIO;
    _dirGPIO = dirGPIO;
    ESP_ERROR_CHECK(gpio_set_direction(_dirGPIO, GPIO_MODE_OUTPUT));
    _gain_step = gain_step;

    /* mcpwm configs */
    _timer_config = {
        .group_id = group_id,
        .clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = PWM_RESOLUTION,
        .count_mode = MCPWM_TIMER_COUNT_MODE_UP,
        .period_ticks = PWM_RESOLUTION/DEFAULT_FREQ,
        .intr_priority = intr_priority,
        .flags = {}
    };
    _operator_config = {
        .group_id = group_id,
        .intr_priority = intr_priority,
        .flags = {}
    };
    _comparator_config = {
        .intr_priority = intr_priority,
        .flags = {}
    };
    _generator_config = {
        .gen_gpio_num = pwmGPIO,
        .flags = {}
    };

    /* pcnt configs */
    _chan_config = {.edge_gpio_num = _pwmGPIO,
                    .level_gpio_num = -1,
                    .flags = {.invert_edge_input = 0,
                        .invert_level_input = 0,
                        .virt_edge_io_level = 0,
                        .virt_level_io_level = 0}
                    };
    _unit_config = {.clk_src = PCNT_CLK_SRC_DEFAULT,
                    .low_limit = -1,
                    .high_limit = max_pcnt,
                    .intr_priority = 0,
                    .flags = {.accum_count = 1}
                    };
    
    int init_success = !_init();
    assert (init_success);
}

int Stepper::_init(){
    /* creates requiered mcpwm modules */
    ESP_ERROR_CHECK(mcpwm_new_timer(&_timer_config,&_timer));
    ESP_ERROR_CHECK(mcpwm_new_operator(&_operator_config,&_oper));
    ESP_ERROR_CHECK(mcpwm_operator_connect_timer(_oper, _timer));
    ESP_ERROR_CHECK(mcpwm_new_comparator(_oper,&_comparator_config,&_comparator));
    ESP_ERROR_CHECK(mcpwm_new_generator(_oper,&_generator_config,&_generator));

    /* set pwm at 50% duty cycle ON then OFF */
    ESP_ERROR_CHECK(mcpwm_generator_set_action_on_timer_event(_generator,{.direction = MCPWM_TIMER_DIRECTION_UP,.event = MCPWM_TIMER_EVENT_EMPTY,.action = MCPWM_GEN_ACTION_HIGH,}));
    ESP_ERROR_CHECK(mcpwm_generator_set_action_on_compare_event(_generator,{.direction = MCPWM_TIMER_DIRECTION_UP,.comparator = _comparator,.action = MCPWM_GEN_ACTION_LOW,}));
    ESP_ERROR_CHECK(mcpwm_comparator_set_compare_value(_comparator,_timer_config.period_ticks / 2));
    
    /* creates requiered pulse counter modules */
    ESP_ERROR_CHECK(pcnt_new_unit(&_unit_config,&_pcnt_unit));
    ESP_ERROR_CHECK(pcnt_new_channel(_pcnt_unit,&_chan_config,&_pcnt_chan));

    /* counts only increase on rising edge (no actions on falling edge)*/
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(_pcnt_chan,PCNT_CHANNEL_EDGE_ACTION_INCREASE,PCNT_CHANNEL_EDGE_ACTION_HOLD));


    /* creates interrupt trigger for pcnt */
    pcnt_event_callbacks_t steps_complete{.on_reach = interrupt_stepper_when_steps_reached};
    ESP_ERROR_CHECK(pcnt_unit_register_event_callbacks(_pcnt_unit, &steps_complete, this));

    /* enables pwm_timer and pcnt_unit */
    ESP_ERROR_CHECK(mcpwm_timer_enable(_timer));
    ESP_ERROR_CHECK(pcnt_unit_enable(_pcnt_unit));

    /* default direction state is 0 */
    ESP_ERROR_CHECK(gpio_set_level(_dirGPIO, 0));
    return 0;
}

int Stepper::set_frequency(int frequency){
    /* sets new period (mcpwm works in time not freq)
    *  WARNING: change in frequency is not done if set_compare_value is not called
    */
    uint32_t new_period = PWM_RESOLUTION / frequency;
    ESP_ERROR_CHECK(mcpwm_timer_set_period(_timer, new_period));
    ESP_ERROR_CHECK(mcpwm_comparator_set_compare_value(_comparator,new_period / 2));
    return 0;
}

int Stepper::set_steps(float target, unsigned int &time_to_wait){
    /* reject concurrencing orders */
    if (!is_available())
        return -1;

    /* compute the number of steps according to the target */
    _steps = abs((int)target/_gain_step);

    /* sets direction */
    if (target < 0)
    {
        ESP_ERROR_CHECK(gpio_set_level(_dirGPIO, 0));
    }
    else
    {
        ESP_ERROR_CHECK(gpio_set_level(_dirGPIO, 1));
    }
    
    /* free output, prep counter, starts pwm */
    ESP_ERROR_CHECK(mcpwm_generator_set_force_level(_generator, -1, true));
    ESP_ERROR_CHECK(pcnt_unit_add_watch_point(_pcnt_unit,_steps));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(_pcnt_unit));
    ESP_ERROR_CHECK(pcnt_unit_start(_pcnt_unit));
    ESP_ERROR_CHECK(mcpwm_timer_start_stop(_timer,MCPWM_TIMER_START_NO_STOP));
    time_to_wait = _steps/_freq;

    return 0;
}

int Stepper::interrupt() {
    unsigned initially_wanted_steps = _steps;
    _steps = 0;
    ESP_ERROR_CHECK(mcpwm_timer_start_stop(_timer,MCPWM_TIMER_STOP_EMPTY)); // stop timer : no pwm is outputted 
    ESP_ERROR_CHECK(pcnt_unit_stop(_pcnt_unit)); //stop counter to prevent any trigger event unwanted (paranoia)
    ESP_ERROR_CHECK(pcnt_unit_remove_watch_point(_pcnt_unit, initially_wanted_steps)); // remove interrupt trigger (will be set by next set_step)

    ESP_ERROR_CHECK(mcpwm_generator_set_force_level(_generator, 0, true)); // force output at 0 (else is at 1 don't know why)
    ESP_ERROR_CHECK(gpio_set_level(_dirGPIO, 0)); // dir GPIO returns to default state
    return 0;
}

bool Stepper::is_available() {
    return _steps != 0;
}

int Stepper::get_steps(int &remaining_steps){
    if (is_available()) {
        remaining_steps = 0;
        return 0;
    }
    int steps_done;
    pcnt_unit_get_count(_pcnt_unit, &steps_done);
    remaining_steps = _steps - steps_done;
    return 0;
}
