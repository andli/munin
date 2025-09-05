// Local firmware LED color configuration (per face)
#ifndef MUNIN_LED_CONFIG_H
#define MUNIN_LED_CONFIG_H

#include <stdint.h>

typedef struct {
    uint8_t r, g, b;
} munin_rgb_t;

/* Returns pointer to array[6] of face colors (index 0 => face1). */
const munin_rgb_t *munin_led_get_face_colors(void);

#endif
