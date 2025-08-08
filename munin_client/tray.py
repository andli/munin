import threading
import asyncio
import time
import os
import subprocess
from pystray import Icon, MenuItem, Menu
from PIL import Image
from munin_client.logger import MuninLogger
from munin_client.config import MuninConfig
from munin_client.ble_manager import BLEDeviceManager

logger = MuninLogger()

# Global shutdown event
shutdown_event = threading.Event()

# Global BLE manager (will be initialized in start_tray)
ble_manager = None
config = MuninConfig()

def get_icon_image():
    
    # Define icon paths relative to the package
    icon_dir = os.path.dirname(__file__)
    icon_path = os.path.join(icon_dir, "munin_tray_icon.png")
    return Image.open(icon_path)

def copy_to_clipboard(text):
    """Copy text to system clipboard using pbcopy on macOS"""
    try:
        process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        process.communicate(input=text.encode('utf-8'))
        return True
    except Exception as e:
        logger.log_event(f"Failed to copy to clipboard: {e}")
        return False
    


# BLE worker - handles connection and communication
async def ble_worker_async():
    logger.log_event("Starting BLE worker")
    
    # Connection state tracking
    was_connected = False
    reconnect_attempts = 0
    max_reconnect_attempts = 5
    
    # Initial connection attempt
    connected = await ble_manager.connect_to_preferred_device()
    if not connected:
        connected = await ble_manager.auto_connect_to_munin()
    
    if not connected:
        logger.log_event("No Munin device found - will keep trying to connect")
    
    # Main BLE loop
    battery_check_counter = 0
    connection_check_counter = 0
    
    while not shutdown_event.is_set():
        try:
            current_connected = ble_manager.is_connected()
            
            # Detect disconnection
            if was_connected and not current_connected:
                logger.log_event("Device disconnected - attempting to reconnect...")
                reconnect_attempts = 0
                was_connected = False
            
            if current_connected:
                # Device is connected - normal operation
                if not was_connected:
                    logger.log_event("Device connected successfully")
                    reconnect_attempts = 0
                    was_connected = True
                
                # Check battery every 30 seconds
                if battery_check_counter >= 30:
                    await ble_manager.read_battery_level()
                    battery_check_counter = 0
                
                # Perform connection health check every 10 seconds
                if battery_check_counter % 10 == 0:
                    if not await ble_manager.check_connection_health():
                        logger.log_event("Connection health check failed")
                        # Force disconnect and let reconnection logic handle it
                        await ble_manager.disconnect(is_temporary=True)
                        current_connected = False
                        was_connected = False
                
                battery_check_counter += 1
                connection_check_counter = 0
                await asyncio.sleep(1)
                
            else:
                # Device not connected - try to reconnect
                connection_check_counter += 1
                
                # Try reconnection every 5 seconds, but with backoff
                if connection_check_counter >= 5:
                    if reconnect_attempts < max_reconnect_attempts:
                        reconnect_attempts += 1
                        logger.log_event(f"Reconnection attempt {reconnect_attempts}/{max_reconnect_attempts}")
                        
                        # Try preferred device first, then auto-discover
                        connected = await ble_manager.connect_to_preferred_device()
                        if not connected:
                            connected = await ble_manager.auto_connect_to_munin()
                            
                        if connected:
                            logger.log_event("Reconnection successful!")
                        else:
                            logger.log_event("Reconnection failed, will retry...")
                            
                    else:
                        # Max attempts reached, wait longer before trying again
                        logger.log_event(f"Max reconnection attempts reached, waiting 30 seconds...")
                        await asyncio.sleep(25)  # Additional 25 + 5 below = 30 seconds
                        reconnect_attempts = 0
                    
                    connection_check_counter = 0
                
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.log_event(f"Error in BLE worker: {e}")
            await asyncio.sleep(5)
    
    # Cleanup
    try:
        await ble_manager.disconnect()
    except Exception as e:
        logger.log_event(f"Error during cleanup: {e}")
    
    logger.log_event("BLE worker shutting down")

def ble_worker():
    """Wrapper to run async BLE worker in thread"""
    asyncio.run(ble_worker_async())

def start_tray(enable_fake_device: bool = False):
    global ble_manager
    
    logger.log_event("Starting application")
    
    # Initialize BLE manager with fake device support if requested
    ble_manager = BLEDeviceManager(enable_fake_device=enable_fake_device)
    
    if enable_fake_device:
        logger.log_event("Started with fake Munin device for testing")
    
    # Start BLE worker in background
    thread = threading.Thread(target=ble_worker, daemon=True)
    thread.start()
    
    def quit_callback(*args):
        logger.log_event("Quitting application")
        shutdown_event.set()
        icon.stop()

    def scan_devices():
        async def do_scan():
            devices = await ble_manager.scan_for_devices(5.0)
            logger.log_event(f"Found {len(devices)} devices")
            for name, addr, rssi in devices:
                logger.log_event(f"  {name} ({addr}) RSSI: {rssi}")
        
        asyncio.run(do_scan())
    
    def show_activity_summary(days=30):
        """Show activity summary for the specified number of days."""
        from munin_client.time_summary import get_summary_text
        summary = get_summary_text(days)
        logger.log_event(summary)

    def show_monthly_summary(*args):
        """Show monthly activity summary."""
        from munin_client.time_summary import get_monthly_summary
        from munin_client.config import MuninConfig
        
        config = MuninConfig()
        start_date = config.get_monthly_start_date()
        time_format = config.get_activity_summary_config().get('time_format', 'hours')
        summary = get_monthly_summary(start_date, time_format)
        
        # Copy summary to clipboard
        if copy_to_clipboard(summary):
            logger.log_event("Monthly summary copied to clipboard")
        else:
            logger.log_event("Failed to copy to clipboard - showing in log")
            logger.log_event(f"Monthly Activity Summary:\n{summary}")

    def show_settings(*args):
        """Show settings configuration."""
        from munin_client.config import MuninConfig
        config = MuninConfig()
        settings_info = [
            "Current Settings:",
            f"Monthly Start Date: {config.get_monthly_start_date()}",
            f"Time Format: {config.get_activity_summary_config().get('time_format', 'hours')}",
            "",
            "Face Labels:"
        ]
        
        for i in range(1, 7):
            label = config.get_face_label(i)
            settings_info.append(f"  Face {i}: {label}")
        
        settings_text = "\n".join(settings_info)
        
        # Copy settings to clipboard
        if copy_to_clipboard(settings_text):
            logger.log_event("Settings copied to clipboard")
        else:
            logger.log_event("Failed to copy to clipboard - showing in log")
            logger.log_event(settings_text)

    def get_status_text():
        """Get current connection status for menu"""
        if ble_manager.is_connected():
            device_info = ble_manager.get_connected_device_info()
            if device_info:
                return f"✔ Connected to {device_info[0]}"
        return "❌ Not connected"
    
    def get_battery_text():
        """Get battery status for menu"""
        if ble_manager.is_connected():
            battery_level = ble_manager.get_battery_level()
            if battery_level is not None:
                # Add battery icon based on level
                if battery_level > 75:
                    icon_battery = "🔋"
                elif battery_level > 50:
                    icon_battery = "🔋"
                elif battery_level > 25:
                    icon_battery = "🪫"
                else:
                    icon_battery = "🪫"
                return f"{icon_battery} Battery: {battery_level}%"
            else:
                return "🔋 Battery: Unknown"
        return None
    
    # Create dynamic menu
    def create_menu():
        menu_items = [
            MenuItem(get_status_text(), None, enabled=False),  # Status (non-clickable)
        ]
        
        # Add battery status if connected
        battery_text = get_battery_text()
        if battery_text:
            menu_items.append(MenuItem(battery_text, None, enabled=False))
        
        menu_items.extend([
            Menu.SEPARATOR,
            MenuItem("Copy monthly summary", show_monthly_summary),
            MenuItem("Settings...", show_settings),
            Menu.SEPARATOR,
            MenuItem("Quit", quit_callback)
        ])
        
        return Menu(*menu_items)
    
    icon = Icon(
        "Munin",
        get_icon_image()
    )
    
    # Function to update the menu - try different methods
    def update_menu():
        new_menu = create_menu()
        icon.menu = new_menu
        # Try multiple update methods as different pystray versions vary
        if hasattr(icon, 'update_menu'):
            icon.update_menu()
        elif hasattr(icon, '_update_menu'):
            icon._update_menu()
        # Force a refresh by temporarily changing the icon
        elif hasattr(icon, 'notify'):
            icon.notify("Menu updated")

    # Set initial menu
    icon.menu = create_menu()
    
    # Schedule periodic menu updates
    def menu_updater():
        while not shutdown_event.is_set():
            try:
                update_menu()
            except Exception as e:
                logger.log_event(f"Error updating menu: {e}")
            time.sleep(5)  # Update every 5 seconds
    
    # Start menu updater in background
    menu_thread = threading.Thread(target=menu_updater, daemon=True)
    menu_thread.start()

    # Run the system tray (this blocks until quit)
    icon.run()
    logger.log_event("Application exited")
