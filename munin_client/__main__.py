import argparse
from munin_client.tray import start_tray

def main():
    parser = argparse.ArgumentParser(description="Munin BLE Time Tracking Client")
    parser.add_argument("--fake", action="store_true", 
                       help="Start a fake Munin device for testing")
    args = parser.parse_args()
    
    # Pass the fake device flag to the tray
    start_tray(enable_fake_device=args.fake)

if __name__ == "__main__":
    main()
