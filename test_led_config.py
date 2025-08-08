#!/usr/bin/env python3
"""
Test script for LED configuration feature.

This script demonstrates how to configure face colors programmatically.
"""

import asyncio
import json
from pathlib import Path
from munin_client.config import MuninConfig
from munin_client.ble_manager import BLEDeviceManager
from munin_client.device import FaceConfig

async def test_led_configuration():
    """Test LED configuration by setting custom colors and sending to device"""
    
    print("🌈 Testing LED Configuration Feature")
    print("=" * 50)
    
    # Initialize config and BLE manager
    config = MuninConfig()
    ble_manager = BLEDeviceManager(enable_fake_device=True)  # Use fake device for testing
    
    # Show current face colors
    print("\n📋 Current face colors:")
    face_colors = config.get_face_colors()
    for face_id, color in face_colors.items():
        label = config.get_face_label(int(face_id))
        print(f"  Face {face_id} ({label}): RGB({color['r']},{color['g']},{color['b']})")
    
    # Set some custom colors
    print("\n🎨 Setting custom colors...")
    test_colors = {
        "1": {"r": 255, "g": 100, "b": 0},   # Orange for Emails
        "2": {"r": 50, "g": 255, "b": 50},   # Bright green for Coding
        "3": {"r": 100, "g": 100, "b": 255}, # Light blue for Meetings
        "4": {"r": 255, "g": 255, "b": 100}, # Light yellow for Planning
        "5": {"r": 200, "g": 0, "b": 200},   # Purple for Break
        "6": {"r": 64, "g": 64, "b": 64}     # Dark gray for Off
    }
    
    # Update configuration
    current_config = config.load_config()
    current_config["face_colors"] = test_colors
    config.save_config(current_config)
    
    for face_id, color in test_colors.items():
        label = config.get_face_label(int(face_id))
        print(f"  Face {face_id} ({label}): RGB({color['r']},{color['g']},{color['b']})")
    
    # Connect to device
    print("\n🔗 Connecting to Munin device...")
    connected = await ble_manager.auto_connect_to_munin()
    
    if connected:
        print("✅ Connected successfully!")
        device_info = ble_manager.get_connected_device_info()
        print(f"📱 Device: {device_info[0]} ({device_info[1]})")
        
        # Send LED configuration
        print("\n📤 Sending LED configuration to device...")
        await ble_manager._send_face_configuration()
        
        print("✅ LED configuration sent!")
        print("💡 The device should now use the new colors when faces change.")
        
        # Wait a bit to see if any face changes occur
        print("\n⏳ Waiting 10 seconds to observe face changes...")
        await asyncio.sleep(10)
        
        # Disconnect
        print("\n🔌 Disconnecting from device...")
        await ble_manager.disconnect()
        print("✅ Disconnected.")
        
    else:
        print("❌ Failed to connect to device.")
        print("💡 Make sure to run with --fake flag: python test_led_config.py")
    
    print("\n🎉 LED configuration test completed!")

if __name__ == "__main__":
    asyncio.run(test_led_configuration())
