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

// Serial instances for Arduino compatibility
class HardwareSerial {
public:
    void begin(unsigned long baud) {
        // No-op for native platform, just print to indicate it's working
        printf("Serial.begin(%lu) - Native platform\n", baud);
    }
    
    void end() {}
    int available() { return 0; }
    int read() { return -1; }
    int peek() { return -1; }
    void flush() {}
    
    size_t write(uint8_t byte) {
        putchar(byte);
        return 1;
    }
    
    size_t write(const char *str) {
        if (str) printf("%s", str);
        return str ? strlen(str) : 0;
    }
    
    size_t write(const uint8_t *buffer, size_t size) {
        if (buffer) {
            for (size_t i = 0; i < size; i++) {
                putchar(buffer[i]);
            }
        }
        return size;
    }
    
    void print(const char str[]) { if (str) printf("%s", str); }
    void print(char c) { putchar(c); }
    void print(int n, int base = 10) { 
        if (base == 16) printf("%x", n);
        else printf("%d", n);
    }
    void print(unsigned int n, int base = 10) { 
        if (base == 16) printf("%x", n);
        else printf("%u", n);
    }
    void print(long n, int base = 10) { 
        if (base == 16) printf("%lx", n);
        else printf("%ld", n);
    }
    void print(unsigned long n, int base = 10) { 
        if (base == 16) printf("%lx", n);
        else printf("%lu", n);
    }
    void print(double n, int digits = 2) { printf("%.*f", digits, n); }
    
    void println(const char str[]) { print(str); putchar('\n'); }
    void println(char c) { print(c); putchar('\n'); }
    void println(int n, int base = 10) { print(n, base); putchar('\n'); }
    void println(unsigned int n, int base = 10) { print(n, base); putchar('\n'); }
    void println(long n, int base = 10) { print(n, base); putchar('\n'); }
    void println(unsigned long n, int base = 10) { print(n, base); putchar('\n'); }
    void println(double n, int digits = 2) { print(n, digits); putchar('\n'); }
    void println(void) { putchar('\n'); }
    
    operator bool() { return true; }
};

// Global Serial instances
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