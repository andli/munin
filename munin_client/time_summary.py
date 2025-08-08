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
        
        # Load configuration
        try:
            from munin_client.config import MuninConfig
            self.config = MuninConfig()
        except ImportError:
            self.config = None
    
    def get_activity_summary(self, days: int = None, start_date: datetime = None, end_date: datetime = None) -> Dict[str, float]:
        """Get activity summary for a specified period"""
        if not self.time_log_path.exists():
            return {}
        
        # Use default days from config if not specified
        if days is None and start_date is None and end_date is None:
            if self.config:
                activity_config = self.config.get_activity_summary_config()
                days = activity_config.get("default_period_days", 30)
            else:
                days = 30
        
        # Calculate date range
        if start_date and end_date:
            cutoff_date = start_date
            end_limit = end_date
        elif days:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            end_limit = datetime.utcnow()
        else:
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            end_limit = datetime.utcnow()
        
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
                    
                    # Skip entries outside date range
                    if timestamp < cutoff_date or timestamp > end_limit:
                        continue
                    
                    # Add duration to activity total
                    face_label = row['face_label']
                    duration_s = float(row['duration_s'])
                    activity_totals[face_label] += duration_s
            
        except Exception as e:
            print(f"Error reading time log: {e}")
            return {}
        
        return dict(activity_totals)
    
    def get_monthly_summary(self, year: int = None, month: int = None) -> Dict[str, float]:
        """Get activity summary for a specific month, starting from configured start date"""
        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month
        
        # Get monthly start date from config
        start_day = 1
        if self.config:
            start_day = self.config.get_monthly_start_date()
        
        # Calculate start and end dates for the month
        start_date = datetime(year, month, start_day)
        
        # Calculate end date (start of next period)
        if month == 12:
            end_date = datetime(year + 1, 1, start_day)
        else:
            end_date = datetime(year, month + 1, start_day)
        
        return self.get_activity_summary(start_date=start_date, end_date=end_date)
    
    def format_duration(self, seconds: float, time_format: str = "auto") -> str:
        """Format duration in human-readable format"""
        if time_format == "seconds":
            return f"{seconds:.0f}s"
        elif time_format == "minutes":
            return f"{seconds/60:.1f}m"
        elif time_format == "hours":
            return f"{seconds/3600:.1f}h"
        else:  # auto format
            if seconds < 60:
                return f"{seconds:.0f}s"
            elif seconds < 3600:
                return f"{seconds/60:.1f}m"
            else:
                hours = seconds / 3600
                return f"{hours:.1f}h"
    
    def get_summary_text(self, days: int = None, start_date: datetime = None, end_date: datetime = None, 
                        period_label: str = None) -> str:
        """Get formatted summary text for display"""
        activities = self.get_activity_summary(days=days, start_date=start_date, end_date=end_date)
        
        if not activities:
            period_desc = period_label or f"last {days or 30} days" if not start_date else "specified period"
            return f"No activity data ({period_desc})"
        
        # Get formatting preferences from config
        time_format = "auto"
        show_percentages = True
        if self.config:
            activity_config = self.config.get_activity_summary_config()
            time_format = activity_config.get("time_format", "auto")
            show_percentages = activity_config.get("show_percentages", True)
        
        # Sort by total time
        sorted_activities = sorted(activities.items(), key=lambda x: x[1], reverse=True)
        
        # Create period description
        if period_label:
            period_desc = period_label
        elif start_date and end_date:
            period_desc = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        else:
            period_desc = f"last {days or 30} days"
        
        lines = [f"Activity Summary ({period_desc}):"]
        lines.append("-" * 40)
        
        # Calculate total excluding "Off" time (inactive/non-working time)
        total_time = sum(duration for activity, duration in activities.items() if activity != "Off")
        
        for activity, duration in sorted_activities:
            formatted_duration = self.format_duration(duration, time_format)
            if show_percentages and total_time > 0:
                percentage = (duration / total_time * 100)
                lines.append(f"{activity}: {formatted_duration} ({percentage:.1f}%)")
            else:
                lines.append(f"{activity}: {formatted_duration}")
        
        lines.append("-" * 40)
        lines.append(f"Total: {self.format_duration(total_time, time_format)}")
        
        return "\n".join(lines)
    
    def get_monthly_summary_text(self, year: int = None, month: int = None) -> str:
        """Get formatted monthly summary text"""
        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month
        
        month_name = datetime(year, month, 1).strftime('%B %Y')
        activities = self.get_monthly_summary(year, month)
        
        # Create date range label
        start_day = 1
        if self.config:
            start_day = self.config.get_monthly_start_date()
        
        start_date = datetime(year, month, start_day)
        if month == 12:
            end_date = datetime(year + 1, 1, start_day)
        else:
            end_date = datetime(year, month + 1, start_day)
        
        period_label = f"{month_name} (from {start_day}th)"
        
        if not activities:
            return f"No activity data for {period_label}"
        
        return self.get_summary_text(
            start_date=start_date, 
            end_date=end_date, 
            period_label=period_label
        )


# Convenience functions for easy access
def get_summary_text(days: int = 30) -> str:
    """Get activity summary text for the specified number of days."""
    summary = TimeTrackingSummary()
    return summary.get_summary_text(days=days)

def get_monthly_summary(start_day: int = None, time_format: str = "hours") -> str:
    """Get monthly activity summary starting from the specified day."""
    summary = TimeTrackingSummary()
    return summary.get_monthly_summary_text()
