# Next steps

## Microcontroller software 

The logic-level software is ready to be implemented in concurrency
if the hardware driver can be piloted throughout non-blocking,
software/rtos-independant orders.
This has been done with the steppers, but with using ESP-IDF (latest) instead of
Arduino built upon ESP-IDF.

- [x] Independent stepper driver with MCPWM
- [ ] Serial communication: Arduino implementation -> ESP-IDF UART implementation
- [ ] Synchronized steppers
- [ ] Stepper controlled with speed instead of step number.
