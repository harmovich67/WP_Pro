"""
API Server Thread - Background FastAPI server for License Dashboard
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
import uvicorn


logger = logging.getLogger(__name__)


class APIServerThread(QThread):
    """Background thread for running FastAPI server"""
    
    server_started = pyqtSignal(str)  # Emits server URL when started
    server_error = pyqtSignal(str)    # Emits error message on failure
    
    def __init__(self, port: int = 8000, db_path: str = "licenses.db", parent=None):
        super().__init__(parent)
        self.port = port
        self.db_path = db_path
        self.server: Optional[uvicorn.Server] = None
        self._stop_event = threading.Event()
        self._running = False
        
    def run(self) -> None:
        """Run the FastAPI server in this thread"""
        try:
            # Import here to avoid circular imports
            from app.core.license_api import create_app
            
            # Create FastAPI app with database path
            app = create_app(self.db_path)
            
            # Configure Uvicorn server
            config = uvicorn.Config(
                app=app,
                host="127.0.0.1",
                port=self.port,
                log_level="error",  # Minimize console output
                access_log=False,
            )
            
            self.server = uvicorn.Server(config)
            
            # Mark as running
            self._running = True
            
            # Emit success signal with server URL
            server_url = f"http://127.0.0.1:{self.port}"
            self.server_started.emit(server_url)
            
            logger.info(f"API server started on {server_url}")
            
            # Run server (blocking call)
            self.server.run()
            
        except OSError as e:
            # Port already in use or permission denied
            error_msg = f"Failed to start API server: {str(e)}"
            logger.error(error_msg)
            self.server_error.emit(error_msg)
            self._running = False
            
        except Exception as e:
            # Other errors
            error_msg = f"API server error: {str(e)}"
            logger.exception(error_msg)
            self.server_error.emit(error_msg)
            self._running = False
    
    def stop(self) -> None:
        """Stop the API server gracefully"""
        if self.server and self._running:
            logger.info("Stopping API server...")
            self._stop_event.set()
            
            # Signal server to shutdown
            if hasattr(self.server, 'should_exit'):
                self.server.should_exit = True
            
            # Wait for thread to finish (max 5 seconds)
            self.wait(5000)
            
            self._running = False
            logger.info("API server stopped")
    
    def is_running(self) -> bool:
        """Check if server is currently running"""
        return self._running
    
    def get_server_url(self) -> str:
        """Get the server URL"""
        return f"http://127.0.0.1:{self.port}"
    
    def health_check(self) -> bool:
        """Check if server is responding"""
        if not self._running:
            return False
        
        try:
            import requests
            response = requests.get(f"{self.get_server_url()}/", timeout=1)
            return response.status_code == 200
        except Exception:
            return False
