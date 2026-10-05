"""
License Dialog - UI for license activation and management.
"""
from __future__ import annotations
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QMessageBox, QWidget, QScrollArea,
    QGraphicsDropShadowEffect, QTabWidget
)

from app.core.license.license_manager import LicenseManager
from app.core.license.feature_flags import PRICING, TIER_NAMES, FEATURE_TIERS
from app.core.i18n import t as tr


# ── Palette ────────────────────────────────────────────────────────────────────
_BG       = "#0B1120"
_SURFACE  = "#141E30"
_CARD     = "#1A2540"
_BORDER   = "#263354"
_TEXT     = "#E2E8F0"
_MUTED    = "#64748B"
_SUBTLE   = "#94A3B8"
_BUY_BG   = "#2E8B68"
_BUY_HOVER = "#38A578"
_BUY_BORDER = "#49B98A"

# ── Tier config (no colored emoji icons) ──────────────────────────────────────
_TIER_CFG = {
    "free": {
        "label": tr("مجاني"),
        "accent": "#64748B",
        "glow":   "#334155",
        "g1": "#1A2540", "g2": "#0B1120",
        "badge": None,
        "features": [
            (True,  tr("لوحة التحكم")),
            (True,  tr("معالج التثبيت")),
            (True,  tr("مشروع واحد فقط")),
            (False, "WP-CLI Console"),
            (False, tr("النسخ الاحتياطي")),
            (False, tr("محول الروابط")),
            (False, tr("الأمان")),
            (False, tr("المساعد الذكي AI")),
        ],
    },
    "basic": {
        "label": tr("أساسي"),
        "accent": "#3B82F6",
        "glow":   "#1D4ED8",
        "g1": "#1C3050", "g2": "#0B1120",
        "badge": None,
        "features": [
            (True,  tr("لوحة التحكم")),
            (True,  tr("معالج التثبيت")),
            (True,  tr("3 مشاريع")),
            (True,  "WP-CLI Console"),
            (True,  tr("النسخ الاحتياطي")),
            (True,  tr("محول الروابط")),
            (False, tr("الجدولة التلقائية")),
            (False, tr("المساعد الذكي AI")),
        ],
    },
    "pro": {
        "label": tr("احترافي"),
        "accent": "#6366F1",
        "glow":   "#4F46E5",
        "g1": "#1E1B4B", "g2": "#0B1120",
        "badge": tr("الأكثر شيوعاً"),
        "features": [
            (True,  tr("لوحة التحكم")),
            (True,  tr("معالج التثبيت")),
            (True,  tr("مشاريع غير محدودة")),
            (True,  "WP-CLI Console"),
            (True,  tr("النسخ الاحتياطي + الجدولة")),
            (True,  tr("محول الروابط")),
            (True,  tr("الأمان + عارض DB")),
            (False, tr("المساعد الذكي AI")),
        ],
    },
    "enterprise": {
        "label": tr("مؤسسي"),
        "accent": "#A78BFA",
        "glow":   "#7C3AED",
        "g1": "#2D1B4E", "g2": "#0B1120",
        "badge": tr("الأقوى"),
        "features": [
            (True, tr("كل ميزات Pro")),
            (True, tr("مشاريع غير محدودة")),
            (True, tr("المساعد الذكي AI")),
            (True, tr("أدوات المطورين")),
            (True, tr("المراقبة الكاملة")),
            (True, tr("محرر الإعدادات")),
            (True, tr("إدارة الإضافات")),
            (True, tr("دعم أولوية")),
        ],
    },
}

# Tier status icons as text (no colored emoji)
_TIER_STATUS_ICON = {
    "free":       "○",
    "basic":      "◈",
    "pro":        "◆",
    "enterprise": "◉",
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _btn(text: str, bg: str, hover: str, color: str = _TEXT,
         pad: str = "10px 22px", fs: int = 13, radius: int = 8) -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(f"""
        QPushButton {{
            background: {bg}; color: {color};
            border: none; border-radius: {radius}px;
            padding: {pad}; font-size: {fs}px; font-weight: 700;
        }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:pressed {{ opacity: 0.85; }}
    """)
    return b


def _with_alpha(color: str, alpha: int) -> str:
    c = QColor(color)
    c.setAlpha(alpha)
    return c.name(QColor.NameFormat.HexArgb)


def _divider() -> QFrame:
    d = QFrame()
    d.setFrameShape(QFrame.Shape.HLine)
    d.setStyleSheet(f"background: {_BORDER}; max-height: 1px; border: none;")
    return d


# ══════════════════════════════════════════════════════════════════════════════
# Plan Card
# ══════════════════════════════════════════════════════════════════════════════

class PlanCard(QFrame):
    buy_clicked = pyqtSignal(str)

    def __init__(self, tier: str, is_current: bool = False, parent=None):
        super().__init__(parent)
        self.tier = tier
        self._cfg = _TIER_CFG[tier]
        self.setMinimumWidth(195)
        self.setMaximumWidth(250)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(24)
        sh.setOffset(0, 6)
        sh.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(sh)

        self._build(is_current)
        self._style(is_current)

    def _build(self, is_current: bool):
        cfg = self._cfg
        price_info = PRICING[self.tier]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        # Badge
        if cfg["badge"]:
            badge = QLabel(cfg["badge"])
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(f"""
                QLabel {{
                    background: {_with_alpha(cfg['accent'], 0x28)};
                    color: {cfg['accent']};
                    border: 1px solid {_with_alpha(cfg['accent'], 0x60)};
                    border-radius: 8px;
                    padding: 3px 10px;
                    font-size: 10px; font-weight: 700;
                }}
            """)
            lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            lay.addSpacing(20)

        # Tier name
        name = QLabel(cfg["label"])
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(f"""
            font-size: 17px; font-weight: 800;
            color: {cfg['accent']}; background: transparent;
        """)
        lay.addWidget(name)

        # Price
        price = price_info.get("price", 0)
        period = price_info.get("period")
        price_row = QHBoxLayout()
        price_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        price_row.setSpacing(4)

        if price == 0:
            pl = QLabel(tr("مجاني"))
            pl.setStyleSheet("font-size: 26px; font-weight: 900; color: #E2E8F0; background: transparent;")
            price_row.addWidget(pl)
        else:
            pl = QLabel(f"${price}")
            pl.setStyleSheet("font-size: 26px; font-weight: 900; color: #E2E8F0; background: transparent;")
            per = QLabel(tr("/شهر") if period == "month" else "")
            per.setStyleSheet(f"font-size: 11px; color: {_MUTED}; background: transparent;")
            per.setAlignment(Qt.AlignmentFlag.AlignBottom)
            price_row.addWidget(pl)
            price_row.addWidget(per)
        lay.addLayout(price_row)

        lay.addWidget(_divider())

        # Features
        for enabled, feat in cfg["features"]:
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel("·" if not enabled else "›")
            dot.setFixedWidth(14)
            dot.setStyleSheet(f"""
                font-size: 16px; font-weight: 900;
                color: {cfg['accent'] if enabled else _BORDER};
                background: transparent;
            """)
            fl = QLabel(feat)
            fl.setStyleSheet(f"""
                font-size: 11px;
                color: {_TEXT if enabled else _MUTED};
                background: transparent;
            """)
            row.addWidget(dot)
            row.addWidget(fl)
            row.addStretch()
            lay.addLayout(row)

        lay.addStretch()

        # Bottom action
        if is_current:
            cur = QLabel(tr("خطتك الحالية"))
            cur.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cur.setStyleSheet(f"""
                QLabel {{
                    background: {_with_alpha(cfg['accent'], 0x18)};
                    color: {cfg['accent']};
                    border: 1px solid {_with_alpha(cfg['accent'], 0x50)};
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 11px; font-weight: 700;
                }}
            """)
            lay.addWidget(cur)
        elif price == 0:
            lay.addSpacing(34)
        else:
            bb = _btn(tr("اشتري الآن"), _BUY_BG, _BUY_HOVER,
                      color="#FFFFFF", pad="9px", fs=12, radius=7)
            bb.setStyleSheet(bb.styleSheet() + f"""
                QPushButton {{
                    border: 1px solid {_BUY_BORDER};
                }}
            """)
            bb.clicked.connect(lambda: self.buy_clicked.emit(self.tier))
            lay.addWidget(bb)

    def _style(self, is_current: bool):
        cfg = self._cfg
        bw = "2px" if is_current else "1px"
        bc = cfg["accent"] if is_current else _BORDER
        self.setStyleSheet(f"""
            PlanCard {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {cfg['g1']}, stop:1 {cfg['g2']});
                border: {bw} solid {bc};
                border-radius: 14px;
            }}
            PlanCard:hover {{ border: 2px solid {cfg['accent']}; }}
        """)

    def enterEvent(self, e):
        sh = self.graphicsEffect()
        if sh:
            sh.setBlurRadius(40)
            sh.setColor(QColor(0, 0, 0, 130))
        super().enterEvent(e)

    def leaveEvent(self, e):
        sh = self.graphicsEffect()
        if sh:
            sh.setBlurRadius(24)
            sh.setColor(QColor(0, 0, 0, 90))
        super().leaveEvent(e)


# ══════════════════════════════════════════════════════════════════════════════
# License Dialog
# ══════════════════════════════════════════════════════════════════════════════

class LicenseDialog(QDialog):
    license_changed = pyqtSignal()
    WHATSAPP_NUMBER = "201000000000"

    def __init__(self, license_manager: LicenseManager, parent=None):
        super().__init__(parent)
        self.lm = license_manager
        self.setWindowTitle(tr("إدارة الترخيص — Harmulizer Pro"))
        self.setMinimumSize(920, 680)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"""
            QDialog {{ background: {_BG}; }}
            QLabel  {{ color: {_TEXT}; background: transparent; }}
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: {_SURFACE}; width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORDER}; border-radius: 3px;
            }}
        """)
        self._setup_ui()
        self._refresh()

    # ── Layout ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        hbar = QFrame()
        hbar.setFixedHeight(64)
        hbar.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border-bottom: 1px solid {_BORDER};
            }}
        """)
        hb = QHBoxLayout(hbar)
        hb.setContentsMargins(28, 0, 28, 0)

        logo = QLabel("Harmulizer Pro")
        logo.setStyleSheet("font-size: 18px; font-weight: 800; color: #A5B4FC;")
        hb.addWidget(logo)
        hb.addStretch()

        self._pill = QLabel("—")
        self._pill.setStyleSheet(f"""
            QLabel {{
                background: {_CARD};
                color: {_SUBTLE};
                border: 1px solid {_BORDER};
                border-radius: 10px;
                padding: 4px 14px;
                font-size: 12px; font-weight: 700;
            }}
        """)
        hb.addWidget(self._pill)
        root.addWidget(hbar)

        # Tabs
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {_BG}; }}
            QTabBar::tab {{
                background: {_SURFACE}; color: {_MUTED};
                border: none; padding: 12px 26px;
                font-size: 13px; font-weight: 600; min-width: 130px;
            }}
            QTabBar::tab:selected {{
                background: {_CARD}; color: #A5B4FC;
                border-bottom: 2px solid #6366F1;
            }}
            QTabBar::tab:hover:!selected {{
                background: {_CARD}; color: {_SUBTLE};
            }}
        """)
        tabs.addTab(self._tab_plans(),    tr("الباقات والأسعار"))
        tabs.addTab(self._tab_activate(), tr("تفعيل الترخيص"))
        tabs.addTab(self._tab_status(),   tr("حالة الترخيص"))
        root.addWidget(tabs, 1)

    # ── Tab: Plans ─────────────────────────────────────────────────────

    def _tab_plans(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {_BG};")
        v = QVBoxLayout(w)
        v.setContentsMargins(28, 22, 28, 22)
        v.setSpacing(18)

        t = QLabel(tr("اختر الباقة المناسبة لك"))
        t.setStyleSheet("font-size: 21px; font-weight: 800; color: #F1F5F9;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)

        s = QLabel(tr("جميع الباقات تشمل تثبيت WordPress المحلي — الترقية تفتح ميزات إضافية"))
        s.setStyleSheet(f"font-size: 12px; color: {_MUTED};")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(s)

        # Trial banner
        self._trial_banner = self._build_trial_banner()
        v.addWidget(self._trial_banner)

        # Cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        cw = QWidget()
        cw.setStyleSheet("background: transparent;")
        cr = QHBoxLayout(cw)
        cr.setContentsMargins(0, 6, 0, 6)
        cr.setSpacing(14)
        cr.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        current = self.lm.get_tier()
        self._cards: dict[str, PlanCard] = {}
        for tier in ["free", "basic", "pro", "enterprise"]:
            card = PlanCard(tier, is_current=(tier == current))
            card.buy_clicked.connect(self._whatsapp)
            cr.addWidget(card)
            self._cards[tier] = card

        scroll.setWidget(cw)
        v.addWidget(scroll, 1)

        cmp = QPushButton(tr("مقارنة تفصيلية لجميع الميزات"))
        cmp.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: #6366F1;
                border: 1px solid #312E81; border-radius: 8px;
                padding: 9px 20px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #1E1B4B; color: #A5B4FC; }}
        """)
        cmp.clicked.connect(lambda: FeaturesComparisonDialog(self).exec())
        v.addWidget(cmp, 0, Qt.AlignmentFlag.AlignHCenter)
        return w

    def _build_trial_banner(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border: 1px solid #312E81;
                border-radius: 10px;
            }}
        """)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(14)

        icon = QLabel("◈")
        icon.setStyleSheet("font-size: 22px; color: #A5B4FC;")
        lay.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(2)
        t1 = QLabel(tr("جرّب Harmulizer Pro مجاناً لمدة 3 أيام"))
        t1.setStyleSheet("font-size: 13px; font-weight: 700; color: #A5B4FC;")
        t2 = QLabel(tr("احصل على جميع ميزات الخطة الاحترافية بدون أي التزام"))
        t2.setStyleSheet(f"font-size: 11px; color: {_MUTED};")
        col.addWidget(t1)
        col.addWidget(t2)
        lay.addLayout(col, 1)

        self._trial_btn = _btn(tr("ابدأ التجربة"), "#4F46E5", "#6366F1", pad="9px 18px", fs=12)
        self._trial_btn.clicked.connect(self._start_trial)
        lay.addWidget(self._trial_btn)
        return f

    # ── Tab: Activate ──────────────────────────────────────────────────

    def _tab_activate(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {_BG};")
        v = QVBoxLayout(w)
        v.setContentsMargins(60, 36, 60, 36)
        v.setSpacing(20)
        v.setAlignment(Qt.AlignmentFlag.AlignTop)

        t = QLabel(tr("تفعيل مفتاح الترخيص"))
        t.setStyleSheet("font-size: 19px; font-weight: 800; color: #F1F5F9;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)

        s = QLabel(tr("أدخل مفتاح الترخيص الذي حصلت عليه بعد الشراء"))
        s.setStyleSheet(f"font-size: 12px; color: {_MUTED};")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(s)

        # Input card
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 14px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(14)

        lbl = QLabel(tr("مفتاح الترخيص"))
        lbl.setStyleSheet(f"font-size: 12px; color: {_SUBTLE}; font-weight: 600;")
        cl.addWidget(lbl)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("HMP-XXXX-XXXX-XXXX-XXXX")
        self.key_input.setMinimumHeight(46)
        self.key_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 10px 14px;
                color: #F1F5F9;
                font-size: 14px;
                font-family: 'Courier New', monospace;
                letter-spacing: 1px;
            }}
            QLineEdit:focus {{ border-color: #6366F1; }}
        """)
        self.key_input.returnPressed.connect(self._activate)
        cl.addWidget(self.key_input)

        ab = _btn(tr("تفعيل الترخيص"), "#4F46E5", "#6366F1", pad="13px", fs=14)
        ab.setMinimumHeight(46)
        ab.clicked.connect(self._activate)
        cl.addWidget(ab)
        v.addWidget(card)

        # Machine ID card
        mc = QFrame()
        mc.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        ml = QHBoxLayout(mc)
        ml.setContentsMargins(18, 12, 18, 12)
        ml.setSpacing(12)

        mid_icon = QLabel("◈")
        mid_icon.setStyleSheet(f"font-size: 18px; color: {_SUBTLE};")
        ml.addWidget(mid_icon)

        mc_col = QVBoxLayout()
        mc_col.setSpacing(2)
        mc_t = QLabel(tr("Machine ID الخاص بك"))
        mc_t.setStyleSheet(f"font-size: 11px; color: {_MUTED};")
        mc_v = QLabel(self.lm.machine_id[:36] + "…")
        mc_v.setStyleSheet("""
            font-size: 11px; color: #A5B4FC;
            font-family: 'Courier New', monospace;
        """)
        mc_col.addWidget(mc_t)
        mc_col.addWidget(mc_v)
        ml.addLayout(mc_col, 1)

        cp = _btn(tr("نسخ"), _BORDER, "#334155", pad="5px 12px", fs=11)
        cp.clicked.connect(self._copy_mid)
        ml.addWidget(cp)
        v.addWidget(mc)
        v.addStretch()
        return w

    # ── Tab: Status ────────────────────────────────────────────────────

    def _tab_status(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {_BG};")
        v = QVBoxLayout(w)
        v.setContentsMargins(40, 30, 40, 30)
        v.setSpacing(18)

        t = QLabel(tr("حالة الترخيص الحالية"))
        t.setStyleSheet("font-size: 19px; font-weight: 800; color: #F1F5F9;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)

        # Status card
        self._sc = QFrame()
        self._sc.setStyleSheet(f"""
            QFrame {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 14px;
            }}
        """)
        sc_lay = QVBoxLayout(self._sc)
        sc_lay.setContentsMargins(28, 28, 28, 28)
        sc_lay.setSpacing(10)

        # Status indicator row (text-based, no colored emoji)
        ind_row = QHBoxLayout()
        ind_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ind_row.setSpacing(12)

        self._status_dot = QLabel("○")
        self._status_dot.setStyleSheet(f"font-size: 28px; color: {_MUTED};")
        ind_row.addWidget(self._status_dot)

        self._status_title = QLabel(tr("غير مفعّل"))
        self._status_title.setStyleSheet("font-size: 20px; font-weight: 800; color: #F1F5F9;")
        ind_row.addWidget(self._status_title)
        sc_lay.addLayout(ind_row)

        # Tier badge
        self._tier_badge = QLabel(tr("الخطة: مجاني"))
        self._tier_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tier_badge.setStyleSheet(f"""
            QLabel {{
                background: {_SURFACE};
                color: {_SUBTLE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 13px; font-weight: 600;
            }}
        """)
        sc_lay.addWidget(self._tier_badge, 0, Qt.AlignmentFlag.AlignHCenter)

        sc_lay.addWidget(_divider())

        # Info rows
        self._info_rows: list[tuple[QLabel, QLabel]] = []
        for label in [tr("الحالة"), tr("الخطة"), tr("تفاصيل")]:
            row = QHBoxLayout()
            row.setSpacing(12)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"font-size: 12px; color: {_MUTED}; font-weight: 600; min-width: 70px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val = QLabel("—")
            val.setStyleSheet(f"font-size: 12px; color: {_TEXT};")
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            sc_lay.addLayout(row)
            self._info_rows.append((lbl, val))

        v.addWidget(self._sc)

        # Buttons
        br = QHBoxLayout()
        br.setAlignment(Qt.AlignmentFlag.AlignCenter)
        br.setSpacing(12)

        self._deact_btn = _btn(tr("إلغاء التفعيل"), "#450A0A", "#7F1D1D",
                               color="#FCA5A5", pad="11px 22px", fs=13)
        self._deact_btn.clicked.connect(self._deactivate)
        self._deact_btn.hide()
        br.addWidget(self._deact_btn)

        close = _btn(tr("إغلاق"), _CARD, _BORDER, pad="11px 28px", fs=13)
        close.clicked.connect(self.close)
        br.addWidget(close)

        v.addLayout(br)
        v.addStretch()
        return w

    # ── Refresh ────────────────────────────────────────────────────────

    def _refresh(self):
        status = self.lm.get_status_display()
        tier   = self.lm.get_tier()
        cfg    = _TIER_CFG.get(tier, _TIER_CFG["free"])
        li     = self.lm.license_info

        # Header pill — text only, no colored emoji
        self._pill.setText(f"{cfg['label']}")
        self._pill.setStyleSheet(f"""
            QLabel {{
                background: {_with_alpha(cfg['accent'], 0x18)};
                color: {cfg['accent']};
                border: 1px solid {_with_alpha(cfg['accent'], 0x50)};
                border-radius: 10px;
                padding: 4px 14px;
                font-size: 12px; font-weight: 700;
            }}
        """)

        # Status tab — dot indicator
        dot_char = _TIER_STATUS_ICON.get(tier, "○")
        self._status_dot.setText(dot_char)
        self._status_dot.setStyleSheet(f"font-size: 28px; color: {cfg['accent']};")

        self._status_title.setText(status["status"])
        self._status_title.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {cfg['accent']};")

        self._tier_badge.setText(f"{tr('الخطة: ')}{cfg['label']}")
        self._tier_badge.setStyleSheet(f"""
            QLabel {{
                background: {_with_alpha(cfg['accent'], 0x14)};
                color: {cfg['accent']};
                border: 1px solid {_with_alpha(cfg['accent'], 0x40)};
                border-radius: 8px;
                padding: 6px 18px;
                font-size: 13px; font-weight: 600;
            }}
        """)

        # Info rows
        is_licensed = self.lm.is_licensed()
        info_vals = [
            tr("مفعّل") if is_licensed else tr("غير مفعّل"),
            cfg["label"],
            status.get("message", "—"),
        ]
        for (_, val_lbl), val in zip(self._info_rows, info_vals):
            val_lbl.setText(val or "—")

        # Deactivate button
        self._deact_btn.setVisible(is_licensed and not li.is_trial)

        # Trial banner
        trial_ok = not li.trial_started_at and not li.license_key
        self._trial_banner.setVisible(trial_ok)

    # ── Actions ────────────────────────────────────────────────────────

    def _activate(self):
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, tr("تنبيه"), tr("الرجاء إدخال مفتاح الترخيص"))
            return
        ok, msg = self.lm.activate(key)
        if ok:
            QMessageBox.information(self, tr("نجاح"), msg)
            self._refresh()
            self.license_changed.emit()
        else:
            QMessageBox.warning(self, tr("خطأ"), msg)

    def _deactivate(self):
        r = QMessageBox.question(self, tr("تأكيد"),
            "هل أنت متأكد من إلغاء تفعيل الترخيص؟\nستعود للخطة المجانية.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self.lm.deactivate()
            self._refresh()
            self.license_changed.emit()

    def _start_trial(self):
        r = QMessageBox.question(self, tr("بدء الفترة التجريبية"),
            "ستحصل على جميع ميزات الخطة الاحترافية لمدة 3 أيام.\n\nهل تريد البدء؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            if self.lm.start_trial():
                QMessageBox.information(self, tr("مبروك"),
                    "تم تفعيل الفترة التجريبية!\nاستمتع بجميع الميزات لمدة 3 أيام.")
                self._refresh()
                self.license_changed.emit()
            else:
                QMessageBox.warning(self, tr("تنبيه"), tr("لقد استخدمت الفترة التجريبية من قبل."))

    def _whatsapp(self, tier: str):
        QDesktopServices.openUrl(QUrl(self.lm.get_whatsapp_url(tier, self.WHATSAPP_NUMBER)))

    def _copy_mid(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.lm.machine_id)
        QMessageBox.information(self, tr("تم"), tr("تم نسخ Machine ID"))


# ══════════════════════════════════════════════════════════════════════════════
# Features Comparison Dialog
# ══════════════════════════════════════════════════════════════════════════════

class FeaturesComparisonDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("مقارنة الخطط والميزات"))
        self.setMinimumSize(860, 560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"QDialog {{ background: {_BG}; }} QLabel {{ color: {_TEXT}; }}")
        self._build()

    def _build(self):
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        hdr = QLabel(tr("مقارنة تفصيلية لجميع الميزات"))
        hdr.setStyleSheet("font-size: 17px; font-weight: 800; color: #F1F5F9;")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hdr)

        tiers = ["free", "basic", "pro", "enterprise"]
        table = QTableWidget()
        table.setStyleSheet(f"""
            QTableWidget {{
                background: {_CARD}; border: 1px solid {_BORDER};
                border-radius: 10px; gridline-color: {_BORDER};
                color: {_TEXT}; font-size: 12px;
            }}
            QHeaderView::section {{
                background: {_SURFACE}; color: {_SUBTLE};
                border: none; border-bottom: 1px solid {_BORDER};
                padding: 10px; font-weight: 700; font-size: 12px;
            }}
            QTableWidget::item {{ padding: 8px; border-bottom: 1px solid {_SURFACE}; }}
            QTableWidget::item:selected {{ background: #1E1B4B; }}
        """)

        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            tr("الميزة"),
            f"مجاني\n$0",
            f"أساسي\n$50/شهر",
            f"احترافي\n$200/شهر",
            f"مؤسسي\n$400/شهر",
        ])

        rows = [
            ("dashboard",        tr("لوحة التحكم")),
            ("wizard",           tr("معالج التثبيت")),
            ("max_projects",     tr("عدد المشاريع")),
            ("wpcli_console",    "WP-CLI Console"),
            ("project_tools",    tr("أدوات المشروع")),
            ("backup",           tr("النسخ الاحتياطي")),
            ("scheduled_backup", tr("الجدولة التلقائية")),
            ("database_viewer",  tr("عارض قاعدة البيانات")),
            ("url_converter",    tr("محول الروابط")),
            ("security",         tr("أدوات الأمان")),
            ("manager",          tr("إدارة الإضافات")),
            ("config_editor",    tr("محرر الإعدادات")),
            ("devtools",         tr("أدوات المطورين")),
            ("ai_assistant",     tr("المساعد الذكي AI")),
            ("monitoring",       tr("المراقبة")),
            ("site_dashboard",   tr("لوحة تحكم الموقع")),
        ]
        table.setRowCount(len(rows))

        _accent = {"free": "#64748B", "basic": "#3B82F6",
                   "pro": "#6366F1", "enterprise": "#A78BFA"}

        for r, (key, name) in enumerate(rows):
            ni = QTableWidgetItem(f"  {name}")
            ni.setFlags(Qt.ItemFlag.ItemIsEnabled)
            ni.setBackground(QColor(_CARD))
            table.setItem(r, 0, ni)

            for c, tier in enumerate(tiers, 1):
                val = FEATURE_TIERS[tier].get(key, False)
                if key == "max_projects":
                    txt = tr("غير محدود") if val == -1 else str(val)
                    col = _accent[tier] if (val == -1 or val > 1) else _MUTED
                elif val:
                    txt = tr("نعم")
                    col = _accent[tier]
                else:
                    txt = "—"
                    col = _BORDER

                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setForeground(QColor(col))
                table.setItem(r, c, item)

            table.setRowHeight(r, 38)

        hh = table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 5):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(table, 1)

        cb = _btn(tr("إغلاق"), _CARD, _BORDER, pad="10px 32px")
        lay.addWidget(cb, 0, Qt.AlignmentFlag.AlignHCenter)
        cb.clicked.connect(self.close)
