import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional, Any
from munin_client.logger import MuninLogger

logger = MuninLogger()

class MuninConfig:
    def __init__(self):
        self.config_dir = Path.home() / ".munin"
        self.config_file = self.config_dir / "config.json"
        # SINGLE SOURCE OF TRUTH for all default configuration values
        # Changes here will propagate to new configs and reset operations
        self.default_config = {
            "preferred_device_name": None,
            "preferred_mac_address": None,
            "face_labels": {
                "1": "Emails",
                "2": "Coding", 
                "3": "Meetings",
                "4": "Planning",
                "5": "Break",
                "6": "Off"
            },
            "face_colors": {
                "1": {"r": 255, "g": 0, "b": 0},      # Red
                "2": {"r": 0, "g": 255, "b": 0},      # Green
                "3": {"r": 0, "g": 0, "b": 255},      # Blue
                "4": {"r": 255, "g": 255, "b": 0},    # Yellow
                "5": {"r": 255, "g": 0, "b": 255},    # Magenta
                "6": {"r": 128, "g": 128, "b": 128}   # Gray
            },
            "activity_summary": {
                "monthly_start_date": 1,  # Day of month to start monthly reports
                "show_percentages": False,
                "time_format": "hours"  # "auto", "seconds", "minutes", "hours"
            },
            "ui_preferences": {
                "show_notifications": True,
                "minimize_to_tray": True,
                "auto_connect": True
            }
        }
        self._config = None
        self._ensure_config_exists()
    
    def _ensure_config_exists(self):
        """Create config directory and file if they don't exist"""
        self.config_dir.mkdir(exist_ok=True)
        if not self.config_file.exists():
            logger.log_event("Creating default config file")
            self.save_config(self.default_config)
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if self._config is None:
            try:
                with open(self.config_file, 'r') as f:
                    self._config = json.load(f)
                logger.log_event("Configuration loaded", "debug")
                
                # Ensure all default face labels are present
                self._ensure_all_face_labels()
                
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.log_event(f"Error loading config: {e}, using defaults")
                self._config = self.default_config.copy()
        return self._config
    
    def _ensure_all_face_labels(self):
        """Ensure all face labels from default config are present"""
        if "face_labels" not in self._config:
            self._config["face_labels"] = {}
        
        default_face_labels = self.default_config["face_labels"]
        config_updated = False
        
        for face_id, default_label in default_face_labels.items():
            if face_id not in self._config["face_labels"]:
                self._config["face_labels"][face_id] = default_label
                config_updated = True
        
        # Also ensure face colors are present
        if "face_colors" not in self._config:
            self._config["face_colors"] = {}
        
        default_face_colors = self.default_config["face_colors"]
        for face_id, default_color in default_face_colors.items():
            if face_id not in self._config["face_colors"]:
                self._config["face_colors"][face_id] = default_color
                config_updated = True
        
        # Save updated config if any labels or colors were added
        if config_updated:
            self.save_config(self._config)
            logger.log_event("Updated config with missing face labels/colors")
    
    def save_config(self, config: Dict[str, Any]):
        """Save configuration atomically (never append / partial write).

        Strategy:
        1. Serialize JSON to a temp file in the same directory.
        2. Flush + fsync to ensure bytes hit disk.
        3. os.replace() to atomically swap into place.
        This prevents duplicated JSON fragments or truncated files if the
        process crashes mid-write.
        """
        try:
            self.config_dir.mkdir(exist_ok=True)
            # Serialize first
            data = json.dumps(config, indent=2)
            # Write to temp file in same directory for atomic replace
            with tempfile.NamedTemporaryFile('w', dir=self.config_dir, delete=False, prefix='config.', suffix='.tmp') as tmp:
                tmp.write(data)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = Path(tmp.name)
            # Atomic replace
            os.replace(temp_path, self.config_file)
            self._config = config
            logger.log_event("Configuration saved (atomic)")
        except Exception as e:
            logger.log_event(f"Error saving config atomically: {e}")
            # Best effort cleanup: remove temp if it still exists
            try:
                if 'temp_path' in locals() and temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
    
    def get_preferred_device(self) -> tuple[Optional[str], Optional[str]]:
        """Get preferred device name and MAC address"""
        config = self.load_config()
        return config.get("preferred_device_name"), config.get("preferred_mac_address")
    
    def set_preferred_device(self, device_name: str, mac_address: str):
        """Set preferred device name and MAC address"""
        config = self.load_config()
        config["preferred_device_name"] = device_name
        config["preferred_mac_address"] = mac_address
        self.save_config(config)
        logger.log_event(f"Set preferred device: {device_name} ({mac_address})")
    
    def get_face_labels(self) -> Dict[str, str]:
        """Get face labels configuration"""
        config = self.load_config()
        return config.get("face_labels", self.default_config["face_labels"])
    
    def set_face_label(self, face_number: str, label: str):
        """Set label for a specific face"""
        config = self.load_config()
        if "face_labels" not in config:
            config["face_labels"] = {}
        config["face_labels"][face_number] = label
        self.save_config(config)
        logger.log_event(f"Set face {face_number} label to: {label}")
    
    def get_face_label(self, face_number: int) -> str:
        """Get label for a specific face number"""
        face_labels = self.get_face_labels()
        return face_labels.get(str(face_number), f"Face {face_number}")
    
    def get_face_colors(self) -> Dict[str, Dict[str, int]]:
        """Get face colors configuration"""
        config = self.load_config()
        return config.get("face_colors", self.default_config["face_colors"])
    
    def get_face_color(self, face_number: int) -> Dict[str, int]:
        """Get color for a specific face number."""
        face_colors = self.get_face_colors()
        default_color = {"r": 128, "g": 128, "b": 128}
        return face_colors.get(str(face_number), default_color)
    
    def set_face_color(self, face_number: str, r: int, g: int, b: int):
        """Set color for a specific face."""
        config = self.load_config()
        if "face_colors" not in config:
            config["face_colors"] = {}
        config["face_colors"][face_number] = {"r": r, "g": g, "b": b}
        self.save_config(config)
        logger.log_event(f"Set face {face_number} color to: RGB({r},{g},{b})")
    
    def get_activity_summary_config(self) -> Dict[str, Any]:
        """Get activity summary configuration"""
        config = self.load_config()
        return config.get("activity_summary", self.default_config["activity_summary"])
    
    def set_activity_summary_config(self, **kwargs):
        """Update activity summary configuration"""
        config = self.load_config()
        if "activity_summary" not in config:
            config["activity_summary"] = self.default_config["activity_summary"].copy()
        
        for key, value in kwargs.items():
            if key in self.default_config["activity_summary"]:
                config["activity_summary"][key] = value
        
        self.save_config(config)
        logger.log_event(f"Updated activity summary config: {kwargs}")
    
    def get_monthly_start_date(self) -> int:
        """Get the day of month when monthly reports should start"""
        summary_config = self.get_activity_summary_config()
        return summary_config.get("monthly_start_date", 1)
    
    def set_monthly_start_date(self, day: int):
        """Set the day of month when monthly reports should start (1-28)"""
        if not 1 <= day <= 28:
            raise ValueError("Monthly start date must be between 1 and 28")
        self.set_activity_summary_config(monthly_start_date=day)
    
    def get_ui_preferences(self) -> Dict[str, Any]:
        """Get UI preferences"""
        config = self.load_config()
        return config.get("ui_preferences", self.default_config["ui_preferences"])
