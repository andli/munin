cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(munin)

target_sources(app PRIVATE src/main.c)
target_sources(app PRIVATE src/munin_protocol.c)
target_sources(app PRIVATE src/ble.c)
target_sources(app PRIVATE src/imu.c)
target_sources(app PRIVATE src/battery.c)
target_sources(app PRIVATE src/led_config.c)
target_sources(app PRIVATE src/led_effects.c)
target_sources(app PRIVATE src/sk6812.c)
