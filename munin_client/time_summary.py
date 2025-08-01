"""
Simple time tracking summary utility for Munin logs.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

class TimeTrackingSummary:
    """Analyzes Munin time tracking CSV logs"""
    
    def __init__(self):
        self.log_dir = Path.home() / "Munin" / "logs"
        self.time_log_path = self.log_dir / "time_log.csv"
    
    def get_activity_summary(self, days: int = 30) -> Dict[str, float]:
        """Get activity summary for the last N days"""
        if not self.time_log_path.exists():
            return {}
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        activity_totals = defaultdict(float)
        
        try:
            with open(self.time_log_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse timestamp
                    try:
                        timestamp = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                    except:
                        continue
                    
                    # Skip entries older than cutoff
                    if timestamp < cutoff_date:
                        continue
                    
                    # Add duration to activity total
                    face_label = row['face_label']
                    duration_s = float(row['duration_s'])
                    activity_totals[face_label] += duration_s
            
        except Exception as e:
            print(f"Error reading time log: {e}")
            return {}
        
        return dict(activity_totals)
    
    def format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
    
    def get_summary_text(self, days: int = 30) -> str:
        """Get formatted summary text for display"""
        activities = self.get_activity_summary(days)
        
        if not activities:
            return f"No activity data (last {days} days)"
        
        # Sort by total time
        sorted_activities = sorted(activities.items(), key=lambda x: x[1], reverse=True)
        
        lines = [f"Activity Summary (last {days} days):"]
        lines.append("-" * 30)
        
        total_time = sum(activities.values())
        
        for activity, duration in sorted_activities:
            percentage = (duration / total_time * 100) if total_time > 0 else 0
            formatted_duration = self.format_duration(duration)
            lines.append(f"{activity}: {formatted_duration} ({percentage:.1f}%)")
        
        lines.append("-" * 30)
        lines.append(f"Total: {self.format_duration(total_time)}")
        
        return "\n".join(lines)
