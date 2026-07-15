"""
Backup Scheduler Module
Handles automated backup scheduling using APScheduler
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

class BackupScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.schedules_file = Path("schedules.json")
        self.schedules = self._load_schedules()
        
    def _load_schedules(self) -> dict:
        """Load schedules from JSON file"""
        if not self.schedules_file.exists():
            return {}
        try:
            return json.loads(self.schedules_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    
    def _save_schedules(self):
        """Save schedules to JSON file"""
        self.schedules_file.write_text(
            json.dumps(self.schedules, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def add_schedule(
        self,
        schedule_id: str,
        project_path: str,
        project_name: str,
        frequency: str,  # "hourly", "daily", "weekly", "custom"
        time_spec: str,  # "14:00" for daily, "mon,wed" for weekly, etc.
        backup_files: bool,
        backup_db: bool,
        callback: Callable
    ):
        """Add a new backup schedule"""
        # Create trigger based on frequency
        if frequency == "hourly":
            trigger = IntervalTrigger(hours=1)
        elif frequency == "daily":
            hour, minute = map(int, time_spec.split(":"))
            trigger = CronTrigger(hour=hour, minute=minute)
        elif frequency == "weekly":
            days = time_spec.split(",")  # e.g., "mon,wed"
            hour, minute = 0, 0  # Default time, can be extended
            trigger = CronTrigger(day_of_week=",".join(days), hour=hour, minute=minute)
        else:  # custom cron
            trigger = CronTrigger.from_crontab(time_spec)
        
        # Add job to scheduler
        self.scheduler.add_job(
            callback,
            trigger=trigger,
            id=schedule_id,
            args=[project_path, backup_files, backup_db],
            replace_existing=True
        )
        
        # Save schedule metadata
        self.schedules[schedule_id] = {
            "project_path": project_path,
            "project_name": project_name,
            "frequency": frequency,
            "time_spec": time_spec,
            "backup_files": backup_files,
            "backup_db": backup_db,
            "created_at": datetime.utcnow().isoformat(),
            "enabled": True
        }
        self._save_schedules()
    
    def remove_schedule(self, schedule_id: str):
        """Remove a backup schedule"""
        try:
            self.scheduler.remove_job(schedule_id)
        except Exception:
            pass
        
        if schedule_id in self.schedules:
            del self.schedules[schedule_id]
            self._save_schedules()

    def get_schedules(self) -> dict:
        """Get all schedules"""
        return self.schedules
    
    def get_schedules_for_project(self, project_path: str) -> list[dict]:
        """Get all schedules for a specific project"""
        result = []
        for schedule_id, schedule in self.schedules.items():
            if schedule["project_path"] == project_path:
                result.append({
                    "id": schedule_id,
                    **schedule
                })
        return result
    
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
