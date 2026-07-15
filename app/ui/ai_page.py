from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QMessageBox, QDialog, QFormLayout,
    QDialogButtonBox, QFrame, QProgressBar
)
from PyQt6.QtCore import QThreadPool, Qt, QTimer
from PyQt6.QtGui import QTextCursor

from app.ui.widgets import make_card, PrimaryButton, row_buttons
from app.core.projects_store import ProjectsStore, ProjectRecord
from app.ui.extra_pages import BaseExtraPage
from app.core.ai_worker import AIWorker


class ScanResultDialog(QDialog):
    """Modern popup dialog that shows scanning animation and results with typing effect."""

    def __init__(self, title: str, icon: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{icon} {title}")
        self.resize(750, 550)
        self.setMinimumSize(600, 400)
        self._full_text = ""
        self._char_index = 0
        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(8)
        self._typing_timer.timeout.connect(self._type_next_chunk)
        self._scan_title = title
        self._scan_icon = icon

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ──
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4F46E5, stop:1 #7C3AED);
                border: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
        """)
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(24, 18, 24, 18)

        title_lbl = QLabel(f"{icon}  {title}")
        title_lbl.setStyleSheet("color: white; font-size: 18px; font-weight: 800; background: transparent;")
        h_lay.addWidget(title_lbl)

        self.status_lbl = QLabel("جاري الفحص...")
        self.status_lbl.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 13px; background: transparent;")
        h_lay.addWidget(self.status_lbl)

        # Animated progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar { background: rgba(255,255,255,0.15); border: none; border-radius: 2px; }
            QProgressBar::chunk { background: rgba(255,255,255,0.8); border-radius: 2px; }
        """)
        h_lay.addWidget(self.progress)

        main_layout.addWidget(header)

        # ── Body ──
        body = QFrame()
        body.setStyleSheet("QFrame { background: #0F172A; border: none; }")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 16, 20, 16)

        # Scanning animation dots
        self.scan_anim_lbl = QLabel("  Scanning ")
        self.scan_anim_lbl.setStyleSheet(
            "color: #A5B4FC; font-size: 14px; font-weight: 600; background: transparent;"
        )
        self.scan_anim_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_lay.addWidget(self.scan_anim_lbl)

        self._dot_count = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(400)
        self._dot_timer.timeout.connect(self._animate_dots)
        self._dot_timer.start()

        # Results text area
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setStyleSheet("""
            QTextEdit {
                background: #1E293B;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 16px;
                color: #E2E8F0;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
                line-height: 1.6;
                selection-background-color: #6366F1;
            }
        """)
        self.results_text.setVisible(False)
        body_lay.addWidget(self.results_text, 1)

        main_layout.addWidget(body, 1)

        # ── Footer ──
        footer = QFrame()
        footer.setStyleSheet("""
            QFrame {
                background: #111827;
                border-top: 1px solid #1E293B;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(20, 12, 20, 12)

        self.result_badge = QLabel("")
        self.result_badge.setStyleSheet("color: #9CA3AF; font-size: 12px; background: transparent;")
        f_lay.addWidget(self.result_badge)
        f_lay.addStretch()

        self.btn_copy = QPushButton("نسخ النتائج")
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background: #1F2937; border: 1px solid #374151; border-radius: 6px;
                padding: 8px 18px; color: #D1D5DB; font-weight: 600;
            }
            QPushButton:hover { background: #374151; }
        """)
        self.btn_copy.setVisible(False)
        self.btn_copy.clicked.connect(self._copy_results)
        f_lay.addWidget(self.btn_copy)

        self.btn_close = QPushButton("إغلاق")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #6366F1, stop:1 #4F46E5);
                border: 1px solid #4F46E5; border-radius: 6px;
                padding: 8px 24px; color: white; font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #818CF8, stop:1 #6366F1);
            }
        """)
        self.btn_close.clicked.connect(self.accept)
        f_lay.addWidget(self.btn_close)

        main_layout.addWidget(footer)

        # Overall dialog styling
        self.setStyleSheet("""
            QDialog {
                background: #0F172A;
                border: 1px solid #1E293B;
                border-radius: 10px;
            }
        """)

    # ── Dot animation ──
    def _animate_dots(self):
        self._dot_count = (self._dot_count + 1) % 4
        dots = "." * self._dot_count
        spaces = " " * (3 - self._dot_count)
        self.scan_anim_lbl.setText(f"  Scanning {dots}{spaces}")

    # ── Show result with typing animation ──
    def show_result(self, text: str):
        """Display the result text with a typing animation."""
        self._dot_timer.stop()
        self.scan_anim_lbl.setVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setStyleSheet("""
            QProgressBar { background: rgba(255,255,255,0.15); border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #34D399; border-radius: 2px; }
        """)
        self.status_lbl.setText("اكتمل الفحص بنجاح")
        self.results_text.setVisible(True)
        self.btn_copy.setVisible(True)
        self.result_badge.setText(f"عدد الأسطر: {len(text.splitlines())}")

        # Format the text for display
        self._full_text = self._format_result_text(text)
        self._char_index = 0
        self.results_text.clear()
        self._typing_timer.start()

    def show_error(self, error: str):
        """Display an error in the dialog."""
        self._dot_timer.stop()
        self.scan_anim_lbl.setVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setStyleSheet("""
            QProgressBar { background: rgba(255,255,255,0.15); border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #EF4444; border-radius: 2px; }
        """)
        self.status_lbl.setText("حدث خطأ أثناء الفحص")
        self.results_text.setVisible(True)
        self.results_text.setHtml(
            f'<div style="color:#FCA5A5; padding:12px;">'
            f'<b style="font-size:15px;">خطأ</b><br><br>{error}</div>'
        )
        self.result_badge.setText("فشل الفحص")

    # ── Typing effect ──
    def _type_next_chunk(self):
        chunk_size = 6
        end = min(self._char_index + chunk_size, len(self._full_text))
        chunk = self._full_text[self._char_index:end]
        self._char_index = end

        cursor = self.results_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.results_text.setTextCursor(cursor)
        self.results_text.ensureCursorVisible()

        if self._char_index >= len(self._full_text):
            self._typing_timer.stop()

    # ── Format result text ──
    @staticmethod
    def _format_result_text(raw: str) -> str:
        """Clean up and enhance the raw result text for display."""
        lines = raw.split("\n")
        formatted = []
        for line in lines:
            stripped = line.strip()
            # Add visual separators for section headers (lines starting with ## or numbers)
            if stripped.startswith("##"):
                formatted.append("\n" + "─" * 50)
                formatted.append(stripped.replace("##", "").strip())
                formatted.append("─" * 50)
            elif stripped.startswith("**") and stripped.endswith("**"):
                formatted.append("\n" + stripped)
            else:
                formatted.append(line)
        return "\n".join(formatted)

    # ── Copy results ──
    def _copy_results(self):
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.results_text.toPlainText())
        self.result_badge.setText("تم النسخ!")
        QTimer.singleShot(2000, lambda: self.result_badge.setText(
            f"عدد الأسطر: {len(self._full_text.splitlines())}"
        ))

class ApiKeyDialog(QDialog):
    """Dialog to set Gemini API Key"""
    def __init__(self, current_key: str = ""):
        super().__init__()
        self.setWindowTitle("Gemini API Key")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        info = QLabel(
            "احصل على API Key مجاني من:\n"
            "https://makersuite.google.com/app/apikey\n\n"
            "سيتم حفظه في ملف .env"
        )
        layout.addWidget(info)
        
        form = QFormLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setText(current_key)
        self.api_key_input.setPlaceholderText("AIza...")
        form.addRow("API Key:", self.api_key_input)
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_key(self) -> str:
        return self.api_key_input.text().strip()


class AIChatWindow(QDialog):
    """Separate window for AI Chat"""
    def __init__(self, ai_assistant, project_record: ProjectRecord, parent=None):
        super().__init__(parent)
        self.ai = ai_assistant
        self.project = project_record
        self.threadpool = QThreadPool()
        
        self.setWindowTitle(f"💬 AI Assistant - {project_record.name}")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Chat History
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("font-size: 14px; line-height: 1.4;")
        layout.addWidget(self.chat_history, 1)
        
        # Input Area
        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("اكتب سؤالك هنا...")
        self.chat_input.setStyleSheet("font-size: 14px; padding: 8px;")
        self.chat_input.returnPressed.connect(self._send_chat)
        
        self.btn_send = PrimaryButton("إرسال")
        self.btn_send.clicked.connect(self._send_chat)
        
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.btn_send)
        layout.addLayout(input_row)
        
        self.chat_history.append("🤖 **AI:** أهلاً بك! كيف يمكنني مساعدتك في هذا المشروع؟")
        self.chat_history.append("─" * 40)
        
    def _send_chat(self):
        message = self.chat_input.text().strip()
        if not message: return
        
        self.chat_history.append(f"\n🙋 **You:** {message}")
        self.chat_input.clear()
        self.btn_send.setEnabled(False)
        self.chat_history.append("⏳ تفكير...")
        
        context = f"Project: {self.project.name}, Path: {self.project.path}, URL: {self.project.url}"
        
        worker = AIWorker(self.ai.chat, message, context)
        worker.signals.finished.connect(self._handle_response)
        worker.signals.error.connect(self._handle_error)
        self.threadpool.start(worker)
        
    def _handle_response(self, response: str):
        self.btn_send.setEnabled(True)
        # Remove last line (Thinking...) if possible or just append
        cursor = self.chat_history.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.select(cursor.SelectionType.LineUnderCursor)
        self.chat_history.append(f"🤖 **AI:** {response}")
        self.chat_history.append("─" * 40)
        
    def _handle_error(self, err: str):
        self.btn_send.setEnabled(True)
        self.chat_history.append(f"❌ Error: {err}")


class AIAssistantPage(BaseExtraPage):
    def __init__(self, store: ProjectsStore, parent_window: QWidget):
        super().__init__(store, parent_window)
        
        self.threadpool = QThreadPool()
        self.api_key = self._load_api_key()
        self._init_ai()
        
        # Header
        header_card, h_lay = make_card(
            "🤖 AI Assistant",
            "مساعد ذكي لتحليل الأخطاء والمشاكل باستخدام Gemini AI"
        )
        
        self.btn_set_api = QPushButton("⚙️ Set API Key")
        self.btn_set_api.clicked.connect(self._set_api_key)
        h_lay.addWidget(row_buttons(self.btn_set_api))
        
        # Main Chat Button
        chat_card, c_lay = make_card("💬 Chat Room", "افتح نافذة المحادثة الكبيرة")
        self.btn_open_chat = PrimaryButton("فتح المحادثة (نافذة منفصلة)")
        self.btn_open_chat.setFixedHeight(50)
        self.btn_open_chat.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.btn_open_chat.clicked.connect(self._open_chat_window)
        c_lay.addWidget(self.btn_open_chat)

        # Quick Actions Card
        actions_card, a_lay = make_card("⚡ Quick Actions", "تحليل سريع")
        
        self.btn_analyze_debug = QPushButton("🔍 Analyze Debug Log")
        self.btn_security_scan = QPushButton("🛡️ Security Scan")
        self.btn_performance = QPushButton("⚡ Performance Tips")
        
        self.btn_analyze_debug.clicked.connect(self._analyze_debug)
        self.btn_security_scan.clicked.connect(self._security_scan)
        self.btn_performance.clicked.connect(self._performance_tips)
        
        actions_row = QHBoxLayout()
        actions_row.addWidget(self.btn_analyze_debug)
        actions_row.addWidget(self.btn_security_scan)
        actions_row.addWidget(self.btn_performance)
        a_lay.addLayout(actions_row)

        self.content_area.addWidget(header_card)
        self.content_area.addWidget(chat_card)
        self.content_area.addWidget(actions_card)

        self._active_dialog = None
        
        self._set_enabled(False)
    
    def _init_ai(self):
        """Initialize AI assistant"""
        try:
            from app.core.ai_assistant import GeminiAssistant
            self.ai = GeminiAssistant(self.api_key)
        except Exception:
            pass
    
    def _get_env_path(self) -> Path:
        """Resolve .env file path for both dev and PyInstaller-bundled exe."""
        import sys
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent / ".env"
        else:
            return Path(__file__).resolve().parent.parent.parent / ".env"
    
    def _load_api_key(self) -> str:
        """Load API key from .env file"""
        env_file = self._get_env_path()
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip()
        return ""
    
    def _save_api_key(self, key: str):
        """Save API key to .env file"""
        env_file = self._get_env_path()
        lines = []
        found = False
        
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines):
                if line.startswith("GEMINI_API_KEY="):
                    lines[i] = f"GEMINI_API_KEY={key}"
                    found = True
        
        if not found:
            lines.append(f"GEMINI_API_KEY={key}")
        
        env_file.write_text("\n".join(lines), encoding="utf-8")
    
    def _set_api_key(self):
        """Open dialog to set API key"""
        dlg = ApiKeyDialog(self.api_key)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            key = dlg.get_key()
            if key:
                self._save_api_key(key)
                self.api_key = key
                self._init_ai()
                QMessageBox.information(self, "Success", "API Key saved successfully!")
    
    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
    
    def _on_project_cleared(self):
        self._set_enabled(False)
    
    def _set_enabled(self, val: bool):
        self.btn_open_chat.setEnabled(val)
        self.btn_analyze_debug.setEnabled(val)
        self.btn_security_scan.setEnabled(val)
        self.btn_performance.setEnabled(val)
    
    def _open_chat_window(self):
        if not self.current: return
        self.chat_window = AIChatWindow(self.ai, self.current, self)
        self.chat_window.show()

    def _open_scan_dialog(self, title: str, icon: str, btn: QPushButton) -> ScanResultDialog:
        """Open a scan result dialog and disable the triggering button."""
        btn.setEnabled(False)
        dlg = ScanResultDialog(title, icon, self)
        dlg.finished.connect(lambda: btn.setEnabled(True))
        self._active_dialog = dlg
        dlg.show()
        return dlg

    def _analyze_debug(self):
        if not self.current: return

        log_path = Path(self.current.path) / "wp-content" / "debug.log"
        if not log_path.exists():
            QMessageBox.warning(self, "Not Found", "لا يوجد ملف debug.log في المشروع.")
            return

        dlg = self._open_scan_dialog("تحليل سجل الأخطاء", "🔍", self.btn_analyze_debug)

        try:
            log_content = log_path.read_text(encoding="utf-8", errors="ignore")
            worker = AIWorker(self.ai.analyze_debug_log, log_content)
            worker.signals.finished.connect(dlg.show_result)
            worker.signals.error.connect(dlg.show_error)
            self.threadpool.start(worker)
        except Exception as e:
            dlg.show_error(str(e))

    def _security_scan(self):
        if not self.current: return

        config_path = Path(self.current.path) / "wp-config.php"
        if not config_path.exists():
            QMessageBox.warning(self, "Not Found", "لا يوجد ملف wp-config.php في المشروع.")
            return

        dlg = self._open_scan_dialog("فحص الحماية والأمان", "🛡️", self.btn_security_scan)

        try:
            code = config_path.read_text(encoding="utf-8")[:3000]
            worker = AIWorker(self.ai.security_scan_code, code, "wp-config.php")
            worker.signals.finished.connect(dlg.show_result)
            worker.signals.error.connect(dlg.show_error)
            self.threadpool.start(worker)
        except Exception as e:
            dlg.show_error(str(e))

    def _performance_tips(self):
        if not self.current: return

        dlg = self._open_scan_dialog("نصائح الأداء والسرعة", "⚡", self.btn_performance)

        project_info = {
            "name": self.current.name,
            "path": self.current.path,
            "url": self.current.url
        }
        worker = AIWorker(self.ai.performance_suggestions, project_info)
        worker.signals.finished.connect(dlg.show_result)
        worker.signals.error.connect(dlg.show_error)
        self.threadpool.start(worker)
