#!/usr/bin/env python3
"""
Serial monitor for Munin device console output.
Provides a more reliable alternative to screen for monitoring device output.
"""

import serial
import sys
import time
import signal
import argparse
from datetime import datetime

class SerialMonitor:
    def __init__(self, port='/dev/cu.usbmodem101', baudrate=115200, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.running = False
        
    def connect(self):
        """Connect to the serial port."""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"Connected to {self.port} at {self.baudrate} baud")
            print("Press Ctrl+C to exit")
            print("-" * 50)
            return True
        except serial.SerialException as e:
            print(f"Failed to connect to {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the serial port."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"\nDisconnected from {self.port}")
    
    def monitor(self, show_timestamps=False, log_file=None):
        """Monitor serial output."""
        if not self.connect():
            return False
            
        self.running = True
        log_handle = None
        
        if log_file:
            log_handle = open(log_file, 'a')
            print(f"Logging to {log_file}")
        
        try:
            while self.running:
                try:
                    if self.ser.in_waiting > 0:
                        try:
                            line = self.ser.readline().decode('utf-8', errors='replace').rstrip()
                            if line:
                                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                                
                                if show_timestamps:
                                    output = f"[{timestamp}] {line}"
                                else:
                                    output = line
                                    
                                print(output)
                                
                                if log_handle:
                                    log_handle.write(f"[{timestamp}] {line}\n")
                                    log_handle.flush()
                                    
                        except UnicodeDecodeError:
                            # Skip invalid characters
                            pass
                    else:
                        time.sleep(0.01)  # Small delay to prevent excessive CPU usage
                except (OSError, serial.SerialException) as e:
                    print(f"\nSerial connection lost: {e}")
                    break
                    
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            self.running = False
        finally:
            if log_handle:
                log_handle.close()
            self.disconnect()
            
        return True

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print("\nReceived interrupt signal")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='Monitor Munin device serial output')
    parser.add_argument('-p', '--port', default='/dev/cu.usbmodem101', 
                       help='Serial port (default: /dev/cu.usbmodem101)')
    parser.add_argument('-b', '--baudrate', type=int, default=115200,
                       help='Baud rate (default: 115200)')
    parser.add_argument('-t', '--timestamps', action='store_true',
                       help='Show timestamps for each line')
    parser.add_argument('-l', '--log', type=str,
                       help='Log output to file')
    
    args = parser.parse_args()
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal_handler)
    
    monitor = SerialMonitor(args.port, args.baudrate)
    success = monitor.monitor(args.timestamps, args.log)
    
    if not success:
        sys.exit(1)

if __name__ == '__main__':
    main()
