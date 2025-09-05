#!/bin/bash

# Build and Flash script for Munin XIAO BLE Sense firmware
# This script handles the complete build and flash process

set -e  # Exit on any error

echo "=== Munin Build and Flash Script ==="

# Navigate to workspace root and source Zephyr environment
cd /Users/Andreas.Limber/repos/munin/zephyr_workspace
echo "Sourcing Zephyr environment..."
source zephyr/zephyr-env.sh

# Navigate to application directory
cd munin_app

# Build the firmware
echo "Building firmware..."
west build -p always -b xiao_ble/nrf52840/sense -d build .

# Check if build was successful
if [ $? -eq 0 ]; then
    echo "✓ Build successful!"
    
    # Flash the firmware
    echo "Flashing firmware..."
    ./flash.sh
    
    if [ $? -eq 0 ]; then
        echo "✓ Flash complete!"
        echo "🚀 Munin firmware updated successfully!"
    else
        echo "❌ Flash failed!"
        exit 1
    fi
else
    echo "❌ Build failed!"
    exit 1
fi
