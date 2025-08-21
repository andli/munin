#include "battery.h"
#include "munin_protocol.h"
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>

LOG_MODULE_REGISTER(battery, LOG_LEVEL_INF);

// Battery monitoring configuration
#define BATTERY_ADC_RESOLUTION 12
#define BATTERY_ADC_GAIN ADC_GAIN_1_6
#define BATTERY_ADC_REFERENCE ADC_REF_INTERNAL
#define BATTERY_ADC_ACQUISITION_TIME ADC_ACQ_TIME_DEFAULT

// Battery voltage thresholds (mV)
#define BATTERY_MIN_VOLTAGE_MV 3300  // 0% - cutoff voltage
#define BATTERY_MAX_VOLTAGE_MV 4200  // 100% - full charge voltage
#define BATTERY_LOW_VOLTAGE_MV 3500  // Low battery warning

// Update intervals
#define BATTERY_UPDATE_INTERVAL_MS 30000  // 30 seconds
#define CHARGING_CHECK_INTERVAL_MS 5000   // 5 seconds

// Static variables
static const struct device *adc_dev;
static struct adc_channel_cfg adc_cfg;
static struct adc_sequence adc_seq;
static int16_t adc_sample_buffer[1];

static uint16_t battery_voltage_mv = 0;
static uint8_t battery_percentage = 0;
static bool battery_connected = false;
static bool battery_charging = false;
static bool battery_low_warned = false;

static int64_t last_battery_update = 0;
static int64_t last_charging_check = 0;

// Function to convert voltage to percentage
static uint8_t voltage_to_percentage(uint16_t voltage_mv)
{
    if (voltage_mv <= BATTERY_MIN_VOLTAGE_MV) {
        return 0;
    }
    if (voltage_mv >= BATTERY_MAX_VOLTAGE_MV) {
        return 100;
    }
    
    // Linear interpolation
    return (uint8_t)(((voltage_mv - BATTERY_MIN_VOLTAGE_MV) * 100) / 
                     (BATTERY_MAX_VOLTAGE_MV - BATTERY_MIN_VOLTAGE_MV));
}

int munin_battery_init(void)
{
    int ret;
    
    LOG_INF("Initializing battery monitoring");
    
    // Get ADC device
    adc_dev = DEVICE_DT_GET(DT_ALIAS(adcctrl));
    if (!device_is_ready(adc_dev)) {
        LOG_ERR("ADC device not ready");
        return -1;
    }
    
    // Configure ADC channel for battery voltage reading
    adc_cfg.gain = BATTERY_ADC_GAIN;
    adc_cfg.reference = BATTERY_ADC_REFERENCE;
    adc_cfg.acquisition_time = BATTERY_ADC_ACQUISITION_TIME;
    adc_cfg.channel_id = 0;  // Use appropriate channel for battery
    adc_cfg.differential = 0;
    
    ret = adc_channel_setup(adc_dev, &adc_cfg);
    if (ret) {
        LOG_ERR("Failed to setup ADC channel: %d", ret);
        return ret;
    }
    
    // Configure ADC sequence
    adc_seq.channels = BIT(adc_cfg.channel_id);
    adc_seq.buffer = adc_sample_buffer;
    adc_seq.buffer_size = sizeof(adc_sample_buffer);
    adc_seq.resolution = BATTERY_ADC_RESOLUTION;
    
    LOG_INF("Battery monitoring initialized");
    return 0;
}

void munin_battery_update(void)
{
    int64_t now = k_uptime_get();
    int ret;
    
    // Update battery voltage reading
    if (now - last_battery_update >= BATTERY_UPDATE_INTERVAL_MS) {
        ret = adc_read(adc_dev, &adc_seq);
        if (ret == 0) {
            // Convert ADC reading to voltage (this needs calibration for real hardware)
            int32_t mv_value = adc_sample_buffer[0];
            adc_raw_to_millivolts(adc_ref_internal(adc_dev), 
                                  adc_cfg.gain, 
                                  adc_seq.resolution, 
                                  &mv_value);
            
            // Apply voltage divider correction if needed
            battery_voltage_mv = (uint16_t)mv_value * 2;  // Assuming 2:1 voltage divider
            
            // Check if battery is connected (reasonable voltage range)
            if (battery_voltage_mv > 2500 && battery_voltage_mv < 5000) {
                battery_connected = true;
                battery_percentage = voltage_to_percentage(battery_voltage_mv);
                
                LOG_INF("Battery: %u%% (%u mV)", battery_percentage, battery_voltage_mv);
                
                // Check for low battery
                if (battery_voltage_mv <= BATTERY_LOW_VOLTAGE_MV && !battery_charging && !battery_low_warned) {
                    LOG_WRN("LOW BATTERY WARNING!");
                    munin_packet_t packet;
                    munin_protocol_create_packet(&packet, MUNIN_EVENT_LOW_BATTERY, 
                                               k_uptime_get() / 1000, 0);
                    munin_protocol_send_packet(&packet);
                    battery_low_warned = true;
                } else if (battery_voltage_mv > (BATTERY_LOW_VOLTAGE_MV + 100)) {
                    battery_low_warned = false;  // Reset warning with hysteresis
                }
            } else {
                battery_connected = false;
                battery_voltage_mv = 0;
                battery_percentage = 0;
                LOG_INF("No battery detected");
            }
        } else {
            LOG_ERR("Failed to read ADC: %d", ret);
        }
        
        last_battery_update = now;
    }
    
    // Check charging status
    if (now - last_charging_check >= CHARGING_CHECK_INTERVAL_MS) {
        bool was_charging = battery_charging;
        
        if (!battery_connected) {
            battery_charging = false;
        } else {
            // TODO: Implement proper charging detection
            // This could be done via GPIO pin from BQ25101 or USB detection
            // For now, assume charging if USB connected (placeholder)
            battery_charging = true;  // Placeholder - implement real detection
        }
        
        // Send charging status events if changed
        if (battery_charging != was_charging && battery_connected) {
            munin_packet_t packet;
            if (battery_charging) {
                LOG_INF("CHARGING STARTED");
                munin_protocol_create_packet(&packet, MUNIN_EVENT_CHARGING_START, 
                                           k_uptime_get() / 1000, 0);
            } else {
                if (battery_percentage >= 95) {
                    LOG_INF("FULLY CHARGED");
                    munin_protocol_create_packet(&packet, MUNIN_EVENT_CHARGING_FULL, 
                                               k_uptime_get() / 1000, 0);
                } else {
                    LOG_INF("CHARGING STOPPED");
                    munin_protocol_create_packet(&packet, MUNIN_EVENT_CHARGING_STOP, 
                                               k_uptime_get() / 1000, 0);
                }
            }
            munin_protocol_send_packet(&packet);
        }
        
        last_charging_check = now;
    }
}

uint16_t munin_battery_get_voltage_mv(void)
{
    return battery_voltage_mv;
}

uint8_t munin_battery_get_percentage(void)
{
    return battery_percentage;
}

bool munin_battery_is_charging(void)
{
    return battery_charging;
}

bool munin_battery_is_connected(void)
{
    return battery_connected;
}
