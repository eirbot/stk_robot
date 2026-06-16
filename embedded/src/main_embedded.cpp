#include "qpcpp.hpp" // QP/C++ real-time embedded framework
#include "bsp.hpp"   // Board Support Package

//............................................................................
int main() {
    QP::QF::init();  // initialize the framework and the underlying RT kernel
    BSP::init();     // initialize the BSP and start the AOs
    return QP::QF::run(); // run the framework
}
