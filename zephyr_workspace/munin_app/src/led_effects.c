#include "led_effects.h"
#include "led_config.h"
#include "sk6812.h"
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

#include <zephyr/device.h>
#include "debug.h"



#define LED0_NODE DT_ALIAS(led0)
#define LED1_NODE DT_ALIAS(led1)
#define LED2_NODE DT_ALIAS(led2)
static const struct gpio_dt_spec led_red = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct gpio_dt_spec led_green = GPIO_DT_SPEC_GET(LED1_NODE, gpios);
static const struct gpio_dt_spec led_blue = GPIO_DT_SPEC_GET(LED2_NODE, gpios);

static led_target_t s_led_target = LED_TARGET_SK6812;

void munin_led_set_target(led_target_t target) {
    s_led_target = target;
}

led_target_t munin_led_get_target(void) {
    return s_led_target;
}

/* Set RGB LED color based on face */
static void set_led_color(uint8_t face_id, bool on)
{
    const munin_rgb_t *colors = munin_led_get_face_colors();
    munin_rgb_t color = {0, 0, 0};
    if (on && face_id >= 1 && face_id <= 6) {
        color = colors[face_id - 1];
    }
    if (s_led_target == LED_TARGET_SK6812 && sk6812_is_ready()) {
        sk6812_set_rgb(color.r, color.g, color.b);
        gpio_pin_set_dt(&led_red, 0);
        gpio_pin_set_dt(&led_green, 0);
        gpio_pin_set_dt(&led_blue, 0);
        return;
    }

    gpio_pin_set_dt(&led_red, color.r > 0 ? 1 : 0);
    gpio_pin_set_dt(&led_green, color.g > 0 ? 1 : 0);
    gpio_pin_set_dt(&led_blue, color.b > 0 ? 1 : 0);

    if (sk6812_is_ready()) {
        sk6812_set_rgb(0, 0, 0);
    }
}

static struct {
    uint8_t active;      /* 1 if a flash in progress */
    int64_t start_ms;    /* when flash started */
    uint8_t face;        /* face being flashed */
    uint16_t total_ms;   /* total duration of flash */
} s_flash;

/* Flash durations */
#define FLASH_TOTAL_MS 2000  /* 2 seconds flash duration */

int munin_led_effects_init(void)
{
    s_led_target = LED_TARGET_SK6812;
    sk6812_init();
    if (!sk6812_is_ready()) {
        printk("LED: SK6812 unavailable, using onboard RGB\n");
        s_led_target = LED_TARGET_ONBOARD_RGB;
    } else {
        sk6812_set_rgb(0, 0, 0);
        printk("LED: Using SK6812 on D6\n");
    }

    int ret = 0;
    if (!gpio_is_ready_dt(&led_red) || !gpio_is_ready_dt(&led_green) || !gpio_is_ready_dt(&led_blue)) {
        printk("LED: Onboard RGB GPIO not ready\n");
        // Don't fail, just warn
    } else {
        ret = gpio_pin_configure_dt(&led_red, GPIO_OUTPUT_INACTIVE);
        ret |= gpio_pin_configure_dt(&led_green, GPIO_OUTPUT_INACTIVE);
        ret |= gpio_pin_configure_dt(&led_blue, GPIO_OUTPUT_INACTIVE);
        if (ret < 0) {
            printk("LED: Failed to configure onboard RGB\n");
        }
    }
    printk("LED: target=%d (ready=%d)\n", s_led_target, sk6812_is_ready());
    return 0;
}

void munin_led_face_flash(uint8_t face_id)
{
    MLOG("LED: Flash start face=%d t=%lld\n", face_id, k_uptime_get());
    s_flash.active = 1;
    s_flash.start_ms = k_uptime_get();
    s_flash.face = face_id;
    s_flash.total_ms = FLASH_TOTAL_MS;
    
    /* Turn on the LED with face color */
    set_led_color(face_id, true);
    MLOG("LED: Set color face=%d\n", face_id);
}

void munin_led_face_flash_ms(uint8_t face_id, uint16_t total_ms)
{
    if (total_ms == 0) total_ms = 1; /* avoid zero */
    MLOG("LED: Flash(ms) start face=%d dur=%u t=%lld\n", face_id, total_ms, k_uptime_get());
    s_flash.active = 1;
    s_flash.start_ms = k_uptime_get();
    s_flash.face = face_id;
    s_flash.total_ms = total_ms;
    set_led_color(face_id, true);
}

void munin_led_effects_update(void)
{
    if (!s_flash.active) return;
    
    int64_t now = k_uptime_get();
    int64_t elapsed = now - s_flash.start_ms;
    
    uint16_t dur = s_flash.total_ms ? s_flash.total_ms : FLASH_TOTAL_MS;
    if (elapsed >= dur) {
        s_flash.active = 0;
        set_led_color(s_flash.face, false);  /* Turn OFF all LEDs */
    MLOG("LED: Flash end t=%lld dur=%lld\n", now, elapsed);
        return;
    }
    
    /* Simple pulse: on for first 60% then off */
    if (elapsed < (dur * 6 / 10)) {
        set_led_color(s_flash.face, true);   /* Turn ON with face color */
    } else {
        set_led_color(s_flash.face, false);  /* Turn OFF */
    }
}
