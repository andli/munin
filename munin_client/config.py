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
                "3": "Meetings"
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
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.log_event(f"Error loading config: {e}, using defaults")
                self._config = self.default_config.copy()
        return self._config
    
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
