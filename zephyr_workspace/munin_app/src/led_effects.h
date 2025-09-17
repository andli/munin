// LED effects: simple face-change flash
#ifndef MUNIN_LED_EFFECTS_H
#define MUNIN_LED_EFFECTS_H

#include <stdint.h>

int munin_led_effects_init(void);
void munin_led_effects_update(void); /* call periodically */
void munin_led_face_flash(uint8_t face_id); /* trigger flash */
/* Trigger a face flash with a custom total duration in milliseconds (non-blocking). */
void munin_led_face_flash_ms(uint8_t face_id, uint16_t total_ms);

#endif
