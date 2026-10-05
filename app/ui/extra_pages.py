from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QUrl, QThread
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog,
    QProgressBar, QLineEdit, QCheckBox, QTextEdit, QDialog, QFormLayout,
    QDialogButtonBox, QSpinBox, QTabWidget, QGridLayout
)

from app.core.projects_store import ProjectsStore, ProjectRecord
from app.core.wp_ops import (
    DBParams, test_mysql, mysql_connect
)
from app.core.workers import (
    BackupWorker, RestoreWorker, UrlConvertWorker
)
from app.ui.widgets import make_card, Pill, PrimaryButton, row_buttons
from app.core.i18n import t as tr

# ----------------- Settings Dialog -----------------
class ProjectSettingsDialog(QDialog):
    def __init__(self, p: ProjectRecord, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('الإعدادات: ')}{p.name}")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # Project Path
        self.project_path = QLineEdit(p.path)
        
        # Database Settings
        self.host = QLineEdit(p.db_host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(p.db_port)
        self.user = QLineEdit(p.db_user)
        self.password = QLineEdit(str(getattr(p, 'db_pass', '') or ""))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.db_name = QLineEdit(p.db_name)
        self.table_prefix = QLineEdit(p.table_prefix)
        
        form.addRow(tr("مسار المشروع:"), self.project_path)
        form.addRow("---", QLabel(tr("اتصال قاعدة البيانات:")))
        form.addRow(tr("مضيف قاعدة البيانات:"), self.host)
        form.addRow(tr("منفذ قاعدة البيانات:"), self.port)
        form.addRow(tr("مستخدم قاعدة البيانات:"), self.user)
        form.addRow(tr("كلمة مرور قاعدة البيانات:"), self.password)
        form.addRow(tr("اسم قاعدة البيانات:"), self.db_name)
        form.addRow(tr("بادئة الجداول:"), self.table_prefix)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
    def get_data(self):
        return {
            "path": self.project_path.text().strip(),
            "db_host": self.host.text().strip(),
            "db_port": self.port.value(),
            "db_user": self.user.text().strip(),
            "db_pass": self.password.text(),
            "db_name": self.db_name.text().strip(),
            "table_prefix": self.table_prefix.text().strip(),
        }


# ----------------- Table Data Viewer Dialog -----------------
class TableDataDialog(QDialog):
    def __init__(self, table_name: str, db_params, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('بيانات الجدول: ')}{table_name}")
        self.setMinimumSize(800, 600)
        
        self.table_name = table_name
        self.db_params = db_params
        
        layout = QVBoxLayout(self)
        
        # Info label
        info = QLabel(f"{tr('عرض البيانات من الجدول: ')}{table_name}")
        info.setStyleSheet("font-weight: bold;")
        layout.addWidget(info)

        # Data table
        self.data_table = QTableWidget()
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self.data_table)

        # Close button
        btn_close = QPushButton(tr("إغلاق"))
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)
        
        # Load data
        self._load_data()
    
    def _load_data(self):
        try:
            conn = mysql_connect(self.db_params.host, self.db_params.port, 
                               self.db_params.user, self.db_params.user_pass)
            with conn.cursor() as cur:
                cur.execute(f"USE `{self.db_params.db_name}`")
                cur.execute(f"SELECT * FROM `{self.table_name}` LIMIT 100")
                rows = cur.fetchall()
                
                if rows:
                    # Get column names
                    cur.execute(f"DESCRIBE `{self.table_name}`")
                    columns = [col[0] for col in cur.fetchall()]
                    
                    # Setup table
                    self.data_table.setColumnCount(len(columns))
                    self.data_table.setHorizontalHeaderLabels(columns)
                    self.data_table.setRowCount(len(rows))
                    
                    # Fill data
                    for i, row in enumerate(rows):
                        for j, val in enumerate(row):
                            item = QTableWidgetItem(str(val) if val is not None else "NULL")
                            self.data_table.setItem(i, j, item)
                    
                    self.data_table.resizeColumnsToContents()
                else:
                    self.data_table.setColumnCount(1)
                    self.data_table.setHorizontalHeaderLabels([tr("رسالة")])
                    self.data_table.setRowCount(1)
                    self.data_table.setItem(0, 0, QTableWidgetItem(tr("الجدول فارغ")))

            conn.close()
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), f"فشل تحميل بيانات الجدول:\n{e}")


# ----------------- Base Page -----------------
class BaseExtraPage(QWidget):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__()
        self.store = store
        self.parent_window = parent_window
        self.current: ProjectRecord | None = None
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(12)

        # Common Project Selector
        top_card, top_lay = make_card(tr("اختر مشروعًا"), "")

        sel_row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_combo_change)
        sel_row.addWidget(self.combo, 1)

        self.btn_settings = QPushButton(tr("⚙ الإعدادات"))
        self.btn_settings.setFixedWidth(100)
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_settings.setEnabled(False)
        sel_row.addWidget(self.btn_settings)
        
        top_lay.addLayout(sel_row)
        self.main_layout.addWidget(top_card)

        self.content_area = QVBoxLayout()
        self.main_layout.addLayout(self.content_area)
        self.main_layout.addStretch(1)

    def showEvent(self, event):
        self.reload_projects()
        super().showEvent(event)

    def reload_projects(self):
        self.combo.blockSignals(True)
        curr_path = self.current.path if self.current else None
        self.combo.clear()
        self.combo.addItem(tr("اختر مشروعًا..."), None)
        
        index_to_set = 0
        projects = self.store.list_projects()
        for i, p in enumerate(projects):
            self.combo.addItem(f"{p.name} ({p.url})", p)
            if curr_path and p.path == curr_path:
                index_to_set = i + 1
                self.current = p # Update ref to fresh object
                
        self.combo.setCurrentIndex(index_to_set)
        self.combo.blockSignals(False)
        
        self.btn_settings.setEnabled(self.current is not None)
        
        if self.current:
            self._on_project_selected(self.current)
        else:
            self._on_project_cleared()

    def _on_combo_change(self):
        data = self.combo.currentData()
        if data:
            self.current = data
            self.btn_settings.setEnabled(True)
            self._on_project_selected(data)
        else:
            self.current = None
            self.btn_settings.setEnabled(False)
            self._on_project_cleared()

    def _on_project_selected(self, p: ProjectRecord):
        pass

    def _get_db_params(self, p: ProjectRecord) -> DBParams:
        # Safe access to db_pass (may not exist in old projects)
        db_pass = getattr(p, 'db_pass', '')
        
        return DBParams(
            host=p.db_host,
            port=p.db_port,
            root_user=p.db_user,
            root_pass=db_pass,
            db_name=p.db_name,
            create_user=False,
            user=p.db_user,
            user_pass=db_pass,
            user_host="localhost",
            table_prefix=p.table_prefix
        )

    def _open_settings(self):
        try:
            if not self.current: return
            dlg = ProjectSettingsDialog(self.current, self)
            if dlg.exec():
                data = dlg.get_data()
                # Update record
                self.current.path = data["path"]  # Update path
                self.current.db_host = data["db_host"]
                self.current.db_port = data["db_port"]
                self.current.db_user = data["db_user"]
                self.current.db_pass = data["db_pass"]
                self.current.db_name = data["db_name"]
                self.current.table_prefix = data["table_prefix"]
                self.store.upsert(self.current)
                self.reload_projects() # Refresh UI
                QMessageBox.information(self, tr("تم الحفظ"), tr("تم تحديث الإعدادات."))
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), f"تعذر فتح الإعدادات:\n{e}")

    def _on_project_cleared(self):
        pass


# ----------------- Backup Page -----------------
class BackupPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card(tr("النسخ الاحتياطي"), tr("إدارة النسخ الاحتياطية لهذا المشروع"))

        # Controls
        row = QHBoxLayout()
        self.btn_backup_files = QPushButton(tr("نسخ الملفات فقط احتياطيًا"))
        self.btn_backup_db = QPushButton(tr("نسخ قاعدة البيانات فقط احتياطيًا"))
        self.btn_backup_full = PrimaryButton(tr("نسخة احتياطية كاملة"))
        row.addWidget(self.btn_backup_files)
        row.addWidget(self.btn_backup_db)
        row.addWidget(self.btn_backup_full)
        lay.addLayout(row)

        # Open Folder
        self.btn_open_folder = QPushButton(tr("📂 فتح مجلد النسخ الاحتياطي"))
        self.btn_open_folder.clicked.connect(self._open_backup_folder)
        row.addWidget(self.btn_open_folder)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        # Status Label
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        lay.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([tr("التاريخ"), tr("المحتوى"), tr("المسار")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table)

        # Restore/Delete buttons
        act_row = QHBoxLayout()
        self.btn_restore = QPushButton(tr("استعادة المحدد"))
        self.btn_delete = QPushButton(tr("حذف المحدد"))
        act_row.addWidget(self.btn_restore)
        act_row.addWidget(self.btn_delete)
        act_row.addStretch(1)
        lay.addLayout(act_row)

        self.content_area.addWidget(card)

        # Schedules Card
        sched_card, s_lay = make_card(tr("📅 النسخ الاحتياطي المجدول"), tr("نسخ احتياطي تلقائي"))

        self.schedule_table = QTableWidget()
        self.schedule_table.setColumnCount(4)
        self.schedule_table.setHorizontalHeaderLabels([tr("التكرار"), tr("الوقت/الأيام"), tr("المحتوى"), tr("تاريخ الإنشاء")])
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        s_lay.addWidget(self.schedule_table)

        sched_btn_row = QHBoxLayout()
        self.btn_add_schedule = QPushButton(tr("➕ إضافة جدولة"))
        self.btn_delete_schedule = QPushButton(tr("🗑️ حذف الجدولة"))
        self.btn_add_schedule.clicked.connect(self._add_schedule)
        self.btn_delete_schedule.clicked.connect(self._delete_schedule)
        sched_btn_row.addWidget(self.btn_add_schedule)
        sched_btn_row.addWidget(self.btn_delete_schedule)
        sched_btn_row.addStretch(1)
        s_lay.addLayout(sched_btn_row)
        
        self.content_area.addWidget(sched_card)
        self.content_area.addWidget(sched_card)

        # Workers
        self.worker = None
        self.thread = None

        # Connects
        self.btn_backup_files.clicked.connect(lambda: self._start_backup(files=True, db=False))
        self.btn_backup_db.clicked.connect(lambda: self._start_backup(files=False, db=True))
        self.btn_backup_full.clicked.connect(lambda: self._start_backup(files=True, db=True))
        self.btn_restore.clicked.connect(self._restore_backup)
        self.btn_delete.clicked.connect(self._delete_backup)
        
        # Initialize scheduler
        from app.core.scheduler import BackupScheduler
        self.scheduler = BackupScheduler()
        
        # Initial State
        self._set_enabled(False)

    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self._refresh_list()
        self._refresh_schedules()

    def _on_project_cleared(self):
        self._set_enabled(False)
        self.table.setRowCount(0)

    def _set_enabled(self, val: bool):
        self.btn_backup_files.setEnabled(val)
        self.btn_backup_db.setEnabled(val)
        self.btn_backup_full.setEnabled(val)
        self.btn_restore.setEnabled(val)
        self.btn_delete.setEnabled(val)
        self.btn_add_schedule.setEnabled(val)
        self.btn_delete_schedule.setEnabled(val)

    def _refresh_list(self):
        if not self.current: return
        self.table.setRowCount(0)
        
        # Scan backup dir
        root = Path("backups")
        if not root.exists(): 
            return
        
        backups = []
        # Find all backup directories
        for backup_dir in root.iterdir():
            if not backup_dir.is_dir():
                continue
            
            manifest_file = backup_dir / "manifest.json"
            if not manifest_file.exists():
                continue
            
            try:
                import json
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                
                # Filter by project path
                if manifest.get("project_path") == self.current.path:
                    backups.append({
                        "date": manifest.get("timestamp", tr("غير معروف")),
                        "has_files": manifest.get("has_files", False),
                        "has_db": manifest.get("has_db", False),
                        "path": str(backup_dir)
                    })
            except Exception:
                continue
        
        # Sort by date (newest first)
        backups.sort(key=lambda x: x["date"], reverse=True)
        
        # Populate table
        for backup in backups:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Date
            self.table.setItem(row, 0, QTableWidgetItem(backup["date"]))
            
            # Contents
            contents = []
            if backup["has_files"]: contents.append(tr("ملفات"))
            if backup["has_db"]: contents.append(tr("قاعدة بيانات"))
            self.table.setItem(row, 1, QTableWidgetItem(" + ".join(contents)))
            
            # Path
            self.table.setItem(row, 2, QTableWidgetItem(backup["path"]))

    def _open_backup_folder(self):
        if not self.current: return
        backup_root = Path("backups")
        if not backup_root.exists():
            backup_root.mkdir(parents=True)
        
        from app.core.utils import open_path
        open_path(backup_root)

    def _start_backup(self, files: bool, db: bool):
        if not self.current: return
        
        # Validate project path
        project_path = Path(self.current.path)
        if not project_path.exists():
            QMessageBox.critical(
                self,
                tr("خطأ في المسار"),
                f"مسار المشروع غير موجود:\n{self.current.path}\n\n"
                f"يرجى تحديث المسار من الإعدادات (زر ⚙)."
            )
            return

        if not project_path.is_dir():
            QMessageBox.critical(
                self,
                tr("خطأ في المسار"),
                f"مسار المشروع ليس مجلدًا:\n{self.current.path}"
            )
            return

        # Count files if backing up files
        if files:
            file_count = sum(1 for _ in project_path.rglob('*') if _.is_file())
            if file_count == 0:
                result = QMessageBox.question(
                    self,
                    tr("مجلد فارغ"),
                    f"يبدو أن مجلد المشروع فارغ (0 ملفات).\n\n"
                    f"المسار: {self.current.path}\n\n"
                    f"هل تريد المتابعة على أي حال؟",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if result == QMessageBox.StandardButton.No:
                    return
        
        db_params = self._get_db_params(self.current)
        
        # Disable buttons during backup
        self._set_enabled(False)
        self.btn_open_folder.setEnabled(False)
        
        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setVisible(True)
        self.status_label.setText(f"{tr('جارٍ تحضير النسخة الاحتياطية من: ')}{self.current.path}")
        
        # Create worker and thread
        self.worker = BackupWorker(
            str(project_path), db_params, "backups", files, db
        )
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._on_backup_log)
        self.worker.progress.connect(self._on_backup_progress)
        self.worker.done.connect(self._on_backup_done)
        
        # Start thread
        self.thread.start()
    
    def _on_backup_log(self, msg: str):
        self.status_label.setText(msg)
    
    def _on_backup_progress(self, val: int):
        self.progress_bar.setValue(val)
    
    def _on_backup_done(self, success: bool, message: str, backup_dir: str):
        # Stop thread
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
        
        # Hide progress
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        
        # Re-enable buttons
        self._set_enabled(True)
        self.btn_open_folder.setEnabled(True)
        
        # Show result
        if success:
            QMessageBox.information(self, tr("تم بنجاح"), f"{message}\n\nتم حفظ النسخة الاحتياطية في:\n{backup_dir}")
            self._refresh_list()
        else:
            QMessageBox.critical(self, tr("خطأ"), f"فشل النسخ الاحتياطي:\n{message}")

    def _open_backup_folder(self):
        root = Path("backups").resolve()
        root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))

    def _restore_backup(self):
        if not self.current: return
        
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.information(self, tr("لا يوجد تحديد"), tr("يرجى اختيار نسخة احتياطية للاستعادة."))
            return

        backup_path = self.table.item(selected, 2).text()
        backup_date = self.table.item(selected, 0).text()

        r = QMessageBox.question(
            self,
            tr("تأكيد الاستعادة"),
            f"سيتم استعادة النسخة الاحتياطية من:\n{backup_date}\n\n"
            f"تحذير: سيؤدي هذا إلى استبدال الملفات الحالية!\n\n"
            f"هل تريد المتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        self.parent_window._run_restore_worker(
            self.current.path,
            self._get_db_params(self.current),
            backup_path
        )

    def _delete_backup(self):
        if not self.current: return
        
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.information(self, tr("لا يوجد تحديد"), tr("يرجى اختيار نسخة احتياطية للحذف."))
            return

        backup_path = self.table.item(selected, 2).text()
        backup_date = self.table.item(selected, 0).text()

        r = QMessageBox.question(
            self,
            tr("تأكيد الحذف"),
            f"{tr('هل تريد حذف النسخة الاحتياطية من ')}{backup_date}؟\n\n"
            f"لا يمكن التراجع عن هذا الإجراء!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        try:
            import shutil
            shutil.rmtree(backup_path)
            QMessageBox.information(self, tr("تم الحذف"), tr("تم حذف النسخة الاحتياطية بنجاح."))
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), f"فشل حذف النسخة الاحتياطية:\n{e}")

    def _refresh_schedules(self):
        """Refresh the schedules table"""
        if not self.current: return
        self.schedule_table.setRowCount(0)
        
        schedules = self.scheduler.get_schedules()
        # Filter by project path
        project_schedules = {k: v for k, v in schedules.items() if v.get("project_path") == self.current.path}
        
        for sched_id, sched in project_schedules.items():
            row = self.schedule_table.rowCount()
            self.schedule_table.insertRow(row)
            
            freq_raw = sched.get("frequency", "")
            freq_labels = {"hourly": tr("كل ساعة"), "daily": tr("يوميًا"), "weekly": tr("أسبوعيًا")}
            freq = freq_labels.get(freq_raw, freq_raw or tr("غير متوفر"))
            time_spec = sched.get("time_spec", tr("غير متوفر"))
            content = []
            if sched.get("backup_files"): content.append(tr("ملفات"))
            if sched.get("backup_db"): content.append(tr("قاعدة بيانات"))
            created = sched.get("created_at", tr("غير متوفر"))[:10]

            self.schedule_table.setItem(row, 0, QTableWidgetItem(freq))
            self.schedule_table.setItem(row, 1, QTableWidgetItem(time_spec))
            self.schedule_table.setItem(row, 2, QTableWidgetItem(" + ".join(content)))
            self.schedule_table.setItem(row, 3, QTableWidgetItem(created))
            # Store ID in hidden column
            self.schedule_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, sched_id)

    def _add_schedule(self):
        """Add a new backup schedule"""
        if not self.current: return
        
        from PyQt6.QtWidgets import QComboBox, QTimeEdit, QCheckBox
        from PyQt6.QtCore import QTime
        
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("إضافة جدولة نسخ احتياطي"))
        dlg.setMinimumWidth(400)

        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        freq_combo = QComboBox()
        # Display text is Arabic; underlying value (used by scheduler logic) stays English.
        freq_combo.addItem(tr("كل ساعة"), "hourly")
        freq_combo.addItem(tr("يوميًا"), "daily")
        freq_combo.addItem(tr("أسبوعيًا"), "weekly")
        form.addRow(tr("التكرار:"), freq_combo)

        time_edit = QTimeEdit()
        time_edit.setTime(QTime(0, 0))
        form.addRow(tr("الوقت (لليومي):"), time_edit)

        days_edit = QLineEdit()
        days_edit.setPlaceholderText(tr("مثال: mon,wed,fri (للأسبوعي)"))
        form.addRow(tr("الأيام (للأسبوعي):"), days_edit)

        files_chk = QCheckBox(tr("نسخ الملفات احتياطيًا"))
        files_chk.setChecked(True)
        form.addRow(files_chk)

        db_chk = QCheckBox(tr("نسخ قاعدة البيانات احتياطيًا"))
        db_chk.setChecked(True)
        form.addRow(db_chk)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            freq = freq_combo.currentData()
            time_val = time_edit.time().toString("HH:mm")
            days_val = days_edit.text().strip()
            
            if freq == "hourly":
                time_spec = ""
            elif freq == "daily":
                time_spec = time_val
            elif freq == "weekly":
                time_spec = days_val if days_val else "mon"
            
            import uuid
            schedule_id = f"backup_{uuid.uuid4().hex[:8]}"
            
            try:
                self.scheduler.add_schedule(
                    schedule_id=schedule_id,
                    project_path=self.current.path,
                    project_name=self.current.name,
                    frequency=freq,
                    time_spec=time_spec,
                    backup_files=files_chk.isChecked(),
                    backup_db=db_chk.isChecked(),
                    callback=self._scheduled_backup_callback
                )
                freq_labels = {"hourly": tr("كل ساعة"), "daily": tr("يوميًا"), "weekly": tr("أسبوعيًا")}
                QMessageBox.information(self, tr("تم بنجاح"), f"{tr('تمت إضافة الجدولة: ')}{freq_labels.get(freq, freq)}")
                self._refresh_schedules()
            except Exception as e:
                QMessageBox.critical(self, tr("خطأ"), f"فشل إضافة الجدولة:\n{e}")

    def _delete_schedule(self):
        """Delete selected schedule"""
        selected = self.schedule_table.currentRow()
        if selected < 0:
            QMessageBox.information(self, tr("لا يوجد تحديد"), tr("يرجى اختيار جدولة للحذف."))
            return

        sched_id = self.schedule_table.item(selected, 0).data(Qt.ItemDataRole.UserRole)

        r = QMessageBox.question(
            self,
            tr("تأكيد الحذف"),
            f"هل تريد حذف هذه الجدولة؟\n\nلا يمكن التراجع عن هذا الإجراء!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        try:
            self.scheduler.remove_schedule(sched_id)
            QMessageBox.information(self, tr("تم الحذف"), tr("تم حذف الجدولة بنجاح."))
            self._refresh_schedules()
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), f"فشل حذف الجدولة:\n{e}")

    def _scheduled_backup_callback(self, project_path: str, backup_files: bool, backup_db: bool):
        """Callback executed by scheduler (usually in bg thread)"""
        print(f"Scheduled backup triggered for {project_path}")
        if not self.current: return
        
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.information(self, tr("لا يوجد تحديد"), tr("يرجى اختيار نسخة احتياطية للحذف."))
            return

        backup_path = self.table.item(selected, 2).text()
        backup_date = self.table.item(selected, 0).text()

        r = QMessageBox.question(
            self,
            tr("تأكيد الحذف"),
            f"{tr('هل تريد حذف النسخة الاحتياطية من ')}{backup_date}؟\n\n"
            f"لا يمكن التراجع عن هذا الإجراء!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        try:
            import shutil
            shutil.rmtree(backup_path)
            QMessageBox.information(self, tr("تم الحذف"), tr("تم حذف النسخة الاحتياطية بنجاح."))
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), f"فشل حذف النسخة الاحتياطية:\n{e}")


# ----------------- Database Page -----------------
class DatabasePage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card(tr("عارض قاعدة البيانات"), tr("عرض مباشر للجداول"))

        self.btn_refresh = QPushButton(tr("تحديث الجداول"))
        lay.addWidget(row_buttons(self.btn_refresh))

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([tr("الجدول"), tr("الصفوف"), tr("الحجم (ميجابايت)"), tr("المحرك")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table)

        self.content_area.addWidget(card)
        
        self.btn_refresh.clicked.connect(self._load_tables)
        self.table.itemDoubleClicked.connect(self._on_table_double_click)
        self._set_enabled(False)

    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self._load_tables()

    def _on_project_cleared(self):
        self._set_enabled(False)
        self.table.setRowCount(0)

    def _set_enabled(self, val: bool):
        self.btn_refresh.setEnabled(val)

    def _load_tables(self):
        if not self.current: return
        self.table.setRowCount(0)
        try:
            db = self._get_db_params(self.current)
            conn = mysql_connect(db.host, db.port, db.user, db.user_pass)
            with conn.cursor() as cur:
                cur.execute(f"USE `{db.db_name}`")
                cur.execute("SHOW TABLE STATUS")
                rows = cur.fetchall()
                self.table.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    # row: Name(0), Engine(1), Rows(4), Data_length(6), Index_length(8)
                    name = str(row[0])
                    engine = str(row[1])
                    num_rows = str(row[4])
                    size_mb = f"{(row[6] + row[8]) / 1024 / 1024:.2f}"
                    
                    self.table.setItem(i, 0, QTableWidgetItem(name))
                    self.table.setItem(i, 1, QTableWidgetItem(num_rows))
                    self.table.setItem(i, 2, QTableWidgetItem(size_mb))
                    self.table.setItem(i, 3, QTableWidgetItem(engine))
            conn.close()
        except Exception as e:
            QMessageBox.warning(self, tr("خطأ في قاعدة البيانات"), str(e))
    
    def _on_table_double_click(self, item: QTableWidgetItem):
        if not self.current:
            return
        
        # Get table name from first column of clicked row
        row = item.row()
        table_name_item = self.table.item(row, 0)
        if not table_name_item:
            return
        
        table_name = table_name_item.text()
        
        try:
            db_params = self._get_db_params(self.current)
            dlg = TableDataDialog(table_name, db_params, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), f"فشل فتح عارض الجدول:\n{e}")


# ----------------- URL Converter Page -----------------
class UrlConvertPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card(tr("محول الروابط"), tr("البحث عن الروابط واستبدالها في قاعدة البيانات"))

        self.old_url = QLineEdit()
        self.old_url.setPlaceholderText(tr("الرابط القديم (مثال: http://localhost/mysite)"))
        self.new_url = QLineEdit()
        self.new_url.setPlaceholderText(tr("الرابط الجديد (مثال: https://example.com)"))
        self.chk_guid = QCheckBox(tr("تحديث المعرّفات الفريدة (GUID) (للمستخدمين المتقدمين فقط)"))

        self.btn_convert = PrimaryButton(tr("تحويل الرابط"))

        lay.addWidget(QLabel(tr("الرابط القديم:")))
        lay.addWidget(self.old_url)
        lay.addWidget(QLabel(tr("الرابط الجديد:")))
        lay.addWidget(self.new_url)

        self.chk_guid = QCheckBox(tr("تحديث المعرّفات الفريدة (GUID) (غير موصى به)"))
        self.chk_guid.setToolTip(tr("فعّل هذا الخيار فقط إذا كنت تعرف ما تفعله. عادةً يجب أن تبقى المعرّفات الفريدة (GUID) ثابتة."))

        self.chk_rename = QCheckBox(tr("إعادة تسمية مجلد المشروع ليطابق اسم الرابط"))
        self.chk_rename.setToolTip(tr("مثال: localhost/myshop -> يُعاد تسمية المجلد إلى 'myshop'"))
        self.chk_rename.setChecked(False)
        
        lay.addWidget(self.chk_guid)
        lay.addWidget(self.chk_rename)
        lay.addWidget(row_buttons(self.btn_convert))

        self.content_area.addWidget(card)
        
        self.btn_convert.clicked.connect(self._run_convert)
        self._set_enabled(False)

    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self.old_url.setText(p.url)

    def _on_project_cleared(self):
        self._set_enabled(False)
        self.old_url.clear()
        self.new_url.clear()

    def _set_enabled(self, val: bool):
        self.old_url.setEnabled(val)
        self.new_url.setEnabled(val)
        self.chk_guid.setEnabled(val)
        self.chk_rename.setEnabled(val)
        self.btn_convert.setEnabled(val)

    def _run_convert(self):
        if not self.current: return
        old = self.old_url.text().strip()
        new = self.new_url.text().strip()
        if not old or not new:
            QMessageBox.warning(self, tr("غير صالح"), tr("كلا الرابطين مطلوبان."))
            return
            
        self.parent_window._run_url_worker(
            self.current, 
            self._get_db_params(self.current), 
            old, new, 
            self.chk_guid.isChecked(),
            self.chk_rename.isChecked()
        )


# ----------------- Security Page -----------------
class SecurityPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        # 1. Hardening Card
        h_card, h_lay = make_card(tr("التحصين"), tr("تطبيق قواعد أمان .htaccess"))
        self.btn_harden = PrimaryButton(tr("تطبيق التحصين"))
        h_lay.addWidget(QLabel(tr("سيؤدي هذا إلى إضافة قواعد إلى ملف .htaccess لمنع تصفح المجلدات وحماية wp-config.php.")))
        h_lay.addWidget(row_buttons(self.btn_harden))

        # 2. Scanner Card
        s_card, s_lay = make_card(tr("فاحص البرمجيات الخبيثة"), tr("فحص ملفات المشروع بحثًا عن أكواد مشبوهة"))
        self.btn_scan = PrimaryButton(tr("تشغيل الفحص"))
        self.scan_results = QTextEdit()
        self.scan_results.setReadOnly(True)
        self.scan_results.setPlaceholderText(tr("ستظهر نتائج الفحص هنا..."))
        self.scan_results.setFixedHeight(200)
        s_lay.addWidget(self.scan_results)
        s_lay.addWidget(row_buttons(self.btn_scan))
        
        # Layout
        self.content_area.addWidget(h_card)
        self.content_area.addWidget(s_card)
        
        # Connections
        self.btn_harden.clicked.connect(self._run_hardening)
        self.btn_scan.clicked.connect(self._run_scan)
        
        self._set_enabled(False)

    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)

    def _on_project_cleared(self):
        self._set_enabled(False)
        self.scan_results.clear()

    def _set_enabled(self, val: bool):
        self.btn_harden.setEnabled(val)
        self.btn_scan.setEnabled(val)

    def _run_hardening(self):
        if not self.current: return
        try:
            from app.core.security import apply_htaccess_hardening
            apply_htaccess_hardening(self.current.path, self.parent_window.log)
            QMessageBox.information(self, tr("تم بنجاح"), tr("تم تطبيق التحصين الأمني بنجاح."))
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), f"فشل تطبيق التحصين:\n{e}")

    def _run_scan(self):
        if not self.current: return
        self.scan_results.clear()
        self.scan_results.append(tr("جارٍ بدء الفحص (في الخلفية)..."))
        self.parent_window._run_scan_worker(self.current.path)

    def on_scan_finished(self, results: list):
        self.scan_results.clear()
        if not results:
            self.scan_results.append(tr("✅ لم يتم العثور على ملفات مشبوهة."))
            QMessageBox.information(self, tr("اكتمل الفحص"), tr("لم يتم العثور على ملفات مشبوهة."))
        else:
            self.scan_results.append(f"{tr('⚠️ تم العثور على ')}{len(results)}{tr(' ملفًا مشبوهًا:')}")
            for r in results:
                self.scan_results.append(f"- {r['file']}{tr(' (التطابقات: ')}{', '.join(r['sigs'])})")
            QMessageBox.warning(self, tr("اكتمل الفحص"), f"{tr('تم العثور على ')}{len(results)}{tr(' ملفًا مشبوهًا! تحقق من منطقة النتائج.')}")


# ----------------- Manager Page (Plugins & Themes) -----------------
class ManagerPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        self.tabs = QTabWidget()
        
        # Plugins tab
        self.plugins_tab = QWidget()
        p_lay = QVBoxLayout(self.plugins_tab)
        self.plugin_list = QTableWidget(0, 3)
        self.plugin_list.setHorizontalHeaderLabels([tr("الاسم"), tr("الحالة"), tr("الإصدار")])
        self.plugin_list.horizontalHeader().setStretchLastSection(True)
        self.btn_refresh_plugins = QPushButton(tr("تحديث الإضافات"))
        p_lay.addWidget(self.plugin_list)
        p_lay.addWidget(row_buttons(self.btn_refresh_plugins))
        
        # Themes tab
        self.themes_tab = QWidget()
        t_lay = QVBoxLayout(self.themes_tab)
        self.theme_list = QTableWidget(0, 3)
        self.theme_list.setHorizontalHeaderLabels([tr("الاسم"), tr("الحالة"), tr("الإصدار")])
        self.theme_list.horizontalHeader().setStretchLastSection(True)
        self.btn_refresh_themes = QPushButton(tr("تحديث القوالب"))
        t_lay.addWidget(self.theme_list)

        # Tools row
        self.btn_fix_wpcli = QPushButton(tr("🛠️ إصلاح/تثبيت WP-CLI"))
        self.btn_fix_wpcli.setToolTip(tr("فرض تنزيل WP-CLI إذا كان مفقودًا أو لا يعمل."))

        t_lay.addWidget(row_buttons(self.btn_refresh_themes, self.btn_fix_wpcli))

        self.tabs.addTab(self.plugins_tab, tr("الإضافات"))
        self.tabs.addTab(self.themes_tab, tr("القوالب"))
        
        self.content_area.addWidget(self.tabs)
        
        self.btn_refresh_plugins.clicked.connect(lambda: self._refresh_items("plugin"))
        self.btn_refresh_themes.clicked.connect(lambda: self._refresh_items("theme"))
        self.btn_fix_wpcli.clicked.connect(self._on_fix_wpcli)
        
        self.plugin_list.itemDoubleClicked.connect(lambda it: self._on_item_double_click(it, "plugin"))
        self.theme_list.itemDoubleClicked.connect(lambda it: self._on_item_double_click(it, "theme"))
        
        self._set_enabled(False)
        
        # Worker thread references (to prevent garbage collection)
        self._worker_thread = None
        self._worker = None

    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self._refresh_items("plugin")
        self._refresh_items("theme")

    def _on_project_cleared(self):
        self._set_enabled(False)
        self.plugin_list.setRowCount(0)
        self.theme_list.setRowCount(0)

    def _set_enabled(self, val: bool):
        self.btn_refresh_plugins.setEnabled(val)
        self.btn_refresh_themes.setEnabled(val)

    def _refresh_items(self, item_type: str):
        """Asynchronously load plugins or themes using background thread."""
        if not self.current: 
            return
        
        # Prevent starting multiple threads
        if self._worker_thread and self._worker_thread.isRunning():
            return
        
        from app.core.wp_ops import get_effective_tooling
        from app.core.workers import ListItemsWorker
        from PyQt6.QtCore import QThread
        
        # Get PHP/WP-CLI tooling
        php, wpcli, is_phar = get_effective_tooling(self.current, log=self.parent_window.log)
        
        # Disable button and show loading state
        btn = self.btn_refresh_plugins if item_type == "plugin" else self.btn_refresh_themes
        original_text = btn.text()
        btn.setEnabled(False)
        btn.setText(tr("جارٍ التحميل..."))
        
        # Create worker and thread
        self._worker_thread = QThread()
        self._worker = ListItemsWorker(
            self.current.path,
            php,
            wpcli,
            is_phar,
            item_type
        )
        self._worker.moveToThread(self._worker_thread)
        
        # Connect signals
        self._worker_thread.started.connect(self._worker.run)
        self._worker.log.connect(self.parent_window.log)
        self._worker.done.connect(
            lambda ok, items, err: self._on_items_loaded(ok, items, err, item_type, btn, original_text)
        )
        
        # Cleanup connections
        self._worker.done.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_thread)
        
        # Start
        self._worker_thread.start()
    
    def _cleanup_thread(self):
        """Clean up worker thread after completion."""
        if self._worker_thread:
            self._worker_thread.wait()  # Wait for thread to fully finish
            self._worker_thread.deleteLater()
            self._worker_thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
    
    def _on_items_loaded(self, success: bool, items: list, error_msg: str, item_type: str, btn, original_text: str):
        """Handle completion of async items loading."""
        # Restore button
        btn.setEnabled(True)
        btn.setText(original_text)
        
        if not success:
            item_type_ar = tr("الإضافات") if item_type == "plugin" else tr("القوالب")
            QMessageBox.critical(self, tr("خطأ"), f"{tr('فشل تحميل ')}{item_type_ar}:\n{error_msg}")
            return
        
        # Populate table
        table = self.plugin_list if item_type == "plugin" else self.theme_list
        table.setRowCount(0)
        for i, item in enumerate(items):
            table.insertRow(i)
            name = item.get("name", "")
            status = item.get("status", "")
            version = item.get("version", "")
            
            # For plugins, WP-CLI uses 'file' or 'name' as the slug
            # For themes, it uses 'name' as the slug
            slug = item.get("file", item.get("name", "")) if item_type == "plugin" else item.get("name", "")
            
            name_item = QTableWidgetItem(name)
            # Store slug in UserRole for later use in activation/deactivation
            name_item.setData(Qt.ItemDataRole.UserRole, slug)
            
            table.setItem(i, 0, name_item)
            table.setItem(i, 1, QTableWidgetItem(status))
            table.setItem(i, 2, QTableWidgetItem(version))

    def _on_item_double_click(self, item: QTableWidgetItem, item_type: str):
        row = item.row()
        table = self.plugin_list if item_type == "plugin" else self.theme_list
        name = table.item(row, 0).text()
        status = table.item(row, 1).text()
        # Get the slug stored in UserRole data
        slug = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # NOTE: `action` stays English ("activate"/"deactivate") because it is passed
        # verbatim to toggle_wp_item() as a WP-CLI command argument. Arabic display
        # text is derived separately via action_ar below.
        action = "deactivate" if status == "active" else "activate"
        action_ar = tr("إلغاء تفعيل") if action == "deactivate" else tr("تفعيل")
        if item_type == "theme" and action == "deactivate":
            self.parent_window.show_toast(tr("لا يمكن إلغاء تفعيل القوالب، يمكن فقط استبدالها بتفعيل قالب آخر"), "warning")
            return

        r = QMessageBox.question(self, tr("إجراء"), f"{tr('هل تريد ')}{action_ar} {name}{tr('؟')}")
        if r == QMessageBox.StandardButton.Yes:
            try:
                from app.core.wp_ops import toggle_wp_item, get_effective_tooling
                php, wpcli, is_phar = get_effective_tooling(self.current, log=self.parent_window.log)
                # Use slug instead of name for WP-CLI command
                toggle_wp_item(Path(self.current.path), php, wpcli, is_phar, slug, action, item_type, log=self.parent_window.log)

                # Show success toast instead of blocking message
                action_past_ar = tr("تفعيل") if action == "activate" else tr("إلغاء تفعيل")
                self.parent_window.show_toast(f"{tr('✓ تم ')}{action_past_ar} {name}{tr(' بنجاح!')}", "success")

                self._refresh_items(item_type)
            except Exception as e:
                # Show error toast with details
                self.parent_window.show_toast(f"{tr('فشل ')}{action_ar} {name}: {str(e)}", "error", duration=5000)

    def _on_fix_wpcli(self):
        if not self.current: return
        r = QMessageBox.question(self, tr("إصلاح WP-CLI"), tr("سيحاول هذا تنزيل WP-CLI لهذا المشروع تحديدًا. هل تريد المتابعة؟"))
        if r == QMessageBox.StandardButton.Yes:
            from app.core.wp_ops import download_wpcli_for_project
            self.parent_window.log(tr("جارٍ بدء إصلاح WP-CLI يدويًا..."))
            ok, path = download_wpcli_for_project(self.current, self.parent_window.log)
            if ok:
                QMessageBox.information(self, tr("تم الإصلاح"), f"تم تثبيت WP-CLI في:\n{path}")
                self._refresh_items("plugin")
            else:
                QMessageBox.critical(self, tr("فشل"), tr("تعذر تنزيل WP-CLI. يرجى التحقق من اتصال الإنترنت أو السجلات."))

# ----------------- Config Page (wp-config.php Editor) -----------------
class ConfigPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card(tr("محرر إعدادات ووردبريس (wp-config)"), tr("تبديل الثوابت الشائعة لووردبريس"))

        self.grid = QGridLayout()
        self.checks = {}

        options = [
            ("WP_DEBUG", tr("تفعيل وضع التصحيح (Debug)")),
            ("WP_DEBUG_LOG", tr("تسجيل الأخطاء في wp-content/debug.log")),
            ("WP_DEBUG_DISPLAY", tr("عرض الأخطاء على الشاشة")),
            ("SCRIPT_DEBUG", tr("استخدام السكربتات غير المضغوطة")),
            ("SAVEQUERIES", tr("حفظ استعلامات قاعدة البيانات للتحليل")),
        ]
        
        for i, (key, label) in enumerate(options):
            chk = QCheckBox(label)
            self.grid.addWidget(chk, i, 0)
            self.checks[key] = chk
            chk.clicked.connect(lambda checked, k=key: self._update_config(k, checked))
            
        lay.addLayout(self.grid)
        self.content_area.addWidget(card)
        
        self._set_enabled(False)

    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self._load_config()

    def _on_project_cleared(self):
        self._set_enabled(False)
        for chk in self.checks.values():
            chk.setChecked(False)

    def _set_enabled(self, val: bool):
        for chk in self.checks.values():
            chk.setEnabled(val)

    def _load_config(self):
        if not self.current: return
        try:
            from app.core.wp_ops import read_wp_config_constants
            consts = read_wp_config_constants(Path(self.current.path))
            for key, chk in self.checks.items():
                val = str(consts.get(key, "false")).lower()
                chk.setChecked(val == "true")
        except Exception: pass

    def _update_config(self, key: str, val: bool):
        if not self.current: return
        try:
            from app.core.wp_ops import update_wp_config_constant
            update_wp_config_constant(Path(self.current.path), key, "true" if val else "false", is_string=False)
            self.parent_window.log(f"{tr('تم تحديث الإعداد: تعيين ')}{key}{tr(' إلى ')}{val}")
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), str(e))

# ----------------- DevTools Page -----------------
class DevToolsPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)

        card, lay = make_card(tr("أدوات المطورين"), tr("أدوات لتحسين الإنتاجية"))

        self.btn_vscode = PrimaryButton(tr("إنشاء إعدادات Xdebug لـ VS Code"))
        lay.addWidget(QLabel(tr("ينشئ ملف .vscode/launch.json لتسهيل التصحيح باستخدام Xdebug.")))
        lay.addWidget(row_buttons(self.btn_vscode))
        
        self.content_area.addWidget(card)
        self.btn_vscode.clicked.connect(self._gen_vscode)
        
        self._set_enabled(False)

    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)

    def _on_project_cleared(self):
        self._set_enabled(False)

    def _set_enabled(self, val: bool):
        self.btn_vscode.setEnabled(val)

    def _gen_vscode(self):
        if not self.current: return
        try:
            vscode_dir = Path(self.current.path) / ".vscode"
            vscode_dir.mkdir(exist_ok=True)
            launch_path = vscode_dir / "launch.json"
            
            config = {
                "version": "0.2.0",
                "configurations": [
                    {
                        "name": "Listen for Xdebug",
                        "type": "php",
                        "request": "launch",
                        "port": 9003,
                        "pathMappings": {
                            "${workspaceRoot}": "${workspaceRoot}"
                        }
                    }
                ]
            }
            import json
            launch_path.write_text(json.dumps(config, indent=4), encoding="utf-8")
            QMessageBox.information(self, tr("تم بنجاح"), f"{tr('تم إنشاء إعدادات VS Code في ')}{launch_path}")
            self.parent_window.log(tr("تم إنشاء ملف VS Code launch.json."))
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), str(e))
