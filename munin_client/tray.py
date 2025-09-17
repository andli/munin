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
import sys
import subprocess

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
                # If there's a pending request to push face colors, do it now on the BLE loop
                if getattr(ble_manager, '_pending_send_config', False):
                    try:
                        await ble_manager._send_face_configuration()
                    finally:
                        ble_manager._pending_send_config = False
                        logger.log_event("Sent face color configuration to device (config reload)")
                
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
        """Launch external settings editor process (Tk on main thread)."""
        try:
            subprocess.Popen([sys.executable, '-m', 'munin_client.settings_editor'])
            logger.log_event("Launched settings editor")
        except Exception as e:
            logger.log_event(f"Failed to launch settings editor: {e}")



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
            is_charging = ble_manager.get_charging_status()
            battery_voltage = ble_manager.get_battery_voltage()
            
            if battery_level is not None:
                # Add battery icon based on level and charging status
                if is_charging:
                    icon_battery = "🔌"  # Charging icon
                elif battery_level > 75:
                    icon_battery = "🔋"
                elif battery_level > 50:
                    icon_battery = "🔋"
                elif battery_level > 25:
                    icon_battery = "🪫"
                else:
                    icon_battery = "🪫"
                
                # Build battery status text
                if is_charging:
                    status_parts = [f"{icon_battery} Battery: {battery_level}% - Charging"]
                else:
                    status_parts = [f"{icon_battery} Battery: {battery_level}%"]
                    if battery_level <= 15:
                        status_parts.append("(Low)")
                
                # Add voltage if available
                if battery_voltage is not None:
                    status_parts.append(f"({battery_voltage:.1f}V)")
                
                return " ".join(status_parts)
            else:
                return "🔋 Battery: Unknown"
        return None
    
    def get_current_face_text():
        """Get current face information for menu"""
        if ble_manager.is_connected() and ble_manager.connected_device:
            # Get current face from time tracker
            current_face = ble_manager.connected_device.time_tracker.current_face
            if current_face is not None:
                try:
                    face_label = config.get_face_label(current_face)
                    face_color = config.get_face_color(current_face)
                    
                    # Create a visual representation of the color
                    # Use colored circle emoji or square as color indicator
                    if face_color['r'] > 200 and face_color['g'] < 100 and face_color['b'] < 100:
                        color_icon = "🔴"  # Red
                    elif face_color['g'] > 200 and face_color['r'] < 100 and face_color['b'] < 100:
                        color_icon = "🟢"  # Green
                    elif face_color['b'] > 200 and face_color['r'] < 100 and face_color['g'] < 100:
                        color_icon = "🔵"  # Blue
                    elif face_color['r'] > 200 and face_color['g'] > 200 and face_color['b'] < 100:
                        color_icon = "🟡"  # Yellow
                    elif face_color['r'] > 200 and face_color['b'] > 200 and face_color['g'] < 100:
                        color_icon = "🟣"  # Purple/Magenta
                    elif face_color['r'] > 100 and face_color['g'] > 100 and face_color['b'] > 100:
                        color_icon = "⚪"  # White/Gray
                    else:
                        color_icon = "🟤"  # Brown/Other
                    
                    return f"{color_icon} Current: {face_label}"
                except Exception:
                    return f"🎲 Current: Face {current_face}"
            else:
                return "🎲 Current: Unknown"
        return None
    
    # Create dynamic menu
    def create_menu():
        menu_items = [
            MenuItem(get_status_text(), None, enabled=False),  # Status (non-clickable)
        ]
        
        # Add current face if connected
        current_face_text = get_current_face_text()
        if current_face_text:
            menu_items.append(MenuItem(current_face_text, None, enabled=False))
        
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
    
    # Track config modification time for external changes (settings editor)
    last_config_mtime = None
    config_path = config.config_file

    # Schedule periodic menu + config updates
    def menu_updater():
        nonlocal last_config_mtime
        while not shutdown_event.is_set():
            try:
                update_menu()
                # Detect config changes
                if config_path.exists():
                    mtime = config_path.stat().st_mtime
                    if last_config_mtime is None:
                        last_config_mtime = mtime
                    elif mtime != last_config_mtime:
                        last_config_mtime = mtime
                        # Reload config
                        config._config = None  # force reload
                        config.load_config()
                        logger.log_event("Config reloaded (detected external change)")
                        # Push colors if connected (schedule for BLE worker loop)
                        try:
                            if ble_manager.is_connected():
                                ble_manager.send_face_colors_to_device()
                                logger.log_event("Scheduled face color configuration push (config reload)")
                        except Exception as e:
                            logger.log_event(f"Failed sending colors after reload: {e}")
            except Exception as e:
                logger.log_event(f"Error in menu loop: {e}")
            time.sleep(5)
    
    # Start menu updater in background
    menu_thread = threading.Thread(target=menu_updater, daemon=True)
    menu_thread.start()

    # Run the system tray (this blocks until quit)
    icon.run()
    logger.log_event("Application exited")
