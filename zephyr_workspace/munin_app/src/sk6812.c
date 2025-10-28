// Minimal SK6812 (NeoPixel) 1-pixel driver for Zephyr (bit-banged)
#include "sk6812.h"
#include <zephyr/devicetree.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

#define SK6812_T0H_NS  300  // 0 bit, high time (ns)
#define SK6812_T1H_NS  600  // 1 bit, high time (ns)
#define SK6812_T0L_NS  900  // 0 bit, low time (ns)
#define SK6812_T1L_NS  600  // 1 bit, low time (ns)
#define SK6812_RESET_US 80  // Reset pulse (us)

static const struct device *const sk6812_gpio_dev = DEVICE_DT_GET(DT_NODELABEL(gpio1));
static int sk6812_init_ok = 0;

void sk6812_init(void) {
    if (sk6812_init_ok) {
        return;
    }
    printk("SK6812: init start (pin %d)\n", SK6812_PIN);
    if (!device_is_ready(sk6812_gpio_dev)) {
        printk("SK6812: GPIO device not ready\n");
        return;
    }
    int ret = gpio_pin_configure(sk6812_gpio_dev, SK6812_PIN, GPIO_OUTPUT_INACTIVE);
    if (ret != 0) {
        printk("SK6812: gpio_pin_configure failed for pin %d (ret=%d)\n", SK6812_PIN, ret);
        return;
    }
    sk6812_init_ok = 1;
    printk("SK6812: init OK on pin %d\n", SK6812_PIN);
}

static void sk6812_delay_ns(uint32_t ns) {
    // Zephyr doesn't provide sub-us delay, so use busy-wait loop
    // This is not precise, but works for a single LED at low clock speeds
    volatile uint32_t count = ns / 10;
    while (count--) {
        __asm__ volatile ("nop");
    }
}

static void sk6812_write_byte(uint8_t byte) {
    for (int i = 7; i >= 0; i--) {
        if (byte & (1 << i)) {
            gpio_pin_set(sk6812_gpio_dev, SK6812_PIN, 1);
            sk6812_delay_ns(SK6812_T1H_NS);
            gpio_pin_set(sk6812_gpio_dev, SK6812_PIN, 0);
            sk6812_delay_ns(SK6812_T1L_NS);
        } else {
            gpio_pin_set(sk6812_gpio_dev, SK6812_PIN, 1);
            sk6812_delay_ns(SK6812_T0H_NS);
            gpio_pin_set(sk6812_gpio_dev, SK6812_PIN, 0);
            sk6812_delay_ns(SK6812_T0L_NS);
        }
    }
}

void sk6812_set_rgb(uint8_t r, uint8_t g, uint8_t b) {
    sk6812_init();
    if (!sk6812_init_ok) {
        printk("SK6812: set_rgb skipped (init failed)\n");
        return;
    }
    printk("SK6812: set_rgb %d,%d,%d\n", r, g, b);
    unsigned int key = irq_lock();
    // SK6812 expects GRB order
    sk6812_write_byte(g);
    sk6812_write_byte(r);
    sk6812_write_byte(b);
    irq_unlock(key);
    k_busy_wait(SK6812_RESET_US); // Reset
}

bool sk6812_is_ready(void) {
    return sk6812_init_ok != 0;
}
