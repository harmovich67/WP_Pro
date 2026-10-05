"""
app/ui/php_switcher_page.py
─────────────────────────────────────────────
PHP Version Switcher: detects every PHP install on the machine (Laragon,
XAMPP, system PATH, or a manually browsed binary) and lets a project pin a
specific version — used for every WP-CLI/tooling call. An optional
"Apache isolation" mode additionally serves the *live* site through that
exact PHP version via an isolated php-cgi FastCGI process.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog, QTextEdit, QGroupBox, QPushButton
)

from app.core.projects_store import ProjectRecord
from app.core import php_manager as phpm
from app.ui.extra_pages import BaseExtraPage
from app.ui.widgets import make_card, Pill, PrimaryButton, row_buttons
from app.core.i18n import t as tr


class PhpSwitcherPage(BaseExtraPage):
    def __init__(self, store, parent_window):
        super().__init__(store, parent_window)

        card, lay = make_card(
            tr("مبدّل إصدارات PHP"),
            tr("اكتشف كل إصدارات PHP المثبتة على جهازك واختر أيّها يستخدمه هذا المشروع."))

        self.current_pill = Pill(tr("لم يتم اختيار مشروع"), "neutral")
        lay.addWidget(self.current_pill)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([tr("الإصدار"), tr("المصدر"), tr("المسار")])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        lay.addWidget(self.table, 1)

        self.btn_refresh = PrimaryButton(tr("🔄 إعادة الفحص"))
        self.btn_browse = QPushButton(tr("استعراض ملف PHP يدوياً..."))
        self.btn_apply = PrimaryButton(tr("✅ استخدام هذا الإصدار للمشروع"))
        lay.addWidget(row_buttons(self.btn_refresh, self.btn_browse, self.btn_apply))

        # ── Advanced: Apache-level isolation ────────────────────────────
        adv_box = QGroupBox(tr("⚙️ عزل PHP على مستوى Apache (تجريبي)"))
        adv_lay = QVBoxLayout(adv_box)
        adv_hint = QLabel(tr(
            "يشغّل هذا الخيار php-cgi.exe للإصدار المحدد ويوجّه vhost الخاص "
            "بالمشروع في Laragon إليه، بحيث يعمل الموقع الفعلي (وليس فقط WP-CLI) "
            "بهذا الإصدار. يُنشئ نسخة احتياطية من ملف الـ vhost تلقائياً، ويتطلب "
            "إعادة تشغيل Apache من Laragon بعد التطبيق."))
        adv_hint.setWordWrap(True)
        adv_hint.setStyleSheet("color:#9CA3AF; font-size:11px;")
        adv_lay.addWidget(adv_hint)

        self.apache_status = Pill(tr("غير مفعّل"), "neutral")
        adv_lay.addWidget(self.apache_status)

        self.btn_apply_apache = QPushButton(tr("تطبيق على Apache (لهذا المشروع)"))
        self.btn_revert_apache = QPushButton(tr("استعادة الإعداد الافتراضي"))
        adv_lay.addWidget(row_buttons(self.btn_apply_apache, self.btn_revert_apache))
        lay.addWidget(adv_box)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(140)
        self.log_box.document().setMaximumBlockCount(500)
        lay.addWidget(self.log_box)

        self.content_area.addWidget(card)

        self.btn_refresh.clicked.connect(self._refresh_versions)
        self.btn_browse.clicked.connect(self._browse_php)
        self.btn_apply.clicked.connect(self._apply_selected)
        self.btn_apply_apache.clicked.connect(self._apply_apache_isolation)
        self.btn_revert_apache.clicked.connect(self._revert_apache_isolation)

        self._versions: list[phpm.PhpVersion] = []
        self._php_cgi_proc = None
        self._set_enabled(False)

    # ── BaseExtraPage hooks ─────────────────────────────────────────────
    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self._refresh_versions()
        self._refresh_current_pill()
        self._refresh_apache_status()

    def _on_project_cleared(self):
        self._set_enabled(False)
        self.table.setRowCount(0)
        self.current_pill.set_state(tr("لم يتم اختيار مشروع"), "neutral")
        self.log_box.clear()

    def _set_enabled(self, val: bool):
        self.btn_refresh.setEnabled(val)
        self.btn_browse.setEnabled(val)
        self.btn_apply.setEnabled(val)
        self.btn_apply_apache.setEnabled(val)
        self.btn_revert_apache.setEnabled(val)

    # ── Detection / selection ───────────────────────────────────────────
    def _refresh_versions(self):
        laragon_root = self.current.laragon_root if self.current else ""
        self._versions = phpm.detect_php_versions(laragon_root)
        self.table.setRowCount(len(self._versions))
        for i, v in enumerate(self._versions):
            self.table.setItem(i, 0, QTableWidgetItem(v.version))
            self.table.setItem(i, 1, QTableWidgetItem(v.source))
            self.table.setItem(i, 2, QTableWidgetItem(v.path))
        if not self._versions:
            self.log_box.append(tr("⚠️ لم يتم العثور على أي تثبيت PHP تلقائياً. استخدم زر الاستعراض اليدوي."))

    def _refresh_current_pill(self):
        if not self.current:
            return
        php_path = self.current.php_path
        if not php_path:
            self.current_pill.set_state(tr("لم يُحدَّد إصدار مخصص — يُستخدم PHP الافتراضي"), "neutral")
            return
        v = phpm.get_php_version_string(php_path, self.log_box.append)
        label = f"{tr('الإصدار الحالي: ')}{v or php_path}"
        self.current_pill.set_state(label, "ok")

    def _selected_version(self) -> phpm.PhpVersion | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._versions):
            return None
        return self._versions[row]

    def _browse_php(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("اختر ملف PHP التنفيذي"), "", "php.exe (php.exe);;All files (*)")
        if not f:
            return
        version = phpm.get_php_version_string(f, self.log_box.append)
        self._versions.append(phpm.PhpVersion(version or Path(f).parent.name, f, "Custom"))
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(self._versions[-1].version))
        self.table.setItem(row, 1, QTableWidgetItem("Custom"))
        self.table.setItem(row, 2, QTableWidgetItem(f))
        self.table.selectRow(row)

    def _apply_selected(self):
        if not self.current:
            return
        v = self._selected_version()
        if not v:
            QMessageBox.information(self, tr("اختر إصداراً"), tr("يرجى اختيار إصدار PHP من القائمة أولاً."))
            return
        self.current.php_path = v.path
        self.store.upsert(self.current)
        self._refresh_current_pill()
        self.log_box.append(f"{tr('تم تعيين PHP لهذا المشروع: ')}{v.version} ({v.path})")
        self.parent_window.show_toast(f"{tr('✓ تم تعيين إصدار PHP: ')}{v.version}", "success")

    # ── Advanced Apache isolation ────────────────────────────────────────
    def _refresh_apache_status(self):
        if not self.current:
            return
        state = phpm.load_override_state(Path(self.current.path))
        if state:
            self.apache_status.set_state(
                f"{tr('مفعّل — PHP ')}{state.get('php_version','')} ({tr('منفذ')} {state.get('port','')})", "ok")
        else:
            self.apache_status.set_state(tr("غير مفعّل"), "neutral")

    def _apply_apache_isolation(self):
        if not self.current:
            return
        v = self._selected_version()
        if not v:
            QMessageBox.information(self, tr("اختر إصداراً"), tr("يرجى اختيار إصدار PHP من القائمة أولاً."))
            return

        php_cgi = phpm.find_php_cgi(v.path)
        if not php_cgi:
            QMessageBox.critical(
                self, tr("php-cgi.exe غير موجود"),
                tr("لم يتم العثور على php-cgi.exe بجانب php.exe لهذا الإصدار. "
                   "بعض تثبيتات PHP لا تتضمنه."))
            return

        laragon_root = self.current.laragon_root or "C:\\laragon"
        vhost = phpm.laragon_apache_vhost_file(laragon_root, self.current.name)
        if not vhost:
            QMessageBox.critical(
                self, tr("لم يتم العثور على vhost"),
                tr("تعذّر العثور على ملف vhost تلقائي لهذا المشروع ضمن Laragon.\n"
                   "هذه الميزة تعمل فقط مع مشاريع Laragon (Apache)."))
            return

        r = QMessageBox.question(
            self, tr("تأكيد"),
            f"{tr('سيتم تعديل ملف الـ vhost التالي:')}\n{vhost}\n\n"
            f"{tr('سيتم إنشاء نسخة احتياطية تلقائياً. هل تريد المتابعة؟')}",
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        try:
            proc, port = phpm.start_php_cgi_server(php_cgi, self.log_box.append)
            phpm.apply_apache_php_override(vhost, port, self.log_box.append)
            phpm.save_override_state(Path(self.current.path), v.version, v.path, port, str(vhost))
            self._php_cgi_proc = proc
            self._refresh_apache_status()
            self.parent_window.show_toast(tr("✓ تم تطبيق عزل PHP — أعد تشغيل Apache من Laragon"), "success")
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), str(e))

    def _revert_apache_isolation(self):
        if not self.current:
            return
        state = phpm.load_override_state(Path(self.current.path))
        if not state:
            QMessageBox.information(self, tr("لا يوجد شيء لاستعادته"), tr("لا يوجد إعداد عزل PHP مفعّل لهذا المشروع."))
            return
        vhost = Path(state.get("vhost_file", ""))
        try:
            if vhost.exists():
                phpm.revert_apache_php_override(vhost, self.log_box.append)
            phpm.stop_php_cgi_server(self._php_cgi_proc)
            self._php_cgi_proc = None
            phpm.clear_override_state(Path(self.current.path))
            self._refresh_apache_status()
            self.parent_window.show_toast(tr("✓ تمت الاستعادة — أعد تشغيل Apache من Laragon"), "success")
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), str(e))
