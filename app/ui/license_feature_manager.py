"""
app/ui/license_feature_manager.py
──────────────────────────────────────────────────────────────────────────────
Developer Admin Panel — License Feature Manager

A password-protected page that lets the developer configure exactly which
features are available per tier (free / basic / pro / enterprise) and set
the pricing shown to users.

Changes are saved to  ~/.harmulizer_pro/feature_config.json  and are applied
to the running app immediately.
"""
from __future__ import annotations

import hashlib
from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QSpinBox, QMessageBox, QLineEdit, QFormLayout, QDialog,
    QDialogButtonBox, QTabWidget, QScrollArea, QFrame,
)

from app.core.license.feature_flags import (
    FEATURE_TIERS, FEATURE_NAMES, TIER_NAMES, PRICING,
    get_default_feature_tiers, get_default_pricing,
    save_tier_overrides, set_dev_password_hash, verify_dev_password,
)
from app.core.i18n import t as tr


# ── Tier header colours (background) ──────────────────────────────────────────
_TIER_COLORS = {
    "free":       "#1E293B",
    "basic":      "#1C3A5E",
    "pro":        "#1A3A2E",
    "enterprise": "#3A1A2E",
}
_TIER_HEADER_BG = {
    "free":       "#334155",
    "basic":      "#1D4ED8",
    "pro":        "#6366F1",
    "enterprise": "#7C3AED",
}

_BTN = """
QPushButton {
    background: #374151; color: white;
    border: 1px solid #4B5563; border-radius: 6px;
    padding: 7px 16px; font-size: 12px;
}
QPushButton:hover { background: #4B5563; }
QPushButton:pressed { background: #6B7280; }
"""

_BTN_PRIMARY = """
QPushButton {
    background: #2563EB; color: white;
    border: none; border-radius: 6px;
    padding: 8px 20px; font-size: 13px; font-weight: bold;
}
QPushButton:hover { background: #1D4ED8; }
QPushButton:pressed { background: #1E40AF; }
"""

_BTN_DANGER = """
QPushButton {
    background: #7F1D1D; color: #FCA5A5;
    border: 1px solid #991B1B; border-radius: 6px;
    padding: 7px 16px; font-size: 12px;
}
QPushButton:hover { background: #991B1B; color: white; }
"""


def _btn(text: str, style: str = _BTN) -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(style)
    return b


# ══════════════════════════════════════════════════════════════════════════════
# Change-password dialog
# ══════════════════════════════════════════════════════════════════════════════

class _ChangePasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("تغيير كلمة مرور المطور"))
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._old  = QLineEdit(); self._old.setEchoMode(QLineEdit.EchoMode.Password)
        self._new1 = QLineEdit(); self._new1.setEchoMode(QLineEdit.EchoMode.Password)
        self._new2 = QLineEdit(); self._new2.setEchoMode(QLineEdit.EchoMode.Password)
        self._new1.setPlaceholderText(tr("8 أحرف على الأقل"))
        self._new2.setPlaceholderText(tr("أعد كتابة كلمة المرور"))

        form.addRow(tr("كلمة المرور الحالية:"), self._old)
        form.addRow(tr("كلمة المرور الجديدة:"), self._new1)
        form.addRow(tr("تأكيد كلمة المرور:"), self._new2)
        layout.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._validate)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _validate(self):
        if not verify_dev_password(self._old.text()):
            QMessageBox.warning(self, tr("خطأ"), tr("كلمة المرور الحالية غير صحيحة."))
            return
        new = self._new1.text()
        if len(new) < 6:
            QMessageBox.warning(self, tr("خطأ"), tr("كلمة المرور الجديدة قصيرة جداً (6 أحرف كحد أدنى)."))
            return
        if new != self._new2.text():
            QMessageBox.warning(self, tr("خطأ"), tr("كلمتا المرور الجديدتان لا تتطابقان."))
            return
        self.accept()

    def new_password(self) -> str:
        return self._new1.text()


# ══════════════════════════════════════════════════════════════════════════════
# Main page widget
# ══════════════════════════════════════════════════════════════════════════════

class LicenseFeatureManagerPage(QWidget):
    """
    Developer-only panel.
    Shows a feature × tier matrix with checkboxes so the developer can
    customise exactly what each tier includes, plus pricing configuration.
    Protected by a developer password on first show.
    """

    # Emitted after saving so main_window can refresh license restrictions
    features_changed = pyqtSignal()

    # Features ordered for display
    _FEATURE_ORDER = [
        "dashboard", "wizard", "max_projects",
        "wpcli_console", "project_tools",
        "backup", "scheduled_backup",
        "database_viewer", "url_converter",
        "security", "manager", "config_editor",
        "devtools", "ai_assistant", "monitoring",
        "site_dashboard",
        "url_sharing", "php_switcher", "multisite",
    ]
    _TIERS = ["free", "basic", "pro", "enterprise"]

    def __init__(self, on_features_saved: Callable | None = None, parent=None):
        super().__init__(parent)
        self._on_features_saved = on_features_saved
        self._unlocked = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Lock screen ───────────────────────────────────────────────
        self._lock_widget = self._build_lock_screen()
        root.addWidget(self._lock_widget)

        # ── Main panel (hidden until unlocked) ────────────────────────
        self._main_widget = self._build_main_panel()
        self._main_widget.setVisible(False)
        root.addWidget(self._main_widget)

    # ─────────────────────────────────────────────────────────────────
    # Lock screen
    # ─────────────────────────────────────────────────────────────────

    def _build_lock_screen(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(16)

        icon = QLabel("🔑")
        icon.setStyleSheet("font-size: 48px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(tr("لوحة تحكم المطور"))
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #F9FAFB;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(tr("أدخل كلمة مرور المطور للوصول إلى إعدادات الباقات"))
        subtitle.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._pass_input = QLineEdit()
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_input.setPlaceholderText(tr("كلمة المرور…"))
        self._pass_input.setMaximumWidth(320)
        self._pass_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pass_input.returnPressed.connect(self._try_unlock)

        self._lock_error = QLabel("")
        self._lock_error.setStyleSheet("color: #F87171; font-size: 12px;")
        self._lock_error.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_unlock = _btn(tr("🔓 دخول"), _BTN_PRIMARY)
        btn_unlock.setMaximumWidth(200)
        btn_unlock.clicked.connect(self._try_unlock)

        hint = QLabel(tr("كلمة المرور الافتراضية: harmulizer2024"))
        hint.setStyleSheet("color: #6B7280; font-size: 11px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        v.addStretch()
        v.addWidget(icon)
        v.addWidget(title)
        v.addWidget(subtitle)
        v.addSpacing(12)
        v.addWidget(self._pass_input, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(self._lock_error)
        v.addWidget(btn_unlock, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(8)
        v.addWidget(hint)
        v.addStretch()
        return w

    def _try_unlock(self):
        pwd = self._pass_input.text()
        if verify_dev_password(pwd):
            self._unlocked = True
            self._pass_input.clear()
            self._lock_error.setText("")
            self._lock_widget.setVisible(False)
            self._main_widget.setVisible(True)
            self._load_matrix()
        else:
            self._lock_error.setText(tr("❌ كلمة المرور غير صحيحة"))
            self._pass_input.clear()
            self._pass_input.setFocus()

    # ─────────────────────────────────────────────────────────────────
    # Main panel
    # ─────────────────────────────────────────────────────────────────

    def _build_main_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 8, 16, 16)
        v.setSpacing(12)

        # ── Header row ────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel(tr("🔑  إدارة مميزات الباقات"))
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #F9FAFB;")
        hdr.addWidget(title)
        hdr.addStretch()

        btn_lock = _btn(tr("🔒 قفل"))
        btn_lock.clicked.connect(self._lock)
        btn_change_pass = _btn(tr("🔑 تغيير كلمة المرور"))
        btn_change_pass.clicked.connect(self._change_password)
        hdr.addWidget(btn_change_pass)
        hdr.addWidget(btn_lock)
        v.addLayout(hdr)

        # ── Tabs ──────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.addTab(self._build_matrix_tab(), tr("📊 مصفوفة الميزات"))
        tabs.addTab(self._build_pricing_tab(), tr("💰 الأسعار والباقات"))
        v.addWidget(tabs, 1)

        # ── Bottom action bar ─────────────────────────────────────────
        bar = QHBoxLayout()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")

        btn_save  = _btn(tr("💾  حفظ جميع التغييرات"), _BTN_PRIMARY)
        btn_reset = _btn(tr("↩  إعادة الافتراضي"), _BTN_DANGER)
        btn_save.clicked.connect(self._save)
        btn_reset.clicked.connect(self._reset_to_defaults)

        bar.addWidget(self._status_lbl, 1)
        bar.addWidget(btn_reset)
        bar.addWidget(btn_save)
        v.addLayout(bar)

        return w

    # ── Feature Matrix tab ────────────────────────────────────────────

    def _build_matrix_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 8, 0, 0)

        hint = QLabel(
            "✏️  ضع علامة ✅ لتفعيل الميزة في الباقة — "
            "عدد المشاريع: أدخل -1 للعدد غير المحدود")
        hint.setStyleSheet("color: #9CA3AF; font-size: 11px; padding: 4px;")
        v.addWidget(hint)

        self._matrix_table = QTableWidget()
        self._matrix_table.setColumnCount(len(self._TIERS) + 1)  # +1 for feature name

        headers = [tr("الميزة")] + [
            f"{TIER_NAMES[t]}\n({PRICING[t]['price']}$)" for t in self._TIERS
        ]
        self._matrix_table.setHorizontalHeaderLabels(headers)
        hh = self._matrix_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, len(self._TIERS) + 1):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        self._matrix_table.verticalHeader().setVisible(False)
        self._matrix_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._matrix_table.setAlternatingRowColors(False)
        self._matrix_table.setShowGrid(True)
        v.addWidget(self._matrix_table, 1)
        return w

    def _load_matrix(self):
        """Populate the matrix table from the current FEATURE_TIERS."""
        self._matrix_table.setRowCount(len(self._FEATURE_ORDER))
        self._cells: dict[tuple[str, str], QWidget] = {}

        for row, feat in enumerate(self._FEATURE_ORDER):
            # Feature name cell
            name_item = QTableWidgetItem(FEATURE_NAMES.get(feat, feat))
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            name_item.setBackground(
                __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#1E293B"))
            self._matrix_table.setItem(row, 0, name_item)

            for col, tier in enumerate(self._TIERS, start=1):
                val = FEATURE_TIERS[tier].get(feat, False)

                if feat == "max_projects":
                    # Use a spinbox (-1 = unlimited)
                    sb = QSpinBox()
                    sb.setRange(-1, 9999)
                    sb.setValue(val if isinstance(val, int) else 1)
                    sb.setSpecialValueText(tr("∞ غير محدود"))
                    sb.setMinimumWidth(110)
                    sb.setStyleSheet(
                        "QSpinBox { background: #1E293B; color: #F9FAFB; "
                        "border: 1px solid #334155; border-radius: 4px; padding: 3px; }")
                    container = QWidget()
                    cl = QHBoxLayout(container)
                    cl.setContentsMargins(4, 2, 4, 2)
                    cl.addWidget(sb)
                    cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._matrix_table.setCellWidget(row, col, container)
                    self._cells[(feat, tier)] = sb
                else:
                    cb = QCheckBox()
                    cb.setChecked(bool(val))
                    cb.setStyleSheet(
                        "QCheckBox { margin-left: auto; margin-right: auto; }")
                    container = QWidget()
                    cl = QHBoxLayout(container)
                    cl.setContentsMargins(0, 0, 0, 0)
                    cl.addWidget(cb)
                    cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._matrix_table.setCellWidget(row, col, container)
                    self._cells[(feat, tier)] = cb

            self._matrix_table.setRowHeight(row, 38)

        # Colour tier column headers
        from PyQt6.QtGui import QColor, QBrush
        for col, tier in enumerate(self._TIERS, start=1):
            item = self._matrix_table.horizontalHeaderItem(col)
            if item:
                item.setBackground(QBrush(QColor(_TIER_HEADER_BG[tier])))
                item.setForeground(QBrush(QColor("#FFFFFF")))

        self._load_pricing_tab()

    # ── Pricing tab ───────────────────────────────────────────────────

    def _build_pricing_tab(self) -> QWidget:
        self._pricing_widgets: dict[str, dict] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(20)

        for tier in self._TIERS:
            # Card per tier
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background: {_TIER_COLORS[tier]}; "
                f"border: 1px solid #334155; border-radius: 10px; padding: 12px; }}")
            card_v = QVBoxLayout(card)
            card_v.setSpacing(8)

            header = QLabel(f"  {TIER_NAMES[tier]}")
            header.setStyleSheet(
                f"background: {_TIER_HEADER_BG[tier]}; color: white; "
                f"font-size: 15px; font-weight: bold; border-radius: 6px; padding: 6px 12px;")
            card_v.addWidget(header)

            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            price_sb = QSpinBox()
            price_sb.setRange(0, 99999)
            price_sb.setValue(int(PRICING[tier].get("price", 0)))
            price_sb.setSuffix(" $")
            price_sb.setStyleSheet(
                "QSpinBox { background: #0F172A; color: #F9FAFB; "
                "border: 1px solid #334155; border-radius: 4px; padding: 4px; "
                "min-width: 100px; }")

            name_edit = QLineEdit(TIER_NAMES.get(tier, tier))
            name_edit.setStyleSheet(
                "QLineEdit { background: #0F172A; color: #F9FAFB; "
                "border: 1px solid #334155; border-radius: 4px; padding: 4px; }")

            form.addRow(tr("اسم الباقة:"), name_edit)
            form.addRow(tr("السعر / شهر:"), price_sb)

            if tier != "free":
                period_lbl = QLabel(tr("شهري"))
                period_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")
                form.addRow(tr("الفترة:"), period_lbl)

            card_v.addLayout(form)
            v.addWidget(card)

            self._pricing_widgets[tier] = {
                "price": price_sb,
                "name":  name_edit,
            }

        v.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _load_pricing_tab(self):
        """Sync pricing tab with current PRICING dict."""
        for tier, widgets in self._pricing_widgets.items():
            widgets["price"].setValue(int(PRICING[tier].get("price", 0)))
            # TIER_NAMES is a module-level dict — update the display
            widgets["name"].setText(TIER_NAMES.get(tier, tier))

    # ─────────────────────────────────────────────────────────────────
    # Save / Reset / Lock
    # ─────────────────────────────────────────────────────────────────

    def _collect_matrix(self) -> dict:
        """Read the matrix checkboxes/spinboxes into a new feature_tiers dict."""
        result = {tier: {} for tier in self._TIERS}
        for feat in self._FEATURE_ORDER:
            for tier in self._TIERS:
                widget = self._cells.get((feat, tier))
                if widget is None:
                    result[tier][feat] = FEATURE_TIERS[tier].get(feat, False)
                elif isinstance(widget, QSpinBox):
                    result[tier][feat] = widget.value()
                elif isinstance(widget, QCheckBox):
                    result[tier][feat] = widget.isChecked()
        return result

    def _collect_pricing(self) -> dict:
        result = {}
        for tier, widgets in self._pricing_widgets.items():
            result[tier] = {
                "price":    widgets["price"].value(),
                "currency": "USD",
                "period":   None if tier == "free" else "month",
            }
            # Also update TIER_NAMES in memory
            TIER_NAMES[tier] = widgets["name"].text().strip() or TIER_NAMES[tier]
        return result

    def _save(self):
        new_tiers   = self._collect_matrix()
        new_pricing = self._collect_pricing()

        # Apply to module-level dicts immediately
        for tier in self._TIERS:
            FEATURE_TIERS[tier].update(new_tiers[tier])
            PRICING[tier].update(new_pricing[tier])

        # Persist
        save_tier_overrides(new_tiers, new_pricing)

        import datetime as _dt
        self._status_lbl.setText(
            f"{tr('✅ تم الحفظ بنجاح — ')}{_dt.datetime.now().strftime('%H:%M:%S')}")
        self._status_lbl.setStyleSheet(
            "color: #34D399; font-size: 11px; padding: 2px;")

        if self._on_features_saved:
            self._on_features_saved()
        self.features_changed.emit()

    def _reset_to_defaults(self):
        reply = QMessageBox.question(
            self, tr("تأكيد الإعادة"),
            "هل تريد إعادة جميع الميزات والأسعار إلى القيم الافتراضية؟\n"
            "سيتم حذف أي تخصيصات محفوظة.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        defaults_tiers   = get_default_feature_tiers()
        defaults_pricing = get_default_pricing()

        for tier in self._TIERS:
            FEATURE_TIERS[tier].update(defaults_tiers[tier])
            PRICING[tier].update(defaults_pricing[tier])

        save_tier_overrides(defaults_tiers, defaults_pricing)
        self._load_matrix()
        self._status_lbl.setText(tr("↩  تمت إعادة الضبط إلى الافتراضي"))
        self._status_lbl.setStyleSheet("color: #F59E0B; font-size: 11px; padding: 2px;")

        if self._on_features_saved:
            self._on_features_saved()
        self.features_changed.emit()

    def _lock(self):
        self._unlocked = False
        self._main_widget.setVisible(False)
        self._lock_widget.setVisible(True)
        self._pass_input.setFocus()

    def _change_password(self):
        dlg = _ChangePasswordDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_hash = hashlib.sha256(
                dlg.new_password().encode()).hexdigest()
            set_dev_password_hash(new_hash)
            QMessageBox.information(
                self, tr("تم"), tr("تم تغيير كلمة مرور المطور بنجاح."))

    # Re-lock when the page is hidden (navigated away from)
    def hideEvent(self, event):
        if self._unlocked:
            self._lock()
        super().hideEvent(event)
