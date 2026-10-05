"""
app/core/url_sharing.py
─────────────────────────────────────────────
Live URL Sharing — exposes a local WordPress site to the internet through a
Cloudflare "quick tunnel" (cloudflared) so a client can preview the site
immediately, with no account/signup and no router/port-forwarding setup.

Flow:
  1. Locate (or download) cloudflared.
  2. Launch `cloudflared tunnel --url <local host:port>` in the background,
     using --http-host-header so name-based Apache/nginx vhosts resolve
     correctly even though the public Host header is *.trycloudflare.com.
  3. Parse the generated https://xxxx.trycloudflare.com URL from stdout.
  4. Optionally rewrite the site's siteurl/home (via WP-CLI search-replace)
     to the tunnel URL so generated links/assets work for the remote client,
     then revert them back to the local URL when sharing stops.
"""
from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QStandardPaths, pyqtSignal, QThread

from app.core.utils import is_windows, which_any
from app.core.wp_ops import download_file
from app.core.i18n import t as tr

LogFn = Callable[[str], None]

CLOUDFLARED_URL_WINDOWS = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
CLOUDFLARED_URL_LINUX = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
CLOUDFLARED_URL_MAC = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz"

_TUNNEL_URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def get_shared_tools_dir() -> Path:
    base = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    d = base / "tools"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_cloudflared() -> str:
    p = which_any(["cloudflared", "cloudflared.exe"])
    if p:
        return p
    local = get_shared_tools_dir() / ("cloudflared.exe" if is_windows() else "cloudflared")
    if local.exists():
        return str(local)
    return ""


def download_cloudflared(log: LogFn, progress) -> str:
    if not is_windows():
        raise RuntimeError(tr(
            "التنزيل التلقائي متاح لويندوز فقط حالياً. "
            "يرجى تثبيت cloudflared يدوياً من موقع Cloudflare ثم إضافته إلى PATH."))
    out = get_shared_tools_dir() / "cloudflared.exe"
    log(tr("جارٍ تنزيل أداة المشاركة المباشرة (cloudflared)..."))
    download_file(CLOUDFLARED_URL_WINDOWS, out, log, progress, start_pct=0, end_pct=100)
    log(tr("تم تنزيل cloudflared بنجاح ✅"))
    return str(out)


def derive_target_and_host(site_url: str) -> tuple[str, str]:
    """Returns (local target url for cloudflared, --http-host-header value or '')."""
    raw = site_url.strip()
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = parsed.hostname or "localhost"
    # If a specific custom port was in the URL (e.g. localhost:8080), use that port.
    # Otherwise, connect over local HTTP (port 80) so cloudflared doesn't choke on self-signed local SSL.
    if parsed.port:
        port = parsed.port
        scheme = parsed.scheme or "http"
    else:
        port = 80
        scheme = "http"
    target = f"{scheme}://127.0.0.1:{port}"
    host_header = "" if host in ("localhost", "127.0.0.1") else host
    return target, host_header


def build_share_url(tunnel_base_url: str, original_site_url: str) -> str:
    raw = original_site_url.strip()
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    path = parsed.path.rstrip("/")
    return tunnel_base_url.rstrip("/") + path


def ensure_reverse_proxy_ssl_config(project_path: Path, log: LogFn = None) -> bool:
    """Ensures wp-config.php recognizes HTTPS when accessed behind a reverse proxy / Cloudflare Tunnel.
    Without this, WordPress generates http:// stylesheet/script URLs, causing browsers to block all styles
    due to Mixed Content security rules."""
    cfg = project_path / "wp-config.php"
    if not cfg.exists():
        return False
    try:
        txt = cfg.read_text(encoding="utf-8", errors="ignore")
        if "HTTP_X_FORWARDED_PROTO" in txt:
            return True
        snippet = (
            "\n// SSL Reverse Proxy Detection (Cloudflare Tunnel / Live Share)\n"
            "if ((isset($_SERVER['HTTP_X_FORWARDED_PROTO']) && strpos($_SERVER['HTTP_X_FORWARDED_PROTO'], 'https') !== false) || "
            "(isset($_SERVER['HTTP_CF_VISITOR']) && strpos($_SERVER['HTTP_CF_VISITOR'], 'https') !== false)) {\n"
            "    $_SERVER['HTTPS'] = 'on';\n"
            "}\n"
        )
        if "<?php" in txt:
            txt = txt.replace("<?php", "<?php" + snippet, 1)
            cfg.write_text(txt, encoding="utf-8")
            if log:
                log(tr("✓ تم تفعيل دعم HTTPS في wp-config.php لتعمل ملفات الاستايل عبر النفق المباشر"))
            return True
    except Exception as e:
        if log:
            log(f"{tr('تحذير: تعذر تحديث wp-config.php: ')}{e}")
    return False


class TunnelWorker(QThread):
    """Runs `cloudflared tunnel --url ...` on a background QThread for the
    lifetime of the share session. Emits url_ready once the public URL is parsed
    from output, and keeps streaming log lines until stop() is called or the
    process exits."""
    log = pyqtSignal(str)
    url_ready = pyqtSignal(str)
    tunnel_finished = pyqtSignal(int)

    def __init__(self, cloudflared_path: str, target_url: str, host_header: str = "", parent=None):
        super().__init__(parent)
        self._cloudflared = cloudflared_path
        self._target = target_url
        self._host_header = host_header
        self._proc: subprocess.Popen | None = None
        self._stop_requested = False

    # If no tunnel URL shows up within this many seconds, give up instead of
    # waiting forever with no feedback (cloudflared normally announces the
    # URL within a few seconds).
    URL_TIMEOUT = 30.0
    _FLUSH_INTERVAL = 0.3

    def run(self):
        cmd = [self._cloudflared, "tunnel", "--url", self._target, "--no-autoupdate"]
        if self._target.startswith("https://"):
            cmd += ["--no-tls-verify"]
        if self._host_header:
            cmd += ["--http-host-header", self._host_header]

        creationflags = subprocess.CREATE_NO_WINDOW if is_windows() else 0
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, creationflags=creationflags,
            )
        except Exception as e:
            self.log.emit(f"{tr('تعذر تشغيل cloudflared: ')}{e}")
            self.tunnel_finished.emit(-1)
            return

        # Lines are read on a dedicated daemon thread and handed off through a
        # queue, because Python's iteration over a pipe blocks with no timeout
        # option — we need a timeout to detect "cloudflared never announced a
        # URL" instead of waiting forever.
        line_queue: queue.Queue = queue.Queue()

        def _reader():
            try:
                if self._proc and self._proc.stdout:
                    for raw in self._proc.stdout:
                        line_queue.put(raw.rstrip())
            except Exception:
                pass
            finally:
                line_queue.put(None)  # sentinel: stdout closed / process exited

        threading.Thread(target=_reader, daemon=True).start()

        url_found = False
        # A single busy tunnel can still produce output fast enough to flood
        # the GUI's event queue (one QTextEdit.append() per cross-thread
        # signal). Batch lines and flush at most a few times per second so
        # the UI thread never has to process a burst of individual events.
        buffer: list[str] = []
        last_flush = time.monotonic()
        started_at = time.monotonic()

        def _flush(force: bool = False):
            nonlocal buffer, last_flush
            now = time.monotonic()
            if buffer and (force or now - last_flush >= self._FLUSH_INTERVAL):
                self.log.emit("\n".join(buffer))
                buffer = []
                last_flush = now

        while not self._stop_requested:
            try:
                line = line_queue.get(timeout=0.5)
            except queue.Empty:
                if not url_found and (time.monotonic() - started_at) > self.URL_TIMEOUT:
                    self.log.emit(tr("⏱️ لم يتم الحصول على رابط المشاركة خلال المهلة المحددة — سيتم الإيقاف. تحقق من اتصال الإنترنت وحاول مرة أخرى."))
                    self._stop_requested = True
                    self._kill_proc()
                    break
                continue

            if line is None:  # stdout closed / process exited
                break
            if line:
                if not url_found:
                    m = _TUNNEL_URL_RE.search(line)
                    if m:
                        url_found = True
                        self.url_ready.emit(m.group(0))
                buffer.append(line)
                _flush()

        _flush(force=True)
        code = 0
        if self._proc:
            try:
                code = self._proc.wait(timeout=2.0) if self._proc.poll() is None else self._proc.returncode
            except Exception:
                self._kill_proc()
                code = -1
        self.tunnel_finished.emit(code if code is not None else 0)

    def _kill_proc(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            except Exception:
                pass

    def stop(self):
        self._stop_requested = True
        self._kill_proc()
