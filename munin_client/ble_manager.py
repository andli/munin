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
        self.is_charging: bool = False
        self.battery_voltage: Optional[float] = None
        
        # Munin-specific UUIDs
        self.MUNIN_FACE_SERVICE_UUID = "6e400001-8a3a-11e5-8994-feff819cdc9f"
        self.MUNIN_FACE_CHAR_UUID = "6e400002-8a3a-11e5-8994-feff819cdc9f"
        
        # Fake device support
        self.fake_device: Optional[FakeMuninDevice] = None
        if enable_fake_device:
            self.fake_device = FakeMuninDevice(ble_manager=self)
            logger.log_event("Fake Munin device enabled for testing")
        
        # Standard BLE Battery Service UUID
        self.BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
        self.BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    
    async def scan_for_devices(self, timeout: float = 5.0) -> List[Tuple[str, str, str]]:
        """Scan for BLE devices and return list of (name, address, rssi) for Munin devices only"""
        logger.log_event(f"Scanning for Munin devices for {timeout}s...")
        devices = []
        
        try:
            discovered = await BleakScanner.discover(timeout=timeout)
            logger.log_event(f"BLE scan completed, found {len(discovered)} raw devices")
            
            for device in discovered:
                name = device.name or "Unknown"
                address = device.address
                rssi = getattr(device, 'rssi', None)
                
                # Check if device advertises the Munin face service
                advertised_services = getattr(device, 'metadata', {}).get('uuids', [])
                has_munin_service = any(
                    uuid.lower() == self.MUNIN_FACE_SERVICE_UUID.lower() 
                    for uuid in advertised_services
                )
                
                # Also check if device name contains "Munin" as fallback
                is_munin_device = has_munin_service or 'munin' in name.lower()
                
                # Only add Munin devices to the list
                if is_munin_device:
                    logger.log_event(f"Found Munin device: {name} ({address}) RSSI: {rssi} Service: {has_munin_service}")
                    devices.append((name, address, str(rssi) if rssi is not None else "Unknown"))
                
        except Exception as e:
            logger.log_event(f"Error scanning for devices: {e}")
        
        # Add fake device if enabled
        if self.fake_device:
            fake_device_info = (self.fake_device.name, self.fake_device.address, "-30")
            devices.append(fake_device_info)
            logger.log_event(f"Added fake device to scan results: {self.fake_device.name}")
        
        logger.log_event(f"Final device list: {len(devices)} Munin devices")
        return devices
    
    async def find_munin_devices(self) -> List[Tuple[str, str, str]]:
        """Find devices with Munin face service UUID or 'Munin' in the name"""
        all_devices = await self.scan_for_devices(5.0)
        
        # scan_for_devices already filtered for Munin devices, so just return them
        logger.log_event(f"Found {len(all_devices)} Munin devices")
        return all_devices
    
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
                    
                    # Send face configuration after successful connection
                    await self._send_face_configuration()
                    
                    return True
                return False
            
            # Handle real device
            if self.client and self.client.is_connected:
                await self.client.disconnect()
            
            self.client = BleakClient(address)
            await self.client.connect()
            
            if self.client.is_connected:
                # Create real device wrapper
                real_munin = RealMuninDevice(name or "Unknown", address, self.client, ble_manager=self)
                if await real_munin.connect():
                    self.connected_device = real_munin
                    self.battery_level = await real_munin.read_battery_level()
                    
                    # Send face configuration after successful connection
                    await self._send_face_configuration()
                    
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
    
    async def disconnect(self, is_temporary: bool = False):
        """Disconnect from current device
        
        Args:
            is_temporary: If True, this is a temporary disconnect (reconnection expected)
        """
        try:
            if self.connected_device:
                # Finalize time tracking session
                if hasattr(self.connected_device, 'time_tracker'):
                    self.connected_device.time_tracker.finalize_current_session(is_temporary)
                
                await self.connected_device.disconnect()
                device_name = self.connected_device.name
                
                if not is_temporary:
                    self.connected_device = None
                    self.battery_level = None
                    
                logger.log_event(f"Disconnected from {device_name}" + 
                               (" (temporary)" if is_temporary else ""))
            
            if self.client and self.client.is_connected:
                await self.client.disconnect()
                if not is_temporary:
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
    
    def get_charging_status(self) -> bool:
        """Get current charging status"""
        return self.is_charging
    
    def get_battery_voltage(self) -> Optional[float]:
        """Get battery voltage if available"""
        return self.battery_voltage
    
    def update_charging_status(self, charging: bool):
        """Update charging status (called by device event processing)"""
        self.is_charging = charging
    
    def update_battery_voltage(self, voltage: float):
        """Update battery voltage (called by device event processing)"""
        self.battery_voltage = voltage
    
    def is_connected(self) -> bool:
        """Check if currently connected to a device"""
        if self.connected_device is None:
            return False
        
        # For real devices, also check the underlying BLE client
        if hasattr(self.connected_device, 'client') and self.connected_device.client:
            try:
                return self.connected_device.client.is_connected and self.connected_device.is_connected()
            except Exception:
                return False
        
        return self.connected_device.is_connected()
    
    async def check_connection_health(self) -> bool:
        """Perform a deeper connection health check"""
        if not self.is_connected():
            return False
        
        try:
            # Try to read battery level as a connection test
            # This will fail if the connection is actually dead
            await self.connected_device.read_battery_level()
            return True
        except Exception as e:
            logger.log_event(f"Connection health check failed: {e}")
            # Mark device as disconnected
            if self.connected_device:
                self.connected_device.is_connected_flag = False
            return False
    
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
    
    async def _send_face_configuration(self):
        """Send face color configuration from config to device"""
        try:
            # Import FaceConfig here to avoid circular imports
            from munin_client.device import FaceConfig
            
            face_configs = []
            face_colors = self.config.get_face_colors()
            
            for face_id_str, color in face_colors.items():
                face_id = int(face_id_str)
                face_config = FaceConfig(
                    face_id=face_id,
                    r=color["r"],
                    g=color["g"],
                    b=color["b"]
                )
                face_configs.append(face_config)
            
            if face_configs:
                success = await self.send_face_config(face_configs)
                if success:
                    logger.log_event(f"Sent face color configuration to device ({len(face_configs)} faces)")
                else:
                    logger.log_event("Failed to send face color configuration to device")
            
        except Exception as e:
            logger.log_event(f"Error sending face configuration: {e}")
