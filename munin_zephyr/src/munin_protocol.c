#include "munin_protocol.h"
#include "ble.h"
#include <zephyr/logging/log.h>
#include <string.h>

LOG_MODULE_REGISTER(protocol, LOG_LEVEL_INF);

int munin_protocol_create_packet(munin_packet_t *packet, uint8_t event_type, uint32_t delta_s, uint8_t face_id)
{
    if (!packet) {
        return -1;
    }
    
    packet->event_type = event_type;
    packet->delta_s = delta_s;  // Stored in native format, will be little-endian on transmission
    packet->face_id = face_id;
    
    return 0;
}

int munin_protocol_send_packet(const munin_packet_t *packet)
{
    if (!packet) {
        return -1;
    }
    
    // Convert to wire format (6 bytes, little-endian delta_s)
    uint8_t wire_packet[MUNIN_PACKET_SIZE];
    wire_packet[0] = packet->event_type;
    wire_packet[1] = packet->delta_s & 0xFF;
    wire_packet[2] = (packet->delta_s >> 8) & 0xFF;
    wire_packet[3] = (packet->delta_s >> 16) & 0xFF;
    wire_packet[4] = (packet->delta_s >> 24) & 0xFF;
    wire_packet[5] = packet->face_id;
    
    LOG_DBG("Sending packet: %02x%02x%02x%02x%02x%02x", 
            wire_packet[0], wire_packet[1], wire_packet[2], 
            wire_packet[3], wire_packet[4], wire_packet[5]);
    
    // Send via BLE
    return munin_ble_send_data(wire_packet, MUNIN_PACKET_SIZE);
}
