#ifndef ARDUINO_H
#define ARDUINO_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>
#include <cstdio>
#include <cstring>

// Serial constants - define early to avoid issues
#define DEC 10
#define HEX 16
#define OCT 8
#define BIN 2

#ifdef __cplusplus
extern "C" {
#endif

// Arduino constants
#define HIGH 0x1
#define LOW  0x0

#ifndef INPUT
#define INPUT 0x0
#endif // INPUT

#ifndef OUTPUT
#define OUTPUT 0x1
#endif // OUTPUT

#ifndef INPUT_PULLUP    
#define INPUT_PULLUP 0x2
#endif // INPUT_PULLUP

#ifndef LED_BUILTIN
#define LED_BUILTIN 13
#endif // LED_BUILTIN

#define true 0x1
#define false 0x0

// Arduino data types
typedef bool boolean;
typedef uint8_t byte;

// -------------------------------------------------------------
// Core timing helpers – always declare so headers can use them
// FastLED's stub generic header expects **exactly** these signatures.
// -------------------------------------------------------------
uint32_t millis(void);
uint32_t micros(void);
void     delay(int ms);
void     delayMicroseconds(unsigned int us);

// Pin functions (no-op implementations for native platform)
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t val);
// digitalRead/analogRead provided as static inline stubs below
void analogReference(uint8_t mode);
void analogWrite(uint8_t pin, int val);

inline long map(long x, long in_min, long in_max, long out_min, long out_max) {
    const long run = in_max - in_min;
    if (run == 0) {
        return 0; // AVR returns -1, SAM returns 0
    }
    const long rise = out_max - out_min;
    const long delta = x - in_min;
    return (delta * rise) / run + out_min;
}

// Timing functions - declare but don't conflict with FastLED  
// Use FastLED's expected signatures when available
#ifndef FASTLED_STUB_IMPL
uint32_t millis(void);
uint32_t micros(void);
void delay(int ms);
void delayMicroseconds(unsigned int us);
#endif

// Don't declare random functions in extern "C" to avoid conflicts
void randomSeed(unsigned long);

// Map function
long map(long, long, long, long, long);

// Bit manipulation
#define lowByte(w) ((uint8_t) ((w) & 0xff))
#define highByte(w) ((uint8_t) ((w) >> 8))

#define bitRead(value, bit) (((value) >> (bit)) & 0x01)
#define bitSet(value, bit) ((value) |= (1UL << (bit)))
#define bitClear(value, bit) ((value) &= ~(1UL << (bit)))
#define bitWrite(value, bit, bitvalue) (bitvalue ? bitSet(value, bit) : bitClear(value, bit))

#define bit(b) (1UL << (b))

// Program space macros (no-op on native)
#define PROGMEM
#define pgm_read_byte(addr) (*(const unsigned char *)(addr))
#define pgm_read_word(addr) (*(const unsigned short *)(addr))
#define pgm_read_dword(addr) (*(const unsigned long *)(addr))

// String constants in program space
#define F(string_literal) (string_literal)

// String class (basic implementation)
class String {
private:
    char *buffer;
    unsigned int _capacity;
    unsigned int _length;

public:
    String(const char *cstr = "");
    String(const String &str);
    ~String();
    
    String& operator=(const String &rhs);
    String& operator=(const char *cstr);
    
    bool operator==(const String &rhs) const;
    bool operator!=(const String &rhs) const;
    
    String operator+(const String &rhs) const;
    String& operator+=(const String &rhs);
    
    char charAt(unsigned int index) const;
    void setCharAt(unsigned int index, char c);
    char operator[](unsigned int index) const;
    
    unsigned int length() const { return _length; }
    const char* c_str() const { return buffer; }
    
    int indexOf(char ch) const;
    int indexOf(const String &str) const;
    
    String substring(unsigned int beginIndex) const;
    String substring(unsigned int beginIndex, unsigned int endIndex) const;
    
    void toUpperCase();
    void toLowerCase();
    void trim();
    
    long toInt() const;
    double toFloat() const;
};

// Serial I/O ------------------------------------------------------------------
class HardwareSerial {
public:
    inline void begin(unsigned long /*baud*/) {}
    inline void end() {}
    inline int  available() { return 0; }
    inline int  read() { return -1; }
    inline int  peek() { return -1; }
    inline void flush() { std::fflush(stdout); }

    inline size_t write(uint8_t b) {
        std::fputc(static_cast<int>(b), stdout);
        return 1;
    }
    inline size_t write(const char *str) {
        if (str) std::fputs(str, stdout);
        return str ? std::strlen(str) : 0;
    }
    inline size_t write(const uint8_t *buf, size_t n) {
        if (buf) for (size_t i = 0; i < n; ++i) std::fputc(buf[i], stdout);
        return n;
    }

    // print / println helpers ------------------------------------------------
    inline void print(const char s[]) { if (s) std::fputs(s, stdout); }
    inline void println(const char s[]) { print(s); std::fputc('\n', stdout); }

    inline void print(char c) { std::fputc(c, stdout); }
    inline void println(char c) { print(c); std::fputc('\n', stdout); }

    inline void print(int n, int base = 10)  { base == 16 ? std::printf("%x", n) : std::printf("%d", n); }
    inline void print(unsigned int n, int base = 10)  { base == 16 ? std::printf("%x", n) : std::printf("%u", n); }
    inline void print(long n, int base = 10) { base == 16 ? std::printf("%lx", n) : std::printf("%ld", n); }
    inline void print(unsigned long n, int base = 10) { base == 16 ? std::printf("%lx", n) : std::printf("%lu", n); }
    inline void print(double d, int digits = 2) { std::printf("%.*f", digits, d); }

    inline void println(int n, int base = 10)  { print(n, base); std::fputc('\n', stdout); }
    inline void println(unsigned int n, int base = 10) { print(n, base); std::fputc('\n', stdout); }
    inline void println(long n, int base = 10) { print(n, base); std::fputc('\n', stdout); }
    inline void println(unsigned long n, int base = 10) { print(n, base); std::fputc('\n', stdout); }
    inline void println(double d, int digits = 2) { print(d, digits); std::fputc('\n', stdout); }
    inline void println() { std::fputc('\n', stdout); }

    inline operator bool() const { return true; }
};

extern HardwareSerial Serial;
extern HardwareSerial Serial1;  // For MIDI communication

// Interrupts (no-op for native)
#define cli()
#define sei()
#define interrupts() sei()
#define noInterrupts() cli()

// Inline stub pin reads for native platform
static inline int digitalRead(uint8_t /*pin*/) { return 0; }
static inline int analogRead(uint8_t /*pin*/)  { return 0; }

#ifdef __cplusplus
}
#endif

// ------------------------------------------------------------------
// Misc utility templates / functions expected by sketches
// ------------------------------------------------------------------

template<typename T> constexpr T min(T a, T b) { return (a < b) ? a : b; }
template<typename T> constexpr T max(T a, T b) { return (a > b) ? a : b; }

// Generic constrain
template<typename T> constexpr T constrain(T amt, T low, T high) {
    return (amt < low) ? low : ((amt > high) ? high : amt);
}

// Random overloads (using std::rand)
inline long random(long max_val) {
    return std::rand() % max_val;
}
inline long random(long min_val, long max_val) {
    if (min_val >= max_val) return min_val;
    return min_val + (std::rand() % (max_val - min_val));
}

#endif // ARDUINO_H 