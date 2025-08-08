import json
import os
from pathlib import Path
from typing import Dict, Optional, Any
from munin_client.logger import MuninLogger

logger = MuninLogger()

class MuninConfig:
    def __init__(self):
        self.config_dir = Path.home() / ".munin"
        self.config_file = self.config_dir / "config.json"
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
                logger.log_event("Configuration loaded")
                
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
        
        # Save updated config if any labels were added
        if config_updated:
            self.save_config(self._config)
            logger.log_event("Updated config with missing face labels")
    
    def save_config(self, config: Dict[str, Any]):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self._config = config
            logger.log_event("Configuration saved")
        except Exception as e:
            logger.log_event(f"Error saving config: {e}")
    
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
