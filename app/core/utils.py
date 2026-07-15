from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass
class CmdResult:
    code: int
    out: str
    err: str

def run_cmd(cmd: list[str], cwd: Path | None = None) -> CmdResult:
    # On Windows, shell=True is often needed to find batch files/scripts in PATH
    use_shell = is_windows()
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        shell=use_shell
    )
    return CmdResult(p.returncode, p.stdout or "", p.stderr or "")

def which_any(names: list[str]) -> str:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return ""

def is_windows() -> bool:
    return platform.system().lower().startswith("win")

def is_linux() -> bool:
    return platform.system().lower().startswith("linux")

def get_default_doc_root() -> str:
    if is_windows():
        return "C:\\laragon\\www"
    return str(Path.home() / "var/www/html")

def open_path(path: Path):
    path = path.resolve()
    try:
        if is_windows():
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
        if platform.system().lower() == "darwin":
            subprocess.run(["open", str(path)], check=False)
            return
        subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass

def parse_wp_config(path: Path) -> dict:
    """Parse wp-config.php to extract DB credentials, prefix, and WordPress URLs."""
    if not path.exists():
        return {}
    
    content = path.read_text(encoding="utf-8", errors="ignore")
    out = {}
    
    # Simple regex for defines
    import re
    patterns = {
        "db_name": r"define\s*\(\s*['\"]DB_NAME['\"]\s*,\s*['\"](.*?)['\"]\s*\);",
        "db_user": r"define\s*\(\s*['\"]DB_USER['\"]\s*,\s*['\"](.*?)['\"]\s*\);",
        "db_pass": r"define\s*\(\s*['\"]DB_PASSWORD['\"]\s*,\s*['\"](.*?)['\"]\s*\);",
        "db_host": r"define\s*\(\s*['\"]DB_HOST['\"]\s*,\s*['\"](.*?)['\"]\s*\);",
        "wp_siteurl": r"define\s*\(\s*['\"]WP_SITEURL['\"]\s*,\s*['\"](.*?)['\"]\s*\);",
        "wp_home": r"define\s*\(\s*['\"]WP_HOME['\"]\s*,\s*['\"](.*?)['\"]\s*\);",
    }
    
    for key, pat in patterns.items():
        m = re.search(pat, content)
        if m:
            out[key] = m.group(1)
            
    # Table prefix
    m_prefix = re.search(r"\$table_prefix\s*=\s*['\"](.*?)['\"];", content)
    if m_prefix:
        out["table_prefix"] = m_prefix.group(1)
    else:
        out["table_prefix"] = "wp_"
        
    return out
