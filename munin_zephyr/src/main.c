#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/printk.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>

/* Use the red LED (led0) */
#define LED0_NODE DT_ALIAS(led0)
static const struct gpio_dt_spec red_led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

static void wait_for_dtr(const struct device *dev) {
#ifdef CONFIG_UART_LINE_CTRL
    uint32_t dtr = 0;
    /* Some hosts need us to assert DTR before they show data */
    (void)uart_line_ctrl_set(dev, UART_LINE_CTRL_DTR, 1);
    do {
        (void)uart_line_ctrl_get(dev, UART_LINE_CTRL_DTR, &dtr);
        k_msleep(50);
    } while (!dtr);
#endif
}

int main(void)
{
	const struct device *console = DEVICE_DT_GET_OR_NULL(DT_CHOSEN(zephyr_console));
	int ret;
	bool led_is_on = true;
	int counter = 0;
	
	printk("*** XIAO nRF52840 Sense - Starting ***\n");
	printk("Board: %s\n", CONFIG_BOARD);
	printk("Console device: %p\n", console);
	
	/* Check if LED GPIO is ready */
	if (!gpio_is_ready_dt(&red_led)) {
		printk("ERROR: Red LED GPIO not ready\n");
		return -1;
	}
	
	/* Configure LED as output */
	ret = gpio_pin_configure_dt(&red_led, GPIO_OUTPUT_ACTIVE);
	if (ret < 0) {
		printk("ERROR: Failed to configure red LED: %d\n", ret);
		return -1;
	}
	
	printk("Red LED configured successfully!\n");
	
	/* Optional: wait for terminal to assert DTR, if console exists */
	if (console && device_is_ready(console)) {
		wait_for_dtr(console);
	}

	printk("\n=== DTR DETECTED! TERMINAL CONNECTED! ===\n");
	printk("=== XIAO nRF52840 Sense Console Ready ===\n");
	printk("Hello from Zephyr USB CDC on XIAO nRF52840!\n\n");
	
	/* Blink forever */
	while (1) {
		gpio_pin_set_dt(&red_led, (int)led_is_on);
		
		printk("Blink %d: LED %s - Tick: %u ms\n", 
		       counter++, led_is_on ? "ON " : "OFF", (uint32_t)k_uptime_get());
		
		led_is_on = !led_is_on;
		k_msleep(1000);  /* Slower blink for easier console reading */
	}
	
	return 0;
}
