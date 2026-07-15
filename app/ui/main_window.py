from __future__ import annotations

import datetime
import json
import platform
import shutil
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QFileDialog, QStackedWidget, QListWidget, QListWidgetItem,
    QFormLayout, QLineEdit, QCheckBox, QSpinBox, QTextEdit, QComboBox, QTabWidget,
    QScrollArea, QFrame, QDialog, QDialogButtonBox
)

from app.ui.widgets import make_card, Pill, PrimaryButton, row_buttons
from app.core.stacks import detect_default_profile
from app.core.projects_store import ProjectsStore, ProjectRecord
from app.core.utils import open_path, is_windows, is_linux, get_default_doc_root
from app.core.wp_ops import (
    DBParams, WPParams, preflight_checks, install_wordpress, clone_project,
    test_mysql, WORDPRESS_LATEST_ZIP, backup_bundle, restore_bundle, wp_cli_search_replace,
    write_project_meta, project_meta_dir, drop_database,
    mysql_connect, search_replace_url_in_db
)


from app.core.workers import (
    InstallWorker, BackupWorker, RestoreWorker, UrlConvertWorker, CloneWorker, ScanWorker
)
from app.core.license import LicenseManager
from app.ui.license_dialog import LicenseDialog


# ---------- Small dialogs ----------
class DbCredsDialog(QDialog):
    """DB credentials for operations (NOT saved)."""
    def __init__(self, title: str, default_user: str = "root"):
        super().__init__()
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.user = QLineEdit()
        self.user.setText(default_user)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("مستخدم قاعدة البيانات:", self.user)
        form.addRow("كلمة مرور قاعدة البيانات:", self.password)
        v.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def creds(self) -> tuple[str, str]:
        return self.user.text().strip(), self.password.text()

class UrlConvertDialog(QDialog):
    def __init__(self, old_url: str):
        super().__init__()
        self.setWindowTitle("تحويل الروابط (URLs)")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.old = QLineEdit()
        self.old.setText(old_url)
        self.new = QLineEdit()
        self.include_guid = QCheckBox("تضمين عمود GUID (يُترك مغلقاً عادةً)")
        form.addRow("الرابط القديم:", self.old)
        form.addRow("الرابط الجديد:", self.new)
        form.addRow("", self.include_guid)
        v.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> tuple[str, str, bool]:
        return self.old.text().strip(), self.new.text().strip(), self.include_guid.isChecked()

class TextInputDialog(QDialog):
    def __init__(self, title: str, fields: list[tuple[str, str]]):
        super().__init__()
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for key, label in fields:
            e = QLineEdit()
            self.edits[key] = e
            form.addRow(label, e)
        v.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> dict[str, str]:
        return {k: e.text().strip() for k, e in self.edits.items()}


# ---------- Pages ----------
class DashboardPage(QWidget):
    project_selected = pyqtSignal(object)  # ProjectRecord|None
    full_deletion_requested = pyqtSignal(object)  # ProjectRecord

    def __init__(self, store: ProjectsStore):
        super().__init__()
        self.store = store
        self.current: ProjectRecord | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(12)

        card, lay = make_card("المشاريع", "مواقع ووردبريس المحلية التي أنشأتها")
        self.list = QListWidget()
        lay.addWidget(self.list)

        self.btn_new = PrimaryButton("مشروع جديد")
        self.btn_import = QPushButton("استيراد مشروع موجود")
        self.btn_open = QPushButton("فتح الموقع")
        self.btn_admin = QPushButton("فتح لوحة التحكم")
        self.btn_folder = QPushButton("فتح المجلد")
        self.btn_clone = QPushButton("استنساخ")
        self.btn_delete = QPushButton("إزالة من القائمة")

        lay.addWidget(row_buttons(self.btn_new, self.btn_import, self.btn_open, self.btn_admin, self.btn_folder, self.btn_clone, self.btn_delete))

        outer.addWidget(card, 1)

        self.list.currentRowChanged.connect(self._on_select)
        self.btn_import.clicked.connect(self._import_project)
        self.btn_open.clicked.connect(self.open_site)
        self.btn_admin.clicked.connect(self.open_admin)
        self.btn_folder.clicked.connect(self.open_folder)
        self.btn_delete.clicked.connect(self.remove_from_list)

        self.reload()

    def reload(self):
        self.list.clear()
        projects = self.store.list_projects()
        for p in projects:
            item = QListWidgetItem(f"{p.name}  —  {p.url}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.list.addItem(item)
        if projects:
            self.list.setCurrentRow(0)
        else:
            self.current = None
            self.project_selected.emit(None)

    def _on_select(self, idx: int):
        item = self.list.item(idx)
        self.current = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.project_selected.emit(self.current)

    def open_site(self):
        if self.current:
            import webbrowser
            webbrowser.open(self.current.url)

    def open_admin(self):
        if self.current:
            import webbrowser
            webbrowser.open(self.current.admin_url)

    def open_folder(self):
        if self.current:
            open_path(Path(self.current.path))

    def remove_from_list(self):
        if not self.current:
            return
            
        msg = QMessageBox(self)
        msg.setWindowTitle("حذف المشروع")
        msg.setText(f"كيف تريد حذف '{self.current.name}'؟")
        msg.setInformativeText("تحذير: خيار 'حذف كل شيء' لا يمكن التراجع عنه.")

        btn_remove_only = msg.addButton("إزالة من القائمة فقط", QMessageBox.ButtonRole.ActionRole)
        btn_full_delete = msg.addButton("حذف كل شيء (الملفات + قاعدة البيانات)", QMessageBox.ButtonRole.DestructiveRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        
        msg.exec()
        
        clicked = msg.clickedButton()
        if clicked == btn_remove_only:
            self.store.delete_by_path(self.current.path)
            self.reload()
        elif clicked == btn_full_delete:
            self.full_deletion_requested.emit(self.current)

    def _import_project(self):
        dlg = ImportProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
            
        data = dlg.get_data()
        path_obj = Path(data["path"])
        
        # Validation
        if not path_obj.exists() or not path_obj.is_dir():
            QMessageBox.critical(self, "خطأ", "مسار المشروع غير صالح.")
            return

        now = datetime.datetime.utcnow().isoformat() + "Z"
        
        # Create record
        rec = ProjectRecord(
            name=data["name"],
            path=data["path"],
            url=data["url"],
            admin_url=data["url"].rstrip("/") + "/wp-admin/",
            stack="Unknown", # Imported
            doc_root=str(path_obj.parent),
            db_host=data["db_host"],
            db_port=data["db_port"],
            db_name=data["db_name"],
            db_user=data["db_user"],
            db_pass=data.get("db_pass", ""),
            table_prefix=data["table_prefix"],
            created_at_iso=now,
            last_action_iso=now,
            notes="مشروع مستورد"
        )
        
        self.store.upsert(rec)
        self.reload()

        # Read old siteurl from DB and update if it differs from the entered URL
        new_url = data["url"].rstrip("/")
        try:
            db = DBParams(
                host=data["db_host"],
                port=data["db_port"],
                root_user=data["db_user"],
                root_pass=data.get("db_pass", ""),
                db_name=data["db_name"],
                create_user=False,
                user=data["db_user"],
                user_pass=data.get("db_pass", ""),
                user_host="localhost",
                table_prefix=data["table_prefix"],
            )
            conn = mysql_connect(db.host, db.port, db.root_user, db.root_pass)
            old_url = None
            try:
                with conn.cursor() as cur:
                    cur.execute(f"USE `{db.db_name}`;")
                    cur.execute(
                        f"SELECT option_value FROM `{db.table_prefix}options` "
                        f"WHERE option_name = 'siteurl' LIMIT 1;"
                    )
                    row = cur.fetchone()
                    if row:
                        old_url = row[0].rstrip("/")
            finally:
                conn.close()

            if old_url and old_url != new_url:
                search_replace_url_in_db(db, old_url, new_url, lambda _: None)
                QMessageBox.information(
                    self, "تم بنجاح",
                    f"تم استيراد المشروع '{rec.name}'.\nتم تحديث الرابط: {old_url} → {new_url}"
                )
            else:
                QMessageBox.information(self, "تم بنجاح", f"تم استيراد المشروع '{rec.name}' بنجاح.")
        except Exception as e:
            QMessageBox.warning(
                self, "تم الاستيراد مع تحذير",
                f"تم حفظ المشروع، لكن تعذّر تحديث الروابط في قاعدة البيانات:\n{e}"
            )


class WizardPage(QWidget):
    install_requested = pyqtSignal(object, object)  # WPParams, DBParams
    preflight_requested = pyqtSignal(object, object)  # WPParams, DBParams

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(12)

        # Top info
        hdr_card, hdr_lay = make_card("معالج مشروع جديد", "إعداد خطوة بخطوة. يمكنك حفظ الإعدادات المسبقة وإعادة استخدامها.")
        outer.addWidget(hdr_card)

        # Stepper + stacked pages
        row = QHBoxLayout()
        row.setSpacing(12)

        self.step_list = QListWidget()
        self.step_list.addItems(["1) المشروع", "2) الموقع", "3) قاعدة البيانات", "4) القالب", "5) المراجعة"])
        self.step_list.setFixedWidth(220)
        self.step_list.setCurrentRow(0)

        self.stack = QStackedWidget()
        self.pages: list[QWidget] = []
        self.pages.append(self._build_project_page())
        self.pages.append(self._build_site_page())
        self.pages.append(self._build_db_page())
        self.pages.append(self._build_template_page())
        self.pages.append(self._build_review_page())
        for p in self.pages:
            self.stack.addWidget(self._wrap_scroll(p))

        # Apply initial defaults now that all widgets exist
        self._apply_stack_defaults(self.stack_combo.currentText())
        self._update_review()

        row.addWidget(self.step_list)
        row.addWidget(self.stack, 1)

        outer.addLayout(row, 1)

        # Bottom nav
        nav_card, nav_lay = make_card("الإجراءات", "")
        self.btn_back = QPushButton("رجوع")
        self.btn_next = PrimaryButton("التالي")
        self.btn_preflight = QPushButton("فحوصات ما قبل التثبيت")
        self.btn_install = PrimaryButton("تثبيت")
        self.btn_install.setEnabled(False)

        nav_lay.addWidget(row_buttons(self.btn_back, self.btn_next, self.btn_preflight, self.btn_install))
        outer.addWidget(nav_card)

        self.step_list.currentRowChanged.connect(self._go_step)
        self.btn_back.clicked.connect(self._back)
        self.btn_next.clicked.connect(self._next)
        self.btn_preflight.clicked.connect(self._preflight)
        self.btn_install.clicked.connect(self._install)

        self._sync_nav()

    def _wrap_scroll(self, w: QWidget) -> QWidget:
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setWidget(w)
        return sc

    # --- Step 1
    def _build_project_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14,14,14,14)
        v.setSpacing(12)

        card, lay = make_card("المشروع", "اختر البيئة (Stack) ومجلد المستندات واسم المشروع")
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.stack_combo = QComboBox()
        if is_windows():
            self.stack_combo.addItems(["Laragon (Windows)", "مخصص"])
        else:
            self.stack_combo.addItems(["بيئة مخصصة (Linux/Unix)", "مخصص"])

        self.laragon_root = QLineEdit()
        self.btn_laragon = QPushButton("استعراض...")

        lr_row = QHBoxLayout()
        lr_row.setContentsMargins(0,0,0,0)
        lr_row.setSpacing(8)
        lr_row.addWidget(self.laragon_root, 1)
        lr_row.addWidget(self.btn_laragon)

        self.doc_root = QLineEdit()
        self.btn_doc = QPushButton("استعراض...")
        dr_row = QHBoxLayout()
        dr_row.setContentsMargins(0,0,0,0)
        dr_row.setSpacing(8)
        dr_row.addWidget(self.doc_root, 1)
        dr_row.addWidget(self.btn_doc)

        self.project_name = QLineEdit()
        self.overwrite = QCheckBox("استبدال المجلد الموجود")

        form.addRow("البيئة (Stack):", self.stack_combo)
        form.addRow("مجلد Laragon الجذري:", QWidget())
        form.itemAt(form.rowCount()-1, QFormLayout.ItemRole.FieldRole).widget().setLayout(lr_row)
        form.addRow("مجلد المستندات (Document root):", QWidget())
        form.itemAt(form.rowCount()-1, QFormLayout.ItemRole.FieldRole).widget().setLayout(dr_row)
        form.addRow("اسم المشروع:", self.project_name)
        form.addRow("", self.overwrite)

        lay.addLayout(form)
        v.addWidget(card)
        v.addStretch(1)

        self.btn_doc.clicked.connect(self._pick_docroot)
        self.btn_laragon.clicked.connect(self._pick_laragon)
        self.stack_combo.currentTextChanged.connect(self._apply_stack_defaults)
        self.project_name.textChanged.connect(self._autofill_from_name)

        # defaults
        self.laragon_root.setText("C:\\laragon" if is_windows() else "")
        self.os_label = QLabel(f"نظام التشغيل المكتشف: {'Windows' if is_windows() else 'Linux/Unix' if is_linux() else 'غير معروف'}")
        if is_windows() or is_linux():
            self.os_label.setStyleSheet("color: #155724; background-color: #d4edda; border-radius: 4px; padding: 4px;")
        else:
            self.os_label.setStyleSheet("color: #721c24; background-color: #f8d7da; border-radius: 4px; padding: 4px;")
        lay.addWidget(self.os_label)
        # NOTE: initial stack defaults are applied after all wizard pages are built
        self.project_name.setText("wp-site")

        return w

    def _apply_stack_defaults(self, stack_name: str):
        prof = detect_default_profile(stack_name, self.laragon_root.text().strip())
        self.doc_root.setText(prof.doc_root)
        if hasattr(self, 'php_path') and self.php_path is not None:
            self.php_path.setText(prof.php_path)

        is_lar = stack_name.lower().startswith("laragon")
        if hasattr(self, 'laragon_root'):
            self.laragon_root.setEnabled(is_lar)
        if hasattr(self, 'btn_laragon'):
            self.btn_laragon.setEnabled(is_lar)

        # DB defaults from stack
        if hasattr(self, 'db_host') and self.db_host is not None:
            self.db_host.setText(prof.db_host)
        if hasattr(self, 'db_port') and self.db_port is not None:
            self.db_port.setValue(prof.db_port)

    def _pick_docroot(self):
        p = QFileDialog.getExistingDirectory(self, "اختر مجلد المستندات (Document Root)", self.doc_root.text() or str(Path.home()))
        if p:
            self.doc_root.setText(p)

    def _pick_laragon(self):
        p = QFileDialog.getExistingDirectory(self, "اختر مجلد Laragon الجذري", self.laragon_root.text() or "C:\\")
        if p:
            self.laragon_root.setText(p)
            # Re-apply stack defaults using updated Laragon root
            self._apply_stack_defaults(self.stack_combo.currentText())
            # NOTE: initial stack defaults are applied after all wizard pages are built

    # --- Step 2
    def _build_site_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14,14,14,14)
        v.setSpacing(12)

        card, lay = make_card("الموقع", "إعدادات مدير ووردبريس والرابط")
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.site_title = QLineEdit()
        self.site_url = QLineEdit()
        self.admin_user = QLineEdit()
        self.admin_pass = QLineEdit()
        self.admin_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_email = QLineEdit()

        self.wp_zip_url = QLineEdit()
        self.wp_zip_url.setText(WORDPRESS_LATEST_ZIP)

        self.local_zip = QLineEdit()
        self.btn_local_zip = QPushButton("اختيار ملف ZIP محلي (اختياري)")
        zrow = QHBoxLayout()
        zrow.setContentsMargins(0,0,0,0)
        zrow.setSpacing(8)
        zrow.addWidget(self.local_zip, 1)
        zrow.addWidget(self.btn_local_zip)

        form.addRow("عنوان الموقع:", self.site_title)
        form.addRow("رابط الموقع:", self.site_url)
        form.addRow("اسم مستخدم المدير:", self.admin_user)
        form.addRow("كلمة مرور المدير:", self.admin_pass)
        form.addRow("البريد الإلكتروني للمدير:", self.admin_email)
        form.addRow("رابط ملف ووردبريس المضغوط:", self.wp_zip_url)
        form.addRow("ملف ZIP بدون اتصال:", QWidget())
        form.itemAt(form.rowCount()-1, QFormLayout.ItemRole.FieldRole).widget().setLayout(zrow)

        lay.addLayout(form)
        v.addWidget(card)

        card2, lay2 = make_card("التثبيت التلقائي", "اختياري: إتمام التثبيت باستخدام WP-CLI")
        form2 = QFormLayout()
        form2.setVerticalSpacing(10)

        self.auto_install = QCheckBox("تثبيت تلقائي باستخدام WP-CLI")
        self.download_wpcli = QCheckBox("تنزيل wp-cli.phar تلقائياً إن لم يكن موجوداً")
        self.download_wpcli.setChecked(True)

        self.php_path = QLineEdit()
        self.wpcli_path = QLineEdit()
        self.btn_php = QPushButton("استعراض PHP")
        self.btn_wpcli = QPushButton("استعراض WP-CLI")

        php_row = QHBoxLayout()
        php_row.setContentsMargins(0,0,0,0)
        php_row.setSpacing(8)
        php_row.addWidget(self.php_path, 1)
        php_row.addWidget(self.btn_php)

        wpcli_row = QHBoxLayout()
        wpcli_row.setContentsMargins(0,0,0,0)
        wpcli_row.setSpacing(8)
        wpcli_row.addWidget(self.wpcli_path, 1)
        wpcli_row.addWidget(self.btn_wpcli)

        form2.addRow("", self.auto_install)
        form2.addRow("", self.download_wpcli)
        form2.addRow("مسار PHP:", QWidget())
        form2.itemAt(form2.rowCount()-1, QFormLayout.ItemRole.FieldRole).widget().setLayout(php_row)
        form2.addRow("مسار WP-CLI:", QWidget())
        form2.itemAt(form2.rowCount()-1, QFormLayout.ItemRole.FieldRole).widget().setLayout(wpcli_row)

        lay2.addLayout(form2)
        v.addWidget(card2)
        v.addStretch(1)

        self.btn_local_zip.clicked.connect(self._pick_zip)
        self.btn_php.clicked.connect(self._pick_php)
        self.btn_wpcli.clicked.connect(self._pick_wpcli)
        self.project_name.textChanged.connect(self._autofill_from_name)

        # defaults
        self.site_title.setText("موقعي على ووردبريس")
        self.admin_user.setText("admin")
        self.admin_email.setText("admin@example.com")
        self.auto_install.setChecked(True)

        return w

    def _pick_zip(self):
        p, _ = QFileDialog.getOpenFileName(self, "اختر ملف wordpress.zip", "", "ZIP (*.zip)")
        if p:
            self.local_zip.setText(p)

    def _pick_php(self):
        p, _ = QFileDialog.getOpenFileName(self, "اختر ملف PHP التنفيذي", self.php_path.text() or str(Path.home()))
        if p:
            self.php_path.setText(p)

    def _pick_wpcli(self):
        p, _ = QFileDialog.getOpenFileName(self, "اختر WP-CLI (wp/wp.bat/wp-cli.phar)", self.wpcli_path.text() or str(Path.home()))
        if p:
            self.wpcli_path.setText(p)

    # --- Step 3
    def _build_db_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14,14,14,14)
        v.setSpacing(12)

        card, lay = make_card("Database", "Create DB + optional dedicated user")
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.db_host = QLineEdit()
        self.db_port = QSpinBox()
        self.db_port.setRange(1, 65535)
        self.db_root_user = QLineEdit()
        self.db_root_pass = QLineEdit()
        self.db_root_pass.setEchoMode(QLineEdit.EchoMode.Password)

        self.db_name = QLineEdit()
        self.table_prefix = QLineEdit()

        self.create_db_user = QCheckBox("Create dedicated DB user")
        self.db_user = QLineEdit()
        self.db_pass = QLineEdit()
        self.db_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.db_user_host = QLineEdit()

        self.btn_test_db = QPushButton("Test DB Connection")
        self.db_status = Pill("Not tested", "neutral")

        form.addRow("Host:", self.db_host)
        form.addRow("Port:", self.db_port)
        form.addRow("Root user:", self.db_root_user)
        form.addRow("Root pass:", self.db_root_pass)
        form.addRow("DB name:", self.db_name)
        form.addRow("Table prefix:", self.table_prefix)
        form.addRow("", self.create_db_user)
        form.addRow("New user:", self.db_user)
        form.addRow("New pass:", self.db_pass)
        form.addRow("New user host:", self.db_user_host)

        lay.addLayout(form)

        status_row = QHBoxLayout()
        status_row.addWidget(self.btn_test_db)
        status_row.addWidget(self.db_status)
        status_row.addStretch(1)
        lay.addLayout(status_row)

        v.addWidget(card)
        v.addStretch(1)

        self.btn_test_db.clicked.connect(self._test_db)
        self.project_name.textChanged.connect(self._autofill_from_name)

        # defaults
        self.db_root_user.setText("root")
        self.db_name.setText("wp_site")
        self.table_prefix.setText("wp_")
        self.create_db_user.setChecked(True)
        self.db_user.setText("wp_user")
        self.db_pass.setText("wp_pass_123")
        self.db_user_host.setText("localhost")

        return w

    def _test_db(self):
        db = self._get_db_params()
        ok, msg = test_mysql(db)
        kind = "ok" if ok else "bad"
        self.db_status.set_state("OK" if ok else "FAILED", kind)
        QMessageBox.information(self, "DB Test", msg)

    # --- Step 4
    def _build_template_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14,14,14,14)
        v.setSpacing(12)

        card, lay = make_card("القالب", "اختر القالب الأساسي والإضافات والقالب ووضع المطور")
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.template = QComboBox()
        self.template.addItems(["فارغ", "بداية للمطورين", "بداية ووكومرس", "بداية SEO"])

        self.theme = QLineEdit()
        self.plugins = QTextEdit()
        self.plugins.setPlaceholderText("اكتب معرّف إضافة واحد في كل سطر (مثال: query-monitor)\nيُطبَّق فقط إذا كان التثبيت التلقائي مفعّلاً (WP-CLI).")

        self.dev_mode = QCheckBox("تفعيل وضع المطور (WP_DEBUG + سجل الأخطاء)")
        self.permalinks = QLineEdit()
        self.permalinks.setText("/%postname%/")

        form.addRow("القالب الأساسي:", self.template)
        form.addRow("معرّف قالب ووردبريس (اختياري):", self.theme)
        form.addRow("الإضافات:", self.plugins)
        form.addRow("", self.dev_mode)
        form.addRow("روابط دائمة (Permalinks):", self.permalinks)

        lay.addLayout(form)
        v.addWidget(card)
        v.addStretch(1)

        self.template.currentTextChanged.connect(self._apply_template)

        # default template
        self._apply_template(self.template.currentText())

        return w

    def _apply_template(self, name: str):
        presets = {
            "فارغ": {"theme": "", "plugins": [], "dev": False},
            "بداية للمطورين": {"theme": "", "plugins": ["query-monitor", "classic-editor"], "dev": True},
            "بداية ووكومرس": {"theme": "storefront", "plugins": ["woocommerce", "query-monitor"], "dev": True},
            "بداية SEO": {"theme": "", "plugins": ["rank-math", "query-monitor"], "dev": True},
        }
        p = presets.get(name, presets["فارغ"])
        self.theme.setText(p["theme"])
        self.plugins.setPlainText("\n".join(p["plugins"]))
        self.dev_mode.setChecked(bool(p["dev"]))

    # --- Step 5
    def _build_review_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14,14,14,14)
        v.setSpacing(12)

        card, lay = make_card("المراجعة", "قم بفحوصات ما قبل التثبيت أولاً، ثم ثبّت")
        self.review = QTextEdit()
        self.review.setReadOnly(True)
        lay.addWidget(self.review)

        self.preflight_box = QTextEdit()
        self.preflight_box.setReadOnly(True)
        self.preflight_box.setFixedHeight(200)
        lay.addWidget(QLabel("فحوصات ما قبل التثبيت:"))
        lay.addWidget(self.preflight_box)

        v.addWidget(card)
        v.addStretch(1)
        return w

    def _autofill_from_name(self):
        name = self.project_name.text().strip()
        if not name:
            return
        if not hasattr(self, 'site_url') or not hasattr(self, 'db_name'):
            return
        # URL
        if self.site_url.text().strip() in ("", "http://localhost/wp-site", "http://localhost/wp_site"):
            self.site_url.setText(f"http://localhost/{name}")
        # DB name (safe)
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        if self.db_name.text().strip() in ("wp_site", "", "wordpress"):
            self.db_name.setText(safe)

        self._update_review()

    def _update_review(self):
        if not hasattr(self, 'review'):
            return
        wp = self._get_wp_params()
        db = self._get_db_params()
        txt = {
            "project": str((wp.doc_root / wp.project_name).resolve()),
            "url": wp.site_url,
            "db": {"host": db.host, "port": db.port, "db_name": db.db_name, "prefix": db.table_prefix, "create_user": db.create_user},
            "auto_install": wp.auto_install,
            "template": wp.template_name,
            "theme": wp.install_theme,
            "plugins": wp.plugins,
            "dev_mode": wp.dev_mode,
            "permalinks": wp.permalinks,
        }
        self.review.setPlainText(json.dumps(txt, ensure_ascii=False, indent=2))

    def _get_db_params(self) -> DBParams:
        return DBParams(
            host=self.db_host.text().strip(),
            port=int(self.db_port.value()),
            root_user=self.db_root_user.text().strip(),
            root_pass=self.db_root_pass.text(),
            db_name=self.db_name.text().strip(),
            create_user=self.create_db_user.isChecked(),
            user=self.db_user.text().strip(),
            user_pass=self.db_pass.text(),
            user_host=(self.db_user_host.text().strip() or "localhost"),
            table_prefix=(self.table_prefix.text().strip() or "wp_"),
        )

    def _get_wp_params(self) -> WPParams:
        plugins = [p.strip() for p in self.plugins.toPlainText().splitlines() if p.strip()]
        return WPParams(
            doc_root=Path(self.doc_root.text().strip() or "."),
            project_name=self.project_name.text().strip(),
            site_title=self.site_title.text().strip(),
            site_url=self.site_url.text().strip(),
            admin_user=self.admin_user.text().strip(),
            admin_pass=self.admin_pass.text(),
            admin_email=self.admin_email.text().strip(),
            wp_zip_url=self.wp_zip_url.text().strip(),
            wp_zip_local=self.local_zip.text().strip(),
            overwrite=self.overwrite.isChecked(),
            stack_name=self.stack_combo.currentText(),
            laragon_root=self.laragon_root.text().strip(),

            auto_install=self.auto_install.isChecked(),
            php_path=self.php_path.text().strip(),
            wpcli_path=self.wpcli_path.text().strip(),
            download_wpcli=self.download_wpcli.isChecked(),

            template_name=self.template.currentText(),
            install_theme=self.theme.text().strip(),
            plugins=plugins,
            dev_mode=self.dev_mode.isChecked(),
            permalinks=self.permalinks.text().strip(),
        )

    def _go_step(self, idx: int):
        self.stack.setCurrentIndex(max(0, idx))
        self._sync_nav()
        self._update_review()

    def _back(self):
        self.step_list.setCurrentRow(max(0, self.step_list.currentRow() - 1))

    def _next(self):
        self.step_list.setCurrentRow(min(self.step_list.count()-1, self.step_list.currentRow() + 1))

    def _sync_nav(self):
        idx = self.step_list.currentRow()
        self.btn_back.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < self.step_list.count()-1)
        self.btn_install.setEnabled(idx == self.step_list.count()-1)

    def _preflight(self):
        wp = self._get_wp_params()
        db = self._get_db_params()
        self.preflight_requested.emit(wp, db)

    def _install(self):
        wp = self._get_wp_params()
        db = self._get_db_params()
        self.install_requested.emit(wp, db)


class WPCLIConsolePage(QWidget):
    def __init__(self, store: ProjectsStore):
        super().__init__()
        self.store = store

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(12)

        card, lay = make_card("طرفية WP-CLI", "تشغيل أوامر wp-cli على مشروع محدد (يتطلب php + wp-cli)")
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.project = QComboBox()
        self.cmd = QLineEdit()
        self.cmd.setPlaceholderText("مثال: plugin list --status=active")
        self.btn_run = PrimaryButton("تشغيل")
        self.out = QTextEdit()
        self.out.setReadOnly(True)

        form.addRow("المشروع:", self.project)
        form.addRow("الأمر:", self.cmd)
        lay.addLayout(form)
        lay.addWidget(row_buttons(self.btn_run))

        lay.addWidget(self.out, 1)
        outer.addWidget(card, 1)

        self.btn_run.clicked.connect(self._run)
        self.reload_projects()

    def reload_projects(self):
        self.project.clear()
        for p in self.store.list_projects():
            self.project.addItem(f"{p.name} — {p.url}", p)

    def _run(self):
        from app.core.wp_ops import run_wpcli, detect_php, detect_wpcli
        from app.core.wp_ops import WPParams as _WPParams  # avoid cycles
        from app.core.utils import which_any

        p: ProjectRecord | None = self.project.currentData()
        if not p:
            return
        # Best effort: use system php/wp or user installs
        php = which_any(["php", "php.exe"])
        if not php:
            QMessageBox.warning(self, "غير موجود", "لم يتم العثور على PHP في PATH. وفّر PHP بتثبيته أو باستخدام Laragon.")
            return

        wpcli = which_any(["wp", "wp.bat", "wp.cmd"])
        is_phar = False
        if not wpcli:
            QMessageBox.warning(self, "غير موجود", "لم يتم العثور على WP-CLI في PATH. ثبّت WP-CLI أو استخدم التنزيل التلقائي من المعالج.")
            return

        cmdline = self.cmd.text().strip()
        if not cmdline:
            return
        args = cmdline.split()
        self.out.clear()
        try:
            run_wpcli(Path(p.path), php, wpcli, is_phar, args, self.out.append)
        except Exception as e:
            self.out.append(str(e))


class ProjectToolsPage(QWidget):
    def __init__(self, store: ProjectsStore, parent_window):
        super().__init__()
        self.store = store
        self.parent_window = parent_window

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(12)

        card, lay = make_card("أدوات المشروع", "قاعدة بيانات لكل مشروع • نسخ احتياطي/استعادة • تحويل الروابط")
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.project = QComboBox()
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setFixedHeight(220)

        self.btn_open_phpmyadmin = QPushButton("فتح phpMyAdmin")
        self.btn_backup = PrimaryButton("نسخ احتياطي (الملفات + قاعدة البيانات)")
        self.btn_restore = QPushButton("استعادة نسخة احتياطية")
        self.btn_convert = PrimaryButton("تحويل الروابط")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_open_phpmyadmin)
        btn_row.addWidget(self.btn_backup)
        btn_row.addWidget(self.btn_restore)
        btn_row.addWidget(self.btn_convert)
        btn_row.addStretch(1)

        form.addRow("المشروع:", self.project)
        lay.addLayout(form)
        lay.addWidget(self.details)
        lay.addLayout(btn_row)

        outer.addWidget(card, 1)

        self.project.currentIndexChanged.connect(self._refresh)
        self.btn_open_phpmyadmin.clicked.connect(self._open_phpmyadmin)
        self.btn_backup.clicked.connect(self._backup)
        self.btn_restore.clicked.connect(self._restore)
        self.btn_convert.clicked.connect(self._convert)

        self.reload_projects()

    def reload_projects(self):
        self.project.clear()
        for p in self.store.list_projects():
            self.project.addItem(f"{p.name} — {p.url}", p)
        self._refresh()

    def current_project(self):
        return self.project.currentData()

    def _laragon_db_dir(self, p) -> str:
        lr = (p.laragon_root or "").strip()
        if not lr:
            return ""
        cand = Path(lr) / "data" / "mysql"
        if cand.exists():
            return str(cand)
        return str(cand)  # show expected path even if missing

    def _refresh(self):
        p = self.current_project()
        if not p:
            self.details.setPlainText("لم يتم اختيار أي مشروع.")
            return

        lar_db = self._laragon_db_dir(p) if (p.stack or "").lower().startswith("laragon") else ""
        note = "يتم تخزين قاعدة البيانات بواسطة خادم MySQL الخاص بك (مجلد البيانات)." if not lar_db else f"مجلد بيانات MySQL في Laragon (المتوقع): {lar_db}"

        txt = {
            "project": p.name,
            "path": p.path,
            "urls": {"site": p.url, "admin": p.admin_url},
            "stack": p.stack,
            "doc_root": p.doc_root,
            "database": {
                "host": p.db_host, "port": p.db_port,
                "name": p.db_name, "user": p.db_user,
                "table_prefix": p.table_prefix
            },
            "meta_file": str(project_meta_dir(Path(p.path)) / "project.json"),
            "note": note
        }
        self.details.setPlainText(json.dumps(txt, ensure_ascii=False, indent=2))

    def _open_phpmyadmin(self):
        import webbrowser
        webbrowser.open("http://localhost/phpmyadmin/")

    def _db_params_with_creds(self, p, user: str, pwd: str) -> DBParams:
        return DBParams(
            host=p.db_host or "127.0.0.1",
            port=int(p.db_port or 3306),
            root_user=user,
            root_pass=pwd,
            db_name=p.db_name,
            create_user=False,
            user="",
            user_pass="",
            user_host="localhost",
            table_prefix=p.table_prefix or "wp_"
        )

    def _backup(self):
        p = self.current_project()
        if not p:
            return
        dlg = DbCredsDialog("بيانات قاعدة البيانات (للنسخ الاحتياطي)", default_user="root")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        user, pwd = dlg.creds()

        default_dir = str((Path(p.path) / ".wpinst" / "backups").resolve())
        out_dir = QFileDialog.getExistingDirectory(self, "اختر مجلد النسخ الاحتياطي", default_dir) or default_dir

        db = self._db_params_with_creds(p, user, pwd)
        self.parent_window._run_backup_worker(p.path, db, out_dir)

    def _restore(self):
        p = self.current_project()
        if not p:
            return
        default_dir = str((Path(p.path) / ".wpinst" / "backups").resolve())
        bdir = QFileDialog.getExistingDirectory(self, "اختر مجلد النسخة الاحتياطية", default_dir)
        if not bdir:
            return
        r = QMessageBox.question(self, "تأكيد الاستعادة", "سيؤدي هذا إلى استبدال الملفات وقاعدة البيانات.\nهل تريد المتابعة؟")
        if r != QMessageBox.StandardButton.Yes:
            return

        dlg = DbCredsDialog("بيانات قاعدة البيانات (للاستعادة)", default_user="root")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        user, pwd = dlg.creds()

        db = self._db_params_with_creds(p, user, pwd)
        self.parent_window._run_restore_worker(p.path, db, bdir)

    def _convert(self):
        p = self.current_project()
        if not p:
            return
        ud = UrlConvertDialog(p.url)
        if ud.exec() != QDialog.DialogCode.Accepted:
            return
        old_url, new_url, include_guid = ud.values()
        if not old_url or not new_url:
            QMessageBox.warning(self, "بيانات ناقصة", "الرابط القديم والرابط الجديد مطلوبان.")
            return

        dlg = DbCredsDialog("بيانات قاعدة البيانات (لتحويل الروابط)", default_user="root")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        user, pwd = dlg.creds()
        db = self._db_params_with_creds(p, user, pwd)

        self.parent_window._run_url_worker(p, db, old_url, new_url, include_guid)


class ImportProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("استيراد مشروع ووردبريس موجود")
        self.setMinimumWidth(500)
        
        self.layout = QVBoxLayout(self)
        self.form = QFormLayout()
        
        # Folder picker
        self.path_edit = QLineEdit()
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse)
        
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(self.btn_browse)
        self.form.addRow("Project Folder:", path_row)
        
        # Details
        self.name_edit = QLineEdit()
        self.url_edit = QLineEdit("http://localhost/")
        self.form.addRow("Project Name:", self.name_edit)
        self.form.addRow("Site URL:", self.url_edit)
        
        # DB Details (Collapsible/Editable)
        self.layout.addLayout(self.form)
        
        self.db_group = QFrame()
        self.db_form = QFormLayout(self.db_group)
        self.db_host = QLineEdit("127.0.0.1")
        self.db_port = QSpinBox()
        self.db_port.setRange(1, 65535)
        self.db_port.setValue(3306)
        self.db_name = QLineEdit()
        self.db_user = QLineEdit("root")
        self.db_pass = QLineEdit()
        self.db_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.table_prefix = QLineEdit("wp_")
        
        self.db_form.addRow("DB Host:", self.db_host)
        self.db_form.addRow("DB Port:", self.db_port)
        self.db_form.addRow("DB Name:", self.db_name)
        self.db_form.addRow("DB User:", self.db_user)
        self.db_form.addRow("DB Pass:", self.db_pass)
        self.db_form.addRow("Table Prefix:", self.table_prefix)
        
        lbl_db = QLabel("Database Connection (Auto-detected from wp-config.php)")
        lbl_db.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.layout.addWidget(lbl_db)
        self.layout.addWidget(self.db_group)
        
        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self.layout.addWidget(btns)
        
        self.path_edit.textChanged.connect(self._on_path_changed)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select WordPress Root Folder")
        if d:
            self.path_edit.setText(d)

    def _on_path_changed(self, path_str):
        p = Path(path_str)
        if not p.exists():
            return
            
        # 1. Try to guess name
        if not self.name_edit.text():
            self.name_edit.setText(p.name)
            
        # 2. Try to parse wp-config
        cfg = p / "wp-config.php"
        if cfg.exists():
            from app.core.utils import parse_wp_config
            data = parse_wp_config(cfg)
            
            if data.get("db_host"):
                # Handle host:port
                h = data["db_host"]
                if ":" in h:
                    parts = h.split(":")
                    self.db_host.setText(parts[0])
                    if parts[1].isdigit():
                        self.db_port.setValue(int(parts[1]))
                else:
                    self.db_host.setText(h)
                    
            if data.get("db_name"): self.db_name.setText(data["db_name"])
            if data.get("db_user"): self.db_user.setText(data["db_user"])
            if data.get("db_pass"): self.db_pass.setText(data["db_pass"])
            if data.get("table_prefix"): self.table_prefix.setText(data["table_prefix"])

            # Extract WordPress URLs from wp-config.php
            # Priority: WP_HOME > WP_SITEURL > fallback to localhost guess
            site_url = None
            if data.get("wp_home"):
                site_url = data["wp_home"]
            elif data.get("wp_siteurl"):
                site_url = data["wp_siteurl"]
            
            if site_url:
                self.url_edit.setText(site_url)
            elif "localhost" in self.url_edit.text():
                # Fallback: guess based on folder name
                self.url_edit.setText(f"http://localhost/{p.name}")
        else:
            # Maybe show warning?
            pass

    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "url": self.url_edit.text().strip(),
            "db_host": self.db_host.text().strip(),
            "db_port": self.db_port.value(),
            "db_name": self.db_name.text().strip(),
            "db_user": self.db_user.text().strip(),
            "db_pass": self.db_pass.text(),
            "table_prefix": self.table_prefix.text().strip()
        }


# ---------- Main window ----------
class MainWindow(QMainWindow):
    def __init__(self, theme_manager=None):
        super().__init__()
        self.setWindowTitle("Harmulizer Pro")
        self.theme_manager = theme_manager

        # ── Responsive initial size ───────────────────────────────────
        self.setMinimumSize(860, 560)
        _screen = QApplication.primaryScreen()
        if _screen:
            _avail = _screen.availableGeometry()
            _win_w = min(1200, max(960,  int(_avail.width()  * 0.88)))
            _win_h = min(820,  max(600,  int(_avail.height() * 0.88)))
            self.resize(_win_w, _win_h)
            self.move(
                _avail.x() + (_avail.width()  - _win_w) // 2,
                _avail.y() + (_avail.height() - _win_h) // 2,
            )
            self._small_screen = _avail.height() < 800
        else:
            self.resize(1100, 720)
            self._small_screen = False
        # ─────────────────────────────────────────────────────────────

        # Initialize license manager
        self.license_manager = LicenseManager()

        self.store = ProjectsStore()

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        _pad = 10 if self._small_screen else 16
        outer.setContentsMargins(_pad, _pad, _pad, _pad)
        outer.setSpacing(4 if self._small_screen else 6)

        # Header
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        t = QLabel("Harmulizer Pro")
        t.setObjectName("AppTitle")
        s = QLabel("Wizard • Templates • DB Tools • Clone/Backup • WP-CLI Console")
        # Icon: resolve for both dev and frozen exe
        import sys as _sys
        if getattr(_sys, 'frozen', False):
            _icon_path = str(Path(_sys._MEIPASS) / "app.ico")
        else:
            _icon_path = str(Path(__file__).resolve().parent.parent.parent / "app.ico")
        self.setWindowIcon(QIcon(_icon_path))

        s.setObjectName("AppSubtitle")
        title_box.addWidget(t)
        title_box.addWidget(s)
        top.addLayout(title_box)
        top.addStretch(1)

        # License status button
        self.btn_license = QPushButton()
        self._update_license_button()
        self.btn_license.setFixedHeight(40)
        self.btn_license.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4F46E5, stop:1 #7C3AED);
                border: none;
                border-radius: 20px;
                font-size: 12px;
                color: white;
                font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4338CA, stop:1 #6D28D9);
            }
        """)
        self.btn_license.setToolTip("إدارة الترخيص")
        self.btn_license.clicked.connect(self._show_license_dialog)
        top.addWidget(self.btn_license)

        # About button
        self.btn_about = QPushButton("  About")
        self.btn_about.setFixedSize(80, 40)
        self.btn_about.setStyleSheet("""
            QPushButton {
                background: #374151;
                border: 1px solid #4B5563;
                border-radius: 20px;
                font-size: 13px;
                color: #D1D5DB;
                font-weight: 600;
            }
            QPushButton:hover { background: #4B5563; }
        """)
        self.btn_about.setToolTip("About Harmulizer Pro")
        self.btn_about.clicked.connect(self._show_about)
        top.addWidget(self.btn_about)
        
        # Theme Toggle Button
        if self.theme_manager:
            self.btn_theme_toggle = QPushButton()
            self._update_theme_button_icon()
            self.btn_theme_toggle.setFixedSize(40, 40)
            self.btn_theme_toggle.setStyleSheet("""
                QPushButton {
                    background: #374151;
                    border: 1px solid #4B5563;
                    border-radius: 20px;
                    font-size: 18px;
                }
                QPushButton:hover {
                    background: #4B5563;
                }
            """)
            self.btn_theme_toggle.clicked.connect(self._toggle_theme)
            self.btn_theme_toggle.setToolTip("Toggle Dark/Light Theme")
            top.addWidget(self.btn_theme_toggle)

        self.status_pill = Pill("Idle", "neutral")
        top.addWidget(self.status_pill)

        outer.addLayout(top)

        # Main layout: Sidebar + Content
        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0,0,0,0)

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(250)
        self.sidebar.addItems([
            "🏠 Dashboard",
            "✨ New Project",
            "💻 WP-CLI Console",
            "📦 Backups",
            "🗄️ Database",
            "🔗 URL Converter",
            "🛡️ Security & Hardening",
            "🩺 Monitoring & Auto-Fix",
            "🧩 Plugin & Theme Manager",
            "⚙️ WP-Config Editor",
            "🛠️ Developer Tools",
            "🤖 AI Assistant",
            "🌐 Site Dashboard",
            "🔑 License Config",
            "📊 License Dashboard",
        ])
        self.sidebar.setCurrentRow(0)
        body.addWidget(self.sidebar)

        # Content Area
        self.main_stack = QStackedWidget()
        body.addWidget(self.main_stack, 1)

        outer.addLayout(body, 1)

        # Pages
        from app.ui.extra_pages import (
            BackupPage, DatabasePage, UrlConvertPage, SecurityPage,
            ManagerPage, ConfigPage, DevToolsPage
        )
        from app.ui.monitoring_page import MonitoringPage
        from app.ui.ai_page import AIAssistantPage
        from app.ui.dashboard import DashboardPage  # New modern dashboard
        from app.ui.site_dashboard_page import SiteDashboardPage
        from app.ui.license_feature_manager import LicenseFeatureManagerPage
        from app.ui.license_dashboard_page import LicenseDashboardPage

        self.dashboard = DashboardPage(self.store)
        self.wizard = WizardPage()
        self.console = WPCLIConsolePage(self.store)
        self.backup_page = BackupPage(self.store, self)
        self.db_page = DatabasePage(self.store, self)
        self.url_page = UrlConvertPage(self.store, self)
        self.security_page = SecurityPage(self.store, self)
        self.monitoring_page = MonitoringPage(self.store, self)
        self.manager_page = ManagerPage(self.store, self)
        self.config_page = ConfigPage(self.store, self)
        self.dev_tools_page = DevToolsPage(self.store, self)
        self.ai_page = AIAssistantPage(self.store, self)
        self.site_dashboard_page = SiteDashboardPage(self.store, self)
        self.license_feature_manager_page = LicenseFeatureManagerPage(
            on_features_saved=self._apply_license_restrictions, parent=self)

        # License Dashboard - use shared licenses.db path
        if getattr(sys, 'frozen', False):
            # In frozen mode, put the active licenses.db next to the executable so it persists.
            # If it doesn't exist, initialize it from the bundled database.
            _exe_dir = Path(sys.executable).parent
            _db_path = _exe_dir / "licenses.db"
            if not _db_path.exists():
                _bundled_db = Path(sys._MEIPASS) / "licenses.db"
                if _bundled_db.exists():
                    try:
                        shutil.copy2(_bundled_db, _db_path)
                    except Exception as e:
                        print(f"Error copying default database: {e}")
            _db_path = str(_db_path)
        else:
            _db_path = str(Path(__file__).resolve().parent.parent.parent / "licenses.db")
        self.license_dashboard_page = LicenseDashboardPage(db_path=_db_path, parent=self)

        self.main_stack.addWidget(self._wrap_pad(self.dashboard))
        self.main_stack.addWidget(self._wrap_pad(self.wizard))
        self.main_stack.addWidget(self._wrap_pad(self.console))
        self.main_stack.addWidget(self._wrap_pad(self.backup_page))
        self.main_stack.addWidget(self._wrap_pad(self.db_page))
        self.main_stack.addWidget(self._wrap_pad(self.url_page))
        self.main_stack.addWidget(self._wrap_pad(self.security_page))
        self.main_stack.addWidget(self._wrap_pad(self.monitoring_page))
        self.main_stack.addWidget(self._wrap_pad(self.manager_page))
        self.main_stack.addWidget(self._wrap_pad(self.config_page))
        self.main_stack.addWidget(self._wrap_pad(self.dev_tools_page))
        self.main_stack.addWidget(self._wrap_pad(self.ai_page))
        self.main_stack.addWidget(self._wrap_pad(self.site_dashboard_page))
        self.main_stack.addWidget(self._wrap_pad(self.license_feature_manager_page))
        self.main_stack.addWidget(self.license_dashboard_page)  # index 14 - no padding needed

        # Custom handler for sidebar navigation with license checks
        self.sidebar.currentRowChanged.connect(self._handle_sidebar_navigation)
        
        # ── Collapsible log area ──────────────────────────────────────
        log_hdr = QHBoxLayout()
        log_hdr.setContentsMargins(0, 0, 0, 0)
        _log_lbl = QLabel("📋 Operation Log")
        _log_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")
        self._btn_toggle_log = QPushButton("▲ Hide")
        self._btn_toggle_log.setFixedHeight(20)
        self._btn_toggle_log.setStyleSheet(
            "QPushButton { background: transparent; color: #6B7280; "
            "border: none; font-size: 10px; padding: 0 4px; }"
            "QPushButton:hover { color: #9CA3AF; }")
        self._btn_toggle_log.clicked.connect(self._toggle_log)
        log_hdr.addWidget(_log_lbl)
        log_hdr.addStretch()
        log_hdr.addWidget(self._btn_toggle_log)
        outer.addLayout(log_hdr)

        self.progress = QTextEdit()
        self.progress.setReadOnly(True)
        self.progress.setPlaceholderText("Installation/Worker logs will appear here...")
        _log_h = 80 if self._small_screen else 100
        self.progress.setFixedHeight(_log_h)
        outer.addWidget(self.progress)
        # ─────────────────────────────────────────────────────────────

        # Connection hooks
        self.dashboard.btn_new.clicked.connect(lambda: self.sidebar.setCurrentRow(1))
        self.dashboard.btn_clone.clicked.connect(self.clone_selected)
        self.dashboard.full_deletion_requested.connect(self._do_full_delete)

        self.wizard.preflight_requested.connect(self.do_preflight)
        self.wizard.install_requested.connect(self.do_install)

        self._worker_thread: QThread | None = None

        # Apply license restrictions
        self._apply_license_restrictions()
        
        # Check if monthly verification is needed
        if self.license_manager.should_verify():
            self.license_manager.refresh_license()

        # Setup periodic license verification timer (every 30 seconds for testing)
        # TODO: Change to 5 * 60 * 1000 (5 minutes) for production
        self._license_check_timer = QTimer(self)
        self._license_check_timer.timeout.connect(self._periodic_license_check)
        self._license_check_timer.start(30 * 1000)  # 30 seconds for testing

        # Connect Signals for project selection Sync
        self.dashboard.project_selected.connect(self._sync_project_choice)

    def _db_params_with_creds(self, p: ProjectRecord, user: str, pwd: str) -> DBParams:
        return DBParams(
            host=p.db_host or "127.0.0.1",
            port=int(p.db_port or 3306),
            root_user=user,
            root_pass=pwd,
            db_name=p.db_name,
            create_user=False,
            user="",
            user_pass="",
            user_host="localhost",
            table_prefix=p.table_prefix or "wp_"
        )

    def _sync_project_choice(self, p: ProjectRecord | None):
        if p:
            # Update pages that depend on a selected project
            self.console.reload_projects()
            self.backup_page.reload_projects()
            self.db_page.reload_projects()
            self.url_page.reload_projects()
            self.security_page.reload_projects()
            self.site_dashboard_page.reload_projects()
    

    def _kill_web_server_processes(self) -> list[str]:
        """Kill Apache/PHP/Nginx processes that may lock project files. Returns list of killed process names."""
        import subprocess
        killed = []
        for exe in ("httpd.exe", "php-cgi.exe", "php.exe", "nginx.exe"):
            result = subprocess.run(
                ["taskkill", "/F", "/IM", exe],
                capture_output=True
            )
            if result.returncode == 0:
                killed.append(exe)
        return killed

    def _force_delete_folder(self, path: Path) -> None:
        """Delete a folder on Windows even if files are locked by another process."""
        import stat
        import time
        import subprocess

        def _on_error(func, fpath, exc_info):
            try:
                os.chmod(fpath, stat.S_IWRITE)
                func(fpath)
            except Exception:
                pass

        def _try_delete() -> bool:
            try:
                shutil.rmtree(str(path), onerror=_on_error)
            except Exception:
                pass
            if path.exists():
                subprocess.run(
                    ["cmd", "/c", "rd", "/s", "/q", str(path)],
                    capture_output=True, timeout=30
                )
            return not path.exists()

        # First attempt
        if _try_delete():
            return

        # Folder is still locked — ask user to kill web server processes
        ans = QMessageBox.question(
            self,
            "Files Locked by Web Server",
            "The project folder is locked by Apache/PHP (Laragon).\n\n"
            "Do you want to automatically stop Apache and PHP processes to complete the deletion?\n\n"
            "You can restart Laragon manually afterwards.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            raise OSError(
                f"Deletion cancelled. Stop Laragon services manually, then try again."
            )

        killed = self._kill_web_server_processes()
        self.log(f"Stopped processes: {', '.join(killed) if killed else 'none found'}")

        time.sleep(1)
        if _try_delete():
            return

        raise OSError(
            f"Could not delete '{path}' even after stopping web server processes.\n"
            "Please close any editors or file explorers that have this folder open, then try again."
        )

    def _do_full_delete(self, p: ProjectRecord):
        self.log(f"Starting full deletion for: {p.name}")
        self.set_status("Deleting...", "info")

        try:
            # 1. DB
            dlg = DbCredsDialog("DB Credentials (for deletion)", default_user="root")
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self.set_status("Ready", "ok")
                return
            user, pwd = dlg.creds()
            db = self._db_params_with_creds(p, user, pwd)
            drop_database(db, self.log)

            # 2. Files
            p_path = Path(p.path)
            if p_path.exists() and p_path.is_dir():
                self.log(f"Deleting folder: {p_path}")
                self._force_delete_folder(p_path)

            # 3. Store
            self.store.delete_by_path(p.path)

            self.log("Full deletion completed ✅")
            self.set_status("Ready", "ok")
            self.dashboard.reload()
            self.console.reload_projects()
            self.backup_page.reload_projects()
            self.db_page.reload_projects()
            self.url_page.reload_projects()
            self.security_page.reload_projects()
            self.manager_page.reload_projects()
            self.config_page.reload_projects()
            self.dev_tools_page.reload_projects()
            self.site_dashboard_page.reload_projects()

            QMessageBox.information(self, "Deleted", f"Project '{p.name}' and its database have been deleted.")

        except Exception as e:
            self.log(f"ERROR: {e}")
            self.set_status("Failed", "bad")
            QMessageBox.critical(self, "Deletion Failed", f"An error occurred during deletion:\n{e}")

    def _wrap_pad(self, w: QWidget) -> QWidget:
        c = QWidget()
        l = QVBoxLayout(c)
        pad = 12 if getattr(self, "_small_screen", False) else 18
        l.setContentsMargins(pad, pad, pad, pad)
        l.addWidget(w)
        return c

    def _toggle_log(self):
        """Show / hide the bottom log area."""
        visible = self.progress.isVisible()
        self.progress.setVisible(not visible)
        self._btn_toggle_log.setText("▼ Show" if visible else "▲ Hide")

    def log(self, s: str):
        self.progress.append(s)

    def set_status(self, text: str, kind: str = "neutral"):
        self.status_pill.setParent(None)
        self.status_pill = Pill(text, kind)
        # Put it back in header: easiest - set window title suffix as well
        self.setWindowTitle(f"WP Local Installer Pro — {text}")
    
    def show_toast(self, message: str, toast_type: str = "info", duration: int = 3000):
        """Show a non-blocking toast notification"""
        from app.ui.widgets import ToastNotification
        toast = ToastNotification(message, toast_type, self)
        toast.show_animated(duration)
    
    def _toggle_theme(self):
        """Toggle between dark and light theme"""
        if self.theme_manager:
            new_theme = self.theme_manager.toggle_theme()
            self._update_theme_button_icon()
            theme_name = "Light" if new_theme == "light" else "Dark"
            self.show_toast(f"Switched to {theme_name} theme", "info", duration=2000)
    
    def _update_theme_button_icon(self):
        """Update theme toggle button icon based on current theme"""
        if self.theme_manager:
            if self.theme_manager.current_theme == "dark":
                self.btn_theme_toggle.setText("☀️")  # Sun for light mode
            else:
                self.btn_theme_toggle.setText("🌙")  # Moon for dark mode

    def _update_license_button(self):
        """Update license button text based on current license status"""
        status = self.license_manager.get_status_display()
        self.btn_license.setText(f"{status['icon']} {status['tier']}")
    
    def _periodic_license_check(self):
        """
        Periodic check for license status changes (called every 5 minutes).
        Detects if license was deactivated from dashboard.
        """
        if not self.license_manager.license_info or not self.license_manager.license_info.license_key:
            # No license to check
            return
        
        # Try to verify license with server
        try:
            result = self.license_manager._verify_online(self.license_manager.license_info.license_key)
            
            if not result.get("success"):
                # License was deactivated or expired
                msg = result.get("message", "تم تعطيل الترخيص")
                
                # Deactivate locally
                self.license_manager.deactivate()
                
                # Update UI
                self._update_license_button()
                self._apply_license_restrictions()
                
                # Show notification
                QMessageBox.warning(
                    self,
                    "تنبيه الترخيص ⚠️",
                    f"تم اكتشاف تغيير في حالة الترخيص:\n\n{msg}\n\nتم تعطيل الميزات المتقدمة.",
                    QMessageBox.StandardButton.Ok
                )
                
                # Return to dashboard
                self.sidebar.blockSignals(True)
                self.sidebar.setCurrentRow(0)
                self.sidebar.blockSignals(False)
                self.main_stack.setCurrentIndex(0)
                
        except Exception as e:
            # Network error or server down - skip this check
            pass
    
    def _show_license_dialog(self):
        """Show license management dialog"""
        dlg = LicenseDialog(self.license_manager, self)
        dlg.license_changed.connect(self._on_license_changed)
        dlg.exec()
    
    def _on_license_changed(self):
        """Handle license status change"""
        self._update_license_button()
        self._apply_license_restrictions()
        self.show_toast("تم تحديث حالة الترخيص", "info")
    
    def _apply_license_restrictions(self):
        """Apply feature restrictions based on license tier"""
        # Map sidebar indices to feature keys
        feature_map = {
            0: "dashboard",          # 🏠 Dashboard
            1: "wizard",             # ✨ New Project
            2: "wpcli_console",      # 💻 WP-CLI Console
            3: "backup",             # 📦 Backups
            4: "database_viewer",    # 🗄️ Database
            5: "url_converter",      # 🔗 URL Converter
            6: "security",           # 🛡️ Security
            7: "monitoring",         # 🩺 Monitoring
            8: "manager",            # 🧩 Plugin & Theme Manager
            9: "config_editor",      # ⚙️ WP-Config Editor
            10: "devtools",          # 🛠️ Developer Tools
            11: "ai_assistant",      # 🤖 AI Assistant
            12: "site_dashboard",    # 🌐 Site Dashboard
            # index 13 (License Config) is never locked
            # index 14 (License Dashboard) is never locked
        }
        
        flags = self.license_manager.feature_flags
        
        for idx, feature_key in feature_map.items():
            item = self.sidebar.item(idx)
            if item:
                is_enabled = flags.is_enabled(feature_key)
                
                if is_enabled:
                    # Restore normal appearance
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    # Keep original text (remove lock if it was added)
                    original_text = item.text()
                    if " 🔒" in original_text:
                        item.setText(original_text.replace(" 🔒", ""))
                else:
                    # Disable and show lock icon
                    original_text = item.text()
                    if " 🔒" not in original_text:
                        item.setText(f"{original_text} 🔒")
                    # Keep selectable but show upgrade message on click
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable)
        
        # Connect to show upgrade message for locked features
        try:
            self.sidebar.itemClicked.disconnect(self._on_sidebar_item_clicked)
        except:
            pass
        self.sidebar.itemClicked.connect(self._on_sidebar_item_clicked)
    
    def _handle_sidebar_navigation(self, index: int):
        """Handle sidebar navigation with license verification."""
        # Map indices to features
        feature_map = {
            0: "dashboard",
            1: "wizard",
            2: "wpcli_console",
            3: "backup",
            4: "database_viewer",
            5: "url_converter",
            6: "security",
            7: "monitoring",
            8: "manager",
            9: "config_editor",
            10: "devtools",
            11: "ai_assistant",
            12: "site_dashboard",
            # 13 = License Config — always allowed, no feature gate
            # 14 = License Dashboard — always allowed, no feature gate
        }

        feature_key = feature_map.get(index)

        # Always allow dashboard, wizard, license config, and license dashboard
        if index in [0, 1, 13, 14]:
            self.main_stack.setCurrentIndex(index)
            return
        
        # Check license for other features
        if feature_key:
            is_enabled = self.license_manager.feature_flags.is_enabled(feature_key)
            
            if is_enabled:
                # Feature is enabled, allow navigation
                self.main_stack.setCurrentIndex(index)
            else:
                # Feature is locked, show upgrade message and return to previous page
                msg = self.license_manager.feature_flags.get_upgrade_message(feature_key)
                
                # Return to dashboard
                self.sidebar.blockSignals(True)
                self.sidebar.setCurrentRow(0)
                self.sidebar.blockSignals(False)
                self.main_stack.setCurrentIndex(0)
                
                reply = QMessageBox.question(
                    self,
                    "الترقية مطلوبة 🔒",
                    f"{msg}\n\nهل تريد فتح نافذة الترخيص للترقية؟",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    self._show_license_dialog()
        else:
            # Unknown index, allow navigation
            self.main_stack.setCurrentIndex(index)
    
    def _on_sidebar_item_clicked(self, item):
        """Handle sidebar item click, show upgrade message for locked features"""
        if " 🔒" in item.text():
            # Find the feature key for this item
            idx = self.sidebar.row(item)
            feature_map = {
                2: "wpcli_console",
                3: "backup",
                4: "database_viewer",
                5: "url_converter",
                6: "security",
                7: "monitoring",
                8: "manager",
                9: "config_editor",
                10: "devtools",
                11: "ai_assistant",
                12: "site_dashboard",
                # 13 never locked
            }
            feature_key = feature_map.get(idx)
            if feature_key:
                msg = self.license_manager.feature_flags.get_upgrade_message(feature_key)
                
                reply = QMessageBox.question(
                    self,
                    "الترقية مطلوبة 🔒",
                    f"{msg}\n\nهل تريد فتح نافذة الترخيص للترقية؟",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    self._show_license_dialog()

    def _show_about(self):
        """Show professional About dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("About Harmulizer Pro")
        dlg.setFixedSize(480, 420)
        dlg.setStyleSheet("""
            QDialog {
                background: #0F172A;
                border: 1px solid #1E293B;
            }
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header gradient
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4F46E5, stop:0.5 #7C3AED, stop:1 #6366F1);
                border: none;
            }
        """)
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(30, 30, 30, 25)
        h_lay.setSpacing(6)

        app_name = QLabel("Harmulizer Pro")
        app_name.setStyleSheet("color: white; font-size: 26px; font-weight: 900; background: transparent;")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.addWidget(app_name)

        version_lbl = QLabel("Version 1.0.0")
        version_lbl.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 13px; background: transparent;")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.addWidget(version_lbl)

        tagline = QLabel("WordPress Local Development Suite")
        tagline.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px; background: transparent;")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.addWidget(tagline)

        layout.addWidget(header)

        # Body
        body = QFrame()
        body.setStyleSheet("QFrame { background: #111827; border: none; }")
        b_lay = QVBoxLayout(body)
        b_lay.setContentsMargins(30, 24, 30, 20)
        b_lay.setSpacing(16)

        # Developer section
        dev_card = QFrame()
        dev_card.setStyleSheet("""
            QFrame {
                background: #1E293B;
                border: 1px solid #334155;
                border-radius: 10px;
            }
        """)
        dc_lay = QVBoxLayout(dev_card)
        dc_lay.setContentsMargins(20, 16, 20, 16)
        dc_lay.setSpacing(8)

        dev_title = QLabel("Developer")
        dev_title.setStyleSheet("color: #9CA3AF; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; background: transparent; border: none;")
        dc_lay.addWidget(dev_title)

        dev_name = QLabel("Saeed Mahmoud")
        dev_name.setStyleSheet("color: #F9FAFB; font-size: 20px; font-weight: 800; background: transparent; border: none;")
        dc_lay.addWidget(dev_name)

        dev_role = QLabel("Software Engineer")
        dev_role.setStyleSheet("color: #A5B4FC; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        dc_lay.addWidget(dev_role)

        b_lay.addWidget(dev_card)

        # Tech info
        tech_card = QFrame()
        tech_card.setStyleSheet("""
            QFrame {
                background: #1E293B;
                border: 1px solid #334155;
                border-radius: 10px;
            }
        """)
        tc_lay = QVBoxLayout(tech_card)
        tc_lay.setContentsMargins(20, 14, 20, 14)
        tc_lay.setSpacing(6)

        tech_title = QLabel("Built With")
        tech_title.setStyleSheet("color: #9CA3AF; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; background: transparent; border: none;")
        tc_lay.addWidget(tech_title)

        tech_info = QLabel("Python  |  PyQt6  |  MySQL  |  Gemini AI")
        tech_info.setStyleSheet("color: #D1D5DB; font-size: 12px; background: transparent; border: none;")
        tc_lay.addWidget(tech_info)

        b_lay.addWidget(tech_card)

        layout.addWidget(body, 1)

        # Footer
        footer = QFrame()
        footer.setStyleSheet("QFrame { background: #0F172A; border-top: 1px solid #1E293B; }")
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(20, 12, 20, 12)

        copy_lbl = QLabel("\u00a9 2025 Saeed Mahmoud. All rights reserved.")
        copy_lbl.setStyleSheet("color: #6B7280; font-size: 11px; background: transparent;")
        f_lay.addWidget(copy_lbl)
        f_lay.addStretch()

        btn_ok = QPushButton("OK")
        btn_ok.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #6366F1, stop:1 #4F46E5);
                border: 1px solid #4F46E5; border-radius: 6px;
                padding: 6px 28px; color: white; font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #818CF8, stop:1 #6366F1);
            }
        """)
        btn_ok.clicked.connect(dlg.accept)
        f_lay.addWidget(btn_ok)

        layout.addWidget(footer)

        dlg.exec()

    def do_preflight(self, wp: WPParams, db: DBParams):
        self.progress.clear()
        checks = preflight_checks(wp, db)
        ok_all = all(c[0] for c in checks)
        for ok, msg in checks:
            self.log(("✅ " if ok else "❌ ") + msg)
        self.wizard.preflight_box.setPlainText("\n".join([("OK " if ok else "FAIL ") + msg for ok, msg in checks]))
        QMessageBox.information(self, "Preflight", "All good ✅" if ok_all else "Some checks failed ❌ (see list)")

    def do_install(self, wp: WPParams, db: DBParams):
        self.progress.clear()

        # keep params for saving project metadata
        self._pending_wp = wp
        self._pending_db = db

        # basic validation
        if not wp.project_name or not str(wp.doc_root).strip():
            QMessageBox.warning(self, "Missing", "Project name and document root are required.")
            return
        if not db.db_name:
            QMessageBox.warning(self, "Missing", "DB name is required.")
            return

        # run worker
        self.set_status("Installing...", "info")
        self.sidebar.setCurrentRow(0)  # show dashboard to see logs or stay in wizard? 
        # User requested to see creation phases, so we keep logs visible.

        self._worker_thread = QThread()
        self.worker = InstallWorker(wp, db)
        self.worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log)
        self.worker.progress.connect(lambda p: self.log(f"[{p}%]"))
        self.worker.done.connect(self._install_done)

        self.worker.done.connect(self._worker_thread.quit)
        self.worker.done.connect(self.worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        self._worker_thread.start()

    def _install_done(self, ok: bool, res: dict, msg: str):
        if ok:
            self.set_status("Ready", "ok")
            self.log(msg)

            now = datetime.datetime.utcnow().isoformat() + "Z"
            # Save project record
            url = res.get("url") or ""
            admin_url = res.get("admin_url") or (url.rstrip("/") + "/wp-admin/")
            proj_path = res.get("project_path") or ""

            # Attempt to read from last wizard params? We store minimal here.
            # Note: db user might be a dedicated user; we store root_user only as "db_user" field for convenience.
            # It's fine for local dev product; you can extend record schema if needed.
            # We'll parse from logs isn't safe.
            # Instead: ask the wizard for current values by switching to it:
            # We'll keep it simple: store what we can.

            # Best effort: these fields are not available from res: keep blanks.
            wp = getattr(self, "_pending_wp", None)
            db = getattr(self, "_pending_db", None)

            rec = ProjectRecord(
                name=(wp.project_name if wp else (Path(proj_path).name or "wp")),
                path=proj_path,
                url=url,
                admin_url=admin_url,
                stack=(wp.stack_name if wp else ""),
                doc_root=(str(wp.doc_root) if wp else ""),
                laragon_root=(getattr(wp, "laragon_root", "") if wp else ""),
                db_host=(db.host if db else ""),
                db_port=(db.port if db else 3306),
                db_name=(db.db_name if db else ""),
                db_user=((db.user if db and db.create_user else (db.root_user if db else ""))),
                table_prefix=(db.table_prefix if db else "wp_"),
                php_path=(res.get("php_path") or ""),
                wpcli_path=(res.get("wpcli_path") or ""),
                wpcli_is_phar=bool(res.get("wpcli_is_phar")),
                created_at_iso=now,
                last_action_iso=now,
                notes=""
            )

            # Write per-project meta file (no passwords)
            try:
                meta = {
                    "name": rec.name,
                    "path": rec.path,
                    "url": rec.url,
                    "admin_url": rec.admin_url,
                    "stack": rec.stack,
                    "doc_root": rec.doc_root,
                    "laragon_root": rec.laragon_root,
                    "db": {
                        "host": rec.db_host,
                        "port": rec.db_port,
                        "name": rec.db_name,
                        "user": rec.db_user,
                        "table_prefix": rec.table_prefix,
                    },
                    "tooling": {
                        "php_path": rec.php_path,
                        "wpcli_path": rec.wpcli_path,
                        "wpcli_is_phar": rec.wpcli_is_phar,
                    },
                    "created_at": rec.created_at_iso
                }
                write_project_meta(Path(rec.path), meta, log=self.log)
            except Exception as e:
                self.log(f"Meta write failed: {e}")
            self.store.upsert(rec)
            self.url_page.reload_projects()
            self.manager_page.reload_projects()
            self.config_page.reload_projects()
            self.dev_tools_page.reload_projects()

            # offer open
            r = QMessageBox.question(self, "Done", "Open site now?")
            if r == QMessageBox.StandardButton.Yes and url:
                import webbrowser
                webbrowser.open(url)
        else:
            self.set_status("Failed", "bad")
            self.log("ERROR: " + msg)
            QMessageBox.critical(self, "Failed", msg)


    def _run_backup_worker(self, project_path: str, db: DBParams, out_dir: str):
        self.progress.clear()
        self.set_status("Backing up...", "info")
        self._worker_thread = QThread()
        self.bw = BackupWorker(project_path, db, out_dir, True, True)
        self.bw.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self.bw.run)
        self.bw.log.connect(self.log)
        self.bw.progress.connect(lambda p: self.log(f"[{p}%]"))
        self.bw.done.connect(self._backup_done)
        self.bw.done.connect(self._worker_thread.quit)
        self.bw.done.connect(self.bw.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _backup_done(self, ok: bool, msg: str, bdir: str):
        if ok:
            self.set_status("Ready", "ok")
            self.log(msg)
            QMessageBox.information(self, "Backup", f"Backup created:\n{bdir}")
        else:
            self.set_status("Failed", "bad")
            self.log("ERROR: " + msg)
            QMessageBox.critical(self, "Backup Failed", msg)

    def _run_restore_worker(self, project_path: str, db: DBParams, backup_dir: str):
        self.progress.clear()
        self.set_status("Restoring...", "info")
        self._worker_thread = QThread()
        self.rw = RestoreWorker(project_path, db, backup_dir, True, True)
        self.rw.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self.rw.run)
        self.rw.log.connect(self.log)
        self.rw.progress.connect(lambda p: self.log(f"[{p}%]"))
        self.rw.done.connect(self._restore_done)
        self.rw.done.connect(self._worker_thread.quit)
        self.rw.done.connect(self.rw.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _restore_done(self, ok: bool, msg: str):
        if ok:
            self.set_status("Ready", "ok")
            self.log(msg)
            QMessageBox.information(self, "Restore", "Restore completed ✅")
        else:
            self.set_status("Failed", "bad")
            self.log("ERROR: " + msg)
            QMessageBox.critical(self, "Restore Failed", msg)

    def _run_url_worker(self, project_record, db: DBParams, old_url: str, new_url: str, include_guid: bool, rename_folder: bool = False):
        self.progress.clear()
        self.set_status("Converting URLs...", "info")

        from app.core.wp_ops import get_effective_tooling
        php, wpcli, is_phar = get_effective_tooling(project_record, log=self.log)

        self._worker_thread = QThread()
        self.uw = UrlConvertWorker(project_record.path, db, old_url, new_url, php, wpcli, is_phar, include_guid, rename_folder)
        self.uw.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self.uw.run)
        self.uw.log.connect(self.log)
        self.uw.progress.connect(lambda p: self.log(f"[{p}%]"))
        self.uw.done.connect(lambda ok, m, new_path: self._url_done(ok, m, project_record, new_url, new_path))
        self.uw.done.connect(self._worker_thread.quit)
        self.uw.done.connect(self.uw.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _url_done(self, success, msg, project_record: ProjectRecord, new_url: str, new_path: str):
        if success:
            self.set_status("Done", "success")
            self.log(msg)
            
            # update record
            now = datetime.datetime.utcnow().isoformat() + "Z"
            project_record.url = new_url
            project_record.admin_url = new_url.rstrip("/") + "/wp-admin/"
            project_record.last_action_iso = now
            
            if new_path and str(new_path) != str(project_record.path):
                old_path = str(project_record.path)
                project_record.path = str(new_path)
                self.log(f"Project path updated to: {new_path}")
                # Remove old record to prevent duplicates
                self.store.delete_by_path(old_path)
            
            self.store.upsert(project_record)
            self.dashboard.reload()
            self.url_page.reload_projects() # Refresh this page specifically to update path in UI
            QMessageBox.information(self, "Success", msg)
        else:
            self.set_status("Failed", "error")
            self.log(f"Error: {msg}")
            QMessageBox.critical(self, "URL Convert Failed", msg)

    


    def clone_selected(self):
        cur = self.dashboard.current
        if not cur:
            QMessageBox.information(self, "Clone", "Select a project first.")
            return

        dlg = TextInputDialog("Clone Project", [
            ("name", "New project folder name"),
            ("url", "New site URL"),
            ("db", "New DB name"),
        ])
        dlg.edits["name"].setText(cur.name + "-clone")
        dlg.edits["url"].setText(cur.url.rstrip("/") + "-clone")
        dlg.edits["db"].setText((cur.db_name or cur.name) + "_clone")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()

        dst_path = str((Path(cur.path).parent / vals["name"]).resolve())

        # We cannot fully reconstruct DB params from record if fields were blank.
        # For now, we do best-effort using localhost defaults.
        src_db = DBParams(
            host=cur.db_host or "127.0.0.1",
            port=cur.db_port or 3306,
            root_user="root",
            root_pass="",
            db_name=cur.db_name or vals["db"],
            create_user=False,
            user="",
            user_pass="",
            user_host="localhost",
            table_prefix=cur.table_prefix or "wp_",
        )
        dst_db = DBParams(
            host=src_db.host,
            port=src_db.port,
            root_user=src_db.root_user,
            root_pass=src_db.root_pass,
            db_name=vals["db"],
            create_user=False,
            user="",
            user_pass="",
            user_host="localhost",
            table_prefix=src_db.table_prefix,
        )

        from app.core.wp_ops import get_effective_tooling
        php, wpcli, is_phar = get_effective_tooling(cur)

        params = {
            "src_path": cur.path,
            "dst_path": dst_path,
            "src_db": src_db,
            "dst_db": dst_db,
            "old_url": cur.url,
            "new_url": vals["url"],
            "php_path": php,
            "wpcli_path": wpcli,
            "wpcli_is_phar": is_phar,
        }

        self.progress.clear()
        self.set_status("Cloning...", "info")

        self._worker_thread = QThread()
        self.clone_worker = CloneWorker(params)
        self.clone_worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self.clone_worker.run)
        self.clone_worker.log.connect(self.log)
        self.clone_worker.progress.connect(lambda p: self.log(f"[{p}%]"))
        self.clone_worker.done.connect(self._clone_done)

        self.clone_worker.done.connect(self._worker_thread.quit)
        self.clone_worker.done.connect(self.clone_worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        self._worker_thread.start()

    def _clone_done(self, ok: bool, msg: str):
        if ok:
            self.set_status("Ready", "ok")
            self.log(msg)
            QMessageBox.information(self, "Clone", "Clone done ✅\n(If URL changes didn't fully apply, enable WP-CLI for perfect search-replace.)")
        else:
            self.set_status("Failed", "bad")
            self.log("ERROR: " + msg)
            QMessageBox.critical(self, "Clone Failed", msg)

    def _run_scan_worker(self, project_path: str):
        self.progress.clear()
        self.set_status("Scanning...", "info")
        self._worker_thread = QThread()
        self.scan_worker = ScanWorker(project_path)
        self.scan_worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self.scan_worker.run)
        self.scan_worker.log.connect(self.log)
        self.scan_worker.progress.connect(lambda p: self.log(f"[{p}%]"))
        self.scan_worker.done.connect(self._scan_done)
        self.scan_worker.done.connect(self._worker_thread.quit)
        self.scan_worker.done.connect(self.scan_worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _scan_done(self, ok: bool, results: list, msg: str):
        self.set_status("Ready", "ok")
        if ok:
            self.log(msg)
            self.security_page.on_scan_finished(results)
        else:
            self.log("ERROR: " + msg)
            QMessageBox.critical(self, "Scan Failed", msg)