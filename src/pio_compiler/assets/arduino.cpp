#include "Arduino.h"
#include <time.h>
#include <unistd.h>
#include <iostream>
#include <cstring>
#include <cstdlib>

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

// Pin functions (no-op implementations for native platform)
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
    return LOW;
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

// Timing functions - always provide for native platforms
// Even FastLED projects need these implementations
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

// Additional function that FastLED uses
void yield(void) {
    // Simple yield implementation - just a small delay
    usleep(1);
}

// Random functions - only provide if FastLED stub is not being used
#ifndef FASTLED_STUB_IMPL
long random(long max_val) {
    return rand() % max_val;
}

long random(long min_val, long max_val) {
    if (min_val >= max_val) return min_val;
    return min_val + (rand() % (max_val - min_val));
}

void randomSeed(unsigned long seed) {
    srand(seed);
}
#endif

// Map function
long map(long x, long in_min, long in_max, long out_min, long out_max) {
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

// HardwareSerial implementation
HardwareSerial Serial;

void HardwareSerial::begin(unsigned long baud) {
    // No-op for native platform, just print to indicate it's working
    std::cout << "Serial.begin(" << baud << ") - Native platform" << std::endl;
}

void HardwareSerial::end() {
    // No-op
}

int HardwareSerial::available() {
    return 0;  // No data available on native platform
}

int HardwareSerial::read() {
    return -1;  // No data
}

int HardwareSerial::peek() {
    return -1;  // No data
}

void HardwareSerial::flush() {
    std::cout.flush();
}

size_t HardwareSerial::write(uint8_t byte) {
    std::cout << (char)byte;
    return 1;
}

size_t HardwareSerial::write(const char *str) {
    if (!str) return 0;
    std::cout << str;
    return strlen(str);
}

size_t HardwareSerial::write(const uint8_t *buffer, size_t size) {
    if (!buffer) return 0;
    for (size_t i = 0; i < size; i++) {
        std::cout << (char)buffer[i];
    }
    return size;
}

void HardwareSerial::print(const char str[]) {
    if (str) std::cout << str;
}

void HardwareSerial::print(char c) {
    std::cout << c;
}

void HardwareSerial::print(unsigned char b, int base) {
    if (base == DEC) {
        std::cout << (int)b;
    } else if (base == HEX) {
        std::cout << std::hex << (int)b << std::dec;
    } else if (base == OCT) {
        std::cout << std::oct << (int)b << std::dec;
    } else if (base == BIN) {
        // Binary output
        for (int i = 7; i >= 0; i--) {
            std::cout << ((b >> i) & 1);
        }
    }
}

void HardwareSerial::print(int n, int base) {
    if (base == DEC) {
        std::cout << n;
    } else if (base == HEX) {
        std::cout << std::hex << n << std::dec;
    } else if (base == OCT) {
        std::cout << std::oct << n << std::dec;
    } else if (base == BIN) {
        // Binary output
        if (n == 0) {
            std::cout << "0";
            return;
        }
        if (n < 0) {
            std::cout << "-";
            n = -n;
        }
        char binary[33];
        int i = 0;
        while (n > 0) {
            binary[i++] = (n % 2) + '0';
            n /= 2;
        }
        for (int j = i - 1; j >= 0; j--) {
            std::cout << binary[j];
        }
    }
}

void HardwareSerial::print(unsigned int n, int base) {
    print((unsigned long)n, base);
}

void HardwareSerial::print(long n, int base) {
    if (base == DEC) {
        std::cout << n;
    } else if (base == HEX) {
        std::cout << std::hex << n << std::dec;
    } else if (base == OCT) {
        std::cout << std::oct << n << std::dec;
    }
}

void HardwareSerial::print(unsigned long n, int base) {
    if (base == DEC) {
        std::cout << n;
    } else if (base == HEX) {
        std::cout << std::hex << n << std::dec;
    } else if (base == OCT) {
        std::cout << std::oct << n << std::dec;
    }
}

void HardwareSerial::print(double n, int digits) {
    std::cout.precision(digits);
    std::cout << std::fixed << n;
}

void HardwareSerial::println(const char c[]) {
    print(c);
    std::cout << std::endl;
}

void HardwareSerial::println(char c) {
    print(c);
    std::cout << std::endl;
}

void HardwareSerial::println(unsigned char b, int base) {
    print(b, base);
    std::cout << std::endl;
}

void HardwareSerial::println(int n, int base) {
    print(n, base);
    std::cout << std::endl;
}

void HardwareSerial::println(unsigned int n, int base) {
    print(n, base);
    std::cout << std::endl;
}

void HardwareSerial::println(long n, int base) {
    print(n, base);
    std::cout << std::endl;
}

void HardwareSerial::println(unsigned long n, int base) {
    print(n, base);
    std::cout << std::endl;
}

void HardwareSerial::println(double n, int digits) {
    print(n, digits);
    std::cout << std::endl;
}

void HardwareSerial::println(void) {
    std::cout << std::endl;
}

// String class implementation
String::String(const char *cstr) {
    if (cstr) {
        _length = strlen(cstr);
        _capacity = _length + 1;
        buffer = (char*)malloc(_capacity);
        strcpy(buffer, cstr);
    } else {
        _length = 0;
        _capacity = 1;
        buffer = (char*)malloc(_capacity);
        buffer[0] = '\0';
    }
}

String::String(const String &str) {
    _length = str._length;
    _capacity = str._capacity;
    buffer = (char*)malloc(_capacity);
    strcpy(buffer, str.buffer);
}

String::~String() {
    free(buffer);
}

String& String::operator=(const String &rhs) {
    if (this != &rhs) {
        free(buffer);
        _length = rhs._length;
        _capacity = rhs._capacity;
        buffer = (char*)malloc(_capacity);
        strcpy(buffer, rhs.buffer);
    }
    return *this;
}

String& String::operator=(const char *cstr) {
    free(buffer);
    if (cstr) {
        _length = strlen(cstr);
        _capacity = _length + 1;
        buffer = (char*)malloc(_capacity);
        strcpy(buffer, cstr);
    } else {
        _length = 0;
        _capacity = 1;
        buffer = (char*)malloc(_capacity);
        buffer[0] = '\0';
    }
    return *this;
}

bool String::operator==(const String &rhs) const {
    return strcmp(buffer, rhs.buffer) == 0;
}

bool String::operator!=(const String &rhs) const {
    return !(*this == rhs);
}

String String::operator+(const String &rhs) const {
    String result(*this);
    result += rhs;
    return result;
}

String& String::operator+=(const String &rhs) {
    unsigned int new_length = _length + rhs._length;
    if (new_length + 1 > _capacity) {
        _capacity = new_length + 1;
        buffer = (char*)realloc(buffer, _capacity);
    }
    strcat(buffer, rhs.buffer);
    _length = new_length;
    return *this;
}

char String::charAt(unsigned int index) const {
    if (index >= _length) return 0;
    return buffer[index];
}

void String::setCharAt(unsigned int index, char c) {
    if (index < _length) {
        buffer[index] = c;
    }
}

char String::operator[](unsigned int index) const {
    return charAt(index);
}

int String::indexOf(char ch) const {
    char *ptr = strchr(buffer, ch);
    return ptr ? (ptr - buffer) : -1;
}

int String::indexOf(const String &str) const {
    char *ptr = strstr(buffer, str.buffer);
    return ptr ? (ptr - buffer) : -1;
}

String String::substring(unsigned int beginIndex) const {
    return substring(beginIndex, _length);
}

String String::substring(unsigned int beginIndex, unsigned int endIndex) const {
    if (beginIndex >= _length) return String();
    if (endIndex > _length) endIndex = _length;
    if (beginIndex >= endIndex) return String();
    
    unsigned int sub_length = endIndex - beginIndex;
    char *sub_buffer = (char*)malloc(sub_length + 1);
    strncpy(sub_buffer, buffer + beginIndex, sub_length);
    sub_buffer[sub_length] = '\0';
    
    String result(sub_buffer);
    free(sub_buffer);
    return result;
}

void String::toUpperCase() {
    for (unsigned int i = 0; i < _length; i++) {
        if (buffer[i] >= 'a' && buffer[i] <= 'z') {
            buffer[i] = buffer[i] - 'a' + 'A';
        }
    }
}

void String::toLowerCase() {
    for (unsigned int i = 0; i < _length; i++) {
        if (buffer[i] >= 'A' && buffer[i] <= 'Z') {
            buffer[i] = buffer[i] - 'A' + 'a';
        }
    }
}

void String::trim() {
    // Trim leading whitespace
    while (_length > 0 && (buffer[0] == ' ' || buffer[0] == '\t' || buffer[0] == '\n' || buffer[0] == '\r')) {
        memmove(buffer, buffer + 1, _length);
        _length--;
    }
    
    // Trim trailing whitespace
    while (_length > 0 && (buffer[_length - 1] == ' ' || buffer[_length - 1] == '\t' || 
                          buffer[_length - 1] == '\n' || buffer[_length - 1] == '\r')) {
        _length--;
    }
    
    buffer[_length] = '\0';
}

long String::toInt() const {
    return atol(buffer);
}

double String::toFloat() const {
    return atof(buffer);
} 