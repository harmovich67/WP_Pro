"""
Theme Bridge - Synchronizes theme between PyQt6 and embedded web dashboard
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

if TYPE_CHECKING:
    from app.ui.theme import ThemeManager


class ThemeBridge:
    """Bridge for synchronizing theme between PyQt6 and QWebEngineView"""
    
    def __init__(self, web_view: QWebEngineView, theme_manager: Optional['ThemeManager'] = None):
        """
        Initialize theme bridge
        
        Args:
            web_view: QWebEngineView instance to inject CSS into
            theme_manager: Optional ThemeManager instance for theme detection
        """
        self.web_view = web_view
        self.theme_manager = theme_manager
        self.current_theme = "dark"  # Default theme
        
        # Connect to theme change events if theme_manager provided
        if self.theme_manager and hasattr(self.theme_manager, 'theme_changed'):
            self.theme_manager.theme_changed.connect(self.on_theme_changed)
    
    def sync_theme(self) -> None:
        """Synchronize current theme with web view"""
        # Detect current theme from theme_manager or use default
        if self.theme_manager:
            self.current_theme = self.theme_manager.get_current_theme()
        
        # Generate and inject CSS
        css = self.get_theme_css(self.current_theme)
        self.inject_css(css)
    
    def get_theme_css(self, theme: str) -> str:
        """
        Generate CSS variables for the specified theme
        
        Args:
            theme: Theme name ("dark" or "light")
            
        Returns:
            CSS string with theme variables
        """
        if theme == "light":
            return """
                :root {
                    --bg-primary: #f8f9fa;
                    --bg-secondary: #e9ecef;
                    --bg-card: #ffffff;
                    --accent: #4f46e5;
                    --accent-hover: #4338ca;
                    --success: #10b981;
                    --warning: #f59e0b;
                    --danger: #ef4444;
                    --text-primary: #1f2937;
                    --text-secondary: #6b7280;
                    --border: #d1d5db;
                }
            """
        else:  # dark theme (default)
            return """
                :root {
                    --bg-primary: #0f0f23;
                    --bg-secondary: #1a1a2e;
                    --bg-card: #16213e;
                    --accent: #4f46e5;
                    --accent-hover: #4338ca;
                    --success: #10b981;
                    --warning: #f59e0b;
                    --danger: #ef4444;
                    --text-primary: #e5e7eb;
                    --text-secondary: #9ca3af;
                    --border: #374151;
                }
            """
    
    def inject_css(self, css: str) -> None:
        """
        Inject CSS into the web view
        
        Args:
            css: CSS string to inject
        """
        # JavaScript to inject CSS variables
        js_code = f"""
        (function() {{
            var style = document.getElementById('theme-bridge-style');
            if (!style) {{
                style = document.createElement('style');
                style.id = 'theme-bridge-style';
                document.head.appendChild(style);
            }}
            style.textContent = `{css}`;
        }})();
        """
        
        # Execute JavaScript in web view
        self.web_view.page().runJavaScript(js_code)
    
    def on_theme_changed(self, new_theme: str) -> None:
        """
        Handle theme change event
        
        Args:
            new_theme: New theme name
        """
        self.current_theme = new_theme
        self.sync_theme()
    
    def set_theme(self, theme: str) -> None:
        """
        Manually set theme
        
        Args:
            theme: Theme name ("dark" or "light")
        """
        self.current_theme = theme
        self.sync_theme()
