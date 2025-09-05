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
        self.last_face_label = None  # Label of previous (from) face

        if not TIME_LOG_PATH.exists():
            with open(TIME_LOG_PATH, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "face_id", "face_label", "duration_s"])

    def log_face_change(self, face_id: int, face_label: str):
        """Record a face transition and emit a single arrow-style log line.

        Writes the session we are leaving (previous face) to CSV and logs
        an arrow line: previous → new (new_label). Initial face uses '-' as previous.
        Duplicate same-face events are suppressed.
        """
        # Suppress redundant events
        if self.last_face_id == face_id:
            return

        now_dt = datetime.utcnow()
        now_iso = now_dt.isoformat()

        if self.last_face_id is None or self.last_timestamp is None:
            # First face after startup / initialization
            logging.info(f"Face changed: - → {face_id} ({face_label})")
        else:
            # Compute duration for the face we're leaving
            duration = (now_dt - self.last_timestamp).total_seconds()
            prev_label = self.last_face_label or f"Face {self.last_face_id}"
            with open(TIME_LOG_PATH, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([now_iso, self.last_face_id, prev_label, int(duration)])
            logging.info(f"Face changed: {self.last_face_id} → {face_id} ({face_label})")

        # Update state
        self.last_face_id = face_id
        self.last_face_label = face_label
        self.last_timestamp = now_dt

    def log_battery(self, level: int):
        logging.info(f"Battery: {level}%")

    def log_event(self, msg: str, level: str = "info"):
        getattr(logging, level.lower())(msg)
