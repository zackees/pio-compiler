// Minimal I/O stub for native FastLED builds – fulfils unresolved symbols
#include "Arduino.h"

extern "C" {

int digitalRead(uint8_t /*pin*/) {
    return 0;  // Always LOW
}

int analogRead(uint8_t /*pin*/) {
    return 0;  // Always 0
}

} // extern "C" 