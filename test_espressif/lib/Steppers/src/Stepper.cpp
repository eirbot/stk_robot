#include "Stepper.hpp"

Stepper::Stepper(   mcpwm_timer_config_t timer_config,
                    mcpwm_operator_config_t operator_config,
                    mcpwm_comparator_config_t comparator_config,
                    mcpwm_generator_config_t generator_config,
                    float gain_step){
    _GPIO = GPIO;
    _MCPWM_UNIT = MCPWM_UNIT;
    _MCPWM_TIMER = MCPWM_TIMER;
    _MCPWM_OUTPUT_TIMER_OPERATOR = MCPWM_OUTPUT_TIMER_OPERATOR;    
}

bool Stepper::init(){
    mcpwm_gpio_init(
        _MCPWM_UNIT,
        _MCPWM_OUTPUT_TIMER_OPERATOR,
        _GPIO
    );
    mcpwm_config_t pwm_config = {
        .frequency = _freq,
        .cmpr_a = 50.0,
        .cmpr_b = 0.0,
        .duty_mode = MCPWM_DUTY_MODE_0,
        .counter_mode = MCPWM_UP_COUNTER
    };
    mcpwm_init(_MCPWM_UNIT, _MCPWM_TIMER, &pwm_config);
}

bool Stepper::set_frequency(int frequency){
    mcpwm_set_frequency(_MCPWM_UNIT, _MCPWM_TIMER, frequency);
    return 0;
}

int Stepper::set_steps(int steps){
    int time = steps/_freq; // in s
    mcpwm_start(_MCPWM_UNIT, _MCPWM_TIMER);
}