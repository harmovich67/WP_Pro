"""
Monitoring and Health Check Module
"""
from __future__ import annotations
import re
import requests
import warnings
from pathlib import Path
from datetime import datetime
from typing import Callable

# Suppress SSL warnings for local development
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

LogFn = Callable[[str], None]

class SiteMonitor:
    @staticmethod
    def check_site_health(url: str) -> dict:
        """Check if site is accessible"""
        try:
            # Disable SSL verification for local development
            verify_ssl = not any(x in url.lower() for x in ['localhost', '127.0.0.1', '.local'])
            
            response = requests.get(url, timeout=10, verify=verify_ssl)
            return {
                "status": "online" if response.status_code == 200 else "error",
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds()
            }
        except Exception as e:
            return {
                "status": "offline",
                "error": str(e)
            }
    
    @staticmethod
    def parse_debug_log(project_path: str) -> list[dict]:
        """Parse WordPress debug.log file"""
        log_path = Path(project_path) / "wp-content" / "debug.log"
        
        if not log_path.exists():
            return []
        
        try:
            content = log_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")[-100:]  # Last 100 lines
            
            errors = []
            error_pattern = r'\[(.*?)\]\s+(PHP\s+)?(Fatal error|Warning|Notice|Error):\s+(.*)'
            
            for line in lines:
                match = re.search(error_pattern, line)
                if match:
                    timestamp, _, severity, message = match.groups()
                    errors.append({
                        "timestamp": timestamp,
                        "severity": severity,
                        "message": message,
                        "full_line": line
                    })
            
            return errors
        except Exception:
            return []
    
    @staticmethod
    def check_disk_space(project_path: str) -> dict:
        """Check disk space for project"""
        import shutil
        try:
            path = Path(project_path)
            usage = shutil.disk_usage(path)
            return {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": (usage.used / usage.total) * 100
            }
        except Exception:
            return {}
