#ifndef STEPPER_HPP
#define STEPPER_HPP

#include "driver/mcpwm_prelude.h"
#include "driver/pulse_cnt.h"

#define DEFAULT_FREQ 1000 // in Hertz
#define PWM_RESOLUTION 10000
class Stepper{
    public:
        Stepper(int group_id,
                int intr_priority,
                int GPIO,
                mcpwm_timer_handle_t timer,
                mcpwm_oper_handle_t oper,
                mcpwm_cmpr_handle_t comparator,
                mcpwm_gen_handle_t generator,  
                float gain_step);
        bool init();
        //TODO: define min and max frequency
        bool set_frequency(int frequency); // set frequency e.g the speed of the motor
        int set_steps(int steps); // set number of step for the stepper and returns the time requiered for the steps to be achieved
    private:
        void stop();

        int _freq = DEFAULT_FREQ;
        int _GPIO;
        float _gain_step;

        mcpwm_timer_config_t _timer_config;
        mcpwm_operator_config_t _operator_config;
        mcpwm_comparator_config_t _comparator_config;
        mcpwm_generator_config_t _generator_config;

        mcpwm_timer_handle_t _timer = NULL;
        mcpwm_oper_handle_t _oper = NULL;
        mcpwm_cmpr_handle_t _comparator = NULL;
        mcpwm_gen_handle_t _generator = NULL;

        pcnt_unit_handle_t _pcnt;
        pcnt_channel_handle_t _pcnt_chan;
        


};

#endif