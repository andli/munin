#include "battery.h"
#include "munin_protocol.h"
#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/device.h>
#include <zephyr/bluetooth/services/bas.h>
#include <hal/nrf_saadc.h>
#include "debug.h"

/* ADC configuration for battery voltage reading */
#define ADC_NODE DT_NODELABEL(adc)
#define ADC_RESOLUTION 12
#define ADC_GAIN ADC_GAIN_1_6
#define ADC_REFERENCE ADC_REF_INTERNAL
#define ADC_ACQUISITION_TIME ADC_ACQ_TIME_DEFAULT

/* Battery voltage divider configuration for XIAO BLE Sense */
#define BATTERY_ADC_CHANNEL 2  /* P0.31/AIN2 used for battery voltage */

/* Charging detection GPIO - P0.17 on XIAO BLE Sense (CHG pin) */
#define CHARGE_GPIO_NODE DT_NODELABEL(gpio0)
#define CHARGE_PIN 17

static const struct device *adc_dev;
static const struct device *gpio_dev;
static struct adc_channel_cfg m_1st_channel_cfg = {
    .gain = ADC_GAIN_1_6,
    .reference = ADC_REF_INTERNAL,
    .acquisition_time = ADC_ACQ_TIME_DEFAULT,
    .channel_id = BATTERY_ADC_CHANNEL,
    #if CONFIG_ADC_NRFX_SAADC
    .input_positive = NRF_SAADC_INPUT_AIN2,  /* P0.31 */
    #endif
};

static uint16_t s_mv = 4000;
static uint8_t s_pct = 100;
static bool s_chg = false;

/* Convert raw battery voltage (mV) to percentage (0-100)
 * Based on typical LiPo discharge curve for 3.7V nominal battery (EEMB 803030)
 * LiPo discharge curve: 4.2V (100%) -> 3.7V (50%) -> 3.0V (0%)
 */
static uint8_t voltage_to_percentage(uint16_t mv, bool is_charging)
{
    ARG_UNUSED(is_charging);
    static const struct { uint16_t mv; uint8_t pct; } table[] = {
        {3620,100},{3550,90},{3500,75},{3450,60},{3400,45},{3350,30},{3300,20},{3250,10},{3200,5},{3000,0}
    };
    for (size_t i = 0; i < (sizeof(table)/sizeof(table[0])); i++) {
        if (mv >= table[i].mv) return table[i].pct;
    }
    return 0;
}

/* Read battery voltage via ADC using proven XIAO BLE Sense approach */
static int read_battery_voltage(uint16_t *mv)
{
    const int num_samples = 8;  /* Average 8 readings for stability */
    int32_t sum = 0;
    
    struct adc_sequence sequence = {
        .channels = BIT(BATTERY_ADC_CHANNEL),
        .buffer_size = sizeof(int16_t),
        .resolution = ADC_RESOLUTION,
    };

    /* Take multiple samples and average them */
    for (int i = 0; i < num_samples; i++) {
        int16_t buf;
        sequence.buffer = &buf;
        
        int ret = adc_read(adc_dev, &sequence);
        if (ret < 0) {
            printk("Battery: ADC read failed: %d\n", ret);
            return ret;
        }
        
        sum += buf;
        
        /* Small delay between samples to reduce noise correlation */
        k_msleep(2);
    }
    
    /* Calculate average */
    int16_t avg_raw = sum / num_samples;
    
    /* Direct empirical calibration based on your measurement
     * Your multimeter: 3.62V
     * Our ADC reading: ~260 raw → ~670mV calculated  
     * Calibration factor needed: 3620mV / 670mV = 5.4
     */
    float vbat_raw = (float)avg_raw / 4096.0 * 3.6 * 2.96;
    float vbat_calibrated = vbat_raw * 5.4;  /* Apply empirical correction */
    *mv = (uint16_t)(vbat_calibrated * 1000);  /* Convert to millivolts */
    
    /* Debug output to understand ADC readings */
    MLOG("Battery: raw=%d avg_of=%d uncal=%dmV cal=%dmV\n", (int)avg_raw, num_samples, (int)(vbat_raw * 1000), (int)*mv);

    return 0;
}

/* Check charging status via GPIO */
static bool read_charging_status(void)
{
    /* On XIAO BLE Sense, charging pin goes LOW when charging */
    int val = gpio_pin_get(gpio_dev, CHARGE_PIN);
    return (val == 0);  /* Active low */
}

int munin_battery_init(void)
{
    printk("Battery: Initializing ADC and GPIO...\n");
    
    /* Get ADC device */
    adc_dev = DEVICE_DT_GET(ADC_NODE);
    if (!device_is_ready(adc_dev)) {
        printk("Battery: ADC device not ready\n");
        return -1;
    }

    /* Configure ADC channel */
    int ret = adc_channel_setup(adc_dev, &m_1st_channel_cfg);
    if (ret < 0) {
        printk("Battery: ADC channel setup failed: %d\n", ret);
        return ret;
    }

    /* Get GPIO device for charging detection */
    gpio_dev = DEVICE_DT_GET(CHARGE_GPIO_NODE);
    if (!device_is_ready(gpio_dev)) {
        printk("Battery: GPIO device not ready\n");
        return -1;
    }

    /* Configure charging detection pin as input with pull-up */
    ret = gpio_pin_configure(gpio_dev, CHARGE_PIN, GPIO_INPUT | GPIO_PULL_UP);
    if (ret < 0) {
        printk("Battery: Charge pin configure failed: %d\n", ret);
        return ret;
    }

    /* Enable battery voltage divider by setting P0.14 low (as per XIAO BLE Sense forum solution) */
    ret = gpio_pin_configure(gpio_dev, 14, GPIO_OUTPUT);
    if (ret < 0) {
        printk("Battery: P0.14 configure failed: %d\n", ret);
        return ret;
    }
    ret = gpio_pin_set(gpio_dev, 14, 0);  /* Set P0.14 low to enable voltage divider */
    if (ret < 0) {
        printk("Battery: P0.14 set low failed: %d\n", ret);
        return ret;
    }
    printk("Battery: Enabled voltage divider via P0.14\n");

    /* Read initial battery status */
    uint16_t mv;
    if (read_battery_voltage(&mv) == 0) {
        s_mv = mv;
        s_chg = read_charging_status();
        s_pct = voltage_to_percentage(mv, s_chg);
        printk("Battery: %dmV %d%% (%s)\n", s_mv, s_pct, s_chg?"chg":"disc");
    }

    s_chg = read_charging_status();
    MLOG("Battery: Initial charging status=%s\n", s_chg ? "charging" : "not charging");

    /* Initialize BLE Battery Service */
    bt_bas_set_battery_level(s_pct);
    bt_bas_bls_set_battery_present(BT_BAS_BLS_BATTERY_PRESENT);

    printk("Battery: Initialization complete\n");
    return 0;
}

void munin_battery_update(void)
{
    static int64_t last_update;
    static int64_t last_broadcast;
    int64_t now = k_uptime_get();
    
    /* Update battery readings every 10 seconds for more responsive charging detection */
    if (now - last_update < 10000) {
        return; 
    }
    last_update = now;

    /* Read current battery voltage */
    uint16_t mv_new;
    bool chg_new = read_charging_status();
    if (read_battery_voltage(&mv_new) == 0) {
        s_mv = mv_new;
        s_pct = voltage_to_percentage(mv_new, chg_new);
        
        /* Update standard BLE Battery Service */
        bt_bas_set_battery_level(s_pct);
    }

    /* Check charging status */
    if (chg_new != s_chg) {
        s_chg = chg_new;
        if (s_chg) {
        printk("Battery: Charging started\n");
        } else {
            printk("Battery: Charging stopped\n");
        }
        
        /* Note: Advanced BLE Battery Service charging state features not available in this Zephyr version */
    }

    static bool low_sent = false;
    static bool full_sent = false;
    const uint16_t LOW_THRESH_MV = 3200;
    const uint16_t FULL_THRESH_MV = 4170; /* Consider ~4.17V effectively full */

    /* Charging transition events */
    if (chg_new != s_chg) {
        bool was_charging = s_chg;
        s_chg = chg_new;
        munin_packet_t pkt;
        if (s_chg) {
            /* Charging started */
            munin_protocol_create_packet(&pkt, MUNIN_EVENT_CHARGING_STARTED, 0, 0);
            munin_protocol_send_packet(&pkt);
            printk("Battery: Charging started\n");
            full_sent = false; /* allow new full notification */
        } else {
            munin_protocol_create_packet(&pkt, MUNIN_EVENT_CHARGING_STOPPED, 0, 0);
            munin_protocol_send_packet(&pkt);
            printk("Battery: Charging stopped\n");
        }
    }

    /* Low battery one-shot (until voltage rises above hysteresis) */
    if (!s_chg && s_mv <= LOW_THRESH_MV) {
        if (!low_sent) {
            munin_packet_t pkt;
            munin_protocol_create_packet(&pkt, MUNIN_EVENT_LOW_BATTERY, s_mv/10, s_pct);
            munin_protocol_send_packet(&pkt);
            printk("Battery: LOW BATTERY (<=%dmV) %dmV %d%%\n", LOW_THRESH_MV, s_mv, s_pct);
            low_sent = true;
        }
    } else if (s_mv > (LOW_THRESH_MV + 80)) { /* ~80mV hysteresis */
        low_sent = false;
    }

    /* Full battery (while charging) */
    if (s_chg && s_mv >= FULL_THRESH_MV) {
        if (!full_sent) {
            munin_packet_t pkt;
            munin_protocol_create_packet(&pkt, MUNIN_EVENT_FULLY_CHARGED, s_mv/10, s_pct);
            munin_protocol_send_packet(&pkt);
            printk("Battery: Fully charged (%dmV)\n", s_mv);
            full_sent = true;
        }
    }

    /* Broadcast battery status every 5 minutes (300s) */
    if (now - last_broadcast >= 300000) {
        last_broadcast = now;
        printk("Battery: Broadcast %dmV %d%% %s\n", s_mv, s_pct, s_chg?"chg":"disc");
        munin_packet_t pkt;
        uint32_t voltage_encoded = s_mv / 10;  /* Encode voltage in 10mV units */
        uint8_t status_encoded = s_pct | (s_chg ? 0x80 : 0x00);  /* MSB = charging flag */
        munin_protocol_create_packet(&pkt, MUNIN_EVENT_BATTERY_STATUS, voltage_encoded, status_encoded);
        munin_protocol_send_packet(&pkt);
    }

    /* Periodic battery status logging */
    MLOG("Battery: periodic %dmV %d%% %s\n", s_mv, s_pct, s_chg?"chg":"disc");
}

uint16_t munin_battery_get_voltage_mv(void) { return s_mv; }
uint8_t munin_battery_get_percentage(void) { return s_pct; }
bool munin_battery_is_charging(void) { return s_chg; }
