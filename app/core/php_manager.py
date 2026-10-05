"""
app/core/php_manager.py
─────────────────────────────────────────────
PHP Version Switcher — detects every PHP install available on the machine
(Laragon, XAMPP, system PATH, or a manually browsed binary) and lets a
project pin a specific version.

Two levels of "switching" are supported:
  1. Tooling-level (always safe): the chosen php.exe is stored on the
     project record and used for every WP-CLI / tooling invocation.
  2. Apache-level (optional/advanced): spins up an isolated php-cgi.exe
     process for the chosen version and points the project's Laragon
     Apache vhost at it via mod_proxy_fcgi, so the live site itself
     (not just WP-CLI) is served by that PHP version. This mutates a
     vhost file, so a .bak backup is always written first and a revert
     helper is provided.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.core.utils import is_windows, run_cmd, which_any
from app.core.i18n import t as tr

LogFn = Callable[[str], None]


@dataclass
class PhpVersion:
    version: str
    path: str
    source: str  # "Laragon" | "XAMPP" | "PATH" | "Custom"


def _version_from_folder_name(php_exe: Path) -> str:
    m = re.search(r"php-(\d+(?:\.\d+){1,2})", php_exe.parent.name)
    if m:
        return m.group(1)
    return php_exe.parent.name


def detect_php_versions(laragon_root: str = "") -> list[PhpVersion]:
    """Scan common install locations for PHP binaries. Windows-focused
    (Laragon/XAMPP) but PATH detection also works on Linux/macOS."""
    found: list[PhpVersion] = []
    seen: set[str] = set()

    def _add(path: Path, source: str, version: str | None = None):
        if not path.exists():
            return
        rp = str(path.resolve())
        if rp in seen:
            return
        seen.add(rp)
        found.append(PhpVersion(version or _version_from_folder_name(path), rp, source))

    roots = [laragon_root.strip()] if laragon_root.strip() else []
    roots += ["C:\\laragon", "D:\\laragon"]
    for lr in roots:
        php_root = Path(lr) / "bin" / "php"
        if php_root.exists():
            for d in sorted(php_root.glob("php-*")):
                exe = d / "php.exe"
                if exe.exists():
                    _add(exe, "Laragon")

    for xr in ["C:\\xampp", "D:\\xampp"]:
        exe = Path(xr) / "php" / "php.exe"
        if exe.exists():
            _add(exe, "XAMPP")

    path_php = which_any(["php", "php.exe"])
    if path_php:
        _add(Path(path_php), "PATH")

    return found


def get_php_version_string(php_path: str, log: LogFn | None = None) -> str:
    """Runs `php -v` and returns the first line (e.g. 'PHP 8.2.12 ...')."""
    if not php_path:
        return ""
    try:
        res = run_cmd([php_path, "-v"])
        if res.out.strip():
            return res.out.strip().splitlines()[0].strip()
    except Exception as e:
        if log:
            log(f"{tr('تعذر تشغيل PHP للتحقق من الإصدار: ')}{e}")
    return ""


def get_php_extension_count(php_path: str) -> int:
    if not php_path:
        return 0
    try:
        res = run_cmd([php_path, "-m"])
        if res.code == 0:
            return len([l for l in res.out.splitlines() if l.strip() and not l.startswith("[")])
    except Exception:
        pass
    return 0


def find_php_cgi(php_exe_path: str) -> str:
    """php-cgi.exe normally lives next to php.exe in the same version folder."""
    if not php_exe_path:
        return ""
    cand = Path(php_exe_path).parent / ("php-cgi.exe" if is_windows() else "php-cgi")
    return str(cand) if cand.exists() else ""


def _free_port(start: int = 9100, span: int = 300) -> int:
    for port in range(start, start + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(tr("تعذر إيجاد منفذ فارغ لتشغيل PHP-CGI."))


def start_php_cgi_server(php_cgi_path: str, log: LogFn, port: int | None = None) -> tuple[subprocess.Popen, int]:
    """Launches an isolated php-cgi.exe FastCGI listener bound to 127.0.0.1:<port>."""
    port = port or _free_port()
    log(f"{tr('جارٍ تشغيل PHP-CGI معزول على المنفذ ')}{port} ({php_cgi_path})")
    creationflags = subprocess.CREATE_NO_WINDOW if is_windows() else 0
    proc = subprocess.Popen(
        [php_cgi_path, "-b", f"127.0.0.1:{port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return proc, port


def stop_php_cgi_server(proc: subprocess.Popen | None):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass


def laragon_apache_vhost_file(laragon_root: str, project_name: str) -> Path | None:
    """Laragon writes one auto-generated vhost per project at
    <root>/etc/apache2/sites-enabled/auto.<name>*.conf"""
    if not laragon_root.strip():
        return None
    vdir = Path(laragon_root) / "etc" / "apache2" / "sites-enabled"
    if not vdir.exists():
        return None
    matches = sorted(vdir.glob(f"auto.{project_name}*.conf"))
    return matches[0] if matches else None


_APACHE_MARKER_START = "# === Harmulizer PHP Version Override (auto-generated) ==="
_APACHE_MARKER_END = "# === End Harmulizer PHP Version Override ==="


def apply_apache_php_override(vhost_file: Path, port: int, log: LogFn) -> None:
    """Points the given Apache vhost at an isolated php-cgi via mod_proxy_fcgi.
    Requires Apache's proxy_fcgi module to be enabled (default in Laragon)."""
    if not vhost_file.exists():
        raise RuntimeError(tr("ملف vhost الخاص بـ Apache غير موجود."))

    backup = vhost_file.with_suffix(vhost_file.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(vhost_file, backup)
        log(f"{tr('تم إنشاء نسخة احتياطية من ملف الـ vhost: ')}{backup}")

    content = vhost_file.read_text(encoding="utf-8", errors="ignore")
    content = re.sub(
        rf"{re.escape(_APACHE_MARKER_START)}.*?{re.escape(_APACHE_MARKER_END)}\n?",
        "", content, flags=re.DOTALL,
    )

    block = (
        f"{_APACHE_MARKER_START}\n"
        f"<FilesMatch \\.php$>\n"
        f'    SetHandler "proxy:fcgi://127.0.0.1:{port}/"\n'
        f"</FilesMatch>\n"
        f"{_APACHE_MARKER_END}\n"
    )

    if "</VirtualHost>" in content:
        content = content.replace("</VirtualHost>", block + "</VirtualHost>", 1)
    else:
        content = content.rstrip() + "\n\n" + block

    vhost_file.write_text(content, encoding="utf-8")
    log(tr("تم تحديث ملف الـ vhost بإعداد PHP-CGI الجديد."))
    log(tr("⚠️ أعد تشغيل Apache من قائمة Laragon (كليك يمين على الأيقونة ← Apache ← Restart) لتطبيق التغيير."))


def revert_apache_php_override(vhost_file: Path, log: LogFn) -> None:
    backup = vhost_file.with_suffix(vhost_file.suffix + ".bak")
    if backup.exists():
        shutil.copy2(backup, vhost_file)
        log(tr("تمت استعادة ملف الـ vhost الأصلي من النسخة الاحتياطية."))
    else:
        content = vhost_file.read_text(encoding="utf-8", errors="ignore")
        content = re.sub(
            rf"{re.escape(_APACHE_MARKER_START)}.*?{re.escape(_APACHE_MARKER_END)}\n?",
            "", content, flags=re.DOTALL,
        )
        vhost_file.write_text(content, encoding="utf-8")
        log(tr("تمت إزالة إعداد PHP-CGI من ملف الـ vhost."))
    log(tr("⚠️ أعد تشغيل Apache من قائمة Laragon لتطبيق الاستعادة."))


def _override_state_file(project_path: Path) -> Path:
    d = project_path / ".wpinst"
    d.mkdir(parents=True, exist_ok=True)
    return d / "php_apache_override.json"


def save_override_state(project_path: Path, php_version: str, php_path: str, port: int, vhost_file: str):
    state = {
        "php_version": php_version, "php_path": php_path,
        "port": port, "vhost_file": vhost_file,
    }
    _override_state_file(project_path).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_override_state(project_path: Path) -> dict:
    f = _override_state_file(project_path)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def clear_override_state(project_path: Path):
    f = _override_state_file(project_path)
    if f.exists():
        f.unlink(missing_ok=True)
