#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>

#include "munin_protocol.h"
#include "battery.h"
#include "imu.h"
#include "ble.h"

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

#define MAIN_LOOP_INTERVAL_MS 1000

void main(void)
{
    int ret;
    
    LOG_INF("Starting Munin Device v2.0");
    
    // Initialize subsystems
    ret = munin_battery_init();
    if (ret) {
        LOG_ERR("Failed to initialize battery monitoring: %d", ret);
        return;
    }
    
    ret = munin_imu_init();
    if (ret) {
        LOG_ERR("Failed to initialize IMU: %d", ret);
        return;
    }
    
    ret = munin_ble_init();
    if (ret) {
        LOG_ERR("Failed to initialize BLE: %d", ret);
        return;
    }
    
    LOG_INF("All subsystems initialized successfully");
    
    // Main loop
    while (1) {
        // Update battery status
        munin_battery_update();
        
        // Check face changes
        munin_imu_update();
        
        // Process BLE events
        munin_ble_update();
        
        k_sleep(K_MSEC(MAIN_LOOP_INTERVAL_MS));
    }
}
