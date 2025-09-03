#!/bin/bash

# Build and flash script for XIAO nRF52840 Sense
echo "=== Build and Flash XIAO nRF52840 Sense ==="

# Build the firmware
echo "🔨 Building firmware..."
source ../.venv/bin/activate
west build -b xiao_ble/nrf52840/sense

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo "✓ Build successful!"
echo ""

# Flash the firmware
echo "🚀 Starting flash process..."
./flash.sh
