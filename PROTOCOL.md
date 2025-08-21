# 🐦‍⬛ Munin Logging Protocol (v2.0)

## Overview
The Munin Logging Protocol defines how a Munin time-tracking device communicates activity logs over Bluetooth Low Energy (BLE) and optionally over Serial. The protocol supports:

- Face switch tracking
- Long-running face sessions  
- Boot and shutdown events
- Disconnection tolerance
- Receiving face color configuration from the client
- Compact and efficient binary structure

---

## Packet Format
Each log entry is sent as a **6-byte binary packet**.

### Log Packet Structure
| Field        | Type     | Size | Description                                     |
|--------------|----------|------|-------------------------------------------------|
| `event_type` | `uint8`  | 1 B  | Type of event (see Event Types below)          |
| `delta_s`    | `uint32` | 4 B  | Seconds since current face session started     |
| `face_id`    | `uint8`  | 1 B  | ID of the face currently active (0–5)           |
| **Total**    |          | 6 B  |                                                 |

---

## Event Types
Event types are represented as single-byte constants in the first field of the packet.

| `event_type` | Name              | Description                                                |
|--------------|-------------------|------------------------------------------------------------|
| `0x01`       | Face Switch        | A new face is now facing up. Always has `delta_s = 0`    |
| `0x02`       | Ongoing Log        | Time has elapsed on the same face                         |
| `0x03`       | State Sync         | Connection state sync - device reports current face and accumulated time |
| `0x10`       | Boot               | Device powered on. Anchors device uptime. Will be rare.   |
| `0x11`       | Shutdown           | Device is powering down (low battery or user-triggered)   |
| `0x12`       | Low Battery        | Battery voltage below safe threshold                      |
| `0x13`       | Charging Started   | USB power connected, battery charging initiated          |
| `0x14`       | Fully Charged      | Battery charging complete, device fully charged          |
| `0x15`       | Charging Stopped   | USB power disconnected, charging stopped                 |
| `0x20`       | BLE Connect        | Client connected over BLE                                 |
| `0x21`       | BLE Disconnect     | Client disconnected or timeout                            |

> Future event types may be added. Clients should ignore unknown event types gracefully.

---

## Face ID Mapping
Each face of the Munin cube is assigned an ID from 0 to 5. The mapping is defined by physical orientation (e.g., +Z = 0, -Z = 1, etc.). The same mapping must be used consistently across firmware and client apps.

---

## Delta Time Interpretation
`delta_s` represents seconds since the current face session started:
- **Face Switch (`0x01`)**: Always `delta_s = 0` - indicates user switched to a new face
- **State Sync (`0x03`)**: `delta_s > 0` - indicates device was already on this face when client connected
- **Ongoing Log (`0x02`)**: `delta_s > 0` - periodic time updates for the same face

### Event Type Usage
- **`0x01` Face Switch**: Only sent when user physically changes cube orientation
- **`0x03` State Sync**: Only sent when BLE client connects to synchronize current state
- **`0x02` Ongoing Log**: Periodic updates during long face sessions (optional)

---

## BLE Connection Behavior
The device provides state synchronization when clients connect or reconnect:

### Connection State Sync
When a BLE client connects, the device sends the current state:
- Event type `0x03` (State Sync)
- `delta_s` = elapsed time since the current face started (0 if device just rebooted)
- Current `face_id`

This ensures clients receive the current device state even if they missed the initial face switch event.

### Device Reboot Handling
When the device reboots (power cycle, firmware update, etc.):
- Device loses all previous timing state (no persistent storage)
- Device detects current face orientation and starts timing from zero
- Next BLE connection will receive state sync with `delta_s = 0`

### Disconnection Tolerance
The protocol handles temporary disconnections:
- Device continues timing internally while disconnected
- Client reconnection receives current state with accumulated `delta_s`
- Timing continuity is maintained for powered-on disconnections

---

## Client-Side Time Reconstruction
Clients reconstruct wall-clock timestamps using:
- The arrival time of any packet
- Working backwards using `delta_s` to determine session start time

### Example:
1. Client receives `{0x03, 300, 2}` at 2025-07-31T12:05:00Z  
   - State sync: Face 2 active for 300s
   - Session start time: 12:05:00Z - 300s = 12:00:00Z
   - Current time on Face 2: 12:05:00Z
2. Later receives `{0x01, 0, 3}` at 12:07:00Z
   - Face switch to Face 3 at 12:07:00Z

---

## Face Configuration Packets
The client may send configuration packets to assign a color to each face.

### Face Config Packet Structure (per face)
| Field         | Type        | Size         | Description                                 |
|---------------|-------------|--------------|---------------------------------------------|
| `face_id`     | `uint8`     | 1 B          | Target face (0–5)                           |
| `r`           | `uint8`     | 1 B          | Red component (0–255)                       |
| `g`           | `uint8`     | 1 B          | Green component (0–255)                     |
| `b`           | `uint8`     | 1 B          | Blue component (0–255)                      |
| **Total**     |             | 4 B          |                                              |

- Sent from client to device  
- Should be sent after BLE connect (event `0x20`)  
- Used for LED feedback, display in app, or sticker generation  
- Device may store config in flash for reuse after reboot

---

## Reserved: Future Face Label Sync
A future version of Munin may accept a UTF-8 label string per face (e.g. for use with OLED display modules).  
This would be introduced as a separate packet type `0xC1` (SetFaceLabel) with an extended structure. For now, face labels are managed entirely in the client app.

---

## Extensions
The protocol may be extended by:
- Adding an `event_data` field after `face_id` (optional, type-dependent)
- Adding CRC or checksum (if needed for noisy transport)
- Supporting device ID prefixing (for multi-device environments)
- Supporting future face label sync (see above)
