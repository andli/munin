#ifndef BATTERY_H
#define BATTERY_H

#include <stdint.h>
#include <stdbool.h>

// Function prototypes
int munin_battery_init(void);
void munin_battery_update(void);
uint16_t munin_battery_get_voltage_mv(void);
uint8_t munin_battery_get_percentage(void);
bool munin_battery_is_charging(void);
bool munin_battery_is_connected(void);

#endif // BATTERY_H
