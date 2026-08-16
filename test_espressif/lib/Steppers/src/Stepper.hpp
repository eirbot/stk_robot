#ifndef STEPPER_HPP
#define STEPPER_HPP

#include "driver/mcpwm_prelude.h"
#include "driver/pulse_cnt.h"
#include "driver/gpio.h"

#define DEFAULT_FREQ 1000 // in Hertz
#define PWM_RESOLUTION 10000
class Stepper{
    public:
        Stepper(int group_id,
                int intr_priority,
                int pwmGPIO,
                gpio_num_t dirGPIO,
                float gain_step,
                int max_pcnt);

        /** Init all the resources of both the pulse counter and the mcpwm.
         *
         *  Return 0 on success.
         */
        int init();

        // TODO: define min and max frequency
        /** Set frequency, e.g. the speed of the motor
         *
         *  Return 0 on success.
         */
        int set_frequency(int frequency);

        /** Launch in the hardware the achievement of the asked step number.
         *
         * Return by referencing the minimum required time to be awaited for the
         * stepper to end all its steps.
         * With awaiting this time after having called this method, the
         * stepper should be available again.
         *
         * Return 0 on success. If the stepper is still busy, reject the
         * launching, do not edit time_to_wait and return -1.
         *
         */
        int set_steps(int steps, unsigned int &time_to_wait);

        /** Stop the PWM, the PCnt, and set the stepper as available.
         *
         * Return 0 if the interrupt has been correctly achieved.
         *
         * This process does take in account the initially wanted step number.
         */
        int interrupt();

        /** If true, then the previous stepper's task has been completely
         * achieved.
         */
        bool is_available();

      private:
        void stop();

        int _freq = DEFAULT_FREQ;
        int _pwmGPIO;
        gpio_num_t _dirGPIO;
        float _gain_step;

        mcpwm_timer_config_t _timer_config;
        mcpwm_operator_config_t _operator_config;
        mcpwm_comparator_config_t _comparator_config;
        mcpwm_generator_config_t _generator_config;

        mcpwm_timer_handle_t _timer;
        mcpwm_oper_handle_t _oper;
        mcpwm_cmpr_handle_t _comparator;
        mcpwm_gen_handle_t _generator;

        pcnt_unit_config_t _unit_config;
        pcnt_chan_config_t _chan_config;

        pcnt_unit_handle_t _pcnt_unit;
        pcnt_channel_handle_t _pcnt_chan;

        int _steps;
        bool _is_busy = false;
        


};

#endif
