#include "led_config.h"

/* Runtime face colors initialized with defaults 
 * NOTE: These are initial fallback values only. The actual colors come from 
 * the client configuration via BLE. See munin_client/config.py for the 
 * authoritative default values.
 */
static munin_rgb_t s_face_colors[6] = {
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

void munin_led_set_face_color(uint8_t face, uint8_t r, uint8_t g, uint8_t b)
{
    if (face < 1 || face > 6) return;
    s_face_colors[face - 1].r = r;
    s_face_colors[face - 1].g = g;
    s_face_colors[face - 1].b = b;
}

