// FastLED-specific Arduino function implementations for native platforms
// This file provides implementations without including Arduino.h since FastLED provides its own headers
#include <time.h>
#include <unistd.h>
#include <cstdlib>
#include <cstdint>
#include <cstdio>
#include <cstring>

// FastLED compatibility macros
#ifndef FL_UNUSED
#define FL_UNUSED(x) ((void)(x))
#endif

// Global time tracking for Arduino timing functions
static struct timespec arduino_start_time;
static bool time_initialized = false;

// Initialize timing
static void init_time() {
    if (!time_initialized) {
        clock_gettime(CLOCK_MONOTONIC, &arduino_start_time);
        time_initialized = true;
        // Initialize random seed
        srand((unsigned int)time(NULL));
    }
}

// Timing functions that FastLED needs
extern "C" {

unsigned long millis(void) {
    init_time();
    struct timespec current_time;
    clock_gettime(CLOCK_MONOTONIC, &current_time);
    
    long seconds = current_time.tv_sec - arduino_start_time.tv_sec;
    long nanoseconds = current_time.tv_nsec - arduino_start_time.tv_nsec;
    
    return (unsigned long)(seconds * 1000 + nanoseconds / 1000000);
}

unsigned long micros(void) {
    init_time();
    struct timespec current_time;
    clock_gettime(CLOCK_MONOTONIC, &current_time);
    
    long seconds = current_time.tv_sec - arduino_start_time.tv_sec;
    long nanoseconds = current_time.tv_nsec - arduino_start_time.tv_nsec;
    
    return (unsigned long)(seconds * 1000000 + nanoseconds / 1000);
}

void delay(unsigned long ms) {
    usleep(ms * 1000);
}

void delayMicroseconds(unsigned int us) {
    usleep(us);
}

void yield(void) {
    // Simple yield implementation - just a small delay
    usleep(1);
}

// Pin functions that FastLED sensors need
void pinMode(uint8_t pin, uint8_t mode) {
    // No-op on native platform
    (void)pin;
    (void)mode;
}

void digitalWrite(uint8_t pin, uint8_t val) {
    // No-op on native platform
    (void)pin;
    (void)val;
}

int digitalRead(uint8_t pin) {
    // Return LOW for native platform
    (void)pin;
    return 0; // LOW
}

int analogRead(uint8_t pin) {
    // Return 0 for native platform
    (void)pin;
    return 0;
}

void analogReference(uint8_t mode) {
    // No-op on native platform
    (void)mode;
}

void analogWrite(uint8_t pin, int val) {
    // No-op on native platform
    (void)pin;
    (void)val;
}

void randomSeed(unsigned long seed) {
    srand(seed);
}

} // extern "C"

// FastLED native-platform Serial stub
// Provides global Serial and Serial1 objects expected by MIDI library when compiling with FastLED's host stub.
// All functions are lightweight no-ops – sufficient for successful linking.

// -----------------------------------------------------------------------------
// Inline helper – write C-string to stdout (used by print/println variants)
// -----------------------------------------------------------------------------
static inline void _serial_write_str(const char *s) {
    if (s != nullptr) std::fputs(s, stdout);
}

// -----------------------------------------------------------------------------
// HardwareSerial method implementations – extremely lightweight.
// -----------------------------------------------------------------------------
void HardwareSerial::begin(unsigned long baud) { (void)baud; /* no-op */ }
void HardwareSerial::end() {}
int  HardwareSerial::available() { return 0; }
int  HardwareSerial::read() { return -1; }
int  HardwareSerial::peek() { return -1; }
void HardwareSerial::flush() { std::fflush(stdout); }

size_t HardwareSerial::write(uint8_t b) {
    std::fputc(static_cast<int>(b), stdout);
    return 1;
}

size_t HardwareSerial::write(const char *str) {
    _serial_write_str(str);
    return str ? std::strlen(str) : 0;
}

size_t HardwareSerial::write(const uint8_t *buf, size_t n) {
    if (buf != nullptr) for (size_t i = 0; i < n; ++i) std::fputc(buf[i], stdout);
    return n;
}

#define SERIAL_IMPL_PRINT(type)                                                        \
    void HardwareSerial::print(type v, int base) {                                    \
        if (base == 16) std::printf("%x", static_cast<unsigned int>(v));            \
        else            std::printf("%d", static_cast<int>(v));                     \
    }                                                                                 \
    void HardwareSerial::println(type v, int base) { print(v, base); std::fputc('\n', stdout); }

SERIAL_IMPL_PRINT(char)
SERIAL_IMPL_PRINT(int)
SERIAL_IMPL_PRINT(unsigned int)
SERIAL_IMPL_PRINT(long)
SERIAL_IMPL_PRINT(unsigned long)

void HardwareSerial::print(const char str[])   { _serial_write_str(str); }
void HardwareSerial::println(const char str[]) { _serial_write_str(str); std::fputc('\n', stdout);} 
void HardwareSerial::print(double d, int digits)   { std::printf("%.*f", digits, d); }
void HardwareSerial::println(double d, int digits) { print(d, digits); std::fputc('\n', stdout);} 
void HardwareSerial::println() { std::fputc('\n', stdout);}                                    

// -----------------------------------------------------------------------------
// Global Serial objects
// -----------------------------------------------------------------------------
HardwareSerial Serial;
HardwareSerial Serial1;

// Random functions using C++ overloading (outside extern "C")
long random(long max) {
    init_time();
    return rand() % max;
}

long random(long min, long max) {
    init_time();
    return min + (rand() % (max - min));
} 