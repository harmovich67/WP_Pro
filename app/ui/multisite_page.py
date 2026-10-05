"""
app/ui/multisite_page.py
─────────────────────────────────────────────
One-Click WordPress Multisite page: pick subdomain/subdirectory mode and
convert the selected project into a Multisite network in a single click.
Apache (.htaccess) rules are written automatically; an nginx rule snippet
is generated (and injected directly into a detected Laragon nginx vhost).
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QRadioButton,
    QButtonGroup, QTextEdit, QMessageBox, QGroupBox
)

from app.core.projects_store import ProjectRecord
from app.core.multisite import is_multisite, preflight_multisite, MODE_SUBDOMAIN, MODE_SUBDIRECTORY
from app.core.wp_ops import get_effective_tooling
from app.core.workers import MultisiteConvertWorker
from app.core.utils import open_path
from app.ui.extra_pages import BaseExtraPage
from app.ui.widgets import make_card, Pill, PrimaryButton, row_buttons
from app.core.i18n import t as tr


class MultisitePage(BaseExtraPage):
    def __init__(self, store, parent_window):
        super().__init__(store, parent_window)

        card, lay = make_card(
            tr("شبكة متعددة (Multisite) بنقرة واحدة"),
            tr("حوّل الموقع الحالي إلى شبكة WordPress متعددة (subdomain أو subdirectory). "
               "يتم تلقائياً: تفعيل الشبكة عبر WP-CLI، وكتابة قواعد .htaccess، وإنشاء/حقن قواعد nginx."))

        self.status_pill = Pill(tr("لم يتم التحقق بعد"), "neutral")
        lay.addWidget(self.status_pill)

        mode_box = QGroupBox(tr("نوع الشبكة"))
        mode_lay = QHBoxLayout(mode_box)
        self.rb_subdirectory = QRadioButton(tr("مجلد فرعي (Subdirectory) — مثال: site.test/sub1"))
        self.rb_subdomain = QRadioButton(tr("نطاق فرعي (Subdomain) — مثال: sub1.site.test"))
        self.rb_subdirectory.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_subdirectory)
        self.mode_group.addButton(self.rb_subdomain)
        mode_lay.addWidget(self.rb_subdirectory)
        mode_lay.addWidget(self.rb_subdomain)
        lay.addWidget(mode_box)

        self.network_title = QLineEdit()
        self.network_title.setPlaceholderText(tr("اسم الشبكة (اختياري)"))
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel(tr("اسم الشبكة:")))
        title_row.addWidget(self.network_title, 1)
        lay.addLayout(title_row)

        warn = QLabel(tr(
            "⚠️ ملاحظة: وضع النطاق الفرعي (Subdomain) يتطلب إضافة نطاقات wildcard "
            "(مثل *.site.test) إلى ملف hosts أو DNS محلياً حتى تعمل المواقع الفرعية. "
            "يُنصح بأخذ نسخة احتياطية كاملة قبل التحويل — لا يمكن التراجع تلقائياً."))
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#F59E0B; font-size:11px;")
        lay.addWidget(warn)

        self.btn_convert = PrimaryButton(tr("🌐 تحويل إلى شبكة متعددة (Multisite)"))
        lay.addWidget(row_buttons(self.btn_convert))

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(220)
        self.log_box.document().setMaximumBlockCount(500)
        self.log_box.setPlaceholderText(tr("سيظهر هنا سجل عملية التحويل..."))
        lay.addWidget(self.log_box)

        self.content_area.addWidget(card)

        self.btn_convert.clicked.connect(self._convert)

        self._thread: QThread | None = None
        self._worker: MultisiteConvertWorker | None = None

        self._set_enabled(False)

    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self.network_title.setText(p.name)
        self._refresh_status(p)

    def _on_project_cleared(self):
        self._set_enabled(False)
        self.log_box.clear()
        self.status_pill.set_state(tr("لم يتم التحقق بعد"), "neutral")

    def _set_enabled(self, val: bool):
        self.rb_subdirectory.setEnabled(val)
        self.rb_subdomain.setEnabled(val)
        self.network_title.setEnabled(val)
        self.btn_convert.setEnabled(val)

    def _refresh_status(self, p: ProjectRecord):
        try:
            already = is_multisite(Path(p.path))
        except Exception:
            already = False
        if already:
            self.status_pill.set_state(tr("الموقع مُحوَّل بالفعل إلى Multisite"), "ok")
            self.btn_convert.setEnabled(False)
        else:
            self.status_pill.set_state(tr("موقع عادي (يمكن تحويله)"), "neutral")
            self.btn_convert.setEnabled(True)

    def _convert(self):
        if not self.current:
            return
        project_path = Path(self.current.path)

        checks = preflight_multisite(project_path)
        failed = [msg for ok, msg in checks if not ok]
        if failed:
            QMessageBox.warning(self, tr("لا يمكن المتابعة"), "\n".join(failed))
            return

        mode = MODE_SUBDOMAIN if self.rb_subdomain.isChecked() else MODE_SUBDIRECTORY
        mode_label = tr("نطاق فرعي (Subdomain)") if mode == MODE_SUBDOMAIN else tr("مجلد فرعي (Subdirectory)")

        r = QMessageBox.question(
            self, tr("تأكيد التحويل"),
            f"{tr('سيتم تحويل الموقع إلى شبكة متعددة بنمط: ')}{mode_label}\n\n"
            f"{tr('يُنصح بأخذ نسخة احتياطية أولاً. هل تريد المتابعة؟')}",
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        try:
            php, wpcli, is_phar = get_effective_tooling(self.current, log=self.log_box.append)
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), str(e))
            return
        if not wpcli:
            QMessageBox.critical(self, tr("WP-CLI غير متوفر"),
                                  tr("تحويل الشبكة المتعددة يتطلب WP-CLI. تأكد من توفر PHP وWP-CLI لهذا المشروع."))
            return

        network_title = self.network_title.text().strip() or self.current.name

        self._set_enabled(False)
        self.log_box.clear()

        self._thread = QThread()
        self._worker = MultisiteConvertWorker(
            str(project_path), php, wpcli, is_phar, network_title, mode,
            self.current.laragon_root, self.current.name,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.log_box.append)
        self._worker.done.connect(self._on_convert_done)
        self._worker.done.connect(self._thread.quit)
        self._thread.start()

    def _on_convert_done(self, ok: bool, message: str, result: dict):
        if self._thread:
            self._thread.wait()
            self._thread = None
        self._worker = None
        self._set_enabled(True)

        if ok:
            self._refresh_status(self.current)
            extra = ""
            if result.get("nginx_written_to_vhost"):
                extra = tr("\nتم حقن قواعد nginx مباشرة في ملف الـ vhost الخاص بـ Laragon.")
            else:
                extra = f"{tr('تم إنشاء ملف قواعد nginx جاهز للنسخ في: ')}{result.get('nginx_snippet', '')}"
            QMessageBox.information(self, tr("تم بنجاح"), f"{message}{extra}")
            if result.get("nginx_snippet") and not result.get("nginx_written_to_vhost"):
                try:
                    open_path(Path(result["nginx_snippet"]).parent)
                except Exception:
                    pass
        else:
            QMessageBox.critical(self, tr("فشل التحويل"), message)
