#!/bin/bash

# Flash script for XIAO nRF52840 Sense
UF2_FILE="build/zephyr/zephyr.uf2"
BOOTLOADER_MOUNT="/Volumes/XIAO-SENSE"
TIMEOUT=30

echo "=== XIAO nRF52840 Sense Flash Script ==="
echo "1. Put your XIAO into bootloader mode (double-click reset button)"
echo "2. Waiting for bootloader drive to appear..."

# Wait for the bootloader drive to appear
for i in $(seq 1 $TIMEOUT); do
    if [ -d "$BOOTLOADER_MOUNT" ]; then
        echo "✓ Bootloader drive found at $BOOTLOADER_MOUNT"
        break
    fi
    echo "Waiting... ($i/$TIMEOUT)"
    sleep 1
done

if [ ! -d "$BOOTLOADER_MOUNT" ]; then
    echo "❌ Bootloader drive not found after ${TIMEOUT}s"
    echo "Make sure to double-click the reset button on your XIAO"
    exit 1
fi

# Check if UF2 file exists
if [ ! -f "$UF2_FILE" ]; then
    echo "❌ UF2 file not found: $UF2_FILE"
    echo "Run 'west build' first to build the firmware"
    exit 1
fi

echo "📁 Copying $UF2_FILE to bootloader..."
cp "$UF2_FILE" "$BOOTLOADER_MOUNT/"

# The drive will disconnect automatically after flashing
echo "✓ Firmware flashed successfully!"
echo "The device should reboot automatically in a few seconds."

# Wait a bit and check if device rebooted
sleep 3
if [ ! -d "$BOOTLOADER_MOUNT" ]; then
    echo "✓ Device rebooted successfully"
else
    echo "⚠️  Drive still mounted - this might indicate an issue"
fi

echo "🚀 Deployment complete!"
