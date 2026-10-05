"""
License Dashboard Page - Embedded web dashboard for license management
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMessageBox, QLabel, QPushButton, QHBoxLayout

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE_AVAILABLE = True
except ImportError:
    _WEBENGINE_AVAILABLE = False
    QWebEngineView = None

from app.core.api_thread import APIServerThread
from app.ui.theme_bridge import ThemeBridge
from app.core.i18n import t as tr


logger = logging.getLogger(__name__)


class LicenseDashboardPage(QWidget):
    """Dashboard page widget with embedded web interface"""
    
    def __init__(self, db_path: str = "licenses.db", port: int = 8000, parent=None):
        """
        Initialize dashboard page
        
        Args:
            db_path: Path to licenses database
            port: Port for API server
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.db_path = db_path
        self.port = port
        self.api_thread: Optional[APIServerThread] = None
        self.web_view: Optional[QWebEngineView] = None
        self.theme_bridge: Optional[ThemeBridge] = None
        self.server_url: Optional[str] = None
        
        self._setup_ui()
        self._start_api_server()  # Always start API server regardless of WebEngine
    
    def _setup_ui(self) -> None:
        """Set up the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not _WEBENGINE_AVAILABLE:
            self._build_fallback_ui(layout)
            return

        # Create QWebEngineView
        self.web_view = QWebEngineView()
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        layout.addWidget(self.web_view)

        # Initialize theme bridge (will sync after page loads)
        self.theme_bridge = ThemeBridge(self.web_view)

    def _build_fallback_ui(self, layout: QVBoxLayout) -> None:
        """Fallback UI when WebEngine is not available - shows browser button"""
        import os
        token = os.environ.get("ADMIN_TOKEN", "admin_secret_token_2024")

        container = QWidget()
        container.setStyleSheet("background: #0f0f23;")
        vbox = QVBoxLayout(container)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(16)

        icon = QLabel("📊")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 64px;")
        vbox.addWidget(icon)

        title = QLabel(tr("لوحة تحكم الترخيص"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #e5e7eb; font-size: 22px; font-weight: bold;")
        vbox.addWidget(title)

        info = QLabel(
            "PyQt6-WebEngine غير مثبت بعد\n"
            "يمكنك فتح الداشبورد في المتصفح مباشرة"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #9ca3af; font-size: 14px;")
        vbox.addWidget(info)

        # Password display
        pw_label = QLabel(f"{tr('🔑 كلمة المرور:  ')}{token}")
        pw_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pw_label.setStyleSheet(
            "color: #f59e0b; font-size: 14px; font-family: monospace; "
            "background: #1a1a2e; border-radius: 8px; padding: 10px 20px;"
        )
        pw_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vbox.addWidget(pw_label)

        # Open in browser button
        self._btn_open_browser = QPushButton(tr("🌐  افتح الداشبورد في المتصفح"))
        self._btn_open_browser.setEnabled(False)  # enabled after server starts
        self._btn_open_browser.setFixedHeight(44)
        self._btn_open_browser.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4f46e5,stop:1 #7c3aed);
                color: white; border: none; border-radius: 10px;
                font-size: 15px; font-weight: bold; padding: 0 24px;
            }
            QPushButton:hover { background: #4338ca; }
            QPushButton:disabled { background: #374151; color: #6b7280; }
        """)
        self._btn_open_browser.clicked.connect(self._open_in_browser)
        vbox.addWidget(self._btn_open_browser)

        self._status_label = QLabel(tr("⏳ جاري تشغيل الـ API server..."))
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        vbox.addWidget(self._status_label)

        install_note = QLabel(tr("لتفعيل الداشبورد المدمج: pip install PyQt6-WebEngine"))
        install_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        install_note.setStyleSheet("color: #4b5563; font-size: 11px;")
        vbox.addWidget(install_note)

        layout.addWidget(container)
    
    def _start_api_server(self) -> None:
        """Start the FastAPI server in background thread"""
        try:
            # Create and configure API thread
            self.api_thread = APIServerThread(port=self.port, db_path=self.db_path)
            
            # Connect signals
            self.api_thread.server_started.connect(self._on_server_started)
            self.api_thread.server_error.connect(self._on_server_error)
            
            # Start thread
            self.api_thread.start()
            
            logger.info(f"Starting API server on port {self.port}")
            
        except Exception as e:
            logger.exception(f"Failed to start API server: {e}")
            self._on_server_error(str(e))
    
    @pyqtSlot(str)
    def _on_server_started(self, server_url: str) -> None:
        self.server_url = server_url
        logger.info(f"API server started at {server_url}")

        if not _WEBENGINE_AVAILABLE:
            # Fallback mode: enable browser button
            if hasattr(self, '_btn_open_browser'):
                self._btn_open_browser.setEnabled(True)
                self._btn_open_browser.setText(f"{tr('🌐  افتح الداشبورد في المتصفح  (')}{server_url.replace('http://', '')})")
            if hasattr(self, '_status_label'):
                self._status_label.setText(f"{tr('✅ الـ API server شغال على ')}{server_url}")
                self._status_label.setStyleSheet("color: #10b981; font-size: 12px;")
            return

        # Load dashboard HTML
        self._load_dashboard()

    def _open_in_browser(self) -> None:
        """Open dashboard in system browser"""
        if not self.server_url:
            return
        import webbrowser
        # Open the HTML file directly - it will use the API URL
        dashboard_html = Path(__file__).parent.parent.parent / "license_dashboard" / "index.html"
        if dashboard_html.exists():
            webbrowser.open(f"file:///{dashboard_html.absolute()}")
        else:
            webbrowser.open(self.server_url)
    
    @pyqtSlot(str)
    def _on_server_error(self, error_msg: str) -> None:
        logger.error(f"API server error: {error_msg}")

        if not _WEBENGINE_AVAILABLE:
            if hasattr(self, '_status_label'):
                self._status_label.setText(f"{tr('❌ فشل تشغيل الـ API: ')}{error_msg[:60]}")
                self._status_label.setStyleSheet("color: #ef4444; font-size: 12px;")
            return

        QMessageBox.critical(
            self,
            tr("خطأ في لوحة التحكم"),
            f"فشل تشغيل خادم لوحة تحكم الترخيص:\n\n{error_msg}\n\n"
            f"يرجى التحقق من أن المنفذ {self.port} متاح، ثم إعادة تشغيل التطبيق."
        )
        self._show_error_page(error_msg)
    
    def _load_dashboard(self) -> None:
        """Load the dashboard HTML in web view"""
        if not self.server_url:
            logger.error("Cannot load dashboard: server URL not set")
            return
        
        # Get path to dashboard HTML
        dashboard_html = Path(__file__).parent.parent.parent / "license_dashboard" / "index.html"
        
        if dashboard_html.exists():
            # Load from file
            url = QUrl.fromLocalFile(str(dashboard_html.absolute()))
            self.web_view.setUrl(url)
            logger.info(f"Loading dashboard from {dashboard_html}")
            
            # Sync theme after page loads
            self.web_view.loadFinished.connect(self._on_page_loaded)
        else:
            logger.error(f"Dashboard HTML not found at {dashboard_html}")
            self._show_error_page(tr("ملف HTML الخاص بلوحة التحكم غير موجود"))
    
    @pyqtSlot(bool)
    def _on_page_loaded(self, success: bool) -> None:
        """
        Handle page load finished event
        
        Args:
            success: Whether page loaded successfully
        """
        if success:
            logger.info("Dashboard page loaded successfully")
            
            # Inject theme CSS
            if self.theme_bridge:
                self.theme_bridge.sync_theme()
            
            # Inject API URL into page
            self._inject_api_url()
        else:
            logger.error("Dashboard page failed to load")
            self._show_error_page(tr("فشل تحميل صفحة لوحة التحكم"))
    
    def _inject_api_url(self) -> None:
        """Inject API URL into the dashboard page"""
        if not self.server_url:
            return
        
        js_code = f"""
        (function() {{
            // Override API_URL constant in dashboard
            if (typeof window !== 'undefined') {{
                window.API_URL = '{self.server_url}';
            }}
        }})();
        """
        
        self.web_view.page().runJavaScript(js_code)
        logger.debug(f"Injected API URL: {self.server_url}")
    
    def _show_error_page(self, error_msg: str) -> None:
        """
        Show error page in web view
        
        Args:
            error_msg: Error message to display
        """
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>خطأ في لوحة التحكم</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, sans-serif;
                    background: #0f0f23;
                    color: #e5e7eb;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    padding: 20px;
                }}
                .error-container {{
                    background: #16213e;
                    border: 1px solid #374151;
                    border-radius: 16px;
                    padding: 40px;
                    max-width: 600px;
                    text-align: center;
                }}
                h1 {{
                    color: #ef4444;
                    font-size: 24px;
                    margin-bottom: 16px;
                }}
                p {{
                    color: #9ca3af;
                    line-height: 1.6;
                    margin-bottom: 24px;
                }}
                .error-details {{
                    background: #0f0f23;
                    border: 1px solid #374151;
                    border-radius: 8px;
                    padding: 16px;
                    font-family: 'Courier New', monospace;
                    font-size: 12px;
                    color: #ef4444;
                    text-align: right;
                    word-break: break-word;
                }}
            </style>
        </head>
        <body>
            <div class="error-container">
                <h1>⚠️ خطأ في لوحة التحكم</h1>
                <p>فشل تشغيل لوحة تحكم الترخيص. يرجى مراجعة تفاصيل الخطأ أدناه ثم إعادة تشغيل التطبيق.</p>
                <div class="error-details">{error_msg}</div>
            </div>
        </body>
        </html>
        """
        
        self.web_view.setHtml(html)
    
    def closeEvent(self, event) -> None:
        """Handle widget close event"""
        self._stop_api_server()
        super().closeEvent(event)
    
    def _stop_api_server(self) -> None:
        """Stop the API server gracefully"""
        if self.api_thread and self.api_thread.is_running():
            logger.info("Stopping API server...")
            self.api_thread.stop()   # joins the daemon thread internally (max 5 s)
            logger.info("API server stopped")
    
    def is_server_running(self) -> bool:
        """Check if API server is running"""
        return self.api_thread is not None and self.api_thread.is_running()
    
    def get_server_url(self) -> Optional[str]:
        """Get the API server URL"""
        return self.server_url
