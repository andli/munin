#include "battery.h"
#include "munin_protocol.h"
#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>

static uint16_t s_mv = 4000;
static uint8_t s_pct = 100;
static bool s_chg = false;

int munin_battery_init(void)
{
    // TODO: wire real ADC + charger GPIO when ready
    return 0;
}

void munin_battery_update(void)
{
    static int64_t last;
    int64_t now = k_uptime_get();
    if (now - last < 30000) return; // 30s
    last = now;

    // Placeholder behavior: assume USB present => charging
    bool chg_now = s_chg; // keep state for eventing later when real signals exist
    if (chg_now != s_chg) {
        s_chg = chg_now;
        munin_packet_t pkt;
        munin_protocol_create_packet(&pkt, s_chg ? MUNIN_EVENT_CHARGING_START : MUNIN_EVENT_CHARGING_STOP, 0, 0);
        munin_protocol_send_packet(&pkt);
    }

    if (s_mv <= 3500) {
        munin_packet_t pkt;
        munin_protocol_create_packet(&pkt, MUNIN_EVENT_LOW_BATTERY, 0, 0);
        munin_protocol_send_packet(&pkt);
    }
}

uint16_t munin_battery_get_voltage_mv(void) { return s_mv; }
uint8_t munin_battery_get_percentage(void) { return s_pct; }
bool munin_battery_is_charging(void) { return s_chg; }
