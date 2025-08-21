#ifndef BLE_H
#define BLE_H

#include <stdint.h>
#include <stdbool.h>

// BLE function prototypes
int munin_ble_init(void);
void munin_ble_update(void);
int munin_ble_send_data(const uint8_t *data, size_t length);
bool munin_ble_is_connected(void);

#endif // BLE_H
