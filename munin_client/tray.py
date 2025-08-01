import threading
import asyncio
import time
import os
from pystray import Icon, MenuItem, Menu
from PIL import Image
from munin_client.logger import MuninLogger

logger = MuninLogger()

# Global shutdown event
shutdown_event = threading.Event()

def get_icon_image():
    
    # Define icon paths relative to the package
    icon_dir = os.path.dirname(__file__)
    icon_path = os.path.join(icon_dir, "munin_tray_icon.png")
    return Image.open(icon_path)
    


# Dummy BLE logic (to be replaced with actual BLE interface)
def ble_worker():
    logger.log_event("Starting BLE worker")
    # placeholder for BLE event loop
    while not shutdown_event.is_set():
        time.sleep(0.1)  # Small sleep to prevent busy waiting
    logger.log_event("BLE worker shutting down")

def start_tray():
    # Start BLE worker in background
    thread = threading.Thread(target=ble_worker, daemon=True)
    thread.start()
    
    def quit_callback(*args):
        logger.log_event("Quitting application")
        shutdown_event.set()
        icon.stop()
    
    icon = Icon(
        "Munin",
        get_icon_image(),
        menu=Menu(
            MenuItem("Open Logs", lambda *args: logger.log_event("TODO: Open Logs")),
            MenuItem("Quit", quit_callback)
        )
    )

    logger.log_event("Starting application")
    icon.run()
    logger.log_event("Application exited")
