from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from PyQt6.QtCore import QStandardPaths

@dataclass
class ProjectRecord:
    # Identity
    name: str = ""
    path: str = ""

    # URLs
    url: str = ""
    admin_url: str = ""

    # Stack + paths
    stack: str = ""
    doc_root: str = ""
    laragon_root: str = ""

    # DB (passwords now encrypted!)
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = ""
    db_user: str = ""
    db_pass: str = ""  # Stored encrypted
    table_prefix: str = "wp_"

    # Tooling (optional)
    php_path: str = ""
    wpcli_path: str = ""
    wpcli_is_phar: bool = False

    # Timestamps
    created_at_iso: str = ""
    last_action_iso: str = ""

    # Misc
    notes: str = ""

def _coerce_project(d: dict) -> ProjectRecord:
    allowed = set(ProjectRecord.__dataclass_fields__.keys())
    clean = {k: d.get(k) for k in allowed if k in d}
    return ProjectRecord(**clean)

class ProjectsStore:

    def __init__(self):
        base = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        base.mkdir(parents=True, exist_ok=True)
        self.file = base / "projects.json"
        self.data: dict[str, Any] = {"projects": []}
        
        # Initialize password manager
        from app.core.password_manager import get_password_manager
        self.pwd_manager = get_password_manager()
        
        self.load()

    def load(self):
        if self.file.exists():
            try:
                self.data = json.loads(self.file.read_text(encoding="utf-8"))
            except Exception:
                self.data = {"projects": []}

    def save(self):
        self.file.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_projects(self) -> list[ProjectRecord]:
        """Load projects and decrypt passwords"""
        out: list[ProjectRecord] = []
        for p in self.data.get("projects", []):
            try:
                rec = _coerce_project(p)
                # Decrypt password when loading
                if rec.db_pass:
                    rec.db_pass = self.pwd_manager.decrypt(rec.db_pass)
                out.append(rec)
            except Exception:
                continue
        out.sort(key=lambda x: x.created_at_iso, reverse=True)
        return out

    def upsert(self, rec: ProjectRecord):
        """Save project and encrypt password"""
        # Create a copy to avoid modifying original
        rec_dict = asdict(rec)
        
        # Encrypt password before saving
        if rec_dict["db_pass"]:
            rec_dict["db_pass"] = self.pwd_manager.encrypt(rec_dict["db_pass"])
        
        projects = self.data.get("projects", [])
        for i, p in enumerate(projects):
            if p.get("path") == rec.path:
                projects[i] = rec_dict
                self.data["projects"] = projects
                self.save()
                return
        projects.append(rec_dict)
        self.data["projects"] = projects
        self.save()

    def delete_by_path(self, path: str):
        projects = [p for p in self.data.get("projects", []) if p.get("path") != path]
        self.data["projects"] = projects
        self.save()

