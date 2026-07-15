from __future__ import annotations
import shutil
import platform
from dataclasses import dataclass
from pathlib import Path
from app.core.utils import is_windows, get_default_doc_root

@dataclass
class StackProfile:
    name: str
    doc_root: str
    db_host: str
    db_port: int
    php_path: str

def _find_laragon_php(laragon_root: str) -> str:
    root = Path(laragon_root)
    php_root = root / "bin" / "php"
    if not php_root.exists():
        return ""
    candidates = []
    for d in php_root.glob("php-*"):
        exe = d / ("php.exe" if platform.system().lower().startswith("win") else "php")
        if exe.exists():
            candidates.append(exe)
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x.parent.name)
    return str(candidates[-1])

def detect_default_profile(stack: str, laragon_root: str = "") -> StackProfile:
    if stack.lower().startswith("laragon") and is_windows():
        lr = laragon_root.strip() or "C:\\laragon"
        doc_root = str(Path(lr) / "www")
        php = _find_laragon_php(lr)
        return StackProfile("Laragon (Windows)", doc_root, "127.0.0.1", 3306, php)

    # Generic fallback:
    php = shutil.which("php") or ""
    doc = get_default_doc_root()
    return StackProfile("Custom", doc, "127.0.0.1", 3306, php)
