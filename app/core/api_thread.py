"""
API Server Thread - Background FastAPI server for License Dashboard
"""
from __future__ import annotations
import logging
import socket
import threading
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from app.core.i18n import t as tr


logger = logging.getLogger(__name__)


def _find_free_port(start: int = 8000, end: int = 8100) -> int:
    """Return the first free TCP port in [start, end). Raises RuntimeError if none found.

    Deliberately does NOT set SO_REUSEADDR: on Windows that flag lets a
    socket bind to a port another process is already listening on, which
    makes this check falsely report a taken port as free.
    """
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}–{end}")


class APIServerThread(QObject):
    """
    Runs a uvicorn/FastAPI server in a plain daemon thread.

    Using a plain thread (instead of QThread) avoids the asyncio ↔ Qt
    timer conflicts that produced the QObject::killTimer / QBasicTimer
    warnings when uvicorn was torn down.
    """

    server_started = pyqtSignal(str)   # Emits server URL when started
    server_error   = pyqtSignal(str)   # Emits error message on failure

    def __init__(self, port: int = 8000, db_path: str = "licenses.db", parent=None):
        super().__init__(parent)
        self.port    = port
        self.db_path = db_path
        self._server: Optional[object] = None   # uvicorn.Server
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ── Public API ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the server in a background daemon thread."""
        if self._running:
            return

        # Pick a free port (may differ from the requested one)
        try:
            self.port = _find_free_port(self.port, self.port + 100)
        except RuntimeError as exc:
            self.server_error.emit(str(exc))
            return

        self._thread = threading.Thread(
            target=self._run_server,
            name="APIServerThread",
            daemon=True,          # killed automatically when the main process exits
        )
        self._thread.start()
        logger.info(f"API server thread started (port {self.port})")

    def stop(self) -> None:
        """Signal uvicorn to shut down and wait for the thread."""
        if self._server is not None:
            try:
                self._server.should_exit = True
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._running = False
        logger.info("API server stopped")

    def is_running(self) -> bool:
        return self._running

    def get_server_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # ── Internal ──────────────────────────────────────────────────────

    def _run_server(self) -> None:
        """Entry point for the daemon thread."""
        import asyncio

        # Each thread needs its own event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            import uvicorn
            from app.core.license_api import create_app

            app = create_app(self.db_path)

            config = uvicorn.Config(
                app=app,
                host="127.0.0.1",
                port=self.port,
                log_level="error",
                access_log=False,
                loop="asyncio",
            )
            self._server = uvicorn.Server(config)
            self._running = True

            # Emit the URL *before* blocking in server.run()
            self.server_started.emit(self.get_server_url())
            logger.info(f"API server running at {self.get_server_url()}")

            # Blocking call — returns when should_exit is set
            loop.run_until_complete(self._server.serve())

        except OSError as exc:
            msg = f"{tr('فشل تشغيل خادم API: ')}{exc}"
            logger.error(msg)
            self.server_error.emit(msg)

        except Exception as exc:
            msg = f"{tr('خطأ في خادم API: ')}{exc}"
            logger.exception(msg)
            self.server_error.emit(msg)

        finally:
            self._running = False
            try:
                loop.close()
            except Exception:
                pass
