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
from munin_client.time_tracker import TimeTracker

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
        self.time_tracker = TimeTracker()  # Add time tracker
        self.is_reconnecting = False  # Track reconnection state
        
        # Munin-specific service UUIDs (matching Arduino code)
        self.MUNIN_SERVICE_UUID = "6e400001-8a3a-11e5-8994-feff819cdc9f"
        self.MUNIN_LOG_CHAR_UUID = "6e400002-8a3a-11e5-8994-feff819cdc9f"
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
    
    def _process_log_entry(self, log_entry: 'MuninLogEntry'):
        """Process a received log entry (shared implementation)"""
        logger.log_event(f"Processed log entry: type=0x{log_entry.event_type:02x}, face={log_entry.face_id}, session={log_entry.session_id}, delta={log_entry.delta_ms}ms")
        
        # Handle face switch events for time tracking
        if log_entry.event_type == 0x01:  # Face switch event
            # Log the face change to CSV
            self.time_tracker.log_face_change(log_entry.face_id)
            
            # Also log to the regular logger for immediate feedback
            try:
                from munin_client.config import MuninConfig
                config = MuninConfig()
                face_label = config.get_face_label(log_entry.face_id)
            except Exception:
                face_label = f"Face {log_entry.face_id}"
            
            logger.log_face_change(log_entry.face_id, face_label)
        
        # TODO: Handle other event types (battery, boot, etc.) if needed

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
                
                # Check if this is a reconnection (time tracker has a current session)
                if self.time_tracker.current_face is not None:
                    self.is_reconnecting = True
                    logger.log_event(f"Reconnected to real Munin device: {self.name}")
                else:
                    logger.log_event(f"Connected to real Munin device: {self.name}")
                
                # Subscribe to log notifications if available
                await self._setup_log_notifications()
                
                return True
            return False
        except Exception as e:
            logger.log_event(f"Error connecting to real device {self.name}: {e}")
            return False
    
    async def disconnect(self, is_temporary: bool = False):
        """Disconnect from the real device"""
        try:
            # Finalize current time tracking session
            if not is_temporary:
                self.time_tracker.finalize_current_session(is_temporary=False)
            
            if self.client.is_connected:
                await self.client.disconnect()
            self.is_connected_flag = False
            logger.log_event(f"Disconnected from real Munin device: {self.name}" + 
                           (" (temporary)" if is_temporary else ""))
        except Exception as e:
            logger.log_event(f"Error disconnecting from real device: {e}")
    
    async def read_battery_level(self) -> Optional[int]:
        """Read battery level from real device"""
        try:
            if not self.is_connected():
                return None
            
            # Check if device has battery service
            services = self.client.services
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
            services = self.client.services
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
                
            elif len(data) == 1:  # Simple face change (from Arduino)
                face_id = int(data[0])
                logger.log_event(f"Received face change notification: face {face_id}")
                
                # Check if this is a reconnection scenario
                was_reconnecting = self.is_reconnecting
                if self.is_reconnecting:
                    # This is the first notification after reconnection
                    self.time_tracker.resume_session_if_same_face(face_id)
                    self.is_reconnecting = False
                    logger.log_event(f"Resumed session after reconnection: face {face_id}")
                else:
                    # This is a normal face change
                    self.time_tracker.log_face_change(face_id)
                
                # Also log to regular logger
                try:
                    from munin_client.config import MuninConfig
                    config = MuninConfig()
                    face_label = config.get_face_label(face_id)
                except Exception:
                    face_label = f"Face {face_id}"
                
                if not was_reconnecting:  # Don't double-log during reconnection
                    logger.log_face_change(face_id, face_label)
                
        except Exception as e:
            logger.log_event(f"Error parsing log notification: {e}")

class FakeMuninDevice(MuninDevice):
    """Fake Munin device for testing"""
    
    def __init__(self, name: str = "Munin-Test", address: str = "00:11:22:33:44:55"):
        super().__init__(name, address)
        self.current_face = 1
        self.session_id = 1
        self.face_configs: Dict[int, FaceConfig] = {}
        self.is_running = False
        self._simulation_task: Optional[asyncio.Task] = None
        
        # Protocol simulation state
        self.device_uptime_ms = 0  # Device uptime in milliseconds
        self.session_start_time = None  # When current session started
    
    async def connect(self) -> bool:
        """Connect to the fake device"""
        try:
            self.is_connected_flag = True
            self.battery_level = 85  # Start with 85% battery
            
            # Check if this is a reconnection (time tracker has a current session)
            if self.time_tracker.current_face is not None:
                self.is_reconnecting = True
                logger.log_event(f"Reconnected to fake Munin device: {self.name}")
            else:
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
    
    async def disconnect(self, is_temporary: bool = False):
        """Disconnect from the fake device"""
        try:
            # Finalize current time tracking session
            if not is_temporary:
                self.time_tracker.finalize_current_session(is_temporary=False)
            
            self.is_connected_flag = False
            self.is_running = False
            
            if self._simulation_task:
                self._simulation_task.cancel()
                try:
                    await self._simulation_task
                except asyncio.CancelledError:
                    pass
                self._simulation_task = None
            
            logger.log_event(f"Disconnected from fake Munin device: {self.name}" + 
                           (" (temporary)" if is_temporary else ""))
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
    
    def _send_protocol_packet(self, event_type: int, delta_ms: int = 0):
        """Generate and process a 7-byte Munin protocol packet internally"""
        try:
            # Create 7-byte packet: event_type, session_id, delta_ms (little-endian), face_id
            packet = struct.pack('<BBIB', event_type, self.session_id, delta_ms, self.current_face)
            
            # Process packet internally (same as real device would via BLE notification)
            log_entry = MuninLogEntry.from_packet(packet, datetime.now())
            self._process_log_entry(log_entry)
            
            logger.log_event(f"Fake device sent packet: type=0x{event_type:02x}, session={self.session_id}, delta={delta_ms}, face={self.current_face}")
        except Exception as e:
            logger.log_event(f"Error sending fake protocol packet: {e}")
    
    def _get_session_delta_ms(self) -> int:
        """Get milliseconds since current session started"""
        if not self.session_start_time:
            return 0
        
        from datetime import datetime
        delta = datetime.now() - self.session_start_time
        return int(delta.total_seconds() * 1000)
    
    async def _simulate_device(self):
        """Simulate device behavior with real Munin protocol"""
        import random
        from datetime import datetime
        
        logger.log_event(f"Started fake Munin device simulation: {self.name}")
        
        # Send BOOT event (0x10) to start simulation
        self.device_uptime_ms = 0
        self.session_start_time = datetime.now()
        self._send_protocol_packet(0x10, 0)  # Boot event
        
        # Send initial face switch event (0x01)
        self._send_protocol_packet(0x01, 0)  # Face switch with delta_ms = 0
        
        last_ongoing_log = datetime.now()
        ongoing_log_interval = 10.0  # Send ongoing log every 10 seconds
        
        while self.is_running and self.is_connected():
            try:
                current_time = datetime.now()
                
                # Update device uptime
                self.device_uptime_ms += 2000  # 2 seconds per cycle
                
                # Send ongoing log entries periodically (0x02)
                if (current_time - last_ongoing_log).total_seconds() >= ongoing_log_interval:
                    delta_ms = self._get_session_delta_ms()
                    self._send_protocol_packet(0x02, delta_ms)  # Ongoing log
                    last_ongoing_log = current_time
                
                # Simulate battery drain
                if random.random() < 0.02:  # 2% chance per cycle
                    old_battery = self.battery_level
                    self.battery_level = max(0, self.battery_level - 1)
                    
                    # Send low battery warning at 15%
                    if old_battery > 15 and self.battery_level <= 15:
                        self._send_protocol_packet(0x12, self.device_uptime_ms)  # Low battery
                
                # Simulate face changes
                if random.random() < 0.1:  # 10% chance per cycle (more frequent for testing)
                    old_face = self.current_face
                    self.current_face = random.randint(1, 6)
                    if old_face != self.current_face:
                        # Face changed - start new session
                        self.session_id = (self.session_id + 1) % 256
                        self.session_start_time = datetime.now()
                        
                        # Send face switch event
                        self._send_protocol_packet(0x01, 0)  # Face switch with delta_ms = 0
                        
                        logger.log_event(f"Fake device face changed from {old_face} to {self.current_face}")
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.log_event(f"Error in fake device simulation: {e}")
                break
        
        # Send shutdown event before stopping
        if self.is_connected():
            self._send_protocol_packet(0x11, self.device_uptime_ms)  # Shutdown event
        
        logger.log_event("Fake Munin device simulation stopped")
