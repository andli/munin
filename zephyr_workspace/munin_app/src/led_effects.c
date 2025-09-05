#include "led_effects.h"
#include "led_config.h"
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/device.h>

/* The devicetree node identifiers for all RGB LEDs */
#define LED0_NODE DT_ALIAS(led0)  /* Red LED */
#define LED1_NODE DT_ALIAS(led1)  /* Green LED */
#define LED2_NODE DT_ALIAS(led2)  /* Blue LED */

static const struct gpio_dt_spec led_red = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct gpio_dt_spec led_green = GPIO_DT_SPEC_GET(LED1_NODE, gpios);
static const struct gpio_dt_spec led_blue = GPIO_DT_SPEC_GET(LED2_NODE, gpios);

/* Set RGB LED color based on face */
static void set_led_color(uint8_t face_id, bool on)
{
    const munin_rgb_t *colors = munin_led_get_face_colors();
    munin_rgb_t color = {0, 0, 0}; /* Default off */
    
    if (on && face_id >= 1 && face_id <= 6) {
        color = colors[face_id - 1];
    }
    
    /* Set each LED based on color values (on/off only) */
    gpio_pin_set_dt(&led_red, color.r > 0 ? 1 : 0);
    gpio_pin_set_dt(&led_green, color.g > 0 ? 1 : 0);
    gpio_pin_set_dt(&led_blue, color.b > 0 ? 1 : 0);
}

static struct {
    uint8_t active;      /* 1 if a flash in progress */
    int64_t start_ms;    /* when flash started */
    uint8_t face;        /* face being flashed */
} s_flash;

/* Flash durations */
#define FLASH_TOTAL_MS 2000  /* 2 seconds flash duration */

int munin_led_effects_init(void)
{
    printk("LED: Checking if RGB LEDs are ready...\n");
    
    /* Check all three LEDs */
    if (!gpio_is_ready_dt(&led_red)) {
        printk("LED: Red LED GPIO device not ready\n");
        return -1;
    }
    if (!gpio_is_ready_dt(&led_green)) {
        printk("LED: Green LED GPIO device not ready\n");
        return -1;
    }
    if (!gpio_is_ready_dt(&led_blue)) {
        printk("LED: Blue LED GPIO device not ready\n");
        return -1;
    }
    
    /* Configure all three LEDs */
    int ret;
    ret = gpio_pin_configure_dt(&led_red, GPIO_OUTPUT_ACTIVE);
    if (ret < 0) {
        printk("LED: Failed to configure Red LED GPIO: %d\n", ret);
        return ret;
    }
    
    ret = gpio_pin_configure_dt(&led_green, GPIO_OUTPUT_ACTIVE);
    if (ret < 0) {
        printk("LED: Failed to configure Green LED GPIO: %d\n", ret);
        return ret;
    }
    
    ret = gpio_pin_configure_dt(&led_blue, GPIO_OUTPUT_ACTIVE);
    if (ret < 0) {
        printk("LED: Failed to configure Blue LED GPIO: %d\n", ret);
        return ret;
    }
    
    printk("LED: Successfully configured all RGB LEDs\n");
    
    /* Test the RGB LEDs with a quick color sequence */
    printk("LED: Testing RGB sequence...\n");
    
    /* Red */
    set_led_color(1, true);  /* Face 1 = Red */
    k_sleep(K_MSEC(300));
    set_led_color(1, false);
    
    /* Green */
    set_led_color(2, true);  /* Face 2 = Green */
    k_sleep(K_MSEC(300));
    set_led_color(2, false);
    
    /* Blue */
    set_led_color(3, true);  /* Face 3 = Blue */
    k_sleep(K_MSEC(300));
    set_led_color(3, false);
    
    printk("LED: RGB test complete\n");
    
    return 0;
}

void munin_led_face_flash(uint8_t face_id)
{
    printk("LED: Starting flash for face %d at %lld ms\n", face_id, k_uptime_get());
    s_flash.active = 1;
    s_flash.start_ms = k_uptime_get();
    s_flash.face = face_id;
    
    /* Turn on the LED with face color */
    set_led_color(face_id, true);
    printk("LED: Set color for face %d\n", face_id);
}

void munin_led_effects_update(void)
{
    if (!s_flash.active) return;
    
    int64_t now = k_uptime_get();
    int64_t elapsed = now - s_flash.start_ms;
    
    if (elapsed >= FLASH_TOTAL_MS) {
        s_flash.active = 0;
        set_led_color(s_flash.face, false);  /* Turn OFF all LEDs */
        printk("LED: Flash ended at %lld ms (duration %lld ms)\n", now, elapsed);
        return;
    }
    
    /* Simple pulse: on for first 60% then off */
    if (elapsed < (FLASH_TOTAL_MS * 6 / 10)) {
        set_led_color(s_flash.face, true);   /* Turn ON with face color */
    } else {
        set_led_color(s_flash.face, false);  /* Turn OFF */
    }
}
