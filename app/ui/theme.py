from PyQt6.QtGui import QPalette, QColor, QFont
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings

class ThemeManager:
    """Manages dark/light theme switching"""
    
    def __init__(self, app: QApplication):
        self.app = app
        self.settings = QSettings("Harmulizer", "ThemePreference")
        self.current_theme = self.settings.value("theme", "dark")  # default dark
        
    def apply_theme(self, theme_name: str = None):
        """Apply dark or light theme"""
        if theme_name:
            self.current_theme = theme_name
            self.settings.setValue("theme", theme_name)
        
        if self.current_theme == "light":
            apply_light_theme(self.app)
        else:
            apply_dark_theme(self.app)
    
    def toggle_theme(self):
        """Toggle between dark and light"""
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme(new_theme)
        return new_theme


def apply_dark_theme(app: QApplication):
    """Apply modern dark theme"""
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#0B1220"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#E5E7EB"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#E5E7EB"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#E5E7EB"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#E5E7EB"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#6366F1"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    app.setStyleSheet("""
        QWidget { font-size: 13px; font-family: "Segoe UI", sans-serif; }
        QMainWindow { background: #0B1221; }

        /* --- Header --- */
        QLabel#AppTitle { font-size: 24px; font-weight: 800; color: #F3F4F6; }
        QLabel#AppSubtitle { color: #9CA3AF; font-size: 13px; }

        /* --- Input Fields --- */
        QLineEdit, QSpinBox, QTextEdit, QComboBox {
            background: #111827;
            border: 1px solid #374151;
            border-radius: 8px;
            padding: 10px 12px;
            color: #E5E7EB;
            selection-background-color: #4F46E5;
        }
        QLineEdit:focus, QSpinBox:focus, QTextEdit:focus, QComboBox:focus {
            border: 1px solid #6366F1;
            background: #1F2937;
        }
        QTextEdit { font-family: "JetBrains Mono", Consolas, monospace; font-size: 12px; }

        /* --- Buttons --- */
        QPushButton {
            background: #1F2937;
            border: 1px solid #374151;
            border-radius: 8px;
            padding: 8px 16px;
            color: #D1D5DB;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #374151;
            border-color: #4B5563;
        }
        QPushButton:pressed { background: #111827; }

        QPushButton#PrimaryButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #6366F1);
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 700;
            padding: 8px 16px;
        }
        QPushButton#PrimaryButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #818CF8);
        }
        QPushButton#PrimaryButton:pressed {
            background: #4338CA;
        }

        QPushButton:disabled {
            background: #111827;
            color: #4B5563;
            border-color: #1F2937;
        }

        /* --- Sidebar Navigation --- */
        QListWidget#Sidebar {
            background: #0F172A;
            border: none;
            border-right: 1px solid #1E293B;
            outline: none;
            padding-top: 20px;
        }
        QListWidget#Sidebar::item {
            color: #94A3B8;
            padding: 12px 20px;
            margin: 4px 12px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
        }
        QListWidget#Sidebar::item:hover {
            background: #1E293B;
            color: #E2E8F0;
        }
        QListWidget#Sidebar::item:selected {
            background: #4F46E5;
            color: white;
        }

        /* --- Cards and Panels --- */
        QFrame#Card {
            background: #111827;
            border: 1px solid #1E293B;
            border-radius: 12px;
        }

        QFrame#ActionCard {
            background: #1E293B;
            border: 1px solid #334155;
            border-radius: 12px;
        }
        QFrame#ActionCard:hover {
            border: 1px solid #6366F1;
            background: #2D3748;
        }

        QLabel#ActionTitle {
            font-weight: bold;
            color: #F9FAFB;
            font-size: 13px;
        }
        QLabel#ActionDesc {
            color: #9CA3AF;
            font-size: 11px;
        }

        QProgressBar {
            border: none;
            background: #1F2937;
            height: 6px;
            border-radius: 3px;
        }
        QProgressBar::chunk {
            background: #6366F1;
            border-radius: 3px;
        }

        QTabWidget::pane { border: 1px solid #374151; border-radius: 8px; }
        QTabBar::tab {
            background: #1F2937;
            padding: 8px 12px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        QTabBar::tab:selected { background: #374151; color: white; }
    """)


def apply_light_theme(app: QApplication):
    """Apply modern light theme"""
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F9FAFB"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F3F4F6"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#F3F4F6"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#6366F1"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    app.setStyleSheet("""
        QWidget { font-size: 13px; font-family: "Segoe UI", sans-serif; }
        QMainWindow { background: #F9FAFB; }

        /* --- Header --- */
        QLabel#AppTitle { font-size: 24px; font-weight: 800; color: #111827; }
        QLabel#AppSubtitle { color: #6B7280; font-size: 13px; }

        /* --- Input Fields --- */
        QLineEdit, QSpinBox, QTextEdit, QComboBox {
            background: #FFFFFF;
            border: 1px solid #D1D5DB;
            border-radius: 8px;
            padding: 10px 12px;
            color: #111827;
            selection-background-color: #6366F1;
        }
        QLineEdit:focus, QSpinBox:focus, QTextEdit:focus, QComboBox:focus {
            border: 1px solid #6366F1;
            background: #F9FAFB;
        }
        QTextEdit { font-family: "JetBrains Mono", Consolas, monospace; font-size: 12px; }

        /* --- Buttons --- */
        QPushButton {
            background: #FFFFFF;
            border: 1px solid #D1D5DB;
            border-radius: 8px;
            padding: 8px 16px;
            color: #374151;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #F3F4F6;
            border-color: #9CA3AF;
        }
        QPushButton:pressed { background: #E5E7EB; }

        QPushButton#PrimaryButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #6366F1);
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 700;
            padding: 8px 16px;
        }
        QPushButton#PrimaryButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #818CF8);
        }
        QPushButton#PrimaryButton:pressed {
            background: #4338CA;
        }
        QPushButton:disabled {
            background: #F3F4F6;
            color: #9CA3AF;
            border-color: #E5E7EB;
        }

        /* --- Sidebar Navigation --- */
        QListWidget#Sidebar {
            background: #FFFFFF;
            border: none;
            border-right: 1px solid #E5E7EB;
            outline: none;
            padding-top: 20px;
        }
        QListWidget#Sidebar::item {
            color: #6B7280;
            padding: 12px 20px;
            margin: 4px 12px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
        }
        QListWidget#Sidebar::item:hover {
            background: #F3F4F6;
            color: #374151;
        }
        QListWidget#Sidebar::item:selected {
            background: #6366F1;
            color: white;
        }

        /* --- Cards and Panels --- */
        QFrame#Card {
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 12px;
        }
        QProgressBar {
            border: none;
            background: #E5E7EB;
            height: 6px;
            border-radius: 3px;
        }
        QProgressBar::chunk {
            background: #6366F1;
            border-radius: 3px;
        }

        QTabWidget::pane { border: 1px solid #D1D5DB; border-radius: 8px; }
        QTabBar::tab {
            background: #F3F4F6;
            padding: 8px 12px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            color: #6B7280;
        }
        QTabBar::tab:selected { background: #FFFFFF; color: #111827; border: 1px solid #D1D5DB; }
    """)


# Backwards compatibility
def apply_modern_theme(app: QApplication):
    """Apply default theme (dark)"""
    apply_dark_theme(app)
