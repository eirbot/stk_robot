# Next steps

## Microcontroller software 

The logic-level software is ready to be implemented in concurrency
if the hardware driver can be piloted throughout non-blocking,
software/rtos-independant orders.
This has been done with the steppers, but with using ESP-IDF (latest) instead of
Arduino built upon ESP-IDF.

- [x] Independent stepper driver with MCPWM
- [ ] Serial communication: Arduino implementation -> ESP-IDF SPI implementation
   - [ ] define SPI commands for position control
- [ ] Stepper controlled with speed instead of position.
   - [ ] define max and min acceleration
   - [ ] define max and min speed
   - [ ] break position command into speed trapezoid
   - [ ] define SPI commands for speed control 
- [ ] Synchronized steppers for wheels
