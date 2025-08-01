import threading
import asyncio
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
import sys
from munin_client.logger import MuninLogger

logger = MuninLogger()

# Dummy image for tray icon
def create_image():
    image = Image.new('RGB', (64, 64), color=(0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
    return image

# Dummy BLE logic (to be replaced with actual BLE interface)
def ble_worker():
    logger.log_event("Starting BLE worker (dummy)")
    # placeholder for BLE event loop
    while True:
        pass

def start_tray():
    icon = Icon("Munin", create_image(), menu=Menu(
        MenuItem("Open Logs", lambda: logger.log_event("TODO: Open Logs")),
        MenuItem("Quit", lambda icon, item: sys.exit(0))
    ))

    # Start BLE worker in background
    thread = threading.Thread(target=ble_worker, daemon=True)
    thread.start()

    icon.run()
