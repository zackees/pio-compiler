// FastLED-specific Arduino function implementations for native platforms
// This file provides implementations without including Arduino.h since FastLED provides its own headers
#include <time.h>
#include <unistd.h>
#include <cstdlib>
#include <cstdint>

// Global time tracking for Arduino timing functions
static struct timespec arduino_start_time;
static bool time_initialized = false;

// Initialize timing
static void init_time() {
    if (!time_initialized) {
        clock_gettime(CLOCK_MONOTONIC, &arduino_start_time);
        time_initialized = true;
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

} // extern "C" 