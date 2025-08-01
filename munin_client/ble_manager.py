import asyncio
from typing import List, Optional, Tuple
import bleak
from bleak import BleakScanner, BleakClient
from munin_client.logger import MuninLogger
from munin_client.config import MuninConfig
from munin_client.device import MuninDevice, RealMuninDevice, FakeMuninDevice

logger = MuninLogger()

class BLEDeviceManager:
    def __init__(self, enable_fake_device: bool = False):
        self.config = MuninConfig()
        self.client: Optional[BleakClient] = None
        self.connected_device: Optional[MuninDevice] = None
        self.battery_level: Optional[int] = None
        
        # Fake device support
        self.fake_device: Optional[FakeMuninDevice] = None
        if enable_fake_device:
            self.fake_device = FakeMuninDevice()
            logger.log_event("Fake Munin device enabled for testing")
        
        # Standard BLE Battery Service UUID
        self.BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
        self.BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    
    async def scan_for_devices(self, timeout: float = 5.0) -> List[Tuple[str, str, str]]:
        """Scan for BLE devices and return list of (name, address, rssi)"""
        logger.log_event(f"Scanning for BLE devices for {timeout}s...")
        devices = []
        
        try:
            discovered = await BleakScanner.discover(timeout=timeout)
            for device in discovered:
                name = device.name or "Unknown"
                address = device.address
                rssi = getattr(device, 'rssi', None)
                
                # Skip devices with no RSSI (often cached/inactive devices)
                if rssi is None:
                    continue
                
                devices.append((name, address, str(rssi)))
                logger.log_event(f"Found device: {name} ({address}) RSSI: {rssi}")
        except Exception as e:
            logger.log_event(f"Error scanning for devices: {e}")
        
        # Add fake device if enabled
        if self.fake_device:
            fake_device_info = (self.fake_device.name, self.fake_device.address, "-30")
            devices.append(fake_device_info)
            logger.log_event(f"Added fake device to scan results: {self.fake_device.name}")
        
        return devices
    
    async def find_munin_devices(self) -> List[Tuple[str, str, str]]:
        """Find devices with 'Munin' in the name"""
        all_devices = await self.scan_for_devices(5.0)
        munin_devices = [
            (name, addr, rssi) for name, addr, rssi in all_devices 
            if 'munin' in name.lower()
        ]
        logger.log_event(f"Found {len(munin_devices)} Munin devices")
        return munin_devices
    
    async def connect_to_preferred_device(self) -> bool:
        """Try to connect to the configured preferred device"""
        device_name, mac_address = self.config.get_preferred_device()
        
        if mac_address:
            logger.log_event(f"Attempting to connect to preferred device: {device_name} ({mac_address})")
            return await self.connect_to_device(mac_address, device_name)
        else:
            logger.log_event("No preferred device configured")
            return False
    
    async def auto_connect_to_munin(self) -> bool:
        """Auto-connect to the first available Munin device"""
        munin_devices = await self.find_munin_devices()
        
        if munin_devices:
            name, address, rssi = munin_devices[0]
            logger.log_event(f"Auto-connecting to first Munin device: {name}")
            return await self.connect_to_device(address, name)
        else:
            logger.log_event("No Munin devices found for auto-connect")
            return False
    
    async def connect_to_device(self, address: str, name: str = None) -> bool:
        """Connect to a specific device by address"""
        try:
            # Check if this is our fake device
            if self.fake_device and address == self.fake_device.address:
                # Use the fake device directly
                if await self.fake_device.connect():
                    self.connected_device = self.fake_device
                    self.battery_level = await self.fake_device.read_battery_level()
                    return True
                return False
            
            # Handle real device
            if self.client and self.client.is_connected:
                await self.client.disconnect()
            
            self.client = BleakClient(address)
            await self.client.connect()
            
            if self.client.is_connected:
                # Create real device wrapper
                real_munin = RealMuninDevice(name or "Unknown", address, self.client)
                if await real_munin.connect():
                    self.connected_device = real_munin
                    self.battery_level = await real_munin.read_battery_level()
                    return True
                else:
                    await self.client.disconnect()
                    return False
            else:
                logger.log_event(f"Failed to connect to {address}")
                return False
        
        except Exception as e:
            logger.log_event(f"Error connecting to {address}: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from current device"""
        try:
            if self.connected_device:
                await self.connected_device.disconnect()
                device_name = self.connected_device.name
                self.connected_device = None
                self.battery_level = None
                logger.log_event(f"Disconnected from {device_name}")
            
            if self.client and self.client.is_connected:
                await self.client.disconnect()
                self.client = None
        except Exception as e:
            logger.log_event(f"Error disconnecting: {e}")
    
    async def read_battery_level(self) -> Optional[int]:
        """Read battery level from connected device"""
        if not self.is_connected():
            return None
        
        try:
            self.battery_level = await self.connected_device.read_battery_level()
            return self.battery_level
        except Exception as e:
            logger.log_event(f"Error reading battery level: {e}")
            return None
    
    def get_battery_level(self) -> Optional[int]:
        """Get cached battery level"""
        return self.battery_level
    
    def is_connected(self) -> bool:
        """Check if currently connected to a device"""
        return self.connected_device is not None and self.connected_device.is_connected()
    
    def get_connected_device_info(self) -> Optional[Tuple[str, str]]:
        """Get info about currently connected device"""
        if self.connected_device:
            return self.connected_device.get_device_info()
        return None
    
    async def send_face_config(self, face_configs):
        """Send face configuration to connected device"""
        if not self.connected_device:
            return False
        return await self.connected_device.send_face_config(face_configs)
