from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect, QWidget, QHBoxLayout, QPushButton,
    QSizePolicy
)

def make_card(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(28)
    shadow.setXOffset(0)
    shadow.setYOffset(10)
    shadow.setColor(QColor(0, 0, 0, 120))
    card.setGraphicsEffect(shadow)

    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(10)

    t = QLabel(title)
    t.setStyleSheet("font-size: 14px; font-weight: 800;")
    lay.addWidget(t)

    if subtitle.strip():
        s = QLabel(subtitle)
        s.setStyleSheet("color: #9CA3AF;")
        s.setWordWrap(True)
        lay.addWidget(s)

    return card, lay

class Pill(QFrame):
    def __init__(self, text: str, kind: str = "neutral"):
        super().__init__()
        self.setObjectName("Pill")
        
        # --- Color Schemes (Modern & Sleek) ---
        self._colors = {
            "neutral": {
                "bg_start": "#374151", "bg_end": "#111827",
                "border": "#4B5563", "text": "#F9FAFB", "icon": "●"
            },
            "ok": {
                "bg_start": "#10B981", "bg_end": "#047857",
                "border": "#34D399", "text": "#ECFDF5", "icon": "✓"
            },
            "success": {
                "bg_start": "#10B981", "bg_end": "#047857",
                "border": "#34D399", "text": "#ECFDF5", "icon": "✓"
            },
            "warn": {
                "bg_start": "#F59E0B", "bg_end": "#B45309",
                "border": "#FCD34D", "text": "#FFFBEB", "icon": "!"
            },
            "bad": {
                "bg_start": "#EF4444", "bg_end": "#991B1B",
                "border": "#FCA5A5", "text": "#FEF2F2", "icon": "✕"
            },
            "error": {
                "bg_start": "#EF4444", "bg_end": "#991B1B",
                "border": "#FCA5A5", "text": "#FEF2F2", "icon": "✕"
            },
            "info": {
                "bg_start": "#3B82F6", "bg_end": "#1E40AF",
                "border": "#93C5FD", "text": "#EFF6FF", "icon": "ℹ"
            },
        }

        # Layout
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 12, 4)
        lay.setSpacing(8)
        
        # Icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Text
        self.text_lbl = QLabel()
        self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lay.addWidget(self.icon_lbl)
        lay.addWidget(self.text_lbl)
        
        # Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setYOffset(4)
        shadow.setXOffset(0)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        self.set_state(text, kind)

    def set_state(self, text: str, kind: str = "neutral"):
        # Fallback to neutral if kind is missing
        if kind not in self._colors:
            kind = "neutral"
            
        theme = self._colors[kind]
        
        # Extract colors safely
        bg1 = theme.get("bg_start", "#333")
        bg2 = theme.get("bg_end", "#111")
        br = theme.get("border", "#555")
        fg = theme.get("text", "#FFF")
        ic = theme.get("icon", "•")

        # Apply Styles
        self.setStyleSheet(f"""
            QFrame#Pill {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {bg1}, stop:1 {bg2});
                border: 1px solid {br};
                border-radius: 14px;
            }}
        """)
        
        self.icon_lbl.setText(ic)
        self.icon_lbl.setStyleSheet(f"color: {fg}; font-weight: 900; font-size: 13px; border: none; background: transparent;")
        
        self.text_lbl.setText(text)
        self.text_lbl.setStyleSheet(f"color: {fg}; font-weight: 600; font-size: 12px; border: none; background: transparent;")
        
        # Adjust size policy
        self.adjustSize()


class ToastNotification(QWidget):
    """Modern toast notification widget with auto-dismiss and animations"""
    
    def __init__(self, message: str, toast_type: str = "info", parent=None):
        super().__init__(parent)
        self.setObjectName("ToastNotificationContainer")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        
        # Color schemes
        self._colors = {
            "success": {"bg": "#10B981", "border": "#34D399", "text": "#ECFDF5", "icon": "✓"},
            "error": {"bg": "#EF4444", "border": "#FCA5A5", "text": "#FEF2F2", "icon": "✕"},
            "warning": {"bg": "#F59E0B", "border": "#FCD34D", "text": "#FFFBEB", "icon": "⚠"},
            "info": {"bg": "#3B82F6", "border": "#93C5FD", "text": "#EFF6FF", "icon": "ℹ"},
        }
        
        theme = self._colors.get(toast_type, self._colors["info"])
        
        # Outer layout to provide room for drop shadow (prevents negative dirty rect on Windows)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(16, 16, 16, 16)
        
        # Inner card
        self.card = QFrame()
        self.card.setObjectName("ToastNotificationCard")
        layout = QHBoxLayout(self.card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # Icon
        icon_label = QLabel(theme["icon"])
        icon_label.setStyleSheet(f"color: {theme['text']}; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(icon_label)
        
        # Message
        msg_label = QLabel(message)
        msg_label.setStyleSheet(f"color: {theme['text']}; font-size: 13px; font-weight: 500; background: transparent; border: none;")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label, 1)
        
        # Styling on inner card
        self.card.setStyleSheet(f"""
            QFrame#ToastNotificationCard {{
                background-color: {theme['bg']};
                border: 2px solid {theme['border']};
                border-radius: 8px;
            }}
        """)
        
        # Shadow applied to inner card so shadow bounds stay strictly inside outer container window
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(14)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.card.setGraphicsEffect(shadow)
        
        outer_layout.addWidget(self.card)
        
        # Set minimum width
        self.setMinimumWidth(320)
        self.setMaximumWidth(520)
        
        # Opacity for fade animation
        self._opacity = 1.0
        
    def show_animated(self, duration=3000):
        """Show toast with slide-in animation and auto-dismiss"""
        if self.parent():
            parent_widget = self.parent()
            self.adjustSize()
            
            # Position relative to parent window in global coordinates
            global_tl = parent_widget.mapToGlobal(parent_widget.rect().topLeft())
            x = global_tl.x() + 30
            y = global_tl.y() + 60

            # Ensure position is valid and within parent window bounds
            max_x = global_tl.x() + parent_widget.width() - self.width() - 20
            x = max(global_tl.x() + 20, min(x, max(global_tl.x() + 20, max_x)))
            y = max(global_tl.y() + 20, y)
            
            self.move(x, y)
        
        self.show()
        
        # Fade in
        self.setWindowOpacity(0)
        fade_in = QPropertyAnimation(self, b"windowOpacity")
        fade_in.setDuration(250)
        fade_in.setStartValue(0)
        fade_in.setEndValue(1)
        fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade_in.start()
        
        self._fade_in_anim = fade_in
        
        # Auto-dismiss after duration
        QTimer.singleShot(duration, self.hide_animated)
        
    def hide_animated(self):
        """Hide toast with fade-out animation"""
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(250)
        fade_out.setStartValue(1)
        fade_out.setEndValue(0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        fade_out.finished.connect(self.deleteLater)
        fade_out.start()
        
        self._fade_out_anim = fade_out


class PrimaryButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("PrimaryButton")

def row_buttons(*btns: QPushButton) -> QWidget:
    """Lay out buttons in a row that always fills its full available width —
    a single button spans the whole row instead of hugging the left edge
    with dead space next to it, and multiple buttons split the width evenly.
    Stays correctly proportioned as the window/screen is resized."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    for b in btns:
        b.setSizePolicy(QSizePolicy.Policy.Expanding, b.sizePolicy().verticalPolicy())
        h.addWidget(b, 1)
    return w
