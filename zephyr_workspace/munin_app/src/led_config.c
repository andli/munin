#include "led_config.h"

/* Default firmware-embedded colors (match README defaults) */
static const munin_rgb_t s_face_colors[6] = {
    {255,   0,   0}, // Face 1: Red
    {  0, 255,   0}, // Face 2: Green
    {  0,   0, 255}, // Face 3: Blue
    {255, 255,   0}, // Face 4: Yellow
    {255,   0, 255}, // Face 5: Magenta
    {128, 128, 128}, // Face 6: Gray
};

const munin_rgb_t *munin_led_get_face_colors(void)
{
    return s_face_colors;
}
