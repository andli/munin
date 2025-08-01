import csv
import logging
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / "Munin" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

TIME_LOG_PATH = LOG_DIR / "time_log.csv"
EVENT_LOG_PATH = LOG_DIR / "events.log"

# Configure event logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(EVENT_LOG_PATH),
        logging.StreamHandler()
    ]
)

class MuninLogger:
    def __init__(self):
        self.last_face_id = None
        self.last_timestamp = None

        if not TIME_LOG_PATH.exists():
            with open(TIME_LOG_PATH, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "face_id", "face_label", "duration_s"])

    def log_face_change(self, face_id: int, face_label: str):
        now = datetime.utcnow().isoformat()
        if self.last_face_id is not None and self.last_timestamp:
            duration = (datetime.utcnow() - self.last_timestamp).total_seconds()
            with open(TIME_LOG_PATH, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([now, self.last_face_id, face_label, int(duration)])
            logging.info(f"Face changed: {self.last_face_id} → {face_id} ({face_label})")
        else:
            logging.info(f"Initial face: {face_id} ({face_label})")

        self.last_face_id = face_id
        self.last_timestamp = datetime.utcnow()

    def log_battery(self, level: int):
        logging.info(f"Battery: {level}%")

    def log_event(self, msg: str, level: str = "info"):
        getattr(logging, level.lower())(msg)
