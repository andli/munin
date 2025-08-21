#ifndef MUNIN_PROTOCOL_H
#define MUNIN_PROTOCOL_H

#include <stdint.h>

// Munin Protocol v2.0 - 6-byte packet format
#define MUNIN_PACKET_SIZE 6

// Event types
#define MUNIN_EVENT_FACE_SWITCH    0x01  // Face changed (delta_s = 0)
#define MUNIN_EVENT_ONGOING_LOG    0x02  // Time elapsed on same face
#define MUNIN_EVENT_STATE_SYNC     0x03  // Connection state sync
#define MUNIN_EVENT_BOOT          0x10  // Device powered on
#define MUNIN_EVENT_SHUTDOWN      0x11  // Device shutting down
#define MUNIN_EVENT_LOW_BATTERY   0x12  // Battery low warning
#define MUNIN_EVENT_CHARGING_START 0x13  // Charging started
#define MUNIN_EVENT_CHARGING_FULL 0x14  // Charging complete
#define MUNIN_EVENT_CHARGING_STOP 0x15  // Charging stopped

// Packet structure
typedef struct {
    uint8_t event_type;
    uint32_t delta_s;    // Little-endian
    uint8_t face_id;
} __attribute__((packed)) munin_packet_t;

// Function prototypes
int munin_protocol_create_packet(munin_packet_t *packet, uint8_t event_type, uint32_t delta_s, uint8_t face_id);
int munin_protocol_send_packet(const munin_packet_t *packet);

#endif // MUNIN_PROTOCOL_H
