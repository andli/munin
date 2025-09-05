#ifndef MUNIN_PROTOCOL_H
#define MUNIN_PROTOCOL_H

#include <stdint.h>

#define MUNIN_PACKET_SIZE 6

// Event types
#define MUNIN_EVENT_FACE_SWITCH        0x01
#define MUNIN_EVENT_ONGOING_LOG        0x02
#define MUNIN_EVENT_STATE_SYNC         0x03
#define MUNIN_EVENT_BATTERY_STATUS     0x04  /* Voltage + % + charging flag (periodic) */
#define MUNIN_EVENT_VERSION            0x05  /* Firmware version (sent once after boot) */

#define MUNIN_EVENT_BOOT               0x10
#define MUNIN_EVENT_SHUTDOWN           0x11
#define MUNIN_EVENT_LOW_BATTERY        0x12  /* First time we dip below low threshold */
#define MUNIN_EVENT_CHARGING_STARTED   0x13
#define MUNIN_EVENT_FULLY_CHARGED      0x14
#define MUNIN_EVENT_CHARGING_STOPPED   0x15  /* USB removed before full OR after full */

typedef struct {
    uint8_t event_type;
    uint32_t delta_s;
    uint8_t face_id;
} __attribute__((packed)) munin_packet_t;

int munin_protocol_create_packet(munin_packet_t *packet, uint8_t event_type, uint32_t delta_s, uint8_t face_id);
int munin_protocol_send_packet(const munin_packet_t *packet);

#endif
