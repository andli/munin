#!/usr/bin/env python3
"""
Generate config.example.json from the authoritative defaults in MuninConfig.

Run this script whenever you change default values in munin_client/config.py
to keep config.example.json in sync.
"""

import json
from munin_client.config import MuninConfig

def generate_example_config():
    """Generate example config file from MuninConfig defaults"""
    config = MuninConfig()
    
    # Add comments to the JSON (though technically not valid JSON, it's helpful)
    example_config = {
        "// NOTE": "This example shows the default configuration values.",
        "// INFO": "The authoritative defaults are defined in munin_client/config.py",
        **config.default_config
    }
    
    # Write to config.example.json with nice formatting
    with open('config.example.json', 'w') as f:
        json.dump(example_config, f, indent=2)
    
    print("Generated config.example.json from MuninConfig defaults")
    print("Face colors:")
    for face_id, color in config.default_config["face_colors"].items():
        print(f"  Face {face_id}: RGB({color['r']},{color['g']},{color['b']})")

if __name__ == "__main__":
    generate_example_config()