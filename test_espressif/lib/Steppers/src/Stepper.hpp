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

        /** Launch in the hardware the achievement of the asked step number.
         *
         * Return the minimum required time to be awaited for the stepper to
         * end all its steps.
         * With awaiting this time after having called this method, the
         * stepper should be available again.
         *
         * If 0 is returned, then the launching has been rejected since the
         * stepper is still busy.
         */
        int set_steps(int steps);

        /** Stop the PWM, the PCnt, and set the stepper as available.
         *
         * Return true if the interrupt has been correctly achieved.
         *
         * This process does take in account the initially wanted step number.
         */
        bool interrupt();

        /** If true, then the previous stepper's task has been completely
         * achieved.
         */
        bool is_available();

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

        bool _is_busy = false;
        


};

#endif
