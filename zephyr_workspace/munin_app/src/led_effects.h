// LED effects: simple face-change flash
#ifndef MUNIN_LED_EFFECTS_H
#define MUNIN_LED_EFFECTS_H

#include <stdint.h>

int munin_led_effects_init(void);
void munin_led_effects_update(void); /* call periodically */
void munin_led_face_flash(uint8_t face_id); /* trigger flash */

#endif
