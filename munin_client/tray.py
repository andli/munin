import threading
import asyncio
import time
import os
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
    


# BLE worker - handles connection and communication
async def ble_worker_async():
    logger.log_event("Starting BLE worker")
    
    # Try to connect to preferred device first, then auto-discover
    connected = await ble_manager.connect_to_preferred_device()
    if not connected:
        connected = await ble_manager.auto_connect_to_munin()
    
    if not connected:
        logger.log_event("No Munin device found - continuing without connection")
    
    # Main BLE loop
    battery_check_counter = 0
    while not shutdown_event.is_set():
        if ble_manager.is_connected():
            # Check battery every 30 seconds (30 * 1 second sleep)
            if battery_check_counter >= 30:
                await ble_manager.read_battery_level()
                battery_check_counter = 0
            
            battery_check_counter += 1
            await asyncio.sleep(1)
        else:
            # Try to reconnect every 10 seconds
            await asyncio.sleep(10)
            if not shutdown_event.is_set():
                logger.log_event("Attempting to reconnect...")
                await ble_manager.auto_connect_to_munin()
                battery_check_counter = 0
    
    # Cleanup
    await ble_manager.disconnect()
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
    
    def configure_device_callback(*args):
        logger.log_event("Configure Device clicked")
        # TODO: Implement device configuration dialog
        # For now, just scan and log available devices
        def scan_devices():
            async def do_scan():
                devices = await ble_manager.scan_for_devices(5.0)
                logger.log_event(f"Found {len(devices)} devices")
                for name, addr, rssi in devices:
                    logger.log_event(f"  {name} ({addr}) RSSI: {rssi}")
            
            asyncio.run(do_scan())
        
        # Run scan in background thread to avoid blocking UI
        scan_thread = threading.Thread(target=scan_devices, daemon=True)
        scan_thread.start()

    def show_activity_summary(*args):
        """Show activity summary in a dialog"""
        try:
            from munin_client.time_summary import TimeTrackingSummary
            summary = TimeTrackingSummary()
            summary_text = summary.get_summary_text(30)  # Last 30 days
            
            # For now, just log it - could be enhanced with a proper dialog
            logger.log_event("Activity Summary requested")
            print("\n" + summary_text + "\n")
            
            # Try to show in a simple dialog if tkinter is available
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()  # Hide the main window
                messagebox.showinfo("Munin Activity Summary", summary_text)
                root.destroy()
            except ImportError:
                logger.log_event("Activity summary displayed in console (tkinter not available)")
        except Exception as e:
            logger.log_event(f"Error showing activity summary: {e}")
    
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
            MenuItem("Activity Summary", show_activity_summary),
            MenuItem("Open Logs", lambda *args: logger.log_event("TODO: Open Logs")),
            MenuItem("Configure Device...", configure_device_callback),
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
