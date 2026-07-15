from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QMessageBox
)
from PyQt6.QtCore import QThread

from app.ui.widgets import make_card, PrimaryButton, row_buttons
from app.core.projects_store import ProjectsStore, ProjectRecord
from app.ui.extra_pages import BaseExtraPage


# ----------------- Monitoring Page -----------------
class MonitoringPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        # Site Health Card
        health_card, h_lay = make_card("صحة الموقع", "مراقبة توفر الموقع")

        self.health_status = QLabel("الحالة: لم يتم الفحص")
        self.health_status.setStyleSheet("font-size: 14px; font-weight: bold;")
        h_lay.addWidget(self.health_status)

        self.btn_check_health = PrimaryButton("فحص صحة الموقع")
        self.btn_check_health.clicked.connect(self._check_health)
        h_lay.addWidget(row_buttons(self.btn_check_health))

        # Debug Log Card
        debug_card, d_lay = make_card("الأخطاء الأخيرة", "من ملف debug.log")

        self.errors_list = QListWidget()
        self.errors_list.setMaximumHeight(200)
        d_lay.addWidget(self.errors_list)

        self.btn_refresh_errors = QPushButton("تحديث الأخطاء")
        self.btn_refresh_errors.clicked.connect(self._refresh_errors)
        d_lay.addWidget(row_buttons(self.btn_refresh_errors))

        # Auto-Fix Card
        fix_card, f_lay = make_card("إصلاحات سريعة", "إصلاح المشاكل الشائعة")

        self.btn_fix_htaccess = QPushButton("إعادة إنشاء .htaccess")
        self.btn_fix_perms = QPushButton("إصلاح الصلاحيات")
        self.btn_clear_cache = QPushButton("مسح الذاكرة المؤقتة")
        
        self.btn_fix_htaccess.clicked.connect(self._regenerate_htaccess)
        self.btn_fix_perms.clicked.connect(self._fix_permissions)
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        
        fix_row = QHBoxLayout()
        fix_row.addWidget(self.btn_fix_htaccess)
        fix_row.addWidget(self.btn_fix_perms)
        fix_row.addWidget(self.btn_clear_cache)
        f_lay.addLayout(fix_row)
        
        self.content_area.addWidget(health_card)
        self.content_area.addWidget(debug_card)
        self.content_area.addWidget(fix_card)

        self._health_thread = None
        self._health_worker = None
        self._set_enabled(False)
    
    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self._refresh_errors()
    
    def _on_project_cleared(self):
        self._set_enabled(False)
        self.errors_list.clear()
        self.health_status.setText("الحالة: لم يتم الفحص")
    
    def _set_enabled(self, val: bool):
        self.btn_check_health.setEnabled(val)
        self.btn_refresh_errors.setEnabled(val)
        self.btn_fix_htaccess.setEnabled(val)
        self.btn_fix_perms.setEnabled(val)
        self.btn_clear_cache.setEnabled(val)
    
    def _check_health(self):
        if not self.current: return
        if self._health_thread and self._health_thread.isRunning(): return

        from app.core.workers import HealthCheckWorker

        self.health_status.setText("جارٍ الفحص...")
        self.health_status.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_check_health.setEnabled(False)

        self._health_thread = QThread()
        self._health_worker = HealthCheckWorker(self.current.url)
        self._health_worker.moveToThread(self._health_thread)
        self._health_thread.started.connect(self._health_worker.run)
        self._health_worker.done.connect(self._on_health_result)
        self._health_worker.done.connect(self._health_thread.quit)
        self._health_thread.start()

    def _on_health_result(self, result: dict):
        self.btn_check_health.setEnabled(True)
        if result["status"] == "online":
            self.health_status.setText(f"✅ متصل - {result['status_code']} ({result['response_time']:.2f} ث)")
            self.health_status.setStyleSheet("color: green; font-size: 14px; font-weight: bold;")
        else:
            error_msg = result.get("error", result.get("status_code", "غير معروف"))
            self.health_status.setText(f"❌ {result['status']} - {error_msg}")
            self.health_status.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
    
    def _refresh_errors(self):
        if not self.current: return
        
        from app.core.monitoring import SiteMonitor
        
        self.errors_list.clear()
        errors = SiteMonitor.parse_debug_log(self.current.path)
        
        if not errors:
            self.errors_list.addItem("✅ لم يتم العثور على أخطاء في debug.log")
            return
        
        for error in errors[-20:]:  # Last 20 errors
            severity_icon = "🔴" if "Fatal" in error["severity"] else "⚠️" if "Warning" in error["severity"] else "ℹ️"
            self.errors_list.addItem(f"{severity_icon} [{error['severity']}] {error['message'][:80]}...")
    
    def _regenerate_htaccess(self):
        if not self.current: return
        
        from app.core.auto_fix import AutoFix
        
        r = QMessageBox.question(
            self,
            "تأكيد",
            "سيؤدي هذا إلى إعادة إنشاء ملف .htaccess بالإعدادات الافتراضية لـ WordPress.\n\nهل تريد المتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        success = AutoFix.regenerate_htaccess(self.current.path, self.parent_window.log)
        if success:
            QMessageBox.information(self, "نجاح", "تمت إعادة إنشاء ملف .htaccess بنجاح! 🎉")
    
    def _fix_permissions(self):
        if not self.current: return
        
        from app.core.auto_fix import AutoFix
        
        r = QMessageBox.question(
            self,
            "تأكيد",
            "سيؤدي هذا إلى إصلاح صلاحيات الملفات (إزالة القراءة فقط).\n\nهل تريد المتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        success = AutoFix.fix_permissions(self.current.path, self.parent_window.log)
        if success:
            QMessageBox.information(self, "نجاح", "تم إصلاح الصلاحيات! 🎉")

    def _clear_cache(self):
        if not self.current: return

        from app.core.auto_fix import AutoFix

        success = AutoFix.clear_cache(self.current.path, self.parent_window.log)
        if success:
            QMessageBox.information(self, "نجاح", "تم مسح الذاكرة المؤقتة! 🎉")
