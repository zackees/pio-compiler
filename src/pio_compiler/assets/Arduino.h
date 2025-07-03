#ifndef ARDUINO_H
#define ARDUINO_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>

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
int  digitalRead(uint8_t pin);
int  analogRead(uint8_t pin);
void analogReference(uint8_t mode);
void analogWrite(uint8_t pin, int val);

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

#ifdef __cplusplus
}

// FastLED compatibility macros
#ifndef FL_UNUSED
#define FL_UNUSED(x) ((void)(x))
#endif

#ifndef FASTLED_UNUSED
#define FASTLED_UNUSED(x) ((void)(x))
#endif

// Random functions (C++ overloads outside extern "C")
long random(long max);
long random(long min, long max);

// Math functions (templates must be outside extern "C")
template<typename T> constexpr T min(T a, T b) { return (a < b) ? a : b; }
template<typename T> constexpr T max(T a, T b) { return (a > b) ? a : b; }
template<typename T> constexpr T abs(T x) { return (x > 0) ? x : -x; }
template<typename T> constexpr T constrain(T amt, T low, T high) { return (amt < low) ? low : ((amt > high) ? high : amt); }
#else
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define abs(x) ((x)>0?(x):-(x))
#define constrain(amt,low,high) ((amt)<(low)?(low):((amt)>(high)?(high):(amt)))
#endif
#define round(x)     ((x)>=0?(long)((x)+0.5):(long)((x)-0.5))
#define radians(deg) ((deg)*DEG_TO_RAD)
#define degrees(rad) ((rad)*RAD_TO_DEG)
#define sq(x) ((x)*(x))

// Constants
#define PI 3.1415926535897932384626433832795
#define HALF_PI 1.5707963267948966192313216916398
#define TWO_PI 6.283185307179586476925286766559
#define DEG_TO_RAD 0.017453292519943295769236907684886
#define RAD_TO_DEG 57.295779513082320876798154814105

// Serial class (stub implementation)
class HardwareSerial {
public:
    void begin(unsigned long baud);
    void end();
    int available();
    int read();
    int peek();
    void flush();
    
    size_t write(uint8_t);
    size_t write(const char *str);
    size_t write(const uint8_t *buffer, size_t size);
    
    void print(const char[]);
    void print(char);
    void print(unsigned char, int = DEC);
    void print(int, int = DEC);
    void print(unsigned int, int = DEC);
    void print(long, int = DEC);
    void print(unsigned long, int = DEC);
    void print(double, int = 2);
    
    void println(const char[]);
    void println(char);
    void println(unsigned char, int = DEC);
    void println(int, int = DEC);
    void println(unsigned int, int = DEC);
    void println(long, int = DEC);
    void println(unsigned long, int = DEC);
    void println(double, int = 2);
    void println(void);
    
    operator bool() { return true; }
};

extern HardwareSerial Serial;
extern HardwareSerial Serial1;  // For MIDI communication

// Interrupts (no-op for native)
#define cli()
#define sei()
#define interrupts() sei()
#define noInterrupts() cli()

#endif // ARDUINO_H 