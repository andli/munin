// Minimal SK6812 (NeoPixel) 1-pixel driver for Zephyr
#ifndef MUNIN_SK6812_H
#define MUNIN_SK6812_H
#include <stdint.h>
#include <stdbool.h>
#include <zephyr/device.h>

// Configure the SK6812 data pin (Seeed XIAO BLE Sense D6 -> P1.11)
#define SK6812_PIN 11

// Set the color of the SK6812 LED (RGB, 0-255)
void sk6812_set_rgb(uint8_t r, uint8_t g, uint8_t b);

// Optionally, add init if needed
void sk6812_init(void);

bool sk6812_is_ready(void);

#endif
