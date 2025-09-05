#ifndef MUNIN_BLE_H
#define MUNIN_BLE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

int munin_ble_init(void);
void munin_ble_update(void);
int munin_ble_send_data(const uint8_t *data, size_t length);
bool munin_ble_is_connected(void);
bool munin_ble_is_advertising(void);

#endif
