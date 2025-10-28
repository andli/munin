// LED effects: simple face-change flash
#ifndef MUNIN_LED_EFFECTS_H
#define MUNIN_LED_EFFECTS_H

#include <stdint.h>


typedef enum {
	LED_TARGET_ONBOARD_RGB = 0,
	LED_TARGET_SK6812 = 1,
} led_target_t;

void munin_led_set_target(led_target_t target);
led_target_t munin_led_get_target(void);

int munin_led_effects_init(void);
void munin_led_effects_update(void); /* call periodically */
void munin_led_face_flash(uint8_t face_id); /* trigger flash */
void munin_led_face_flash_ms(uint8_t face_id, uint16_t total_ms);

#endif
