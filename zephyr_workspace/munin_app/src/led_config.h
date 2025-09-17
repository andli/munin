// Local firmware LED color configuration (per face)
#ifndef MUNIN_LED_CONFIG_H
#define MUNIN_LED_CONFIG_H

#include <stdint.h>

typedef struct {
    uint8_t r, g, b;
} munin_rgb_t;

/* Returns pointer to array[6] of face colors (index 0 => face1). */
const munin_rgb_t *munin_led_get_face_colors(void);

/* Update a single face color at runtime (face in 1..6). */
void munin_led_set_face_color(uint8_t face, uint8_t r, uint8_t g, uint8_t b);

#endif
