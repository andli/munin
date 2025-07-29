# 🐦‍⬛ Munin

Munin is a physical, dice-like Bluetooth time tracker. Each face represents a different activity — just flip the cube to start logging time.  
It’s 3D-printed, powered by a Seeed XIAO board, and designed to be **subscription-free and hackable**.

## Hardware
The device consists of a 3d printed translucent enclosure, a single board for control and connectivity, plus a battery.

- 3D-printed translucent enclosure (STL to come)
- [Seeed XIAO nRF54L15 Sense]([https://www.seeedstudio.com/XIAO-nRF52840-Sense-p-5201.html](https://www.seeedstudio.com/XIAO-nRF54L15-Sense-p-6494.html)) — BLE + IMU + USB-C microcontroller
- LiPo battery (3.7 V, 400–1000 mAh)

### LED feedback
The internal LED provides status feedback:

- Face switch confirmation (short glow in configured color)
- Low battery (pulsing red)
- Bluetooth pairing mode
- Charging (pulsing green) and fully charged (steady green)

### Bluetooth pairing
Pairing is triggered when the USB-C connector side is UP and USB is connected.

## Software
The Munin time tracker is paired via bluetooth and has a CLI based app that handles configuration and writes to a log file.

### Log file format
/logs/
munin_time_log.csv       # Primary tracked time
```
timestamp_start,timestamp_end,duration_sec,activity_face,activity_label,notes
2025-07-29T08:00:00Z,2025-07-29T09:30:00Z,5400,2,Coding,
2025-07-29T09:30:00Z,2025-07-29T09:45:00Z,900,5,Coffee Break,
2025-07-29T09:45:00Z,2025-07-29T10:15:00Z,1800,3,Emails
```
munin_events.log         # System, connection, and status events
```
2025-07-29T10:02:51Z BOOT reason=cold firmware=1.2.0
2025-07-29T10:02:54Z BLE_CONNECTED peer=MacBook-Pro
2025-07-29T10:44:00Z BATTERY_WARNING voltage=3.51V
2025-07-29T10:50:12Z CHARGING_STARTED source=usb
2025-07-29T10:55:33Z CHARGING_ENDED voltage=4.19V
```

### Configuration
- Label and color for each side.
- Time log file location


## Event codes
| Event Code         | Description                                      | Example Parameters                        |
|--------------------|--------------------------------------------------|-------------------------------------------|
| `BOOT`             | Device startup event                             | `reason=cold`, `firmware=1.2.0`           |
| `BLE_CONNECTED`    | BLE connection established                       | `peer=MacBook-Pro`, `rssi=-58`            |
| `BLE_DISCONNECTED` | BLE connection lost                              | `peer=MacBook-Pro`, `reason=timeout`      |
| `BATTERY_WARNING`  | Battery voltage dropped below threshold          | `voltage=3.51V`                           |
| `CHARGING_STARTED` | USB power detected; charging begins              | `source=usb`                              |
| `CHARGING_ENDED`   | Charging finished or unplugged                   | `voltage=4.19V`                           |
| `PAIRING_MODE`     | Device entered pairing mode                      | `method=face6_usb`, `timeout=30s`         |
| `RESET_REQUESTED`  | Device reset or data wipe triggered              | `reason=imu_sequence`                     |
| `ERROR`            | Any unexpected fault or assertion                | `code=IMU_FAIL`, `detail=timeout`         |
| `INFO`             | Generic info message (e.g. log roll, sync ping)  | `msg=log_rotation`, `file=2025-07-29.log` |
