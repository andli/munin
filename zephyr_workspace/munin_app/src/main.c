// Stub for missing function to allow build
void wait_for_dtr(const struct device *dev) {
	(void)dev;
}

// Stub for missing function to allow build
static void munin_send_version_packet(void) {
	/* No-op stub */
}

#include <zephyr/sys/util.h> // For ARG_UNUSED
#include "led_effects.h"
#include "led_config.h"
#include "ble.h"
#include "imu.h"
#include "battery.h"
#include "munin_protocol.h"
#include "debug.h"

// Prototypes for local functions
static void munin_send_version_packet(void);


#ifndef MUNIN_DEBUG
#define MUNIN_DEBUG 0
#endif
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/printk.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/settings/settings.h>
#include <zephyr/bluetooth/services/bas.h>

#include "ble.h"
#include "imu.h"
#include "battery.h"
#include "munin_protocol.h"
#include "led_config.h"
int main(void)
{
	printk("=== Munin (Zephyr) BOOT ===\n");
	const struct device *console = DEVICE_DT_GET_OR_NULL(DT_CHOSEN(zephyr_console));
	int ret;

	printk("Console: %p\n", console);

	// LED target selection is now handled in led_effects_init and can be changed at runtime
	// Default is SK6812, fallback to onboard RGB if not present
	if (munin_led_effects_init()) {
		printk("LED effects init failed\n");
	}

	printk("Munin: after led_effects_init\n");

	if (console && device_is_ready(console)) {
		wait_for_dtr(console);
	}
	printk("Console ready. Initializing subsystems...\n");

	// Init settings subsystem first (required for BLE persistent identity)
	int settings_err = settings_subsys_init();
	if (settings_err) {
		printk("Settings subsystem init failed: %d\n", settings_err);
	} else {
		int load_ret = settings_load();
		printk("Settings load result: %d\n", load_ret);
	}

	// Init other subsystems
	if (munin_battery_init()) printk("Battery init failed\n");
	if (munin_imu_init()) printk("IMU init failed\n");
	if (munin_ble_init()) printk("BLE init failed\n");

	printk("Munin: after all subsystem init\n");

	/* Send version packet once BLE is up (client can log firmware version) */
	munin_send_version_packet();

	// Main loop
	int counter = 0;
	while (1) {
		uint8_t current_face = munin_imu_get_current_face();
		const munin_rgb_t *colors = munin_led_get_face_colors();
		munin_rgb_t c = colors[(current_face ? current_face : 1) - 1];

		munin_led_effects_update();

		/* Reduce console spam: only log every 20 iterations (~10s) when debug enabled */
		if (MUNIN_DEBUG && (counter % 20 == 0)) {
			printk("tick %d face=%u color=%u,%u,%u batt=%u%% conn=%d adv=%d\n", counter, current_face,
				   c.r, c.g, c.b,
				   munin_battery_get_percentage(), munin_ble_is_connected(), munin_ble_is_advertising());
		}
		counter++;

		munin_battery_update();
		munin_imu_update();
		munin_ble_update();

		k_sleep(K_MSEC(500));
	}
	return 0;
}
