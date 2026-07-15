"""Modern Dashboard Page with Statistics and Card-based Project Display"""
from __future__ import annotations
import datetime
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QDialog, QScrollArea, QSizePolicy
)
from PyQt6.QtGui import QFont

from app.core.projects_store import ProjectRecord, ProjectsStore
from app.core.utils import open_path
from app.ui.widgets import make_card, PrimaryButton


class StatCard(QFrame):
    """Statistics card widget for dashboard"""
    def __init__(self, title: str, value: str, icon: str, color: str = "#3B82F6"):
        super().__init__()
        self.setObjectName("StatCard")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        
        # Icon and Title row
        top_row = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 24px; color: {color};")
        top_row.addWidget(icon_label)
        top_row.addStretch()
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #9CA3AF; font-size: 12px; font-weight: 600;")
        top_row.addWidget(title_label)
        
        layout.addLayout(top_row)
        
        # Value
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"color: {color}; font-size: 32px; font-weight: 800;")
        layout.addWidget(self.value_label)
        
        # Styling
        self.setStyleSheet(f"""
            QFrame#StatCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #1F2937, stop:1 #111827);
                border: 1px solid #374151;
                border-radius: 12px;
            }}
        """)


class ProjectCard(QFrame):
    """Individual project card widget"""
    open_site_clicked = pyqtSignal(object)
    open_admin_clicked = pyqtSignal(object)
    open_folder_clicked = pyqtSignal(object)
    delete_clicked = pyqtSignal(object)
    selected = pyqtSignal(object)  # New: emit when card is selected
    
    def __init__(self, project: ProjectRecord):
        super().__init__()
        self.project = project
        self.setObjectName("ProjectCard")
        self.is_selected = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Title
        title = QLabel(f"🌐 {project.name}")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #F9FAFB;")
        layout.addWidget(title)
        
        # URL
        url_label = QLabel(project.url)
        url_label.setStyleSheet("color: #60A5FA; font-size: 13px;")
        layout.addWidget(url_label)
        
        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #374151;")
        layout.addWidget(divider)
        
        # Info row
        info_row = QHBoxLayout()
        
        # Stack info
        stack_label = QLabel(f"📊 {project.stack or 'Unknown'}")
        stack_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        info_row.addWidget(stack_label)
        
        info_row.addStretch()
        
        # DB info  
        db_label = QLabel(f"💾 {project.db_name}")
        db_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        info_row.addWidget(db_label)
        
        layout.addLayout(info_row)
        
        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        
        btn_open = QPushButton("Open")
        btn_open.clicked.connect(lambda: self.open_site_clicked.emit(self.project))
        btn_open.setStyleSheet("""
            QPushButton {
                background: #3B82F6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #2563EB;
            }
        """)
        btn_row.addWidget(btn_open)
        
        btn_admin = QPushButton("Admin")
        btn_admin.clicked.connect(lambda: self.open_admin_clicked.emit(self.project))
        btn_admin.setStyleSheet("""
            QPushButton {
                background: #10B981;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #059669;
            }
        """)
        btn_row.addWidget(btn_admin)
        
        btn_folder = QPushButton("📁")
        btn_folder.clicked.connect(lambda: self.open_folder_clicked.emit(self.project))
        btn_folder.setStyleSheet("""
            QPushButton {
                background: #6B7280;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #4B5563;
            }
        """)
        btn_row.addWidget(btn_folder)
        
        btn_row.addStretch()
        
        btn_delete = QPushButton("🗑️")
        btn_delete.clicked.connect(lambda: self.delete_clicked.emit(self.project))
        btn_delete.setStyleSheet("""
            QPushButton {
                background: #EF4444;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #DC2626;
            }
        """)
        btn_row.addWidget(btn_delete)
        
        layout.addLayout(btn_row)
        
        self._update_style()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    
    def _update_style(self):
        """Update card styling based on selection state"""
        if self.is_selected:
            self.setStyleSheet("""
                QFrame#ProjectCard {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                        stop:0 #1F2937, stop:1 #111827);
                    border: 3px solid #3B82F6;
                    border-radius: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#ProjectCard {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                        stop:0 #1F2937, stop:1 #111827);
                    border: 2px solid #374151;
                    border-radius: 12px;
                }
                QFrame#ProjectCard:hover {
                    border-color: #4B5563;
                }
            """)
    
    def set_selected(self, selected: bool):
        """Set selection state"""
        self.is_selected = selected
        self._update_style()
    
    def mousePressEvent(self, event):
        """Handle card click for selection"""
        self.selected.emit(self.project)
        super().mousePressEvent(event)


class DashboardPage(QWidget):
    """Modern dashboard with statistics and project cards"""
    project_selected = pyqtSignal(object)  # ProjectRecord|None
    full_deletion_requested = pyqtSignal(object)  # ProjectRecord
    
    def __init__(self, store: ProjectsStore):
        super().__init__()
        self.store = store
        self.current: ProjectRecord | None = None
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)
        
        # Statistics Cards Row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        
        # Create stat cards and keep reference to value labels
        self.stat_total = StatCard("Total Projects", "0", "📦", "#3B82F6")
        self.stat_running = StatCard("Active", "0", "⚡", "#10B981")
        self.stat_backups = StatCard("Backups", "0", "🔄", "#F59E0B")
        self.stat_issues = StatCard("Issues", "0", "⚠️", "#EF4444")
        
        # Direct references to value labels
        self.stat_total_value = self.stat_total.value_label
        self.stat_running_value = self.stat_running.value_label
        self.stat_backups_value = self.stat_backups.value_label
        self.stat_issues_value = self.stat_issues.value_label
        
        stats_row.addWidget(self.stat_total)
        stats_row.addWidget(self.stat_running)
        stats_row.addWidget(self.stat_backups)
        stats_row.addWidget(self.stat_issues)
        
        main_layout.addLayout(stats_row)
        
        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        
        self.btn_new = PrimaryButton("➕ New Project")
        self.btn_import = QPushButton("📥 Import Existing")
        self.btn_import.setStyleSheet("""
            QPushButton {
                background: #374151;
                color: white;
                border: 1px solid #4B5563;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #4B5563;
            }
        """)
        
        self.btn_clone = QPushButton("📋 Clone")
        self.btn_clone.setStyleSheet("""
            QPushButton {
                background: #374151;
                color: white;
                border: 1px solid #4B5563;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #4B5563;
            }
        """)
        
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_import)
        btn_row.addWidget(self.btn_clone)
        btn_row.addStretch()
        
        main_layout.addLayout(btn_row)
        
        # Projects Grid (Scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_content = QWidget()
        self.projects_grid = QGridLayout(scroll_content)
        self.projects_grid.setSpacing(16)
        self.projects_grid.setContentsMargins(0, 0, 0, 0)
        
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)
        
        # Connections
        self.btn_import.clicked.connect(self._import_project)
        
        self.reload()
    
    def reload(self):
        """Reload projects and update statistics"""
        # Clear existing cards
        for i in reversed(range(self.projects_grid.count())):
            widget = self.projects_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        projects = self.store.list_projects()
        
        # Update statistics
        total = len(projects)
        running = sum(1 for p in projects if p.url)

        # Count backups from manifest files
        backup_count = 0
        backup_root = Path("backups")
        if backup_root.exists():
            import json
            for backup_dir in backup_root.iterdir():
                manifest = backup_dir / "manifest.json"
                if manifest.is_file():
                    try:
                        data = json.loads(manifest.read_text(encoding="utf-8"))
                        project_paths = {p.path for p in projects}
                        if data.get("project_path") in project_paths:
                            backup_count += 1
                    except Exception:
                        pass

        # Count issues (projects with missing path or unreachable doc_root)
        issues_count = sum(
            1 for p in projects
            if (p.path and not Path(p.path).exists())
            or (p.doc_root and not Path(p.doc_root).exists())
        )

        self.stat_total_value.setText(str(total))
        self.stat_running_value.setText(str(running))
        self.stat_backups_value.setText(str(backup_count))
        self.stat_issues_value.setText(str(issues_count))
        
        # Store cards for selection management
        self.project_cards = []
        
        # Create project cards (3 columns)
        for idx, project in enumerate(projects):
            row = idx // 3
            col = idx % 3
            
            card = ProjectCard(project)
            card.open_site_clicked.connect(self.open_site)
            card.open_admin_clicked.connect(self.open_admin)
            card.open_folder_clicked.connect(self.open_folder)
            card.delete_clicked.connect(self.remove_project)
            card.selected.connect(self._on_card_selected)
            
            self.project_cards.append(card)
            self.projects_grid.addWidget(card, row, col)
        
        # Auto-select first project if available
        if self.project_cards:
            self.project_cards[0].set_selected(True)
            self.current = self.project_cards[0].project
            self.project_selected.emit(self.current)
    
    def _on_card_selected(self, project: ProjectRecord):
        """Handle project card selection"""
        # Deselect all cards
        for card in self.project_cards:
            card.set_selected(False)
        
        # Select clicked card
        for card in self.project_cards:
            if card.project.path == project.path:
                card.set_selected(True)
                break
        
        # Update current and emit signal
        self.current = project
        self.project_selected.emit(project)
    
    def open_site(self, project: ProjectRecord):
        import webbrowser
        webbrowser.open(project.url)
    
    def open_admin(self, project: ProjectRecord):
        import webbrowser
        webbrowser.open(project.admin_url)
    
    def open_folder(self, project: ProjectRecord):
        open_path(Path(project.path))
    
    def remove_project(self, project: ProjectRecord):
        msg = QMessageBox(self)
        msg.setWindowTitle("Delete Project")
        msg.setText(f"How would you like to delete '{project.name}'?")
        msg.setInformativeText("Warning: 'Delete Everything' cannot be undone.")
        
        btn_remove_only = msg.addButton("Remove from List Only", QMessageBox.ButtonRole.ActionRole)
        btn_full_delete = msg.addButton("Delete Everything (Files + DB)", QMessageBox.ButtonRole.DestructiveRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        
        msg.exec()
        
        clicked = msg.clickedButton()
        if clicked == btn_remove_only:
            self.store.delete_by_path(project.path)
            self.reload()
        elif clicked == btn_full_delete:
            self.full_deletion_requested.emit(project)
    
    def _import_project(self):
        from app.ui.main_window import ImportProjectDialog
        dlg = ImportProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
            
        data = dlg.get_data()
        path_obj = Path(data["path"])
        
        # Validation
        if not path_obj.exists() or not path_obj.is_dir():
            QMessageBox.critical(self, "Error", "Invalid project path.")
            return

        now = datetime.datetime.utcnow().isoformat() + "Z"
        
        # Create record
        rec = ProjectRecord(
            name=data["name"],
            path=data["path"],
            url=data["url"],
            admin_url=data["url"].rstrip("/") + "/wp-admin/",
            stack="Unknown",  # Imported
            doc_root=str(path_obj.parent),
            db_host=data["db_host"],
            db_port=data["db_port"],
            db_name=data["db_name"],
            db_user=data["db_user"],
            db_pass=data.get("db_pass", ""),
            table_prefix=data["table_prefix"],
            created_at_iso=now,
            last_action_iso=now,
            notes="Imported project"
        )
        
        self.store.upsert(rec)
        self.reload()
        QMessageBox.information(self, "Success", f"Project '{rec.name}' imported successfully.")
