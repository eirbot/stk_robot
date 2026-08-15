#ifndef STEPPER_HPP
#define STEPPER_HPP

#include "driver/mcpwm_prelude.h"
#define DEFAULT_FREQ 1000 // in Hertz
#define PWM_RESOLUTION
class Stepper{
    public:
        Stepper(mcpwm_timer_config_t timer_config,
                mcpwm_operator_config_t operator_config,
                mcpwm_comparator_config_t comparator_config,
                mcpwm_generator_config_t generator_config,
                float gain_step);
        bool init();
        //TODO: define min and max frequency
        bool set_frequency(int frequency); // set frequency e.g the speed of the motor
        int set_steps(int steps); // set number of step for the stepper and returns the time requiered for the steps to be achieved
    private:
        int _freq = DEFAULT_FREQ;
        int _GPIO;
        mcpwm_timer_config_t _timer_config;
        mcpwm_operator_config_t _operator_config;
        mcpwm_comparator_config_t _comparator_config;
        mcpwm_generator_config_t _generator_config;

};

#endif