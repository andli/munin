#include "munin_protocol.h"
#include "ble.h"
#include <string.h>

int munin_protocol_create_packet(munin_packet_t *packet, uint8_t event_type, uint32_t delta_s, uint8_t face_id)
{
    if (!packet) return -1;
    packet->event_type = event_type;
    packet->delta_s = delta_s;
    packet->face_id = face_id;
    return 0;
}

int munin_protocol_send_packet(const munin_packet_t *packet)
{
    if (!packet) return -1;
    uint8_t wire[MUNIN_PACKET_SIZE];
    wire[0] = packet->event_type;
    wire[1] = (uint8_t)(packet->delta_s & 0xFF);
    wire[2] = (uint8_t)((packet->delta_s >> 8) & 0xFF);
    wire[3] = (uint8_t)((packet->delta_s >> 16) & 0xFF);
    wire[4] = (uint8_t)((packet->delta_s >> 24) & 0xFF);
    wire[5] = packet->face_id;
    return munin_ble_send_data(wire, sizeof(wire));
}
