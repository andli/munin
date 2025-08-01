"""
Device abstraction for Munin BLE devices.

This module provides a unified interface for both real and fake Munin devices,
handling the custom Munin protocol as defined in PROTOCOL.md.
"""

import asyncio
import struct
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from munin_client.logger import MuninLogger

logger = MuninLogger()

@dataclass
class MuninLogEntry:
    """Represents a Munin time tracking log entry"""
    event_type: int
    session_id: int
    delta_ms: int
    face_id: int
    timestamp: datetime
    
    @classmethod
    def from_packet(cls, packet_data: bytes, arrival_time: datetime) -> 'MuninLogEntry':
        """Parse a 7-byte Munin log packet"""
        if len(packet_data) != 7:
            raise ValueError(f"Invalid packet length: {len(packet_data)} (expected 7)")
        
        # Unpack the 7-byte packet: uint8, uint8, uint32 (little-endian), uint8
        event_type, session_id, delta_ms, face_id = struct.unpack('<BBIB', packet_data)
        
        return cls(
            event_type=event_type,
            session_id=session_id,
            delta_ms=delta_ms,
            face_id=face_id,
            timestamp=arrival_time
        )

@dataclass
class FaceConfig:
    """Face color configuration"""
    face_id: int
    r: int
    g: int
    b: int
    
    def to_packet(self) -> bytes:
        """Convert to 4-byte configuration packet"""
        return struct.pack('<BBBB', self.face_id, self.r, self.g, self.b)

class MuninDevice(ABC):
    """Abstract base class for Munin devices (real and fake)"""
    
    def __init__(self, name: str, address: str):
        self.name = name
        self.address = address
        self.battery_level: Optional[int] = None
        self.is_connected_flag = False
        
        # Munin-specific service UUIDs
        self.MUNIN_SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
        self.MUNIN_LOG_CHAR_UUID = "87654321-4321-4321-4321-cba987654321"
        self.MUNIN_CONFIG_CHAR_UUID = "11111111-2222-3333-4444-555555555555"
        
        # Standard BLE Battery Service
        self.BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
        self.BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the device"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from the device"""
        pass
    
    @abstractmethod
    async def read_battery_level(self) -> Optional[int]:
        """Read battery level from device"""
        pass
    
    @abstractmethod
    async def send_face_config(self, face_configs: List[FaceConfig]) -> bool:
        """Send face color configuration to device"""
        pass
    
    def is_connected(self) -> bool:
        """Check if device is connected"""
        return self.is_connected_flag
    
    def get_device_info(self) -> Tuple[str, str]:
        """Get device name and address"""
        return (self.name, self.address)

class RealMuninDevice(MuninDevice):
    """Real Munin BLE device implementation"""
    
    def __init__(self, name: str, address: str, client):
        super().__init__(name, address)
        self.client = client
    
    async def connect(self) -> bool:
        """Connect to the real device"""
        try:
            if not self.client.is_connected:
                await self.client.connect()
            
            if self.client.is_connected:
                self.is_connected_flag = True
                logger.log_event(f"Connected to real Munin device: {self.name}")
                
                # Subscribe to log notifications if available
                await self._setup_log_notifications()
                
                return True
            return False
        except Exception as e:
            logger.log_event(f"Error connecting to real device {self.name}: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the real device"""
        try:
            if self.client.is_connected:
                await self.client.disconnect()
            self.is_connected_flag = False
            logger.log_event(f"Disconnected from real Munin device: {self.name}")
        except Exception as e:
            logger.log_event(f"Error disconnecting from real device: {e}")
    
    async def read_battery_level(self) -> Optional[int]:
        """Read battery level from real device"""
        try:
            if not self.is_connected():
                return None
            
            # Check if device has battery service
            services = await self.client.get_services()
            for service in services:
                if service.uuid.lower() == self.BATTERY_SERVICE_UUID.lower():
                    battery_data = await self.client.read_gatt_char(self.BATTERY_LEVEL_CHAR_UUID)
                    if battery_data:
                        self.battery_level = int(battery_data[0])
                        return self.battery_level
            
            logger.log_event("Real device does not have battery service")
            return None
        except Exception as e:
            logger.log_event(f"Error reading battery from real device: {e}")
            return None
    
    async def send_face_config(self, face_configs: List[FaceConfig]) -> bool:
        """Send face configuration to real device"""
        try:
            if not self.is_connected():
                return False
            
            # Send each face config as a 4-byte packet
            for config in face_configs:
                packet = config.to_packet()
                await self.client.write_gatt_char(self.MUNIN_CONFIG_CHAR_UUID, packet)
                logger.log_event(f"Sent face config for face {config.face_id}: RGB({config.r},{config.g},{config.b})")
            
            return True
        except Exception as e:
            logger.log_event(f"Error sending face config to real device: {e}")
            return False
    
    async def _setup_log_notifications(self):
        """Setup notifications for log entries"""
        try:
            # Check if device has Munin service
            services = await self.client.get_services()
            for service in services:
                if service.uuid.lower() == self.MUNIN_SERVICE_UUID.lower():
                    # Setup notification handler for log characteristic
                    await self.client.start_notify(self.MUNIN_LOG_CHAR_UUID, self._log_notification_handler)
                    logger.log_event("Setup log notifications for real Munin device")
                    return
            
            logger.log_event("Real device does not have Munin service")
        except Exception as e:
            logger.log_event(f"Error setting up notifications: {e}")
    
    def _log_notification_handler(self, sender, data: bytearray):
        """Handle incoming log notifications"""
        try:
            if len(data) == 7:  # Valid Munin log packet
                log_entry = MuninLogEntry.from_packet(bytes(data), datetime.now())
                
                # Process log entry immediately - no caching needed
                self._process_log_entry(log_entry)
                
        except Exception as e:
            logger.log_event(f"Error parsing log notification: {e}")
    
    def _process_log_entry(self, log_entry: MuninLogEntry):
        """Process a received log entry immediately"""
        logger.log_event(f"Received log entry: type=0x{log_entry.event_type:02x}, face={log_entry.face_id}, session={log_entry.session_id}")
        
        # TODO: Add proper log entry processing:
        # - Save to database/file
        # - Update UI/statistics  
        # - Handle different event types (face change, battery, boot, etc.)
        # - Reconstruct wall-clock timestamps using delta_ms

class FakeMuninDevice(MuninDevice):
    """Fake Munin device for testing"""
    
    def __init__(self, name: str = "Munin-Test", address: str = "00:11:22:33:44:55"):
        super().__init__(name, address)
        self.current_face = 1
        self.session_id = 1
        self.face_configs: Dict[int, FaceConfig] = {}
        self.is_running = False
        self._simulation_task: Optional[asyncio.Task] = None
    
    async def connect(self) -> bool:
        """Connect to the fake device"""
        try:
            self.is_connected_flag = True
            self.battery_level = 85  # Start with 85% battery
            logger.log_event(f"Connected to fake Munin device: {self.name}")
            
            # Start simulation
            if not self.is_running:
                self.is_running = True
                self._simulation_task = asyncio.create_task(self._simulate_device())
            else:
                logger.log_event(f"Fake device {self.name} simulation already running")
            
            return True
        except Exception as e:
            logger.log_event(f"Error connecting to fake device: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the fake device"""
        try:
            self.is_connected_flag = False
            self.is_running = False
            
            if self._simulation_task:
                self._simulation_task.cancel()
                try:
                    await self._simulation_task
                except asyncio.CancelledError:
                    pass
                self._simulation_task = None
            
            logger.log_event(f"Disconnected from fake Munin device: {self.name}")
        except Exception as e:
            logger.log_event(f"Error disconnecting from fake device: {e}")
    
    async def read_battery_level(self) -> Optional[int]:
        """Read battery level from fake device"""
        if self.is_connected():
            return self.battery_level
        return None
    
    async def send_face_config(self, face_configs: List[FaceConfig]) -> bool:
        """Send face configuration to fake device"""
        if not self.is_connected():
            return False
        
        for config in face_configs:
            self.face_configs[config.face_id] = config
            logger.log_event(f"Fake device received face config for face {config.face_id}: RGB({config.r},{config.g},{config.b})")
        
        return True
    
    async def _simulate_device(self):
        """Simulate device behavior"""
        import random
        
        logger.log_event(f"Started fake Munin device simulation: {self.name}")
        
        while self.is_running and self.is_connected():
            try:
                # Simulate battery drain
                if random.random() < 0.05:  # 5% chance per cycle
                    self.battery_level = max(0, self.battery_level - 1)
                
                # Simulate face changes
                if random.random() < 0.2:  # 20% chance per cycle
                    old_face = self.current_face
                    self.current_face = random.randint(1, 6)
                    if old_face != self.current_face:
                        self.session_id = (self.session_id + 1) % 256
                        logger.log_event(f"Fake device face changed from {old_face} to {self.current_face}")
                
                await asyncio.sleep(2)  # Check every 2 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.log_event(f"Error in fake device simulation: {e}")
                break
        
        logger.log_event("Fake Munin device simulation stopped")
