"""
Time tracking and CSV logging for Munin face changes.

This module handles logging face changes to CSV files in the format specified
in the README.md file.
"""

import csv
import os
from datetime import datetime
from typing import Optional
from munin_client.logger import MuninLogger
from munin_client.config import MuninConfig

logger = MuninLogger()

class TimeTracker:
    """Handles time tracking and CSV logging for face changes"""
    
    def __init__(self):
        self.config = MuninConfig()
        self.current_face: Optional[int] = None
        self.current_face_start_time: Optional[datetime] = None
        self.csv_file_path = self._get_csv_file_path()
        
        # Ensure CSV file exists with headers
        self._initialize_csv_file()
    
    def _get_csv_file_path(self) -> str:
        """Get the path for the CSV log file"""
        # For now, use a default path. Later this can be configurable
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "munin_time_log.csv")
    
    def _initialize_csv_file(self):
        """Initialize CSV file with headers if it doesn't exist"""
        if not os.path.exists(self.csv_file_path):
            try:
                with open(self.csv_file_path, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['timestamp', 'face_id', 'face_label', 'duration_s'])
                logger.log_event(f"Created new time log file: {self.csv_file_path}")
            except Exception as e:
                logger.log_event(f"Error creating CSV file: {e}")
    
    def log_face_change(self, new_face_id: int):
        """Track a face change (CSV + internal state) without emitting user INFO log."""
        current_time = datetime.now()

        # Suppress duplicate same-face notifications
        if self.current_face == new_face_id:
            return

        # Finalize previous face duration
        if self.current_face is not None and self.current_face_start_time is not None:
            duration = (current_time - self.current_face_start_time).total_seconds()
            self._write_csv_entry(self.current_face_start_time, self.current_face, duration)

        # Start new face session
        self.current_face = new_face_id
        self.current_face_start_time = current_time

        # Debug only (avoid duplicate visible logs handled by MuninLogger.log_face_change)
        face_label = self.config.get_face_label(new_face_id)
        logger.log_event(f"Face tracker updated to {new_face_id} ({face_label})", "debug")
    
    def _write_csv_entry(self, timestamp: datetime, face_id: int, duration_s: float):
        """Write a single CSV entry"""
        try:
            face_label = self.config.get_face_label(face_id)
            
            with open(self.csv_file_path, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    timestamp.isoformat(),
                    face_id,
                    face_label,
                    round(duration_s, 1)
                ])
            
            logger.log_event(f"Logged time entry: {face_label} for {duration_s:.1f}s")
            
        except Exception as e:
            logger.log_event(f"Error writing to CSV: {e}")
    
    def finalize_current_session(self, is_temporary: bool = False):
        """Finalize the current session when disconnecting
        
        Args:
            is_temporary: If True, this is for a temporary disconnection (reconnection expected)
        """
        if self.current_face is not None and self.current_face_start_time is not None:
            current_time = datetime.now()
            duration = (current_time - self.current_face_start_time).total_seconds()
            self._write_csv_entry(self.current_face_start_time, self.current_face, duration)
            
            if is_temporary:
                # Keep tracking state for reconnection, but update start time
                self.current_face_start_time = current_time
                logger.log_event(f"Temporarily finalized session for face {self.current_face}", "debug")
            else:
                # Reset tracking completely
                self.current_face = None
                self.current_face_start_time = None
                logger.log_event("Finalized current time tracking session", "debug")
    
    def resume_session_if_same_face(self, face_id: int):
        """Resume session if reconnecting to the same face"""
        if self.current_face == face_id and self.current_face_start_time is not None:
            # Continue with the same face, just update start time to now
            logger.log_event(f"Resumed tracking for face {face_id} after reconnection", "debug")
        else:
            # Different face or no previous session, start fresh
            self.log_face_change(face_id)
    
    def sync_current_face(self, face_id: int, elapsed_seconds: int):
        """Sync with device state - face was already active for elapsed_seconds"""
        current_time = datetime.now()
        
        # Calculate when this face session actually started
        from datetime import timedelta
        actual_start_time = current_time - timedelta(seconds=elapsed_seconds)
        
        # If we have a different current face, finalize it first
        if self.current_face is not None and self.current_face != face_id:
            # Calculate duration up to when the device switched (not now)
            if self.current_face_start_time is not None:
                duration = (actual_start_time - self.current_face_start_time).total_seconds()
                if duration > 0:  # Only log if positive duration
                    self._write_csv_entry(self.current_face_start_time, self.current_face, duration)
        
        # Set current face state to match device
        self.current_face = face_id
        self.current_face_start_time = actual_start_time
        
        face_label = self.config.get_face_label(face_id)
        logger.log_event(f"Synced with device: face {face_id} ({face_label}) active for {elapsed_seconds}s")
    
    def get_csv_file_path(self) -> str:
        """Get the current CSV file path"""
        return self.csv_file_path
