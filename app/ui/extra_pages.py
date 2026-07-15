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

# ----------------- Settings Dialog -----------------
class ProjectSettingsDialog(QDialog):
    def __init__(self, p: ProjectRecord, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Settings: {p.name}")
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
        
        form.addRow("Project Path:", self.project_path)
        form.addRow("---", QLabel("Database Connection:"))
        form.addRow("DB Host:", self.host)
        form.addRow("DB Port:", self.port)
        form.addRow("DB User:", self.user)
        form.addRow("DB Pass:", self.password)
        form.addRow("DB Name:", self.db_name)
        form.addRow("Table Prefix:", self.table_prefix)
        
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
        self.setWindowTitle(f"Table Data: {table_name}")
        self.setMinimumSize(800, 600)
        
        self.table_name = table_name
        self.db_params = db_params
        
        layout = QVBoxLayout(self)
        
        # Info label
        info = QLabel(f"Showing data from table: {table_name}")
        info.setStyleSheet("font-weight: bold;")
        layout.addWidget(info)
        
        # Data table
        self.data_table = QTableWidget()
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self.data_table)
        
        # Close button
        btn_close = QPushButton("Close")
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
                    self.data_table.setHorizontalHeaderLabels(["Message"])
                    self.data_table.setRowCount(1)
                    self.data_table.setItem(0, 0, QTableWidgetItem("Table is empty"))
            
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load table data:\n{e}")


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
        top_card, top_lay = make_card("Select Project", "")
        
        sel_row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_combo_change)
        sel_row.addWidget(self.combo, 1)
        
        self.btn_settings = QPushButton("⚙ Settings")
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
        self.combo.addItem("Select a project...", None)
        
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
                QMessageBox.information(self, "Saved", "Settings updated.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open settings:\n{e}")

    def _on_project_cleared(self):
        pass


# ----------------- Backup Page -----------------
class BackupPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card("Backups", "Manage backups for this project")
        
        # Controls
        row = QHBoxLayout()
        self.btn_backup_files = QPushButton("Backup Files Only")
        self.btn_backup_db = QPushButton("Backup DB Only")
        self.btn_backup_full = PrimaryButton("Full Backup")
        row.addWidget(self.btn_backup_files)
        row.addWidget(self.btn_backup_db)
        row.addWidget(self.btn_backup_full)
        lay.addLayout(row)

        # Open Folder
        self.btn_open_folder = QPushButton("📂 Open Backup Folder")
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
        self.table.setHorizontalHeaderLabels(["Date", "Contents", "Path"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table)
        
        # Restore/Delete buttons
        act_row = QHBoxLayout()
        self.btn_restore = QPushButton("Restore Selected")
        self.btn_delete = QPushButton("Delete Selected")
        act_row.addWidget(self.btn_restore)
        act_row.addWidget(self.btn_delete)
        act_row.addStretch(1)
        lay.addLayout(act_row)

        self.content_area.addWidget(card)
        
        # Schedules Card
        sched_card, s_lay = make_card("📅 Scheduled Backups", "Automatic backups")
        
        self.schedule_table = QTableWidget()
        self.schedule_table.setColumnCount(4)
        self.schedule_table.setHorizontalHeaderLabels(["Frequency", "Time/Days", "Content", "Created"])
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        s_lay.addWidget(self.schedule_table)
        
        sched_btn_row = QHBoxLayout()
        self.btn_add_schedule = QPushButton("➕ Add Schedule")
        self.btn_delete_schedule = QPushButton("🗑️ Delete Schedule")
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
                        "date": manifest.get("timestamp", "Unknown"),
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
            if backup["has_files"]: contents.append("Files")
            if backup["has_db"]: contents.append("DB")
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
                "Path Error", 
                f"Project path does not exist:\n{self.current.path}\n\n"
                f"Please update the path in Settings (⚙ button)."
            )
            return
        
        if not project_path.is_dir():
            QMessageBox.critical(
                self, 
                "Path Error", 
                f"Project path is not a directory:\n{self.current.path}"
            )
            return
        
        # Count files if backing up files
        if files:
            file_count = sum(1 for _ in project_path.rglob('*') if _.is_file())
            if file_count == 0:
                result = QMessageBox.question(
                    self,
                    "Empty Directory",
                    f"The project directory appears to be empty (0 files).\n\n"
                    f"Path: {self.current.path}\n\n"
                    f"Do you want to continue anyway?",
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
        self.status_label.setText(f"Preparing backup from: {self.current.path}")
        
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
            QMessageBox.information(self, "Success", f"{message}\n\nBackup saved to:\n{backup_dir}")
            self._refresh_list()
        else:
            QMessageBox.critical(self, "Error", f"Backup failed:\n{message}")

    def _open_backup_folder(self):
        root = Path("backups").resolve()
        root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))

    def _restore_backup(self):
        if not self.current: return
        
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.information(self, "No Selection", "Please select a backup to restore.")
            return
        
        backup_path = self.table.item(selected, 2).text()
        backup_date = self.table.item(selected, 0).text()
        
        r = QMessageBox.question(
            self,
            "Confirm Restore",
            f"This will restore backup from:\n{backup_date}\n\n"
            f"WARNING: This will overwrite current files!\n\n"
            f"Continue?",
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
            QMessageBox.information(self, "No Selection", "Please select a backup to delete.")
            return
        
        backup_path = self.table.item(selected, 2).text()
        backup_date = self.table.item(selected, 0).text()
        
        r = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete backup from {backup_date}?\n\n"
            f"This cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        
        try:
            import shutil
            shutil.rmtree(backup_path)
            QMessageBox.information(self, "Deleted", "Backup deleted successfully.")
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete backup:\n{e}")

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
            
            freq = sched.get("frequency", "N/A")
            time_spec = sched.get("time_spec", "N/A")
            content = []
            if sched.get("backup_files"): content.append("Files")
            if sched.get("backup_db"): content.append("DB")
            created = sched.get("created_at", "N/A")[:10]
            
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
        dlg.setWindowTitle("Add Backup Schedule")
        dlg.setMinimumWidth(400)
        
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        
        freq_combo = QComboBox()
        freq_combo.addItems(["Hourly", "Daily", "Weekly"])
        form.addRow("Frequency:", freq_combo)
        
        time_edit = QTimeEdit()
        time_edit.setTime(QTime(0, 0))
        form.addRow("Time (for Daily):", time_edit)
        
        days_edit = QLineEdit()
        days_edit.setPlaceholderText("e.g. mon,wed,fri (for Weekly)")
        form.addRow("Days (for Weekly):", days_edit)
        
        files_chk = QCheckBox("Backup Files")
        files_chk.setChecked(True)
        form.addRow(files_chk)
        
        db_chk = QCheckBox("Backup Database")
        db_chk.setChecked(True)
        form.addRow(db_chk)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            freq = freq_combo.currentText().lower()
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
                QMessageBox.information(self, "Success", f"Schedule added: {freq}")
                self._refresh_schedules()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add schedule:\n{e}")

    def _delete_schedule(self):
        """Delete selected schedule"""
        selected = self.schedule_table.currentRow()
        if selected < 0:
            QMessageBox.information(self, "No Selection", "Please select a schedule to delete.")
            return
        
        sched_id = self.schedule_table.item(selected, 0).data(Qt.ItemDataRole.UserRole)
        
        r = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete this schedule?\n\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        
        try:
            self.scheduler.remove_schedule(sched_id)
            QMessageBox.information(self, "Deleted", "Schedule deleted successfully.")
            self._refresh_schedules()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete schedule:\n{e}")

    def _scheduled_backup_callback(self, project_path: str, backup_files: bool, backup_db: bool):
        """Callback executed by scheduler (usually in bg thread)"""
        print(f"Scheduled backup triggered for {project_path}")
        if not self.current: return
        
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.information(self, "No Selection", "Please select a backup to delete.")
            return
        
        backup_path = self.table.item(selected, 2).text()
        backup_date = self.table.item(selected, 0).text()
        
        r = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete backup from {backup_date}?\n\n"
            f"This cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        
        try:
            import shutil
            shutil.rmtree(backup_path)
            QMessageBox.information(self, "Deleted", "Backup deleted successfully.")
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete backup:\n{e}")


# ----------------- Database Page -----------------
class DatabasePage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card("Database Viewer", "Live view of tables")
        
        self.btn_refresh = QPushButton("Refresh Tables")
        lay.addWidget(row_buttons(self.btn_refresh))

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Table", "Rows", "Size (MB)", "Engine"])
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
            QMessageBox.warning(self, "DB Error", str(e))
    
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
            QMessageBox.critical(self, "Error", f"Failed to open table viewer:\n{e}")


# ----------------- URL Converter Page -----------------
class UrlConvertPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card("URL Converter", "Search and Replace URLs in Database")
        
        self.old_url = QLineEdit()
        self.old_url.setPlaceholderText("Old URL (e.g. http://localhost/mysite)")
        self.new_url = QLineEdit()
        self.new_url.setPlaceholderText("New URL (e.g. https://example.com)")
        self.chk_guid = QCheckBox("Update GUIDs (Advanced users only)")
        
        self.btn_convert = PrimaryButton("Convert URL")
        
        lay.addWidget(QLabel("Old URL:"))
        lay.addWidget(self.old_url)
        lay.addWidget(QLabel("New URL:"))
        lay.addWidget(self.new_url)
        
        self.chk_guid = QCheckBox("Update GUIDs (Not recommended)")
        self.chk_guid.setToolTip("Only enable if you know what you are doing. Usually GUIDs should stay static.")
        
        self.chk_rename = QCheckBox("Rename project folder to match URL slug")
        self.chk_rename.setToolTip("Example: localhost/myshop -> folder renamed to 'myshop'")
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
            QMessageBox.warning(self, "Invalid", "Both URLs are required.")
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
        h_card, h_lay = make_card("Hardening", "Apply .htaccess security rules")
        self.btn_harden = PrimaryButton("Apply Hardening")
        h_lay.addWidget(QLabel("This will add rules to your .htaccess to prevent directory browsing and protect wp-config.php."))
        h_lay.addWidget(row_buttons(self.btn_harden))
        
        # 2. Scanner Card
        s_card, s_lay = make_card("Malware Scanner", "Scan project files for suspicious code")
        self.btn_scan = PrimaryButton("Run Scan")
        self.scan_results = QTextEdit()
        self.scan_results.setReadOnly(True)
        self.scan_results.setPlaceholderText("Scan results will appear here...")
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
            QMessageBox.information(self, "Success", "Security hardening applied successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply hardening:\n{e}")

    def _run_scan(self):
        if not self.current: return
        self.scan_results.clear()
        self.scan_results.append("Starting scan (in background)...")
        self.parent_window._run_scan_worker(self.current.path)

    def on_scan_finished(self, results: list):
        self.scan_results.clear()
        if not results:
            self.scan_results.append("✅ No suspicious files found.")
            QMessageBox.information(self, "Scan Complete", "No suspicious files found.")
        else:
            self.scan_results.append(f"⚠️ Found {len(results)} suspicious files:")
            for r in results:
                self.scan_results.append(f"- {r['file']} (Matches: {', '.join(r['sigs'])})")
            QMessageBox.warning(self, "Scan Complete", f"Found {len(results)} suspicious files! Check the results area.")


# ----------------- Manager Page (Plugins & Themes) -----------------
class ManagerPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        self.tabs = QTabWidget()
        
        # Plugins tab
        self.plugins_tab = QWidget()
        p_lay = QVBoxLayout(self.plugins_tab)
        self.plugin_list = QTableWidget(0, 3)
        self.plugin_list.setHorizontalHeaderLabels(["Name", "Status", "Version"])
        self.plugin_list.horizontalHeader().setStretchLastSection(True)
        self.btn_refresh_plugins = QPushButton("Refresh Plugins")
        p_lay.addWidget(self.plugin_list)
        p_lay.addWidget(row_buttons(self.btn_refresh_plugins))
        
        # Themes tab
        self.themes_tab = QWidget()
        t_lay = QVBoxLayout(self.themes_tab)
        self.theme_list = QTableWidget(0, 3)
        self.theme_list.setHorizontalHeaderLabels(["Name", "Status", "Version"])
        self.theme_list.horizontalHeader().setStretchLastSection(True)
        self.btn_refresh_themes = QPushButton("Refresh Themes")
        t_lay.addWidget(self.theme_list)
        
        # Tools row
        self.btn_fix_wpcli = QPushButton("🛠️ Fix/Install WP-CLI")
        self.btn_fix_wpcli.setToolTip("Force download WP-CLI if it's missing or not working.")
        
        t_lay.addWidget(row_buttons(self.btn_refresh_themes, self.btn_fix_wpcli))
        
        self.tabs.addTab(self.plugins_tab, "Plugins")
        self.tabs.addTab(self.themes_tab, "Themes")
        
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
        btn.setText("Loading...")
        
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
            QMessageBox.critical(self, "Error", f"Failed to load {item_type}s:\n{error_msg}")
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
        
        action = "deactivate" if status == "active" else "activate"
        if item_type == "theme" and action == "deactivate":
            self.parent_window.show_toast("Themes cannot be deactivated, only replaced by activating another", "warning")
            return

        r = QMessageBox.question(self, "Action", f"Do you want to {action} {name}?")
        if r == QMessageBox.StandardButton.Yes:
            try:
                from app.core.wp_ops import toggle_wp_item, get_effective_tooling
                php, wpcli, is_phar = get_effective_tooling(self.current, log=self.parent_window.log)
                # Use slug instead of name for WP-CLI command
                toggle_wp_item(Path(self.current.path), php, wpcli, is_phar, slug, action, item_type, log=self.parent_window.log)
                
                # Show success toast instead of blocking message
                action_past = "activated" if action == "activate" else "deactivated"
                self.parent_window.show_toast(f"✓ {name} {action_past} successfully!", "success")
                
                self._refresh_items(item_type)
            except Exception as e:
                # Show error toast with details
                self.parent_window.show_toast(f"Failed to {action} {name}: {str(e)}", "error", duration=5000)

    def _on_fix_wpcli(self):
        if not self.current: return
        r = QMessageBox.question(self, "Fix WP-CLI", "This will attempt to download WP-CLI for this project specifically. Proceed?")
        if r == QMessageBox.StandardButton.Yes:
            from app.core.wp_ops import download_wpcli_for_project
            self.parent_window.log("Starting manual WP-CLI fix...")
            ok, path = download_wpcli_for_project(self.current, self.parent_window.log)
            if ok:
                QMessageBox.information(self, "Fixed", f"WP-CLI installed at:\n{path}")
                self._refresh_items("plugin")
            else:
                QMessageBox.critical(self, "Failed", "Could not download WP-CLI. Please check internet connection or logs.")

# ----------------- Config Page (wp-config.php Editor) -----------------
class ConfigPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card("WP-Config Editor", "Toggle common WordPress constants")
        
        self.grid = QGridLayout()
        self.checks = {}
        
        options = [
            ("WP_DEBUG", "Enable Debug Mode"),
            ("WP_DEBUG_LOG", "Log errors to wp-content/debug.log"),
            ("WP_DEBUG_DISPLAY", "Display errors on screen"),
            ("SCRIPT_DEBUG", "Use unminified scripts"),
            ("SAVEQUERIES", "Save database queries for analysis"),
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
            self.parent_window.log(f"Config updated: {key} set to {val}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

# ----------------- DevTools Page -----------------
class DevToolsPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        card, lay = make_card("Developer Tools", "Productivity helpers")
        
        self.btn_vscode = PrimaryButton("Generate VS Code Xdebug Config")
        lay.addWidget(QLabel("Creates .vscode/launch.json for easy debugging with Xdebug."))
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
            QMessageBox.information(self, "Success", f"VS Code config generated at {launch_path}")
            self.parent_window.log("VS Code launch.json created.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
