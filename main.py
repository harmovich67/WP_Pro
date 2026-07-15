import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
from app.ui.theme import ThemeManager
from app.ui.main_window import MainWindow


def _get_icon_path() -> str:
    """Resolve icon path for both dev and PyInstaller-bundled exe."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return str(base / "app.ico")


def main():
    # Windows taskbar: show app icon instead of default Python icon
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "SaeedMahmoud.HarmulizerPro.1.0"
        )

    app = QApplication(sys.argv)

    # Full RTL layout mirroring for Arabic localization (menus, toolbars,
    # scrollbars, and default alignment all mirror automatically).
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # Set application-wide icon
    icon_path = _get_icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Initialize theme manager
    theme_manager = ThemeManager(app)
    theme_manager.apply_theme()  # Apply saved preference

    w = MainWindow(theme_manager)

    # Auto-maximize on small/laptop screens (height ≤ 768px)
    screen = app.primaryScreen()
    if screen and screen.availableGeometry().height() <= 768:
        w.showMaximized()
    else:
        w.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
