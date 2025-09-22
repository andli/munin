# 🐦‍⬛ Munin

Munin helps you track time for different tasks during your work day. Each face represents a different activity — just flip the cube to start logging time for a specific task (ex. _"Product support"_, _"Emails"_, _"Coding"_ etc). Add labels to each side if you want.

- 3D-printed
- Bluetooth connected
- Subscription-free (unlike for example Timeular and EARLY)
- Hackable

Depending on usage, battery time should be 2-8 weeks.

![Munin mockup](munin-mockup.png)

## Hardware

The device consists of a 3d printed translucent enclosure, a single board for control and connectivity, plus a battery.

- 3D-printed translucent enclosure (STL to come)
- Seeed XIAO nRF52840 Sense — BLE + IMU + USB-C microcontroller
- LiPo battery (3.7 V, EEMB 803030 with PCM)
- SK6812 mini LED

Total cost of components is something like 40€ at the moment. Could be lowered significantly but that would make assembly much more cumbersome.

### LED feedback

The internal LED provides status feedback:

- :rainbow: Face switch confirmation (short glow in configured color)
- :red_square: Low battery (pulsing red)
- :green_square: Charging (pulsing green) and fully charged (steady green)

## Software

The Munin time tracker has, besides its own firmware, a systray client app that handles connectivity, configuration and writes to a log file. The app is based on python and `bleak` and will work on macOS, Windows and Linux. It will not require root and will probably be distributed using something like `pipx install munin-client`. We shall see.

![Munin systray](systray_screenshot.png)

### Log file format

munin_time_log.csv # Primary tracked time

```
timestamp,face_id,face_label,duration_s
2025-08-20T15:59:15.847411,6,Off,8.0
2025-08-20T15:59:23.875021,5,Break,4.0
2025-08-20T15:59:27.901076,2,Coding,18.0
2025-08-20T15:59:45.933763,3,Meetings,30.0
2025-08-20T16:00:15.970091,2,Coding,2.0
2025-08-21T15:51:53.807371,2,Coding,1332.3
2025-08-21T16:14:06.146382,1,Emails,11.2
2025-08-21T16:15:44.557220,1,Emails,10.0
2025-08-21T16:35:39.860765,1,Emails,22.0
2025-08-21T16:36:01.859839,2,Coding,4.1
2025-08-21T22:15:41.733766,1,Emails,87.5
```

### Configuration

- Label and color for each side.
- Time log file location

Face colors (and labels) can be configured via the tray Settings UI ("Settings…") or by editing `~/.munin/config.json` directly. The client automatically sends the configured colors to the device when connecting.

Each face can be customized with any color and label. See `config.example.json` for the default configuration values.

The device will flash the configured color briefly when switching faces.

### Settings UI

Open from the tray icon → "Settings…". Features:

- Edit face labels
- Edit face colors (hex #RRGGBB)
  

Config writes are atomic; the running tray process detects external changes and pushes updates live without restart.

## Dev

### Client App

Run locally:
```bash
source .venv/bin/activate
python -m munin_client
```

Or with pipx:
`pipx run --spec . munin-client`

### Firmware Development

Using the xiao_ble_nrf52840_sense.dts board definition.

Build firmware:
```bash
cd ./zephyr_workspace && source zephyr/zephyr-env.sh && cd munin_app && west build -p always -b xiao_ble/nrf52840/sense .
```

Deploy firmware:
1. Double-click reset button on XIAO to enter bootloader mode
2. Run: `./flash.sh` (or drag `build/zephyr/zephyr.uf2` to XIAO-SENSE drive)

### Zephyr info 

Battery life is more important than detecting a face change quickly and moreover the Munin should not change face that easily in case one accidentally rotate it or fiddle with it.

* Battery: https://github.com/Tjoms99/xiao_sense_nrf52840_battery_lib
* IMU: https://devzone.nordicsemi.com/f/nordic-q-a/109732/running-the-lsm6dls-imu-zephyr-example-with-nrf52840-based-xiao-ble-sense


# Roadmap

## Client app

- ✅ Log face change to log file (CSV format as specified above) 
- ✅ Handle device reconnection when connection is lost 
- ✅ Test client app on Windows
- ✅ Show current face in menu
- Implement a Settings UI in system tray for:
  - ✅ LED colors
  - ✅ Face labels
  - preferred device selection/pairing
- Implement a basic view for time tracking statistics and reports
- Make the tray menu update while it is open
- Add firmware update menu item and function

## Munin device

- ✅ Get BLE working
- ✅ Get IMU sensor working
- ✅ Light up LED on face change 
- ✅ Implement real battery voltage reading (ADC)
- ✅ Broadcast battery level periodically
- ✅ Receive LED configuration from client 
- ✅ Broadcast face change only on movement
- ✅ Add on/off button and reset button
- Add charging status detection and fix voltage being all wrong 
- Stronger LED than the builtin one needed - add an SK6812
- Add firmware support for using the SK6812
- LED support for low battery
- Power saving mode - "sleep" and wake on movement
- Optimize BLE connection parameters for battery life

## 3d print
- Test print enclosure in PETG
- Create mount points
- Confirm snap-in lid

## Protocol & Infrastructure

- Create proper installer/packaging for client app
- Write a manual
- BLE initial pairing
- Implement device firmware update mechanism


