# 🐦‍⬛ Munin Logging Protocol (v1.3)

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
Each log entry is sent as a **7-byte binary packet**.

### Log Packet Structure
| Field        | Type     | Size | Description                                     |
|--------------|----------|------|-------------------------------------------------|
| `event_type` | `uint8`  | 1 B  | Type of event (see Event Types below)          |
| `session_id` | `uint8`  | 1 B  | Session identifier for current face activity    |
| `delta_ms`   | `uint32` | 4 B  | Milliseconds since start of session or boot     |
| `face_id`    | `uint8`  | 1 B  | ID of the face currently active (0–5)           |
| **Total**    |          | 7 B  |                                                 |

---

## Event Types
Event types are represented as single-byte constants in the first field of the packet.

| `event_type` | Name              | Description                                                |
|--------------|-------------------|------------------------------------------------------------|
| `0x01`       | Face Switch        | A new face is now facing up. `delta_ms = 0`               |
| `0x02`       | Ongoing Log        | Time has elapsed on the same face                         |
| `0x10`       | Boot               | Device powered on. Anchors device uptime. Will be rare.   |
| `0x11`       | Shutdown           | Device is powering down (low battery or user-triggered)   |
| `0x12`       | Low Battery        | Battery voltage below safe threshold                      |
| `0x20`       | BLE Connect        | Client connected over BLE                                 |
| `0x21`       | BLE Disconnect     | Client disconnected or timeout                            |

> Future event types may be added. Clients should ignore unknown event types gracefully.

---

## Face ID Mapping
Each face of the Munin cube is assigned an ID from 0 to 5. The mapping is defined by physical orientation (e.g., +Z = 0, -Z = 1, etc.). The same mapping must be used consistently across firmware and client apps.

---

## Session ID
`session_id` is an 8-bit counter incremented on each face switch. It allows the client to:
- Distinguish between different face sessions
- Reconstruct wall-clock time from `delta_ms` and arrival time
- Handle Bluetooth disconnects and resume logging with continuity

Wraparound is allowed (255 → 0). Clients must manage anchors accordingly.

---

## Client-Side Time Reconstruction
Clients reconstruct wall-clock timestamps using:
- The time of arrival of a packet with `delta_ms = 0` (start of session)
- All subsequent logs for the same `session_id`

### Example:
1. Client receives `{0x01, 42, 0, 2}` at 2025-07-31T12:00:00Z  
   - Anchor: Session 42, Face 2 started at 12:00:00Z  
2. Receives `{0x02, 42, 300000, 2}` (delta 5 min)  
   - Timestamp: 12:05:00Z

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
