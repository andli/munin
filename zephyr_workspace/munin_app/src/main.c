#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/printk.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>

#include "ble.h"
#include "imu.h"
#include "battery.h"
#include "munin_protocol.h"

/* Use the red LED (led0) */
#define LED0_NODE DT_ALIAS(led0)
static const struct gpio_dt_spec red_led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

static void wait_for_dtr(const struct device *dev) {
#ifdef CONFIG_UART_LINE_CTRL
	uint32_t dtr = 0;
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

	printk("*** Munin (Zephyr) starting on %s ***\n", CONFIG_BOARD);
	printk("Console: %p\n", console);

	if (!gpio_is_ready_dt(&red_led)) {
		printk("LED not ready\n");
		return -1;
	}
	ret = gpio_pin_configure_dt(&red_led, GPIO_OUTPUT_ACTIVE);
	if (ret) return ret;

	if (console && device_is_ready(console)) {
		wait_for_dtr(console);
	}
	printk("Console ready. Initializing subsystems...\n");

	// Init subsystems
	if (munin_battery_init()) printk("Battery init failed\n");
	if (munin_imu_init()) printk("IMU init failed\n");
	if (munin_ble_init()) printk("BLE init failed\n");

	// Main loop
	bool led = true;
	int counter = 0;
	while (1) {
		// Show face-based LED behavior (less annoying)
		uint8_t current_face = munin_imu_get_current_face();
		if (current_face == 0) {
			// Face 0 (unknown/flat) - slow blink (once every 2 seconds)
			if ((counter % 4) == 0) {
				led = !led;
			}
			gpio_pin_set_dt(&red_led, (int)led);
		} else {
			// For detected faces 1-6, show solid LED (no blinking)
			gpio_pin_set_dt(&red_led, 1);
		}
		
		printk("tick %d face=%u batt=%u%% conn=%d\n", counter++, current_face,
			   munin_battery_get_percentage(), munin_ble_is_connected());

		munin_battery_update();
		munin_imu_update();
		munin_ble_update();

		k_sleep(K_MSEC(500));
	}
	return 0;
}
