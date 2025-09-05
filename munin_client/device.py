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
    delta_s: int
    face_id: int
    timestamp: datetime
    
    @classmethod
    def from_packet(cls, packet_data: bytes, arrival_time: datetime) -> 'MuninLogEntry':
        """Parse a 6-byte Munin log packet"""
        if len(packet_data) != 6:
            raise ValueError(f"Invalid packet length: {len(packet_data)} (expected 6)")
        
        # Unpack the 6-byte packet: uint8, uint32 (little-endian), uint8
        event_type, delta_s, face_id = struct.unpack('<BIB', packet_data)
        
        return cls(
            event_type=event_type,
            delta_s=delta_s,
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
    
    def __init__(self, name: str, address: str, ble_manager=None):
        self.name = name
        self.address = address
        self.battery_level: Optional[int] = None
        self.is_connected_flag = False
        self.time_tracker = TimeTracker()  # Add time tracker
        self.is_reconnecting = False  # Track reconnection state
        self.ble_manager = ble_manager  # Reference to BLE manager for callbacks
        
        # Munin-specific service UUIDs (matching Arduino code)
        self.MUNIN_SERVICE_UUID = "6e400001-8a3a-11e5-8994-feff819cdc9f"
        self.MUNIN_LOG_CHAR_UUID = "6e400002-8a3a-11e5-8994-feff819cdc9f"
        self.MUNIN_LED_CONFIG_CHAR_UUID = "6e400003-8a3a-11e5-8994-feff819cdc9f"
        self.MUNIN_FACE_CHAR_UUID = "6e400004-8a3a-11e5-8994-feff819cdc9f"
        
        # Standard BLE Battery Service
        self.BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
        self.BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
        self.BATTERY_LEVEL_STATUS_CHAR_UUID = "00002a1b-0000-1000-8000-00805f9b34fb"
    
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
        logger.log_event(f"Processed log entry: type=0x{log_entry.event_type:02x}, face={log_entry.face_id}, delta={log_entry.delta_s}s", "debug")
        
        # Handle face switch events for time tracking
        if log_entry.event_type == 0x01:  # Face switch event (always delta=0 now)
            self.time_tracker.log_face_change(log_entry.face_id)
            
            # Also log to the regular logger for immediate feedback
            try:
                from munin_client.config import MuninConfig
                config = MuninConfig()
                face_label = config.get_face_label(log_entry.face_id)
            except Exception:
                face_label = f"Face {log_entry.face_id}"
            
            logger.log_face_change(log_entry.face_id, face_label)
            
        elif log_entry.event_type == 0x03:  # State sync event
            # This is a connection state sync - the device was already on this face
            logger.log_event(f"Connection state sync: face {log_entry.face_id} active for {log_entry.delta_s}s")
            # Don't log as a new face change, just update tracking state
            self.time_tracker.sync_current_face(log_entry.face_id, log_entry.delta_s)
            
        elif log_entry.event_type == 0x04:  # Battery status event
            # Decode battery status from packet
            voltage_10mv = log_entry.delta_s  # Voltage in 10mV units
            voltage_mv = voltage_10mv * 10    # Convert to mV
            percentage = log_entry.face_id & 0x7F  # Lower 7 bits
            is_charging = bool(log_entry.face_id & 0x80)  # MSB is charging flag
            
            logger.log_event(f"Battery status: {voltage_mv}mV, {percentage}%, {'charging' if is_charging else 'discharging'}")
            if self.ble_manager:
                self.ble_manager.update_battery_status(voltage_mv, percentage, is_charging)
            
        elif log_entry.event_type == 0x10:  # Boot event
            logger.log_event("Device booted")
            
        elif log_entry.event_type == 0x11:  # Shutdown event
            logger.log_event("Device shutting down")
            
        elif log_entry.event_type == 0x12:  # Low battery event
            logger.log_event(f"LOW BATTERY WARNING - device voltage below safe threshold")
            
        elif log_entry.event_type == 0x20:  # BLE connect event
            logger.log_event("BLE client connected")
            
        elif log_entry.event_type == 0x21:  # BLE disconnect event
            logger.log_event("BLE client disconnected")
            
        # TODO: Handle other event types if needed in the future

class RealMuninDevice(MuninDevice):
    """Real Munin BLE device implementation"""
    
    def __init__(self, name: str, address: str, client, ble_manager=None):
        super().__init__(name, address, ble_manager)
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
                    # Read battery level
                    battery_data = await self.client.read_gatt_char(self.BATTERY_LEVEL_CHAR_UUID)
                    if battery_data:
                        self.battery_level = int(battery_data[0])
                        logger.log_event(f"Read battery level from BLE service: {self.battery_level}%")
                        
                        # Try to read charging status from Battery Level Status characteristic
                        try:
                            status_data = await self.client.read_gatt_char(self.BATTERY_LEVEL_STATUS_CHAR_UUID)
                            if status_data and len(status_data) >= 1:
                                # Battery Level Status format: bit 0-1 = battery charge state
                                # 0 = unknown, 1 = charging, 2 = discharging active, 3 = discharging inactive
                                charge_state = status_data[0] & 0x03
                                is_charging = (charge_state == 1)  # 1 = charging
                                
                                # Update charging status in BLE manager
                                self.ble_manager.update_charging_status(is_charging)
                                logger.log_event(f"Read charging status from BLE service: {'charging' if is_charging else 'not charging'}")
                        except Exception:
                            # Battery Level Status characteristic not available - will use custom protocol events
                            pass
                        
                        return self.battery_level
            
            # No standard battery service found - battery data comes via custom protocol
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
                await self.client.write_gatt_char(self.MUNIN_LED_CONFIG_CHAR_UUID, packet)
                #logger.log_event(f"Sent face config for face {config.face_id}: RGB({config.r},{config.g},{config.b})")
            
            return True
        except Exception as e:
            logger.log_event(f"Error sending face config to real device: {e}")
            return False
    
    async def _setup_log_notifications(self):
        """Setup notifications for log entries and face changes"""
        try:
            # Check if device has Munin service
            services = self.client.services
            for service in services:
                if service.uuid.lower() == self.MUNIN_SERVICE_UUID.lower():
                    # Setup notification handler for log characteristic
                    await self.client.start_notify(self.MUNIN_LOG_CHAR_UUID, self._log_notification_handler)
                    logger.log_event("Setup log notifications for real Munin device")
                    
                    # Setup notification handler for face characteristic  
                    try:
                        await self.client.start_notify(self.MUNIN_FACE_CHAR_UUID, self._face_notification_handler)
                        logger.log_event("Setup face notifications for real Munin device")
                        
                        # Read current face immediately after enabling notifications
                        current_face_data = await self.client.read_gatt_char(self.MUNIN_FACE_CHAR_UUID)
                        if current_face_data and len(current_face_data) > 0:
                            current_face = int(current_face_data[0])
                            logger.log_event(f"Read current face on connect: {current_face}")
                            
                            # Initialize time tracker with current face
                            if not self.is_reconnecting:
                                self.time_tracker.log_face_change(current_face)
                            else:
                                # Reconnection - resume if same face
                                self.time_tracker.resume_session_if_same_face(current_face)
                                self.is_reconnecting = False
                            
                    except Exception as e:
                        logger.log_event(f"Could not setup face notifications (older firmware?): {e}")
                    
                    return
            
            logger.log_event("Real device does not have Munin service")
        except Exception as e:
            logger.log_event(f"Error setting up notifications: {e}")
    
    def _face_notification_handler(self, sender, data: bytearray):
        """Handle incoming face change notifications"""
        try:
            if len(data) == 1:
                face_id = int(data[0])
                logger.log_event(f"Received face notification: face {face_id}", "debug")
                
                # Process face change
                self.time_tracker.log_face_change(face_id)
                
                # Also log to regular logger
                try:
                    from munin_client.config import MuninConfig
                    config = MuninConfig()
                    face_label = config.get_face_label(face_id)
                except Exception:
                    face_label = f"Face {face_id}"
                
                logger.log_face_change(face_id, face_label)
            else:
                logger.log_event(f"Received invalid face notification: {len(data)} bytes", "debug")
                
        except Exception as e:
            logger.log_event(f"Error parsing face notification: {e}")
    
    def _log_notification_handler(self, sender, data: bytearray):
        """Handle incoming log notifications"""
        try:
            logger.log_event(f"Received BLE notification: {len(data)} bytes: {data.hex()}", "debug")
            
            if len(data) == 6:  # Valid Munin log packet (now 6 bytes without session)
                log_entry = MuninLogEntry.from_packet(bytes(data), datetime.now())
                
                # Process log entry immediately - no caching needed
                self._process_log_entry(log_entry)
                
            elif len(data) == 1:  # Simple face change (from Arduino)
                face_id = int(data[0])
                logger.log_event(f"Received face change notification: face {face_id}", "debug")
                
                # Check if this is a reconnection scenario
                was_reconnecting = self.is_reconnecting
                if self.is_reconnecting:
                    # This is the first notification after reconnection
                    self.time_tracker.resume_session_if_same_face(face_id)
                    self.is_reconnecting = False
                    logger.log_event(f"Resumed session after reconnection: face {face_id}", "debug")
                else:
                    # Normal face change; suppress if duplicate
                    if self.time_tracker.current_face != face_id:
                        self.time_tracker.log_face_change(face_id)
                
                # Also log to regular logger
                try:
                    from munin_client.config import MuninConfig
                    config = MuninConfig()
                    face_label = config.get_face_label(face_id)
                except Exception:
                    face_label = f"Face {face_id}"
                
                if not was_reconnecting:  # Don't double-log during reconnection
                    if self.time_tracker.current_face == face_id and self.time_tracker.current_face_start_time is not None:
                        # Only log transition if it was actually a change (time_tracker updated)
                        pass
                    else:
                        logger.log_face_change(face_id, face_label)
            else:
                logger.log_event(f"Received unknown notification format: {len(data)} bytes", "debug")
                
        except Exception as e:
            logger.log_event(f"Error parsing log notification: {e}")

class FakeMuninDevice(MuninDevice):
    """Fake Munin device for testing"""
    
    def __init__(self, name: str = "Munin-Test", address: str = "00:11:22:33:44:55", ble_manager=None):
        super().__init__(name, address, ble_manager)
        self.current_face = 1
        self.face_configs: Dict[int, FaceConfig] = {}
        self.is_running = False
        self._simulation_task: Optional[asyncio.Task] = None
        
        # Protocol simulation state
        self.device_uptime_s = 0  # Device uptime in seconds
        self.session_start_time = None  # When current session started
        
        # Battery and charging simulation
        self.is_charging = False
        self.charging_start_time = None
        self.last_battery_check = None
    
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
            logger.log_event(f"Fake device received face config for face {config.face_id}: RGB({config.r},{config.g},{config.b})", "debug")
        
        return True
    
    def _send_protocol_packet(self, event_type: int, delta_s: int = 0):
        """Generate and process a 6-byte Munin protocol packet internally"""
        try:
            # Create 6-byte packet: event_type, delta_s (little-endian), face_id
            packet = struct.pack('<BIB', event_type, delta_s, self.current_face)
            
            # Process packet internally (same as real device would via BLE notification)
            log_entry = MuninLogEntry.from_packet(packet, datetime.now())
            self._process_log_entry(log_entry)
            
            logger.log_event(f"Fake device sent packet: type=0x{event_type:02x}, delta={delta_s}, face={self.current_face}", "debug")
        except Exception as e:
            logger.log_event(f"Error sending fake protocol packet: {e}")
    
    def _get_session_delta_s(self) -> int:
        """Get seconds since current session started"""
        if not self.session_start_time:
            return 0
        
        from datetime import datetime
        delta = datetime.now() - self.session_start_time
        return int(delta.total_seconds())
    
    async def _simulate_device(self):
        """Simulate device behavior with real Munin protocol"""
        import random
        from datetime import datetime
        
        logger.log_event(f"Started fake Munin device simulation: {self.name}")
        
        # Send BOOT event (0x10) to start simulation
        self.device_uptime_s = 0
        self.session_start_time = datetime.now()
        self.last_battery_check = datetime.now()
        self._send_protocol_packet(0x10, 0)  # Boot event
        
        # Send initial face switch event (0x01)
        self._send_protocol_packet(0x01, 0)  # Face switch with delta_s = 0
        
        last_ongoing_log = datetime.now()
        ongoing_log_interval = 10.0  # Send ongoing log every 10 seconds
        
        while self.is_running and self.is_connected():
            try:
                current_time = datetime.now()
                
                # Update device uptime
                self.device_uptime_s += 2  # 2 seconds per cycle
                
                # Send ongoing log entries periodically (0x02)
                if (current_time - last_ongoing_log).total_seconds() >= ongoing_log_interval:
                    delta_s = self._get_session_delta_s()
                    self._send_protocol_packet(0x02, delta_s)  # Ongoing log
                    last_ongoing_log = current_time
                
                # Simulate charging status changes
                if random.random() < 0.05:  # 5% chance per cycle to change charging status
                    if not self.is_charging:
                        # Start charging
                        self.is_charging = True
                        self.charging_start_time = current_time
                        logger.log_event("Fake device: Charging simulation started")
                    elif random.random() < 0.3:  # 30% chance to stop charging if already charging
                        # Stop charging
                        was_fully_charged = self.battery_level >= 95
                        self.is_charging = False
                        self.charging_start_time = None
                        
                        if was_fully_charged:
                            logger.log_event("Fake device: Fully charged simulation")
                        else:
                            logger.log_event("Fake device: Charging stopped simulation")
                
                # Simulate battery changes based on charging status
                if (current_time - self.last_battery_check).total_seconds() >= 5.0:  # Check every 5 seconds
                    old_battery = self.battery_level
                    
                    if self.is_charging:
                        # Battery increases while charging
                        if self.battery_level < 100:
                            self.battery_level = min(100, self.battery_level + random.randint(1, 3))
                    else:
                        # Battery decreases when not charging
                        if random.random() < 0.3:  # 30% chance to drain
                            self.battery_level = max(0, self.battery_level - 1)
                    
                    # Send low battery warning at 15%
                    if old_battery > 15 and self.battery_level <= 15:
                        self._send_protocol_packet(0x12, self.device_uptime_s)  # Low battery
                        logger.log_event("Fake device: Low battery warning")
                    
                    self.last_battery_check = current_time
                
                # Simulate face changes
                if random.random() < 0.1:  # 10% chance per cycle (more frequent for testing)
                    old_face = self.current_face
                    self.current_face = random.randint(1, 6)
                    if old_face != self.current_face:
                        # Face changed - start new session time tracking
                        self.session_start_time = datetime.now()
                        
                        # Send face switch event
                        self._send_protocol_packet(0x01, 0)  # Face switch with delta_s = 0
                        
                        logger.log_event(f"Fake device face changed from {old_face} to {self.current_face}")
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.log_event(f"Error in fake device simulation: {e}")
                break
        
        # Send shutdown event before stopping
        if self.is_connected():
            self._send_protocol_packet(0x11, self.device_uptime_s)  # Shutdown event
        
        logger.log_event("Fake Munin device simulation stopped")
