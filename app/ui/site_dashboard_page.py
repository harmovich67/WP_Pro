"""
app/ui/site_dashboard_page.py
─────────────────────────────────────────────
Mini WordPress Site Dashboard
Manage posts, pages, users, plugins, themes and options
directly from the app — no need to open wp-admin.

Uses WP-CLI for content operations and direct MySQL for Options.
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QProgressBar, QLineEdit, QTextEdit, QDialog, QFormLayout,
    QDialogButtonBox, QTabWidget, QComboBox, QSizePolicy,
    QCheckBox, QListWidget, QListWidgetItem, QSplitter, QApplication,
    QInputDialog, QFrame, QGridLayout,
)

from app.core.projects_store import ProjectsStore, ProjectRecord
from app.core.wp_ops import (
    mysql_connect, get_effective_tooling, run_wpcli,
)
from app.ui.extra_pages import BaseExtraPage
from app.ui.widgets import PrimaryButton, make_card


# ──────────────────────────────────────────────────────────────────────────────
# Background worker
# ──────────────────────────────────────────────────────────────────────────────

class _WPCLIWorker(QObject):
    """Run a single WP-CLI command list in a background QThread."""
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)   # (success, raw_output_or_error_msg)

    def __init__(self, project_path: str, php: str, wpcli: str,
                 is_phar: bool, args: list[str]):
        super().__init__()
        self._path = Path(project_path)
        self._php = php
        self._wpcli = wpcli
        self._is_phar = is_phar
        self._args = args

    def run(self):
        try:
            res = run_wpcli(
                self._path, self._php, self._wpcli, self._is_phar,
                self._args, self.log.emit,
            )
            self.done.emit(True, res.out.strip())
        except Exception as exc:
            self.done.emit(False, str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Small dialogs
# ──────────────────────────────────────────────────────────────────────────────

class _PostEditDialog(QDialog):
    """Create / Edit a post or page."""

    def __init__(self, post_type: str = "post",
                 data: dict | None = None, parent=None):
        super().__init__(parent)
        is_edit = data is not None
        label = "مقال" if post_type == "post" else "صفحة"
        self.setWindowTitle(f"{'تعديل' if is_edit else 'إضافة'} {label}")
        self.setMinimumSize(640, 520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._title = QLineEdit(data.get("post_title", "") if data else "")
        self._title.setPlaceholderText("اكتب العنوان هنا…")

        self._status = QComboBox()
        self._status.addItems(["publish", "draft", "private", "pending"])
        if data and data.get("post_status"):
            idx = self._status.findText(data["post_status"])
            if idx >= 0:
                self._status.setCurrentIndex(idx)

        self._excerpt = QLineEdit(
            data.get("post_excerpt", "") if data else "")
        self._excerpt.setPlaceholderText("مقتطف اختياري")

        self._content = QTextEdit()
        self._content.setPlaceholderText(
            "محتوى المقال (نص عادي أو HTML)…")
        if data and data.get("post_content"):
            self._content.setPlainText(data["post_content"])

        form.addRow("العنوان:", self._title)
        form.addRow("الحالة:", self._status)
        form.addRow("المقتطف:", self._excerpt)
        layout.addLayout(form)
        layout.addWidget(QLabel("المحتوى:"))
        layout.addWidget(self._content, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "title":   self._title.text().strip(),
            "status":  self._status.currentText(),
            "content": self._content.toPlainText(),
            "excerpt": self._excerpt.text().strip(),
        }


class _UserCreateDialog(QDialog):
    """Create a new WordPress user."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إنشاء مستخدم جديد")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._username  = QLineEdit(); self._username.setPlaceholderText("اسم المستخدم")
        self._email     = QLineEdit(); self._email.setPlaceholderText("user@example.com")
        self._password  = QLineEdit(); self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._firstname = QLineEdit()
        self._lastname  = QLineEdit()
        self._role = QComboBox()
        self._role.addItems(
            ["subscriber", "contributor", "author", "editor", "administrator"])

        form.addRow("اسم المستخدم:", self._username)
        form.addRow("البريد الإلكتروني:", self._email)
        form.addRow("كلمة المرور:", self._password)
        form.addRow("الاسم الأول:", self._firstname)
        form.addRow("اسم العائلة:", self._lastname)
        form.addRow("الدور:", self._role)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "username":   self._username.text().strip(),
            "email":      self._email.text().strip(),
            "password":   self._password.text(),
            "first_name": self._firstname.text().strip(),
            "last_name":  self._lastname.text().strip(),
            "role":       self._role.currentText(),
        }


class _OptionEditDialog(QDialog):
    """Edit a WordPress option value."""

    def __init__(self, name: str, value: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"تعديل الخيار: {name}")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-weight: bold;")
        self._value = QTextEdit()
        self._value.setPlainText(value)
        self._value.setMaximumHeight(220)

        form.addRow("الخيار:", name_lbl)
        form.addRow("القيمة:", self._value)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_value(self) -> str:
        return self._value.toPlainText()


class _AcfGroupDialog(QDialog):
    """Create or edit an ACF field group (saved as acf-json)."""

    def __init__(self, data: dict | None = None, parent=None):
        super().__init__(parent)
        is_edit = data is not None
        self.setWindowTitle("تعديل مجموعة حقول ACF" if is_edit else "مجموعة حقول ACF جديدة")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._title = QLineEdit(data.get("title", "") if data else "")
        self._title.setPlaceholderText("مثال: تفاصيل المنتج")

        _locations = ["post", "page", "attachment", "user",
                      "taxonomy", "comment", "widget", "nav_menu"]
        self._location = QComboBox()
        self._location.addItems(_locations)
        if data:
            loc = ""
            loc_rules = data.get("location", [])
            if loc_rules and loc_rules[0]:
                loc = loc_rules[0][0].get("value", "")
            idx = self._location.findText(loc)
            if idx >= 0:
                self._location.setCurrentIndex(idx)

        self._position = QComboBox()
        self._position.addItems(["normal", "side", "acf_after_title"])
        if data:
            idx = self._position.findText(data.get("position", "normal"))
            if idx >= 0:
                self._position.setCurrentIndex(idx)

        self._desc = QLineEdit(data.get("description", "") if data else "")
        self._desc.setPlaceholderText("وصف اختياري")

        form.addRow("الاسم *:", self._title)
        form.addRow("الموقع (post type):", self._location)
        form.addRow("الموضع في الصفحة:", self._position)
        form.addRow("الوصف:", self._desc)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "title":       self._title.text().strip(),
            "location":    self._location.currentText(),
            "position":    self._position.currentText(),
            "description": self._desc.text().strip(),
        }


class _AcfFieldDialog(QDialog):
    """Add or edit a field in an ACF field group."""

    def __init__(self, field_types: list[tuple[str, str]],
                 data: dict | None = None, parent=None):
        super().__init__(parent)
        is_edit = data is not None
        self.setWindowTitle("تعديل حقل ACF" if is_edit else "إضافة حقل ACF جديد")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._label = QLineEdit(data.get("label", "") if data else "")
        self._label.setPlaceholderText("مثال: صورة الغلاف")

        self._name = QLineEdit(data.get("name", "") if data else "")
        self._name.setPlaceholderText("مثال: cover_image  (حروف إنجليزية وأرقام و _)")

        # Auto-fill name from label only when adding (not editing)
        if not is_edit:
            def _auto_name(text: str):
                if not self._name.text():
                    slug = re.sub(r"[^a-z0-9]", "_",
                                  text.lower().replace(" ", "_"))
                    slug = re.sub(r"_+", "_", slug).strip("_")
                    self._name.setText(slug)
            self._label.textChanged.connect(_auto_name)

        self._type = QComboBox()
        for value, display in field_types:
            self._type.addItem(display, value)
        if data:
            idx = self._type.findData(data.get("type", "text"))
            if idx >= 0:
                self._type.setCurrentIndex(idx)

        self._instructions = QLineEdit(data.get("instructions", "") if data else "")
        self._instructions.setPlaceholderText("تعليمات للمحرر (اختياري)")

        self._required = QCheckBox("حقل مطلوب")
        if data:
            self._required.setChecked(bool(data.get("required", 0)))

        if is_edit:
            self._name.setEnabled(False)  # slug should not change after creation

        form.addRow("التسمية *:", self._label)
        form.addRow("الاسم (slug) *:", self._name)
        form.addRow("النوع:", self._type)
        form.addRow("التعليمات:", self._instructions)
        form.addRow("", self._required)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "label":        self._label.text().strip(),
            "name":         self._name.text().strip(),
            "type":         self._type.currentData(),
            "instructions": self._instructions.text().strip(),
            "required":     self._required.isChecked(),
        }


class _CptDialog(QDialog):
    """Create a new Custom Post Type (written to mu-plugins)."""

    _DEFAULT_SUPPORTS = ["title", "editor", "thumbnail"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة نوع محتوى مخصص (CPT)")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._slug     = QLineEdit()
        self._slug.setPlaceholderText("مثال: product  (حروف صغيرة وأرقام و _)")
        self._singular = QLineEdit()
        self._singular.setPlaceholderText("مثال: Product")
        self._plural   = QLineEdit()
        self._plural.setPlaceholderText("مثال: Products")
        self._icon     = QLineEdit("dashicons-admin-post")
        self._icon.setPlaceholderText("dashicons-admin-post")

        # Auto-fill labels from slug
        def _auto_labels(text: str):
            if not self._singular.text() and not self._plural.text():
                nice = text.replace("_", " ").title()
                self._singular.setText(nice)
                self._plural.setText(nice + "s")
        self._slug.textChanged.connect(_auto_labels)

        form.addRow("الـ Slug *:", self._slug)
        form.addRow("التسمية المفردة *:", self._singular)
        form.addRow("التسمية الجمع *:", self._plural)
        form.addRow("الأيقونة (dashicon):", self._icon)
        layout.addLayout(form)

        # Supports checkboxes
        layout.addWidget(QLabel("يدعم (supports):"))
        supports_row1 = QHBoxLayout()
        supports_row2 = QHBoxLayout()

        self._sup: dict[str, QCheckBox] = {}
        for key, label, default, row in [
            ("title",          "العنوان",          True,  supports_row1),
            ("editor",         "المحرر",           True,  supports_row1),
            ("thumbnail",      "الصورة البارزة",   True,  supports_row1),
            ("excerpt",        "المقتطف",          False, supports_row2),
            ("comments",       "التعليقات",        False, supports_row2),
            ("revisions",      "المراجعات",        False, supports_row2),
            ("custom-fields",  "الحقول المخصصة",   False, supports_row2),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(default)
            self._sup[key] = cb
            row.addWidget(cb)

        layout.addLayout(supports_row1)
        layout.addLayout(supports_row2)

        # Options row
        options_row = QHBoxLayout()
        self._public     = QCheckBox("عام (Public)");     self._public.setChecked(True)
        self._archive    = QCheckBox("له أرشيف");          self._archive.setChecked(True)
        self._rest       = QCheckBox("إظهار في REST");     self._rest.setChecked(True)
        self._hier       = QCheckBox("هرمي (Hierarchical)"); self._hier.setChecked(False)
        for cb in [self._public, self._archive, self._rest, self._hier]:
            options_row.addWidget(cb)
        options_row.addStretch()
        layout.addLayout(options_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self) -> dict:
        supports = [k for k, cb in self._sup.items() if cb.isChecked()]
        return {
            "slug":         self._slug.text().strip(),
            "singular":     self._singular.text().strip(),
            "plural":       self._plural.text().strip(),
            "icon":         self._icon.text().strip() or "dashicons-admin-post",
            "supports":     supports,
            "public":       self._public.isChecked(),
            "has_archive":  self._archive.isChecked(),
            "show_in_rest": self._rest.isChecked(),
            "hierarchical": self._hier.isChecked(),
        }


class _AcfCodeDialog(QDialog):
    """Show ready-to-paste PHP template code for an ACF field."""

    # Type-aware PHP code templates
    _CODE_TEMPLATES: dict[str, str] = {
        "text":      "<?php\n$value = get_field('{name}');\nif ($value) {\n    echo esc_html($value);\n}\n?>",
        "textarea":  "<?php\n$value = get_field('{name}');\nif ($value) {\n    echo nl2br(esc_html($value));\n}\n?>",
        "number":    "<?php\n$value = get_field('{name}');\nif ($value !== false && $value !== '') {\n    echo esc_html($value);\n}\n?>",
        "email":     "<?php\n$email = get_field('{name}');\nif ($email) {\n    echo '<a href=\"mailto:' . esc_attr($email) . '\">' . esc_html($email) . '</a>';\n}\n?>",
        "url":       "<?php\n$url = get_field('{name}');\nif ($url) {\n    echo '<a href=\"' . esc_url($url) . '\" target=\"_blank\">' . esc_url($url) . '</a>';\n}\n?>",
        "image":     "<?php\n$image = get_field('{name}');\nif ($image) {\n    // $image is an array with keys: url, alt, title, sizes\n    echo '<img src=\"' . esc_url($image['url']) . '\" alt=\"' . esc_attr($image['alt']) . '\">';\n    // Or use a specific size:\n    // echo '<img src=\"' . esc_url($image['sizes']['medium']) . '\" alt=\"' . esc_attr($image['alt']) . '\">';\n}\n?>",
        "file":      "<?php\n$file = get_field('{name}');\nif ($file) {\n    // $file is an array with keys: url, filename, filesize, mime_type\n    echo '<a href=\"' . esc_url($file['url']) . '\">' . esc_html($file['filename']) . '</a>';\n}\n?>",
        "gallery":   "<?php\n$images = get_field('{name}');\nif ($images) {\n    echo '<div class=\"gallery\">';\n    foreach ($images as $image) {\n        echo '<img src=\"' . esc_url($image['url']) . '\" alt=\"' . esc_attr($image['alt']) . '\">';\n    }\n    echo '</div>';\n}\n?>",
        "wysiwyg":   "<?php\n$content = get_field('{name}');\nif ($content) {\n    // WYSIWYG output is already HTML — use wp_kses_post for safety\n    echo wp_kses_post($content);\n}\n?>",
        "select":    "<?php\n$value = get_field('{name}');\nif ($value) {\n    // Single selection returns the value string\n    echo esc_html($value);\n}\n\n// For multiple selections (array):\n$values = get_field('{name}');\nif ($values && is_array($values)) {\n    foreach ($values as $v) {\n        echo esc_html($v) . '<br>';\n    }\n}\n?>",
        "checkbox":  "<?php\n$values = get_field('{name}');\nif ($values) {\n    // Returns an array of checked values\n    foreach ($values as $value) {\n        echo '<li>' . esc_html($value) . '</li>';\n    }\n}\n?>",
        "radio":     "<?php\n$value = get_field('{name}');\nif ($value) {\n    echo esc_html($value);\n}\n?>",
        "true_false": "<?php\nif (get_field('{name}')) {\n    // Field is true / checked\n    echo '<span class=\"badge-yes\">نعم</span>';\n} else {\n    echo '<span class=\"badge-no\">لا</span>';\n}\n?>",
        "link":      "<?php\n$link = get_field('{name}');\nif ($link) {\n    $target = $link['target'] ? ' target=\"_blank\"' : '';\n    echo '<a href=\"' . esc_url($link['url']) . '\"' . $target . '>' . esc_html($link['title']) . '</a>';\n}\n?>",
        "post_object": "<?php\n$post_obj = get_field('{name}');\nif ($post_obj) {\n    // $post_obj is a WP_Post object\n    echo '<a href=\"' . get_permalink($post_obj->ID) . '\">' . get_the_title($post_obj->ID) . '</a>';\n}\n?>",
        "relationship": "<?php\n$related_posts = get_field('{name}');\nif ($related_posts) {\n    foreach ($related_posts as $post) {\n        echo '<a href=\"' . get_permalink($post->ID) . '\">' . get_the_title($post->ID) . '</a><br>';\n    }\n}\n?>",
        "taxonomy":  "<?php\n$terms = get_field('{name}');\nif ($terms) {\n    foreach ($terms as $term) {\n        // $term is a WP_Term object\n        echo '<a href=\"' . get_term_link($term) . '\">' . esc_html($term->name) . '</a><br>';\n    }\n}\n?>",
        "user":      "<?php\n$user = get_field('{name}');\nif ($user) {\n    // $user is a WP_User object\n    echo esc_html($user->display_name);\n    // Access more data: $user->user_email, get_avatar($user->ID)\n}\n?>",
        "date_picker": "<?php\n// Date is returned in the format specified in field settings\n$date = get_field('{name}');\nif ($date) {\n    echo esc_html($date);\n    // Or convert: $timestamp = strtotime($date); echo date('d/m/Y', $timestamp);\n}\n?>",
        "color_picker": "<?php\n$color = get_field('{name}');\nif ($color) {\n    echo '<div style=\"background-color:' . esc_attr($color) . '; width:30px; height:30px;\"></div>';\n}\n?>",
        "repeater":  "<?php\nif (have_rows('{name}')) {\n    while (have_rows('{name}')) {\n        the_row();\n        // Access sub-fields with get_sub_field()\n        $sub_value = get_sub_field('sub_field_name');\n        echo esc_html($sub_value);\n    }\n}\n?>",
        "group":     "<?php\n$group = get_field('{name}');\nif ($group) {\n    // Access sub-fields via array keys\n    echo esc_html($group['sub_field_name'] ?? '');\n}\n?>",
        "flexible_content": "<?php\nif (have_rows('{name}')) {\n    while (have_rows('{name}')) {\n        the_row();\n        if (get_row_layout() === 'layout_name') {\n            $value = get_sub_field('sub_field_name');\n            echo esc_html($value);\n        }\n    }\n}\n?>",
    }

    _DEFAULT_TEMPLATE = "<?php\n$value = get_field('{name}');\nif ($value) {\n    echo esc_html($value);\n}\n?>"

    def __init__(self, fname: str, ftype: str, flabel: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"كود PHP: {flabel} ({ftype})")
        self.setMinimumSize(680, 520)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            f"<b>حقل:</b> {flabel}  &nbsp;|&nbsp;  "
            f"<b>الاسم:</b> <code>{fname}</code>  &nbsp;|&nbsp;  "
            f"<b>النوع:</b> <code>{ftype}</code>")
        header.setStyleSheet("padding: 6px; color: #D1FAE5;")
        layout.addWidget(header)

        hint = QLabel(
            "الكود التالي جاهز للاستخدام في ملفات القالب "
            "(single.php, page.php, template files…):")
        hint.setStyleSheet("color: #9CA3AF; font-size: 11px; padding: 2px;")
        layout.addWidget(hint)

        template = self._CODE_TEMPLATES.get(ftype, self._DEFAULT_TEMPLATE)
        code = template.replace("{name}", fname)

        self._code_edit = QTextEdit()
        self._code_edit.setPlainText(code)
        self._code_edit.setReadOnly(True)
        self._code_edit.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 12px; background: #0F172A; color: #E2E8F0;"
            "border: 1px solid #334155; border-radius: 6px; padding: 8px;")
        layout.addWidget(self._code_edit, 1)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("📋 نسخ الكود")
        btn_copy.clicked.connect(self._copy_code)
        btn_close = QPushButton("إغلاق")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _copy_code(self):
        QApplication.clipboard().setText(self._code_edit.toPlainText())
        QMessageBox.information(self, "تم", "تم نسخ الكود إلى الـ Clipboard!")


class _CodePreviewDialog(QDialog):
    """Generic read-only code preview with copy-to-clipboard."""

    def __init__(self, title: str, code: str,
                 language: str = "php", parent=None):
        super().__init__(parent)
        self._language = language   # reserved for future syntax highlighting
        self.setWindowTitle(title)
        self.setMinimumSize(680, 480)

        layout = QVBoxLayout(self)

        self._code_edit = QTextEdit()
        self._code_edit.setPlainText(code)
        self._code_edit.setReadOnly(True)
        self._code_edit.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 12px; background: #0F172A; color: #E2E8F0;"
            "border: 1px solid #334155; border-radius: 6px; padding: 8px;")
        layout.addWidget(self._code_edit, 1)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("📋 نسخ الكود")
        btn_copy.clicked.connect(self._copy_code)
        btn_close = QPushButton("إغلاق")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _copy_code(self):
        QApplication.clipboard().setText(self._code_edit.toPlainText())
        QMessageBox.information(self, "تم", "تم نسخ الكود إلى الـ Clipboard!")


# ──────────────────────────────────────────────────────────────────────────────
# Helper: button style
# ──────────────────────────────────────────────────────────────────────────────

_BTN_STYLE = """
QPushButton {
    background: #374151; color: white;
    border: 1px solid #4B5563; border-radius: 6px;
    padding: 6px 14px; font-size: 12px;
}
QPushButton:hover { background: #4B5563; }
QPushButton:disabled { background: #1F2937; color: #6B7280; border-color: #374151; }
"""


def _secondary_btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(_BTN_STYLE)
    return b


# ──────────────────────────────────────────────────────────────────────────────
# Main page
# ──────────────────────────────────────────────────────────────────────────────

class SiteDashboardPage(BaseExtraPage):
    """
    Mini WordPress Site Dashboard.

    Lets the user manage Posts, Pages, Users, Plugins, Themes and common
    Options for the selected project without touching wp-admin.
    All write operations go through WP-CLI; the Options tab uses direct MySQL
    for fast reads and WP-CLI `option update` for safe writes.
    """

    # WordPress options shown in the Options tab by default
    _COMMON_OPTIONS = [
        "blogname", "blogdescription", "siteurl", "home",
        "admin_email", "blogpublic", "date_format", "time_format",
        "timezone_string", "permalink_structure",
        "default_comment_status", "default_ping_status",
        "posts_per_page", "users_can_register", "default_role",
    ]

    # Known multilingual plugin folder slugs → display name
    _MULTILINGUAL_SLUGS = {
        "sitepress-multilingual-cms": "WPML",
        "wpml-multilingual-cms": "WPML",
        "polylang": "Polylang",
        "translatepress-multilingual": "TranslatePress",
        "multilingualpress": "MultilingualPress",
        "qtranslate-xt": "qTranslate",
    }

    # Extra options exposed when WooCommerce is active
    _WOO_OPTIONS = [
        "woocommerce_currency", "woocommerce_currency_pos",
        "woocommerce_price_num_decimals", "woocommerce_price_thousand_sep",
        "woocommerce_price_decimal_sep", "woocommerce_default_country",
        "woocommerce_store_address", "woocommerce_calc_taxes",
        "woocommerce_enable_coupons", "woocommerce_shop_page_id",
        "woocommerce_cart_page_id", "woocommerce_checkout_page_id",
        "woocommerce_enable_guest_checkout", "woocommerce_enable_signup_and_login_from_checkout",
    ]

    # Extra options exposed when a multilingual plugin is active
    _MULTILANG_OPTIONS = [
        "WPLANG", "wpml_language_negotiation_type",
        "polylang",
    ]

    def __init__(self, store: ProjectsStore, parent_window):
        super().__init__(store, parent_window)

        # Remove the trailing stretch BaseExtraPage adds so our tab widget
        # can expand to fill the full available height.
        n = self.main_layout.count()
        if n > 0:
            last = self.main_layout.itemAt(n - 1)
            if last and last.spacerItem():
                self.main_layout.removeItem(last)

        # ── Site info header ──────────────────────────────────────────
        info_card, info_lay = make_card("", "")
        hdr = QHBoxLayout()

        self._lbl_title   = QLabel("—")
        self._lbl_title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #F9FAFB;")

        self._lbl_url     = QLabel("—")
        self._lbl_url.setStyleSheet("color: #60A5FA; font-size: 13px;")

        self._lbl_version = QLabel("")
        self._lbl_version.setStyleSheet("color: #9CA3AF; font-size: 12px;")

        btn_open  = _secondary_btn("🌐 فتح الموقع")
        btn_admin = _secondary_btn("⚙️ فتح لوحة الإدارة")
        btn_open.clicked.connect(self._open_site)
        btn_admin.clicked.connect(self._open_admin)

        hdr.addWidget(self._lbl_title)
        hdr.addWidget(QLabel("·"))
        hdr.addWidget(self._lbl_url)
        hdr.addWidget(QLabel("·"))
        hdr.addWidget(self._lbl_version)
        hdr.addStretch()
        hdr.addWidget(btn_open)
        hdr.addWidget(btn_admin)
        info_lay.addLayout(hdr)

        # ── Smart Site Profile bar ────────────────────────────────────
        self._profile_bar = QHBoxLayout()
        self._lbl_profile_store = QLabel("")
        self._lbl_profile_store.setVisible(False)
        self._lbl_profile_store.setStyleSheet(
            "background:#065F46; color:#6EE7B7; border-radius:4px;"
            "padding:2px 8px; font-size:11px; font-weight:600;")
        self._lbl_profile_lang = QLabel("")
        self._lbl_profile_lang.setVisible(False)
        self._lbl_profile_lang.setStyleSheet(
            "background:#1E3A5F; color:#93C5FD; border-radius:4px;"
            "padding:2px 8px; font-size:11px; font-weight:600;")
        self._lbl_profile_hint = QLabel("جاري تحليل الموقع…")
        self._lbl_profile_hint.setStyleSheet("color:#6B7280; font-size:11px;")
        self._lbl_profile_hint.setVisible(False)
        self._profile_bar.addWidget(self._lbl_profile_store)
        self._profile_bar.addWidget(self._lbl_profile_lang)
        self._profile_bar.addWidget(self._lbl_profile_hint)
        self._profile_bar.addStretch()
        info_lay.addLayout(self._profile_bar)
        self.content_area.addWidget(info_card)

        # Detected site profile: {"is_store": bool, "store_plugin": str,
        #                          "is_multilingual": bool, "lang_plugin": str}
        self._site_profile: dict = {}

        # ── Tab widget ────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setEnabled(False)
        self._tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_area.addWidget(self._tabs, 1)

        # ── Indeterminate progress bar (thin) ─────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)   # indeterminate spin
        self._progress.setFixedHeight(4)
        self.content_area.addWidget(self._progress)

        self._build_tabs()

        # Worker bookkeeping
        self._worker: _WPCLIWorker | None = None
        self._thread: QThread | None = None

    # ─────────────────────────────────────────────────────────────────
    # Tab construction
    # ─────────────────────────────────────────────────────────────────

    def _build_tabs(self):
        self._tabs.addTab(self._build_content_tab("post"),  "📝 المقالات")
        self._tabs.addTab(self._build_content_tab("page"),  "📄 الصفحات")
        self._tabs.addTab(self._build_users_tab(),           "👥 المستخدمون")
        self._tabs.addTab(self._build_plugins_tab(),         "🧩 الإضافات")
        self._tabs.addTab(self._build_themes_tab(),          "🎨 القوالب")
        self._tabs.addTab(self._build_options_tab(),         "⚙️ الخيارات")
        self._tabs.addTab(self._build_acf_tab(),             "🔧 حقول ACF")
        self._tabs.addTab(self._build_cpt_tab(),             "📋 أنواع المحتوى")
        self._tabs.addTab(self._build_comments_tab(),        "💬 التعليقات")
        self._tabs.addTab(self._build_taxonomies_tab(),      "🏷️ التصنيفات")
        self._tabs.addTab(self._build_quick_actions_tab(),   "⚡ إجراءات سريعة")
        self._tabs.currentChanged.connect(self._on_tab_changed)

    # ── Posts & Pages ─────────────────────────────────────────────────

    def _build_content_tab(self, post_type: str) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)

        label = "مقال" if post_type == "post" else "صفحة"
        btn_new     = PrimaryButton(f"➕ {label} جديد" if post_type == "post" else f"➕ {label} جديدة")
        btn_edit    = _secondary_btn("✏️ تعديل")
        btn_delete  = _secondary_btn("🗑️ حذف")
        btn_refresh = _secondary_btn("🔄 تحديث")

        row = QHBoxLayout()
        row.addWidget(btn_new)
        row.addWidget(btn_edit)
        row.addWidget(btn_delete)
        row.addStretch()
        row.addWidget(btn_refresh)
        vbox.addLayout(row)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["ID", "العنوان", "الحالة", "التاريخ"])
        hh = table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        vbox.addWidget(table, 1)

        # Wire by post_type
        if post_type == "post":
            self._posts_table = table
        else:
            self._pages_table = table

        btn_new.clicked.connect(
            lambda: self._new_content(post_type))
        btn_edit.clicked.connect(
            lambda: self._edit_content(post_type))
        btn_delete.clicked.connect(
            lambda: self._delete_content(post_type))
        btn_refresh.clicked.connect(
            lambda: self._load_content(post_type))

        return w

    # ── Users ─────────────────────────────────────────────────────────

    def _build_users_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)

        btn_new     = PrimaryButton("➕ مستخدم جديد")
        btn_delete  = _secondary_btn("🗑️ حذف المستخدم")
        btn_refresh = _secondary_btn("🔄 تحديث")

        row = QHBoxLayout()
        row.addWidget(btn_new)
        row.addWidget(btn_delete)
        row.addStretch()
        row.addWidget(btn_refresh)
        vbox.addLayout(row)

        self._users_table = QTableWidget()
        self._users_table.setColumnCount(5)
        self._users_table.setHorizontalHeaderLabels(
            ["ID", "اسم الدخول", "الاسم المعروض", "البريد الإلكتروني", "الدور"])
        self._users_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._users_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._users_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._users_table.setAlternatingRowColors(True)
        vbox.addWidget(self._users_table, 1)

        btn_new.clicked.connect(self._new_user)
        btn_delete.clicked.connect(self._delete_user)
        btn_refresh.clicked.connect(self._load_users)
        return w

    # ── Plugins ───────────────────────────────────────────────────────

    def _build_plugins_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)

        btn_toggle  = _secondary_btn("⚡ تفعيل / إلغاء التفعيل")
        btn_delete  = _secondary_btn("🗑️ حذف")
        btn_refresh = _secondary_btn("🔄 تحديث")

        row = QHBoxLayout()
        row.addWidget(btn_toggle)
        row.addWidget(btn_delete)
        row.addStretch()
        row.addWidget(btn_refresh)
        vbox.addLayout(row)

        self._plugins_table = QTableWidget()
        self._plugins_table.setColumnCount(4)
        self._plugins_table.setHorizontalHeaderLabels(
            ["Slug", "الحالة", "الإصدار", "تحديث"])
        hh = self._plugins_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._plugins_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._plugins_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._plugins_table.setAlternatingRowColors(True)
        vbox.addWidget(self._plugins_table, 1)

        btn_toggle.clicked.connect(self._toggle_plugin)
        btn_delete.clicked.connect(self._delete_plugin)
        btn_refresh.clicked.connect(self._load_plugins)
        return w

    # ── Themes ────────────────────────────────────────────────────────

    def _build_themes_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)

        btn_activate = PrimaryButton("✅ تفعيل القالب")
        btn_refresh  = _secondary_btn("🔄 تحديث")

        row = QHBoxLayout()
        row.addWidget(btn_activate)
        row.addStretch()
        row.addWidget(btn_refresh)
        vbox.addLayout(row)

        self._themes_table = QTableWidget()
        self._themes_table.setColumnCount(3)
        self._themes_table.setHorizontalHeaderLabels(
            ["الاسم", "الحالة", "الإصدار"])
        hh = self._themes_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._themes_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._themes_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._themes_table.setAlternatingRowColors(True)
        vbox.addWidget(self._themes_table, 1)

        btn_activate.clicked.connect(self._activate_theme)
        btn_refresh.clicked.connect(self._load_themes)
        return w

    # ── Options ───────────────────────────────────────────────────────

    def _build_options_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)

        btn_edit    = _secondary_btn("✏️ تعديل الخيار")
        btn_refresh = _secondary_btn("🔄 تحديث")

        row = QHBoxLayout()
        row.addWidget(btn_edit)
        row.addStretch()
        row.addWidget(btn_refresh)
        vbox.addLayout(row)

        hint = QLabel(
            "خيارات ووردبريس الشائعة — انقر نقراً مزدوجاً على صف لتعديله.  "
            "🟢 WooCommerce   🔵 تعدد اللغات")
        hint.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        vbox.addWidget(hint)

        self._options_table = QTableWidget()
        self._options_table.setColumnCount(2)
        self._options_table.setHorizontalHeaderLabels(
            ["اسم الخيار", "القيمة"])
        hh = self._options_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._options_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._options_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._options_table.setAlternatingRowColors(True)
        self._options_table.doubleClicked.connect(
            lambda _: self._edit_option())
        vbox.addWidget(self._options_table, 1)

        btn_edit.clicked.connect(self._edit_option)
        btn_refresh.clicked.connect(self._load_options)
        return w

    # ─────────────────────────────────────────────────────────────────
    # BaseExtraPage hooks
    # ─────────────────────────────────────────────────────────────────

    def _on_project_selected(self, p: ProjectRecord):
        self._tabs.setEnabled(True)
        self._load_site_info(p)
        self._refresh_active_tab()

    def _on_project_cleared(self):
        self._tabs.setEnabled(False)
        self._lbl_title.setText("—")
        self._lbl_url.setText("—")
        self._lbl_version.setText("")

    # ─────────────────────────────────────────────────────────────────
    # Tab change
    # ─────────────────────────────────────────────────────────────────

    def _on_tab_changed(self, idx: int):
        if not self.current:
            return
        loaders = {
            0: lambda: self._load_content("post"),
            1: lambda: self._load_content("page"),
            2: self._load_users,
            3: self._load_plugins,
            4: self._load_themes,
            5: self._load_options,
            6: self._load_acf_groups,
            7: self._load_cpt_list,
            8: self._load_comments,
            9: self._load_taxonomies,
            # index 10 (Quick Actions) needs no auto-load
        }
        fn = loaders.get(idx)
        if fn:
            fn()

    def _refresh_active_tab(self):
        self._on_tab_changed(self._tabs.currentIndex())

    # ─────────────────────────────────────────────────────────────────
    # Site info header
    # ─────────────────────────────────────────────────────────────────

    def _load_site_info(self, p: ProjectRecord):
        self._lbl_url.setText(p.url or "—")

        # Blog title from DB
        try:
            db_pass = getattr(p, "db_pass", "")
            conn = mysql_connect(p.db_host, p.db_port, p.db_user, db_pass)
            prefix = p.table_prefix or "wp_"
            with conn.cursor() as cur:
                cur.execute(f"USE `{p.db_name}`")
                cur.execute(
                    f"SELECT option_value FROM `{prefix}options` "
                    f"WHERE option_name='blogname' LIMIT 1")
                row = cur.fetchone()
                self._lbl_title.setText(row[0] if row else p.name)
            conn.close()
        except Exception:
            self._lbl_title.setText(p.name)

        # WP version from wp-includes/version.php
        try:
            vfile = Path(p.path) / "wp-includes" / "version.php"
            if vfile.exists():
                m = re.search(
                    r"\$wp_version\s*=\s*'([^']+)'",
                    vfile.read_text(encoding="utf-8", errors="ignore"))
                if m:
                    self._lbl_version.setText(f"WordPress {m.group(1)}")
        except Exception:
            pass

        # Trigger smart site detection
        self._lbl_profile_hint.setVisible(True)
        self._lbl_profile_store.setVisible(False)
        self._lbl_profile_lang.setVisible(False)
        self._detect_site_profile(p)

    def _detect_site_profile(self, p: ProjectRecord):
        """Detect WooCommerce and multilingual plugins from DB and update profile bar."""
        profile: dict = {"is_store": False, "store_plugin": "",
                         "is_multilingual": False, "lang_plugin": ""}
        try:
            db_pass = getattr(p, "db_pass", "")
            conn = mysql_connect(p.db_host, p.db_port, p.db_user, db_pass)
            prefix = p.table_prefix or "wp_"
            with conn.cursor() as cur:
                cur.execute(f"USE `{p.db_name}`")
                cur.execute(
                    f"SELECT option_value FROM `{prefix}options` "
                    f"WHERE option_name='active_plugins' LIMIT 1")
                row = cur.fetchone()
            conn.close()

            active_raw = str(row[0]) if row and row[0] else ""

            # WooCommerce detection
            if "woocommerce/woocommerce.php" in active_raw:
                profile["is_store"] = True
                profile["store_plugin"] = "WooCommerce"

            # Multilingual plugin detection
            for slug, name in self._MULTILINGUAL_SLUGS.items():
                if f'"{slug}/' in active_raw or f"'{slug}/" in active_raw:
                    profile["is_multilingual"] = True
                    profile["lang_plugin"] = name
                    break

        except Exception:
            pass

        self._site_profile = profile
        self._lbl_profile_hint.setVisible(False)

        if profile["is_store"]:
            self._lbl_profile_store.setText(f"🛒 {profile['store_plugin']}")
            self._lbl_profile_store.setVisible(True)
        if profile["is_multilingual"]:
            self._lbl_profile_lang.setText(f"🌐 {profile['lang_plugin']}")
            self._lbl_profile_lang.setVisible(True)

        if not profile["is_store"] and not profile["is_multilingual"]:
            self._lbl_profile_hint.setText("موقع عادي — لا يوجد متجر أو تعدد لغات")
            self._lbl_profile_hint.setVisible(True)

    # ─────────────────────────────────────────────────────────────────
    # WP-CLI async helper
    # ─────────────────────────────────────────────────────────────────

    def _get_tooling(self) -> tuple[str, str, bool] | None:
        if not self.current:
            return None
        try:
            php, wpcli, is_phar = get_effective_tooling(self.current)
            return (php, wpcli, is_phar) if wpcli else None
        except Exception:
            return None

    def _run_async(self, args: list[str], callback):
        """
        Fire a WP-CLI command in a background QThread.
        callback(ok: bool, output: str) is called on completion (in main thread
        via Qt signal).
        """
        tooling = self._get_tooling()
        if not tooling:
            QMessageBox.warning(
                self, "WP-CLI غير متوفر",
                "لم يتم العثور على PHP أو WP-CLI.\n"
                "تأكد من تثبيتهما أو أن المشروع يحتوي على .tools/wp-cli.phar")
            return

        if self._thread and self._thread.isRunning():
            QMessageBox.warning(
                self, "جاري التنفيذ",
                "عملية أخرى قيد التشغيل بالفعل، يرجى الانتظار.")
            return

        php, wpcli, is_phar = tooling
        self._worker = _WPCLIWorker(
            self.current.path, php, wpcli, is_phar, args)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(
            lambda ok, out: self._on_async_done(ok, out, callback))
        self._worker.done.connect(self._thread.quit)
        self._thread.start()
        self._progress.setVisible(True)

    def _on_async_done(self, ok: bool, output: str, callback):
        self._progress.setVisible(False)
        callback(ok, output)

    # ─────────────────────────────────────────────────────────────────
    # Shared JSON parser
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(output: str) -> list[dict]:
        m = re.search(r'\[.*\]', output, re.DOTALL)
        raw = m.group(0) if m else output
        return json.loads(raw)

    # ─────────────────────────────────────────────────────────────────
    # Posts / Pages
    # ─────────────────────────────────────────────────────────────────

    def _load_content(self, post_type: str):
        if not self.current:
            return
        table = self._posts_table if post_type == "post" else self._pages_table
        table.setRowCount(0)
        args = [
            "post", "list",
            f"--post_type={post_type}",
            "--format=json",
            "--fields=ID,post_title,post_status,post_date",
            "--posts_per_page=200",
        ]
        self._run_async(
            args,
            lambda ok, out: self._fill_content_table(table, ok, out))

    def _fill_content_table(self, table: QTableWidget,
                            ok: bool, output: str):
        if not ok:
            QMessageBox.warning(
                self, "خطأ", f"فشل تحميل المحتوى:\n{output[:600]}")
            return
        try:
            posts = self._parse_json(output)
            table.setRowCount(len(posts))
            for i, p in enumerate(posts):
                id_item = QTableWidgetItem(str(p.get("ID", "")))
                id_item.setData(Qt.ItemDataRole.UserRole, p)
                table.setItem(i, 0, id_item)
                table.setItem(i, 1, QTableWidgetItem(
                    str(p.get("post_title", ""))))
                status = str(p.get("post_status", ""))
                s_item = QTableWidgetItem(status)
                if status == "publish":
                    s_item.setForeground(Qt.GlobalColor.green)
                elif status == "draft":
                    s_item.setForeground(Qt.GlobalColor.yellow)
                table.setItem(i, 2, s_item)
                table.setItem(i, 3, QTableWidgetItem(
                    str(p.get("post_date", ""))[:10]))
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ في التحليل",
                f"لا يمكن قراءة بيانات المحتوى:\n{exc}")

    def _new_content(self, post_type: str):
        if not self.current:
            return
        dlg = _PostEditDialog(post_type, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        if not d["title"]:
            QMessageBox.warning(self, "مطلوب", "العنوان مطلوب.")
            return
        args = [
            "post", "create",
            f"--post_type={post_type}",
            f"--post_title={d['title']}",
            f"--post_status={d['status']}",
            f"--post_content={d['content']}",
        ]
        if d["excerpt"]:
            args.append(f"--post_excerpt={d['excerpt']}")
        self._run_async(
            args,
            lambda ok, out: self._after_content_op(ok, out, post_type))

    def _edit_content(self, post_type: str):
        if not self.current:
            return
        table = self._posts_table if post_type == "post" else self._pages_table
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "اختر", "اختر عنصراً للتعديل.")
            return
        id_item = table.item(row, 0)
        post_data: dict = id_item.data(Qt.ItemDataRole.UserRole) if id_item else {}
        post_id = str(post_data.get("ID", ""))
        if not post_id:
            return

        dlg = _PostEditDialog(post_type, post_data, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        args = [
            "post", "update", post_id,
            f"--post_title={d['title']}",
            f"--post_status={d['status']}",
            f"--post_content={d['content']}",
        ]
        if d["excerpt"]:
            args.append(f"--post_excerpt={d['excerpt']}")
        self._run_async(
            args,
            lambda ok, out: self._after_content_op(ok, out, post_type))

    def _delete_content(self, post_type: str):
        if not self.current:
            return
        table = self._posts_table if post_type == "post" else self._pages_table
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "اختر", "اختر عنصراً للحذف.")
            return
        id_item = table.item(row, 0)
        post_data: dict = id_item.data(Qt.ItemDataRole.UserRole) if id_item else {}
        post_id   = str(post_data.get("ID", ""))
        post_title = (table.item(row, 1).text()
                      if table.item(row, 1) else post_id)
        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"هل تريد حذف '{post_title}' بشكل نهائي؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_async(
            ["post", "delete", post_id, "--force"],
            lambda ok, out: self._after_content_op(ok, out, post_type))

    def _after_content_op(self, ok: bool, output: str, post_type: str):
        if ok:
            self._load_content(post_type)
        else:
            QMessageBox.warning(
                self, "فشلت العملية", f"{output[:600]}")

    # ─────────────────────────────────────────────────────────────────
    # Users
    # ─────────────────────────────────────────────────────────────────

    def _load_users(self):
        if not self.current:
            return
        self._users_table.setRowCount(0)
        self._run_async(
            ["user", "list", "--format=json",
             "--fields=ID,user_login,display_name,user_email,roles"],
            self._fill_users_table)

    def _fill_users_table(self, ok: bool, output: str):
        if not ok:
            QMessageBox.warning(
                self, "خطأ", f"فشل تحميل المستخدمين:\n{output[:600]}")
            return
        try:
            users = self._parse_json(output)
            self._users_table.setRowCount(len(users))
            for i, u in enumerate(users):
                id_item = QTableWidgetItem(str(u.get("ID", "")))
                id_item.setData(Qt.ItemDataRole.UserRole, u)
                self._users_table.setItem(i, 0, id_item)
                self._users_table.setItem(
                    i, 1, QTableWidgetItem(str(u.get("user_login", ""))))
                self._users_table.setItem(
                    i, 2, QTableWidgetItem(str(u.get("display_name", ""))))
                self._users_table.setItem(
                    i, 3, QTableWidgetItem(str(u.get("user_email", ""))))
                self._users_table.setItem(
                    i, 4, QTableWidgetItem(str(u.get("roles", ""))))
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ في التحليل",
                f"لا يمكن قراءة بيانات المستخدمين:\n{exc}")

    def _new_user(self):
        if not self.current:
            return
        dlg = _UserCreateDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        if not d["username"] or not d["email"]:
            QMessageBox.warning(self, "مطلوب",
                                "اسم المستخدم والبريد الإلكتروني مطلوبان.")
            return
        args = [
            "user", "create",
            d["username"], d["email"],
            f"--user_pass={d['password']}",
            f"--role={d['role']}",
        ]
        if d["first_name"]:
            args.append(f"--first_name={d['first_name']}")
        if d["last_name"]:
            args.append(f"--last_name={d['last_name']}")
        self._run_async(
            args,
            lambda ok, out: (
                self._load_users() if ok else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم إنشاء المستخدم:\n{out[:600]}")))

    def _delete_user(self):
        if not self.current:
            return
        row = self._users_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "اختر", "اختر مستخدماً للحذف.")
            return
        id_item = self._users_table.item(row, 0)
        user_data: dict = id_item.data(Qt.ItemDataRole.UserRole) if id_item else {}
        user_id = str(user_data.get("ID", ""))
        login   = (self._users_table.item(row, 1).text()
                   if self._users_table.item(row, 1) else user_id)
        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"حذف المستخدم '{login}'؟ (المحتوى يبقى كما هو)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_async(
            ["user", "delete", user_id, "--yes"],
            lambda ok, out: (
                self._load_users() if ok else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم حذف المستخدم:\n{out[:600]}")))

    # ─────────────────────────────────────────────────────────────────
    # Plugins
    # ─────────────────────────────────────────────────────────────────

    def _load_plugins(self):
        if not self.current:
            return
        self._plugins_table.setRowCount(0)
        self._run_async(
            ["plugin", "list", "--format=json"],
            self._fill_plugins_table)

    def _fill_plugins_table(self, ok: bool, output: str):
        if not ok:
            QMessageBox.warning(
                self, "خطأ", f"فشل تحميل الإضافات:\n{output[:600]}")
            return
        try:
            plugins = self._parse_json(output)
            self._plugins_table.setRowCount(len(plugins))
            for i, pl in enumerate(plugins):
                name_item = QTableWidgetItem(str(pl.get("name", "")))
                name_item.setData(Qt.ItemDataRole.UserRole, pl)
                self._plugins_table.setItem(i, 0, name_item)

                status = str(pl.get("status", ""))
                s_item = QTableWidgetItem(status)
                if status == "active":
                    s_item.setForeground(Qt.GlobalColor.green)
                else:
                    s_item.setForeground(Qt.GlobalColor.gray)
                self._plugins_table.setItem(i, 1, s_item)
                self._plugins_table.setItem(
                    i, 2, QTableWidgetItem(str(pl.get("version", ""))))
                upd = str(pl.get("update", "none"))
                u_item = QTableWidgetItem(upd)
                if upd == "available":
                    u_item.setForeground(Qt.GlobalColor.yellow)
                self._plugins_table.setItem(i, 3, u_item)
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ في التحليل",
                f"لا يمكن قراءة بيانات الإضافات:\n{exc}")

    def _toggle_plugin(self):
        if not self.current:
            return
        row = self._plugins_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "اختر", "اختر إضافة.")
            return
        pl_data: dict = (self._plugins_table.item(row, 0)
                         .data(Qt.ItemDataRole.UserRole) or {})
        name   = pl_data.get("name", "")
        status = pl_data.get("status", "inactive")
        action = "deactivate" if status == "active" else "activate"
        self._run_async(
            ["plugin", action, name],
            lambda ok, out: (
                self._load_plugins() if ok else
                QMessageBox.warning(
                    self, "فشل",
                    f"لم يتم تنفيذ الإجراء:\n{out[:600]}")))

    def _delete_plugin(self):
        if not self.current:
            return
        row = self._plugins_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "اختر", "اختر إضافة للحذف.")
            return
        pl_data: dict = (self._plugins_table.item(row, 0)
                         .data(Qt.ItemDataRole.UserRole) or {})
        name = pl_data.get("name", "")
        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"هل تريد حذف الإضافة '{name}' بشكل كامل؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_async(
            ["plugin", "delete", name],
            lambda ok, out: (
                self._load_plugins() if ok else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم حذف الإضافة:\n{out[:600]}")))

    # ─────────────────────────────────────────────────────────────────
    # Themes
    # ─────────────────────────────────────────────────────────────────

    def _load_themes(self):
        if not self.current:
            return
        self._themes_table.setRowCount(0)
        self._run_async(
            ["theme", "list", "--format=json"],
            self._fill_themes_table)

    def _fill_themes_table(self, ok: bool, output: str):
        if not ok:
            QMessageBox.warning(
                self, "خطأ", f"فشل تحميل القوالب:\n{output[:600]}")
            return
        try:
            themes = self._parse_json(output)
            self._themes_table.setRowCount(len(themes))
            for i, t in enumerate(themes):
                name_item = QTableWidgetItem(str(t.get("name", "")))
                name_item.setData(Qt.ItemDataRole.UserRole, t)
                self._themes_table.setItem(i, 0, name_item)
                status = str(t.get("status", ""))
                s_item = QTableWidgetItem(status)
                if status == "active":
                    s_item.setForeground(Qt.GlobalColor.green)
                self._themes_table.setItem(i, 1, s_item)
                self._themes_table.setItem(
                    i, 2, QTableWidgetItem(str(t.get("version", ""))))
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ في التحليل",
                f"لا يمكن قراءة بيانات القوالب:\n{exc}")

    def _activate_theme(self):
        if not self.current:
            return
        row = self._themes_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "اختر", "اختر قالباً لتفعيله.")
            return
        t_data: dict = (self._themes_table.item(row, 0)
                        .data(Qt.ItemDataRole.UserRole) or {})
        name = t_data.get("name", "")
        self._run_async(
            ["theme", "activate", name],
            lambda ok, out: (
                self._load_themes() if ok else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم تفعيل القالب:\n{out[:600]}")))

    # ─────────────────────────────────────────────────────────────────
    # Options  (read = direct MySQL  |  write = WP-CLI option update)
    # ─────────────────────────────────────────────────────────────────

    def _load_options(self):
        if not self.current:
            return
        self._options_table.setRowCount(0)
        p = self.current

        # Build smart options list based on detected site profile
        options_to_load = list(self._COMMON_OPTIONS)
        profile = getattr(self, "_site_profile", {})
        if profile.get("is_store"):
            for opt in self._WOO_OPTIONS:
                if opt not in options_to_load:
                    options_to_load.append(opt)
        if profile.get("is_multilingual"):
            for opt in self._MULTILANG_OPTIONS:
                if opt not in options_to_load:
                    options_to_load.append(opt)

        try:
            db_pass = getattr(p, "db_pass", "")
            conn = mysql_connect(p.db_host, p.db_port, p.db_user, db_pass)
            prefix = p.table_prefix or "wp_"
            with conn.cursor() as cur:
                cur.execute(f"USE `{p.db_name}`")
                ph = ", ".join(["%s"] * len(options_to_load))
                cur.execute(
                    f"SELECT option_name, option_value FROM `{prefix}options` "
                    f"WHERE option_name IN ({ph}) ORDER BY option_name",
                    options_to_load)
                rows = cur.fetchall()
            conn.close()

            # Color-code rows by category
            woo_set = set(self._WOO_OPTIONS)
            lang_set = set(self._MULTILANG_OPTIONS)
            self._options_table.setRowCount(len(rows))
            for i, (opt_name, opt_val) in enumerate(rows):
                n_item = QTableWidgetItem(opt_name)
                n_item.setData(Qt.ItemDataRole.UserRole, opt_name)
                if opt_name in woo_set:
                    n_item.setForeground(Qt.GlobalColor.green)
                elif opt_name in lang_set:
                    n_item.setForeground(Qt.GlobalColor.cyan)
                self._options_table.setItem(i, 0, n_item)
                val_str = str(opt_val) if opt_val is not None else ""
                display = val_str[:200] + ("…" if len(val_str) > 200 else "")
                self._options_table.setItem(i, 1, QTableWidgetItem(display))
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ في قاعدة البيانات",
                f"لا يمكن تحميل الإعدادات:\n{exc}")

    def _edit_option(self):
        if not self.current:
            return
        row = self._options_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "اختر", "اختر خياراً للتعديل.")
            return
        n_item = self._options_table.item(row, 0)
        if not n_item:
            return
        opt_name: str = n_item.data(Qt.ItemDataRole.UserRole) or n_item.text()

        # Fetch the full (possibly long) value from the DB
        p = self.current
        try:
            db_pass = getattr(p, "db_pass", "")
            conn = mysql_connect(p.db_host, p.db_port, p.db_user, db_pass)
            prefix = p.table_prefix or "wp_"
            with conn.cursor() as cur:
                cur.execute(f"USE `{p.db_name}`")
                cur.execute(
                    f"SELECT option_value FROM `{prefix}options` "
                    f"WHERE option_name=%s LIMIT 1", (opt_name,))
                r = cur.fetchone()
                full_val = str(r[0]) if r and r[0] is not None else ""
            conn.close()
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ", f"لا يمكن تحميل قيمة الخيار:\n{exc}")
            return

        dlg = _OptionEditDialog(opt_name, full_val, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_val = dlg.get_value()
        # Use WP-CLI so WordPress can handle serialised values correctly
        self._run_async(
            ["option", "update", opt_name, new_val],
            lambda ok, out: (
                self._load_options() if ok else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم حفظ الخيار:\n{out[:600]}")))

    # ─────────────────────────────────────────────────────────────────
    # Quick-open helpers
    # ─────────────────────────────────────────────────────────────────

    def _open_site(self):
        if self.current:
            import webbrowser
            webbrowser.open(self.current.url)

    def _open_admin(self):
        if self.current:
            import webbrowser
            webbrowser.open(self.current.admin_url)

    # ═════════════════════════════════════════════════════════════════
    # ██  ACF FIELDS TAB
    # ═════════════════════════════════════════════════════════════════

    # ── Field type options offered in the "Add Field" dialog ─────────
    _ACF_FIELD_TYPES = [
        ("text",         "نص"),
        ("textarea",     "نص متعدد الأسطر"),
        ("number",       "رقم"),
        ("email",        "بريد إلكتروني"),
        ("url",          "رابط (URL)"),
        ("password",     "كلمة مرور"),
        ("image",        "صورة"),
        ("file",         "ملف"),
        ("gallery",      "معرض صور"),
        ("wysiwyg",      "محرر WYSIWYG"),
        ("oembed",       "oEmbed"),
        ("select",       "قائمة اختيار"),
        ("checkbox",     "مربع اختيار"),
        ("radio",        "زر اختيار (Radio)"),
        ("button_group", "مجموعة أزرار"),
        ("true_false",   "صح / خطأ"),
        ("link",         "رابط"),
        ("post_object",  "كائن مقال (Post Object)"),
        ("page_link",    "رابط صفحة"),
        ("relationship", "علاقة (Relationship)"),
        ("taxonomy",     "تصنيف"),
        ("user",         "مستخدم"),
        ("date_picker",  "منتقي تاريخ"),
        ("date_time_picker", "منتقي تاريخ ووقت"),
        ("time_picker",  "منتقي وقت"),
        ("color_picker", "منتقي لون"),
        ("group",        "مجموعة"),
        ("repeater",     "متكرر (Repeater)"),
        ("flexible_content", "محتوى مرن (Flexible Content)"),
    ]

    # ── ACF tab builder ───────────────────────────────────────────────

    def _build_acf_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)
        vbox.setSpacing(8)

        # ── ACF status label ──────────────────────────────────────────
        self._acf_status_lbl = QLabel(
            "⚠️  لم يتم اكتشاف ACF بعد — اختر مشروعاً للتحقق")
        self._acf_status_lbl.setStyleSheet(
            "color: #9CA3AF; font-size: 12px; padding: 4px;")
        vbox.addWidget(self._acf_status_lbl)

        # ── Splitter: left = groups list  |  right = fields list ─────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left pane — field groups
        left = QWidget()
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(0, 0, 4, 0)

        grp_btn_row = QHBoxLayout()
        btn_new_group   = PrimaryButton("➕ مجموعة جديدة")
        btn_edit_group  = _secondary_btn("✏️ تعديل")
        btn_del_group   = _secondary_btn("🗑️ حذف")
        btn_ref_groups  = _secondary_btn("🔄")
        btn_ref_groups.setFixedWidth(36)
        grp_btn_row.addWidget(btn_new_group)
        grp_btn_row.addWidget(btn_edit_group)
        grp_btn_row.addWidget(btn_del_group)
        grp_btn_row.addStretch()
        grp_btn_row.addWidget(btn_ref_groups)
        left_v.addLayout(grp_btn_row)

        left_v.addWidget(QLabel("مجموعات الحقول:"))
        self._acf_groups_list = QListWidget()
        self._acf_groups_list.setAlternatingRowColors(True)
        left_v.addWidget(self._acf_groups_list, 1)

        # Right pane — fields in selected group
        right = QWidget()
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(4, 0, 0, 0)

        fld_btn_row = QHBoxLayout()
        btn_new_field    = PrimaryButton("➕ حقل جديد")
        btn_edit_field   = _secondary_btn("✏️ تعديل")
        btn_del_field    = _secondary_btn("🗑️ حذف")
        btn_show_code    = _secondary_btn("🖥️ كود PHP")
        btn_all_code     = _secondary_btn("📋 كود الكل")
        btn_ask_ai       = _secondary_btn("🤖 اسأل AI")
        for b in [btn_edit_field, btn_del_field, btn_show_code, btn_all_code, btn_ask_ai]:
            b.setStyleSheet(_BTN_STYLE)
        fld_btn_row.addWidget(btn_new_field)
        fld_btn_row.addWidget(btn_edit_field)
        fld_btn_row.addWidget(btn_del_field)
        fld_btn_row.addWidget(btn_show_code)
        fld_btn_row.addWidget(btn_all_code)
        fld_btn_row.addWidget(btn_ask_ai)
        fld_btn_row.addStretch()
        right_v.addLayout(fld_btn_row)

        right_v.addWidget(QLabel("الحقول في المجموعة المختارة:"))
        self._acf_fields_table = QTableWidget()
        self._acf_fields_table.setColumnCount(4)
        self._acf_fields_table.setHorizontalHeaderLabels(
            ["التسمية", "الاسم (slug)", "النوع", "المفتاح"])
        hh = self._acf_fields_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._acf_fields_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._acf_fields_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._acf_fields_table.setAlternatingRowColors(True)
        self._acf_fields_table.doubleClicked.connect(
            lambda _: self._edit_acf_field())
        right_v.addWidget(self._acf_fields_table, 1)

        # ── Auto code preview panel ───────────────────────────────────
        code_hdr = QHBoxLayout()
        code_hdr.addWidget(QLabel("⚡ كود الفرونت (تلقائي):"))
        btn_copy_preview = _secondary_btn("📋 نسخ")
        btn_copy_preview.setFixedWidth(70)
        code_hdr.addStretch()
        code_hdr.addWidget(btn_copy_preview)
        right_v.addLayout(code_hdr)

        self._acf_code_preview = QTextEdit()
        self._acf_code_preview.setReadOnly(True)
        self._acf_code_preview.setFixedHeight(160)
        self._acf_code_preview.setPlaceholderText(
            "← اختر حقلاً من الجدول لعرض كود PHP الخاص به هنا تلقائياً")
        self._acf_code_preview.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 11px; background: #0F172A; color: #86EFAC;"
            "border: 1px solid #1E3A5F; border-radius: 6px; padding: 6px;")
        right_v.addWidget(self._acf_code_preview)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([260, 500])
        vbox.addWidget(splitter, 1)

        # ── Wire signals ──────────────────────────────────────────────
        btn_new_group.clicked.connect(self._new_acf_group)
        btn_edit_group.clicked.connect(self._edit_acf_group)
        btn_del_group.clicked.connect(self._delete_acf_group)
        btn_ref_groups.clicked.connect(self._load_acf_groups)
        btn_new_field.clicked.connect(self._new_acf_field)
        btn_edit_field.clicked.connect(self._edit_acf_field)
        btn_del_field.clicked.connect(self._delete_acf_field)
        btn_show_code.clicked.connect(self._show_acf_field_code)
        btn_all_code.clicked.connect(self._show_acf_group_code)
        btn_ask_ai.clicked.connect(self._acf_ask_ai)
        btn_copy_preview.clicked.connect(self._copy_acf_preview)
        self._acf_groups_list.currentRowChanged.connect(
            self._on_acf_group_selected)
        self._acf_groups_list.doubleClicked.connect(
            lambda _: self._edit_acf_group())
        self._acf_fields_table.itemSelectionChanged.connect(
            lambda: self._on_acf_field_selected(
                self._acf_fields_table.currentRow()))

        return w

    # ── ACF helpers ───────────────────────────────────────────────────

    def _acf_json_dir(self) -> Path | None:
        """Returns the acf-json folder path (creates it + mu-plugin if missing)."""
        if not self.current:
            return None
        d = Path(self.current.path) / "wp-content" / "acf-json"
        d.mkdir(parents=True, exist_ok=True)
        # Ensure a mu-plugin registers this path with ACF so fields appear in WP admin
        self._ensure_acf_mu_plugin(Path(self.current.path))
        return d

    def _ensure_acf_mu_plugin(self, wp_root: Path):
        """Write a mu-plugin that tells ACF to load/save JSON from wp-content/acf-json/."""
        mu_dir = wp_root / "wp-content" / "mu-plugins"
        mu_dir.mkdir(parents=True, exist_ok=True)
        mu_file = mu_dir / "harmulizer-acf-json.php"
        if mu_file.exists():
            return
        mu_file.write_text(
            "<?php\n"
            "/**\n"
            " * Register ACF local JSON path.\n"
            " * Auto-generated by Harmulizer Pro — do not edit manually.\n"
            " */\n"
            "add_filter('acf/settings/load_json', function($paths) {\n"
            "    $paths[] = WP_CONTENT_DIR . '/acf-json';\n"
            "    return $paths;\n"
            "});\n"
            "add_filter('acf/settings/save_json', function($path) {\n"
            "    return WP_CONTENT_DIR . '/acf-json';\n"
            "});\n",
            encoding="utf-8",
        )

    def _is_acf_present(self) -> bool:
        """Quick check: plugin dir or DB post_type exists."""
        if not self.current:
            return False
        p = self.current
        plugins_dir = Path(p.path) / "wp-content" / "plugins"
        for slug in ("advanced-custom-fields", "advanced-custom-fields-pro",
                     "acf"):
            if (plugins_dir / slug).exists():
                return True
        # DB fallback
        try:
            db_pass = getattr(p, "db_pass", "")
            conn = mysql_connect(p.db_host, p.db_port, p.db_user, db_pass)
            prefix = p.table_prefix or "wp_"
            with conn.cursor() as cur:
                cur.execute(f"USE `{p.db_name}`")
                cur.execute(
                    f"SELECT COUNT(*) FROM `{prefix}posts` "
                    f"WHERE post_type='acf-field-group' LIMIT 1")
            conn.close()
            return True
        except Exception:
            return False

    @staticmethod
    def _gen_acf_key(prefix: str = "group") -> str:
        """Generate a unique ACF key like group_XXXXXXXXXXXXXXXX."""
        rand = secrets.token_hex(8)
        return f"{prefix}_{rand}"

    def _load_acf_groups(self):
        """Load ACF field groups from acf-json folder or DB."""
        if not self.current:
            return
        self._acf_groups_list.clear()
        self._acf_fields_table.setRowCount(0)

        present = self._is_acf_present()
        self._acf_status_lbl.setText(
            "✅  ACF مُكتشف ونشط" if present
            else "⚠️  لم يتم اكتشاف ACF — الوظائف محدودة")
        self._acf_status_lbl.setStyleSheet(
            f"color: {'#34D399' if present else '#F59E0B'};"
            f" font-size: 12px; padding: 4px;")

        # Try acf-json folder first (most reliable)
        acf_dir = self._acf_json_dir()
        groups = []
        if acf_dir and acf_dir.exists():
            for jf in sorted(acf_dir.glob("group_*.json")):
                try:
                    data = json.loads(jf.read_text(encoding="utf-8"))
                    groups.append({
                        "key":    data.get("key", jf.stem),
                        "title":  data.get("title", jf.stem),
                        "file":   str(jf),
                        "data":   data,
                        "source": "json",
                    })
                except Exception:
                    pass

        # Fall back to DB
        if not groups:
            try:
                p = self.current
                db_pass = getattr(p, "db_pass", "")
                conn = mysql_connect(p.db_host, p.db_port, p.db_user, db_pass)
                prefix = p.table_prefix or "wp_"
                with conn.cursor() as cur:
                    cur.execute(f"USE `{p.db_name}`")
                    cur.execute(
                        f"SELECT ID, post_title, post_name, post_content "
                        f"FROM `{prefix}posts` WHERE post_type='acf-field-group' "
                        f"AND post_status NOT IN ('trash') ORDER BY post_title")
                    rows = cur.fetchall()
                conn.close()
                for row_id, title, post_name, content in rows:
                    try:
                        grp_data = json.loads(content) if content.strip().startswith("{") else {}
                    except Exception:
                        grp_data = {}
                    groups.append({
                        "key":    post_name or f"group_{row_id}",
                        "title":  title,
                        "db_id":  row_id,
                        "data":   grp_data,
                        "source": "db",
                    })
            except Exception as exc:
                QMessageBox.warning(
                    self, "خطأ في قاعدة البيانات", f"لا يمكن تحميل مجموعات ACF:\n{exc}")

        for g in groups:
            item = QListWidgetItem(
                f"{'📂' if g['source'] == 'json' else '🗄️'}  {g['title']}")
            item.setData(Qt.ItemDataRole.UserRole, g)
            self._acf_groups_list.addItem(item)

        if groups:
            self._acf_groups_list.setCurrentRow(0)

    def _on_acf_group_selected(self, row: int):
        item = self._acf_groups_list.item(row)
        if not item:
            self._acf_fields_table.setRowCount(0)
            return
        group = item.data(Qt.ItemDataRole.UserRole)
        self._load_acf_fields_for_group(group)

    def _load_acf_fields_for_group(self, group: dict):
        self._acf_fields_table.setRowCount(0)
        fields: list[dict] = []

        # From JSON file
        if group.get("source") == "json" and group.get("data"):
            fields = group["data"].get("fields", [])

        # From DB
        elif group.get("source") == "db" and group.get("db_id"):
            try:
                p = self.current
                db_pass = getattr(p, "db_pass", "")
                conn = mysql_connect(p.db_host, p.db_port, p.db_user, db_pass)
                prefix = p.table_prefix or "wp_"
                with conn.cursor() as cur:
                    cur.execute(f"USE `{p.db_name}`")
                    cur.execute(
                        f"SELECT post_title, post_name, post_content "
                        f"FROM `{prefix}posts` "
                        f"WHERE post_type='acf-field' "
                        f"AND post_parent=%s "
                        f"ORDER BY menu_order, post_title",
                        (group["db_id"],))
                    rows = cur.fetchall()
                conn.close()
                for title, post_name, content in rows:
                    ftype = "text"
                    fname = post_name
                    # Parse PHP-serialized or JSON content
                    try:
                        fd = json.loads(content)
                        ftype = fd.get("type", "text")
                        fname = fd.get("name", post_name)
                    except Exception:
                        # regex fallback on PHP-serialized string
                        m = re.search(r's:4:"type";s:\d+:"([^"]+)"', content)
                        if m:
                            ftype = m.group(1)
                        m2 = re.search(r's:4:"name";s:\d+:"([^"]+)"', content)
                        if m2:
                            fname = m2.group(1)
                    fields.append({
                        "key":   post_name,
                        "label": title,
                        "name":  fname,
                        "type":  ftype,
                    })
            except Exception as exc:
                QMessageBox.warning(
                    self, "خطأ في قاعدة البيانات", f"لا يمكن تحميل الحقول:\n{exc}")

        self._acf_fields_table.setRowCount(len(fields))
        for i, f in enumerate(fields):
            label_item = QTableWidgetItem(f.get("label", ""))
            label_item.setData(Qt.ItemDataRole.UserRole, f)
            self._acf_fields_table.setItem(i, 0, label_item)
            self._acf_fields_table.setItem(
                i, 1, QTableWidgetItem(f.get("name", "")))
            self._acf_fields_table.setItem(
                i, 2, QTableWidgetItem(f.get("type", "")))
            self._acf_fields_table.setItem(
                i, 3, QTableWidgetItem(f.get("key", "")))

    # ── Add Field Group ───────────────────────────────────────────────

    def _new_acf_group(self):
        if not self.current:
            return
        dlg = _AcfGroupDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        if not d["title"]:
            QMessageBox.warning(self, "مطلوب", "اسم المجموعة مطلوب.")
            return

        key = self._gen_acf_key("group")
        group_json = {
            "key":   key,
            "title": d["title"],
            "fields": [],
            "location": [[{
                "param":    "post_type",
                "operator": "==",
                "value":    d["location"],
            }]],
            "menu_order": 0,
            "position":   d["position"],
            "style":      "default",
            "label_placement":       "top",
            "instruction_placement": "label",
            "hide_on_screen": "",
            "active": True,
            "description": d.get("description", ""),
            "show_in_rest": 0,
        }

        acf_dir = self._acf_json_dir()
        if acf_dir is None:
            return
        out_file = acf_dir / f"{key}.json"
        out_file.write_text(
            json.dumps(group_json, ensure_ascii=False, indent=4),
            encoding="utf-8")

        QMessageBox.information(
            self, "تم",
            f"تم إنشاء مجموعة الحقول '{d['title']}' بنجاح!\n"
            f"الملف: {out_file}\n\n"
            "ستظهر الحقول في ACF تلقائياً عند زيارة الموقع.")
        self._load_acf_groups()

    # ── Add Field ─────────────────────────────────────────────────────

    def _new_acf_field(self):
        if not self.current:
            return
        row = self._acf_groups_list.currentRow()
        item = self._acf_groups_list.item(row)
        if not item:
            QMessageBox.information(
                self, "اختر مجموعة", "اختر مجموعة حقول أولاً.")
            return
        group = item.data(Qt.ItemDataRole.UserRole)
        if group.get("source") != "json":
            QMessageBox.information(
                self, "غير مدعوم",
                "إضافة الحقول مباشرةً متاحة فقط للمجموعات المحفوظة كـ JSON.\n"
                "انقر 'مجموعة جديدة' لإنشاء مجموعة جديدة.")
            return

        dlg = _AcfFieldDialog(self._ACF_FIELD_TYPES, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        if not d["label"] or not d["name"]:
            QMessageBox.warning(self, "مطلوب", "العنوان والـ name مطلوبان.")
            return

        # Normalise slug
        d["name"] = re.sub(r"[^a-z0-9_]", "_", d["name"].lower()).strip("_")

        field_key = self._gen_acf_key("field")
        new_field: dict = {
            "key":               field_key,
            "label":             d["label"],
            "name":              d["name"],
            "type":              d["type"],
            "instructions":      d.get("instructions", ""),
            "required":          1 if d.get("required") else 0,
            "conditional_logic": 0,
            "wrapper":           {"width": "", "class": "", "id": ""},
        }
        # Type-specific defaults
        if d["type"] in ("select", "checkbox", "radio", "button_group"):
            new_field["choices"] = {}
            new_field["default_value"] = []
            new_field["return_format"] = "value"
        elif d["type"] == "true_false":
            new_field["message"] = ""
            new_field["default_value"] = 0
        elif d["type"] in ("image", "file"):
            new_field["return_format"] = "array"
            new_field["library"] = "all"
        elif d["type"] == "gallery":
            new_field["return_format"] = "array"
            new_field["library"] = "all"
        elif d["type"] == "repeater":
            new_field["sub_fields"] = []
            new_field["layout"] = "table"
            new_field["min"] = 0
            new_field["max"] = 0

        # Update the JSON file
        jf = Path(group["file"])
        grp_data = json.loads(jf.read_text(encoding="utf-8"))
        grp_data.setdefault("fields", []).append(new_field)
        jf.write_text(
            json.dumps(grp_data, ensure_ascii=False, indent=4),
            encoding="utf-8")
        # Refresh in memory
        group["data"] = grp_data

        self._load_acf_fields_for_group(group)

        # Auto-select the new field and show its code immediately
        new_row = self._acf_fields_table.rowCount() - 1
        if new_row >= 0:
            self._acf_fields_table.selectRow(new_row)
            self._on_acf_field_selected(new_row)

    # ── Edit Group ────────────────────────────────────────────────────

    def _edit_acf_group(self):
        row = self._acf_groups_list.currentRow()
        item = self._acf_groups_list.item(row)
        if not item:
            QMessageBox.information(self, "اختر", "اختر مجموعة للتعديل.")
            return
        group = item.data(Qt.ItemDataRole.UserRole)
        if group.get("source") != "json":
            QMessageBox.information(
                self, "غير مدعوم",
                "التعديل المباشر متاح فقط للمجموعات المحفوظة كـ JSON.")
            return

        dlg = _AcfGroupDialog(data=group.get("data", {}), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        if not d["title"]:
            QMessageBox.warning(self, "مطلوب", "اسم المجموعة مطلوب.")
            return

        jf = Path(group["file"])
        grp_data = json.loads(jf.read_text(encoding="utf-8"))
        grp_data["title"] = d["title"]
        grp_data["position"] = d["position"]
        grp_data["description"] = d.get("description", "")
        grp_data["location"] = [[{
            "param": "post_type",
            "operator": "==",
            "value": d["location"],
        }]]
        jf.write_text(
            json.dumps(grp_data, ensure_ascii=False, indent=4),
            encoding="utf-8")
        self._load_acf_groups()

    # ── Edit Field ────────────────────────────────────────────────────

    def _edit_acf_field(self):
        row_g = self._acf_groups_list.currentRow()
        item_g = self._acf_groups_list.item(row_g)
        if not item_g:
            QMessageBox.information(self, "اختر", "اختر مجموعة أولاً.")
            return
        group = item_g.data(Qt.ItemDataRole.UserRole)
        if group.get("source") != "json":
            QMessageBox.information(
                self, "غير مدعوم",
                "التعديل المباشر متاح فقط للحقول المحفوظة كـ JSON.")
            return

        row_f = self._acf_fields_table.currentRow()
        if row_f < 0:
            QMessageBox.information(self, "اختر", "اختر حقلاً للتعديل.")
            return
        label_item = self._acf_fields_table.item(row_f, 0)
        fd: dict = label_item.data(Qt.ItemDataRole.UserRole) or {}

        dlg = _AcfFieldDialog(self._ACF_FIELD_TYPES, data=fd, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        if not d["label"]:
            QMessageBox.warning(self, "مطلوب", "التسمية مطلوبة.")
            return

        jf = Path(group["file"])
        grp_data = json.loads(jf.read_text(encoding="utf-8"))
        for f in grp_data.get("fields", []):
            if f.get("key") == fd.get("key"):
                f["label"] = d["label"]
                f["type"] = d["type"]
                f["instructions"] = d["instructions"]
                f["required"] = 1 if d["required"] else 0
                break
        jf.write_text(
            json.dumps(grp_data, ensure_ascii=False, indent=4),
            encoding="utf-8")
        group["data"] = grp_data
        self._load_acf_fields_for_group(group)

    # ── Delete Group ──────────────────────────────────────────────────

    def _delete_acf_group(self):
        row = self._acf_groups_list.currentRow()
        item = self._acf_groups_list.item(row)
        if not item:
            QMessageBox.information(self, "اختر", "اختر مجموعة للحذف.")
            return
        group = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"حذف مجموعة '{group['title']}'؟\n"
            "سيتم حذف ملف JSON — الحقول الموجودة في DB لن تُحذف.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        if group.get("source") == "json" and group.get("file"):
            try:
                Path(group["file"]).unlink(missing_ok=True)
            except Exception as exc:
                QMessageBox.warning(self, "خطأ", str(exc))
        self._load_acf_groups()

    # ── Delete Field ──────────────────────────────────────────────────

    def _delete_acf_field(self):
        row_g = self._acf_groups_list.currentRow()
        item_g = self._acf_groups_list.item(row_g)
        if not item_g:
            QMessageBox.information(self, "اختر", "اختر مجموعة أولاً.")
            return
        group = item_g.data(Qt.ItemDataRole.UserRole)
        if group.get("source") != "json":
            QMessageBox.information(
                self, "غير مدعوم",
                "الحذف المباشر متاح فقط للحقول المحفوظة كـ JSON.")
            return

        row_f = self._acf_fields_table.currentRow()
        if row_f < 0:
            QMessageBox.information(self, "اختر", "اختر حقلاً للحذف.")
            return
        label_item = self._acf_fields_table.item(row_f, 0)
        fd: dict = label_item.data(Qt.ItemDataRole.UserRole) or {}
        field_key = fd.get("key", "")
        field_label = fd.get("label", field_key)

        reply = QMessageBox.question(
            self, "تأكيد الحذف", f"حذف الحقل '{field_label}'؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        jf = Path(group["file"])
        grp_data = json.loads(jf.read_text(encoding="utf-8"))
        grp_data["fields"] = [
            f for f in grp_data.get("fields", [])
            if f.get("key") != field_key]
        jf.write_text(
            json.dumps(grp_data, ensure_ascii=False, indent=4),
            encoding="utf-8")
        group["data"] = grp_data
        self._load_acf_fields_for_group(group)

    # ── Show PHP code for selected field ─────────────────────────────

    def _show_acf_field_code(self):
        row_f = self._acf_fields_table.currentRow()
        if row_f < 0:
            QMessageBox.information(self, "اختر", "اختر حقلاً أولاً.")
            return
        label_item = self._acf_fields_table.item(row_f, 0)
        fd: dict = label_item.data(Qt.ItemDataRole.UserRole) or {}
        fname = fd.get("name", "field_name")
        ftype = fd.get("type", "text")
        flabel = fd.get("label", fname)

        dlg = _AcfCodeDialog(fname, ftype, flabel, parent=self)
        dlg.exec()

    def _on_acf_field_selected(self, row: int):
        """Auto-update code preview when a field row is selected."""
        if row < 0:
            self._acf_code_preview.setPlainText("")
            return
        item = self._acf_fields_table.item(row, 0)
        if not item:
            return
        fd: dict = item.data(Qt.ItemDataRole.UserRole) or {}
        fname  = fd.get("name", "field_name")
        ftype  = fd.get("type", "text")
        flabel = fd.get("label", fname)
        template = _AcfCodeDialog._CODE_TEMPLATES.get(
            ftype, _AcfCodeDialog._DEFAULT_TEMPLATE)
        code = template.replace("{name}", fname)
        header = f"// ── {flabel} ({ftype}) ──\n"
        self._acf_code_preview.setPlainText(header + code)

    def _copy_acf_preview(self):
        text = self._acf_code_preview.toPlainText()
        if text.strip():
            QApplication.clipboard().setText(text)

    def _show_acf_group_code(self):
        """Generate a complete PHP template for ALL fields in the selected group."""
        row_g = self._acf_groups_list.currentRow()
        item_g = self._acf_groups_list.item(row_g)
        if not item_g:
            QMessageBox.information(self, "اختر", "اختر مجموعة أولاً.")
            return
        group = item_g.data(Qt.ItemDataRole.UserRole)
        fields: list[dict] = group.get("data", {}).get("fields", [])
        if not fields:
            QMessageBox.information(
                self, "لا توجد حقول", "لا توجد حقول في هذه المجموعة.")
            return

        lines = [
            "<?php",
            f"// ═══════════════════════════════════════════",
            f"// ACF Group: {group.get('title', 'Group')}",
            f"// Location:  {self._acf_group_location_str(group)}",
            f"// Generated by Harmulizer Pro",
            f"// ═══════════════════════════════════════════",
            "",
        ]
        for fd in fields:
            fname  = fd.get("name", "field")
            ftype  = fd.get("type", "text")
            flabel = fd.get("label", fname)
            template = _AcfCodeDialog._CODE_TEMPLATES.get(
                ftype, _AcfCodeDialog._DEFAULT_TEMPLATE)
            # Strip <?php ... ?> wrappers for inline embedding
            snippet = template.replace("{name}", fname)
            snippet = re.sub(r"^<\?php\s*", "", snippet)
            snippet = re.sub(r"\s*\?>$", "", snippet)
            lines.append(f"// ── {flabel} ({ftype}) ──")
            lines.append(snippet)
            lines.append("")

        lines.append("?>")
        full_code = "\n".join(lines)

        dlg = _CodePreviewDialog(
            f"كود PHP لكل حقول: {group.get('title', 'Group')}",
            full_code, parent=self)
        dlg.exec()

    @staticmethod
    def _acf_group_location_str(group: dict) -> str:
        try:
            return group["data"]["location"][0][0].get("value", "—")
        except Exception:
            return "—"

    # ── Ask AI about ACF field frontend usage ────────────────────────

    def _acf_ask_ai(self):
        row_f = self._acf_fields_table.currentRow()
        fd: dict = {}
        if row_f >= 0:
            label_item = self._acf_fields_table.item(row_f, 0)
            if label_item:
                fd = label_item.data(Qt.ItemDataRole.UserRole) or {}

        fname  = fd.get("name", "field_name")
        ftype  = fd.get("type", "text")
        flabel = fd.get("label", fname)

        question = (
            f"أنا مطور WordPress أستخدم إضافة ACF (Advanced Custom Fields).\n"
            f"عندي حقل اسمه '{fname}' (Label: {flabel}) ونوعه '{ftype}'.\n"
            f"كيف أعرض قيمة هذا الحقل في قوالب WordPress (theme templates)؟\n"
            f"أعطني:\n"
            f"1. الكود PHP الصحيح لعرض القيمة في الـ template\n"
            f"2. مثال للاستخدام في الـ loop\n"
            f"3. كيف أستخدمه في Gutenberg block (block.json + JS/JSX)\n"
            f"4. نصائح مهمة لهذا النوع من الحقول"
        )
        self._open_ai_with_question(question)

    # ═════════════════════════════════════════════════════════════════
    # ██  CUSTOM POST TYPES TAB
    # ═════════════════════════════════════════════════════════════════

    # Built-in WordPress post types to exclude from the list
    _BUILTIN_CPTS = {
        "post", "page", "attachment", "revision", "nav_menu_item",
        "custom_css", "customize_changeset", "oembed_cache",
        "user_request", "wp_block", "wp_template",
        "wp_template_part", "wp_global_styles", "wp_navigation",
        "acf-field-group", "acf-field",
    }

    _MU_PLUGIN_FILE = "harmulizer-cpt.php"

    def _build_cpt_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)
        vbox.setSpacing(8)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_new_cpt    = PrimaryButton("➕ نوع محتوى جديد")
        btn_del_cpt    = _secondary_btn("🗑️ حذف")
        btn_show_cpt_code = _secondary_btn("🖥️ كود PHP")
        btn_ask_cpt_ai = _secondary_btn("🤖 اسأل AI")
        btn_refresh    = _secondary_btn("🔄 تحديث")
        btn_refresh.setFixedWidth(80)
        btn_row.addWidget(btn_new_cpt)
        btn_row.addWidget(btn_del_cpt)
        btn_row.addWidget(btn_show_cpt_code)
        btn_row.addWidget(btn_ask_cpt_ai)
        btn_row.addStretch()
        btn_row.addWidget(btn_refresh)
        vbox.addLayout(btn_row)

        hint = QLabel(
            "📌  الأنواع المُضافة بواسطة Harmulizer تُحفظ في "
            "wp-content/mu-plugins/harmulizer-cpt.php")
        hint.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        vbox.addWidget(hint)

        # ── CPT Table ─────────────────────────────────────────────────
        self._cpt_table = QTableWidget()
        self._cpt_table.setColumnCount(5)
        self._cpt_table.setHorizontalHeaderLabels(
            ["Slug", "التسمية", "عام", "له أرشيف", "المصدر"])
        hh = self._cpt_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._cpt_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._cpt_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._cpt_table.setAlternatingRowColors(True)
        vbox.addWidget(self._cpt_table, 1)

        btn_new_cpt.clicked.connect(self._new_cpt)
        btn_del_cpt.clicked.connect(self._delete_cpt)
        btn_show_cpt_code.clicked.connect(self._show_cpt_code)
        btn_ask_cpt_ai.clicked.connect(self._cpt_ask_ai)
        btn_refresh.clicked.connect(self._load_cpt_list)
        return w

    # ── CPT loader ────────────────────────────────────────────────────

    def _load_cpt_list(self):
        """Load CPTs from WP-CLI and also from the local mu-plugin file."""
        if not self.current:
            return
        self._cpt_table.setRowCount(0)

        # Read mu-plugin file to know which CPTs we manage
        mu_slugs = self._mu_plugin_read_slugs()

        args = [
            "post-type", "list",
            "--format=json",
            "--fields=name,label,description,hierarchical,public,show_in_rest,has_archive",
        ]
        self._run_async(args, lambda ok, out: self._fill_cpt_table(ok, out, mu_slugs))

    def _fill_cpt_table(self, ok: bool, output: str, mu_slugs: set):
        if not ok:
            # If WP-CLI fails, at least show mu-plugin CPTs
            for slug in sorted(mu_slugs):
                self._add_cpt_row(
                    slug, slug.replace("_", " ").title(),
                    "?", "?", "🔧 Harmulizer")
            return
        try:
            cpts = self._parse_json(output)
            rows = []
            for c in cpts:
                name = str(c.get("name", ""))
                if name in self._BUILTIN_CPTS:
                    continue
                rows.append(c)

            # Merge: add managed ones not returned by WP-CLI
            wpcli_names = {str(c.get("name", "")) for c in cpts}
            for slug in sorted(mu_slugs - wpcli_names):
                rows.append({
                    "name": slug, "label": slug.replace("_", " ").title(),
                    "public": "?", "has_archive": "?",
                    "_managed": True,
                })

            for c in rows:
                name = str(c.get("name", ""))
                src = "🔧 Harmulizer" if name in mu_slugs else "🔌 إضافة/قالب"
                self._add_cpt_row(
                    name,
                    str(c.get("label", name)),
                    "✅" if str(c.get("public", "0")) in ("1", "True", "true") else "—",
                    "✅" if str(c.get("has_archive", "0")) not in ("0", "", "False", "false") else "—",
                    src)
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ", f"لا يمكن قراءة أنواع المحتوى:\n{exc}")

    def _add_cpt_row(self, slug, label, public, archive, source):
        r = self._cpt_table.rowCount()
        self._cpt_table.insertRow(r)
        slug_item = QTableWidgetItem(slug)
        slug_item.setData(Qt.ItemDataRole.UserRole, slug)
        self._cpt_table.setItem(r, 0, slug_item)
        self._cpt_table.setItem(r, 1, QTableWidgetItem(label))
        self._cpt_table.setItem(r, 2, QTableWidgetItem(public))
        self._cpt_table.setItem(r, 3, QTableWidgetItem(archive))
        src_item = QTableWidgetItem(source)
        if source == "🔧 Harmulizer":
            src_item.setForeground(Qt.GlobalColor.cyan)
        self._cpt_table.setItem(r, 4, src_item)

    # ── mu-plugin helpers ─────────────────────────────────────────────

    def _mu_plugin_path(self) -> Path | None:
        if not self.current:
            return None
        mu_dir = Path(self.current.path) / "wp-content" / "mu-plugins"
        mu_dir.mkdir(parents=True, exist_ok=True)
        return mu_dir / self._MU_PLUGIN_FILE

    def _mu_plugin_read_slugs(self) -> set:
        fp = self._mu_plugin_path()
        if not fp or not fp.exists():
            return set()
        content = fp.read_text(encoding="utf-8", errors="ignore")
        return set(re.findall(r"// \[CPT:([a-z0-9_]+):start\]", content))

    def _mu_plugin_write(self, content: str):
        fp = self._mu_plugin_path()
        if fp:
            fp.write_text(content, encoding="utf-8")

    def _mu_plugin_read(self) -> str:
        fp = self._mu_plugin_path()
        if not fp or not fp.exists():
            return (
                "<?php\n"
                "/**\n"
                " * Harmulizer Pro — Custom Post Types\n"
                " * Auto-generated. Do not edit manually.\n"
                " */\n\n"
            )
        return fp.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _generate_cpt_php(d: dict) -> str:
        """Build register_post_type() PHP snippet for a CPT dict."""
        slug     = d["slug"]
        singular = d["singular"]
        plural   = d["plural"]
        icon     = d.get("icon", "dashicons-admin-post")
        public   = "true" if d.get("public", True) else "false"
        archive  = "true" if d.get("has_archive", True) else "false"
        rest     = "true" if d.get("show_in_rest", True) else "false"
        hier     = "true" if d.get("hierarchical", False) else "false"
        supports = d.get("supports", ["title", "editor", "thumbnail"])
        supports_php = ", ".join(f"'{s}'" for s in supports)

        return (
            f"// [CPT:{slug}:start]\n"
            f"add_action( 'init', function() {{\n"
            f"    register_post_type( '{slug}', [\n"
            f"        'label'       => __('{plural}'),\n"
            f"        'labels'      => [\n"
            f"            'name'          => __('{plural}'),\n"
            f"            'singular_name' => __('{singular}'),\n"
            f"            'add_new_item'  => __('Add New {singular}'),\n"
            f"            'edit_item'     => __('Edit {singular}'),\n"
            f"            'view_item'     => __('View {singular}'),\n"
            f"            'search_items'  => __('Search {plural}'),\n"
            f"        ],\n"
            f"        'public'        => {public},\n"
            f"        'hierarchical'  => {hier},\n"
            f"        'has_archive'   => {archive},\n"
            f"        'show_in_rest'  => {rest},\n"
            f"        'menu_icon'     => '{icon}',\n"
            f"        'supports'      => [ {supports_php} ],\n"
            f"        'rewrite'       => [ 'slug' => '{slug}' ],\n"
            f"    ] );\n"
            f"}}, 0 );\n"
            f"// [CPT:{slug}:end]\n\n"
        )

    # ── Add CPT ───────────────────────────────────────────────────────

    def _new_cpt(self):
        if not self.current:
            return
        dlg = _CptDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.get_data()
        if not d["slug"]:
            QMessageBox.warning(self, "مطلوب", "Slug (اسم النوع) مطلوب.")
            return
        d["slug"] = re.sub(r"[^a-z0-9_]", "_",
                           d["slug"].lower()).strip("_")

        existing = self._mu_plugin_read_slugs()
        if d["slug"] in existing:
            QMessageBox.warning(
                self, "موجود بالفعل",
                f"نوع المحتوى '{d['slug']}' موجود بالفعل في الـ mu-plugin.")
            return

        snippet  = self._generate_cpt_php(d)
        current  = self._mu_plugin_read()
        self._mu_plugin_write(current.rstrip() + "\n\n" + snippet)

        QMessageBox.information(
            self, "تم",
            f"✅ تم إضافة نوع المحتوى '{d['slug']}' بنجاح!\n"
            f"الملف: wp-content/mu-plugins/{self._MU_PLUGIN_FILE}\n\n"
            "يُحمَّل تلقائياً بواسطة WordPress.")
        self._load_cpt_list()

    # ── Delete CPT ────────────────────────────────────────────────────

    def _delete_cpt(self):
        row = self._cpt_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "اختر", "اختر نوع محتوى للحذف.")
            return
        slug_item = self._cpt_table.item(row, 0)
        slug = slug_item.data(Qt.ItemDataRole.UserRole) if slug_item else ""
        src_item = self._cpt_table.item(row, 4)
        if src_item and "Harmulizer" not in src_item.text():
            QMessageBox.information(
                self, "غير قابل للحذف",
                "يمكن حذف أنواع المحتوى المُضافة بواسطة Harmulizer فقط.\n"
                "الأنواع القادمة من إضافات أو القالب تُدار من wp-admin.")
            return

        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"إزالة نوع المحتوى '{slug}' من mu-plugin؟\n"
            "المحتوى الموجود في DB لن يُحذف.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        content = self._mu_plugin_read()
        pattern = rf"// \[CPT:{re.escape(slug)}:start\].*?// \[CPT:{re.escape(slug)}:end\]\n*"
        new_content = re.sub(pattern, "", content, flags=re.DOTALL)
        self._mu_plugin_write(new_content)
        self._load_cpt_list()

    # ── Show CPT PHP code ─────────────────────────────────────────────

    def _show_cpt_code(self):
        row = self._cpt_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "اختر", "اختر نوع محتوى.")
            return
        slug_item = self._cpt_table.item(row, 0)
        slug  = slug_item.data(Qt.ItemDataRole.UserRole) if slug_item else ""
        label = (self._cpt_table.item(row, 1).text()
                 if self._cpt_table.item(row, 1) else slug)

        content = self._mu_plugin_read()
        pattern = rf"// \[CPT:{re.escape(slug)}:start\](.*?)// \[CPT:{re.escape(slug)}:end\]"
        m = re.search(pattern, content, re.DOTALL)
        snippet = m.group(0) if m else f"// CPT '{slug}' registered externally"

        dlg = _CodePreviewDialog(
            title=f"كود CPT: {label}",
            code=snippet,
            language="php",
            parent=self)
        dlg.exec()

    # ── Ask AI about CPT ──────────────────────────────────────────────

    def _cpt_ask_ai(self):
        row = self._cpt_table.currentRow()
        slug  = ""
        label = ""
        if row >= 0:
            si = self._cpt_table.item(row, 0)
            li = self._cpt_table.item(row, 1)
            slug  = si.data(Qt.ItemDataRole.UserRole) if si else ""
            label = li.text() if li else slug

        question = (
            f"أنا مطور WordPress. عندي Custom Post Type اسمه '{slug}' "
            f"(Label: {label or slug}).\n"
            f"أحتاج مساعدة في:\n"
            f"1. كيفية عرض محتوى هذا النوع في الـ template (archive-{slug}.php و single-{slug}.php)\n"
            f"2. كيفية استخدام WP_Query لاستعلام هذا النوع\n"
            f"3. كيفية إضافة taxonomy مخصصة له\n"
            f"4. كيفية عرضه في Gutenberg مع block patterns\n"
            f"أعطني كود PHP + JavaScript عملي وقابل للتطبيق."
        )
        self._open_ai_with_question(question)

    # ═════════════════════════════════════════════════════════════════
    # ██  AI INTEGRATION
    # ═════════════════════════════════════════════════════════════════

    def _open_ai_with_question(self, question: str):
        """Navigate to the AI assistant and pre-fill + send the question."""
        try:
            ai_page = self.parent_window.ai_page
            from app.ui.ai_page import AIChatWindow
            win = AIChatWindow(ai_page.ai, self.current, self)
            win.chat_input.setText(question)
            win.show()
            win.raise_()
        except Exception:
            # Fallback: copy to clipboard and show tip
            cb = QApplication.clipboard()
            cb.setText(question)
            QMessageBox.information(
                self, "تم النسخ",
                "تم نسخ السؤال إلى الـ Clipboard.\n"
                "افتح تبويب 'المساعد الذكي' والصق السؤال هناك.\n\n"
                f"السؤال:\n{question[:300]}…")

    # ═════════════════════════════════════════════════════════════════
    # ██  COMMENTS TAB  (index 8)
    # ═════════════════════════════════════════════════════════════════

    def _build_comments_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)
        vbox.setSpacing(6)

        # Filter row
        filter_row = QHBoxLayout()
        self._comments_filter = QComboBox()
        self._comments_filter.addItems([
            "all", "approve", "hold", "spam", "trash"])
        self._comments_filter.currentIndexChanged.connect(self._load_comments)
        filter_row.addWidget(QLabel("الفلتر:"))
        filter_row.addWidget(self._comments_filter)
        filter_row.addStretch()

        btn_approve = PrimaryButton("✅ موافقة")
        btn_hold    = _secondary_btn("⏸️ تعليق")
        btn_spam    = _secondary_btn("🚫 بريد مزعج")
        btn_trash   = _secondary_btn("🗑️ سلة المهملات")
        btn_delete  = _secondary_btn("❌ حذف نهائي")
        btn_refresh = _secondary_btn("🔄 تحديث")

        for b in [btn_approve, btn_hold, btn_spam, btn_trash, btn_delete, btn_refresh]:
            filter_row.addWidget(b)
        vbox.addLayout(filter_row)

        hint = QLabel("انقر مرتين على تعليق لعرض محتواه الكامل.")
        hint.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        vbox.addWidget(hint)

        self._comments_table = QTableWidget()
        self._comments_table.setColumnCount(6)
        self._comments_table.setHorizontalHeaderLabels(
            ["ID", "الكاتب", "البريد", "التعليق", "الحالة", "التاريخ"])
        hh = self._comments_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._comments_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._comments_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._comments_table.setAlternatingRowColors(True)
        self._comments_table.doubleClicked.connect(self._view_comment)
        vbox.addWidget(self._comments_table, 1)

        btn_approve.clicked.connect(lambda: self._comment_action("approve"))
        btn_hold.clicked.connect(lambda: self._comment_action("unapprove"))
        btn_spam.clicked.connect(lambda: self._comment_action("spam"))
        btn_trash.clicked.connect(lambda: self._comment_action("trash"))
        btn_delete.clicked.connect(self._delete_comment)
        btn_refresh.clicked.connect(self._load_comments)
        return w

    def _load_comments(self):
        if not self.current:
            return
        self._comments_table.setRowCount(0)
        status = self._comments_filter.currentText()
        args = [
            "comment", "list", "--format=json",
            "--fields=comment_ID,comment_author,comment_author_email,"
            "comment_content,comment_status,comment_date",
            "--number=200",
        ]
        if status != "all":
            args.append(f"--status={status}")
        self._run_async(args, self._fill_comments_table)

    def _fill_comments_table(self, ok: bool, output: str):
        if not ok:
            QMessageBox.warning(
                self, "خطأ", f"فشل تحميل التعليقات:\n{output[:600]}")
            return
        try:
            comments = self._parse_json(output)
            self._comments_table.setRowCount(len(comments))
            _STATUS_COLORS = {
                "approve": Qt.GlobalColor.green,
                "1":       Qt.GlobalColor.green,
                "hold":    Qt.GlobalColor.yellow,
                "0":       Qt.GlobalColor.yellow,
                "spam":    Qt.GlobalColor.red,
                "trash":   Qt.GlobalColor.gray,
            }
            for i, c in enumerate(comments):
                cid = str(c.get("comment_ID", ""))
                id_item = QTableWidgetItem(cid)
                id_item.setData(Qt.ItemDataRole.UserRole, c)
                self._comments_table.setItem(i, 0, id_item)
                self._comments_table.setItem(
                    i, 1, QTableWidgetItem(str(c.get("comment_author", ""))))
                self._comments_table.setItem(
                    i, 2, QTableWidgetItem(str(c.get("comment_author_email", ""))))
                content = str(c.get("comment_content", "")).replace("\n", " ")
                self._comments_table.setItem(
                    i, 3, QTableWidgetItem(content[:120]))
                status = str(c.get("comment_status", ""))
                s_item = QTableWidgetItem(status)
                color = _STATUS_COLORS.get(status)
                if color:
                    s_item.setForeground(color)
                self._comments_table.setItem(i, 4, s_item)
                self._comments_table.setItem(
                    i, 5, QTableWidgetItem(
                        str(c.get("comment_date", ""))[:16]))
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ في التحليل",
                f"لا يمكن قراءة التعليقات:\n{exc}")

    def _selected_comment_id(self) -> str | None:
        row = self._comments_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "اختر", "اختر تعليقاً أولاً.")
            return None
        id_item = self._comments_table.item(row, 0)
        c: dict = id_item.data(Qt.ItemDataRole.UserRole) if id_item else {}
        return str(c.get("comment_ID", ""))

    def _comment_action(self, action: str):
        """approve / unapprove / spam / trash."""
        cid = self._selected_comment_id()
        if not cid:
            return
        self._run_async(
            ["comment", action, cid],
            lambda ok, out: (
                self._load_comments() if ok else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم تنفيذ الإجراء:\n{out[:400]}")))

    def _delete_comment(self):
        cid = self._selected_comment_id()
        if not cid:
            return
        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"حذف التعليق #{cid} بشكل نهائي؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_async(
            ["comment", "delete", cid, "--force"],
            lambda ok, out: (
                self._load_comments() if ok else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم حذف التعليق:\n{out[:400]}")))

    def _view_comment(self):
        row = self._comments_table.currentRow()
        if row < 0:
            return
        id_item = self._comments_table.item(row, 0)
        c: dict = id_item.data(Qt.ItemDataRole.UserRole) if id_item else {}
        author  = c.get("comment_author", "")
        content = c.get("comment_content", "")
        status  = c.get("comment_status", "")
        dlg = _CodePreviewDialog(
            title=f"تعليق من {author}  [{status}]",
            code=content,
            language="text",
            parent=self)
        dlg.exec()

    # ═════════════════════════════════════════════════════════════════
    # ██  TAXONOMIES TAB  (index 9)
    # ═════════════════════════════════════════════════════════════════

    def _build_taxonomies_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 8, 0, 0)
        vbox.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left — taxonomy list
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        tax_btn_row = QHBoxLayout()
        btn_ref_tax = _secondary_btn("🔄 تحديث")
        tax_btn_row.addWidget(QLabel("التصنيفات:"))
        tax_btn_row.addStretch()
        tax_btn_row.addWidget(btn_ref_tax)
        lv.addLayout(tax_btn_row)

        self._tax_list = QListWidget()
        self._tax_list.setAlternatingRowColors(True)
        lv.addWidget(self._tax_list, 1)

        # Right — terms in selected taxonomy
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 0, 0, 0)

        term_btn_row = QHBoxLayout()
        btn_new_term = PrimaryButton("➕ مصطلح جديد")
        btn_del_term = _secondary_btn("🗑️ حذف")
        btn_ref_terms = _secondary_btn("🔄")
        btn_ref_terms.setFixedWidth(36)
        term_btn_row.addWidget(btn_new_term)
        term_btn_row.addWidget(btn_del_term)
        term_btn_row.addStretch()
        term_btn_row.addWidget(btn_ref_terms)
        rv.addLayout(term_btn_row)

        rv.addWidget(QLabel("المصطلحات في التصنيف المختار:"))
        self._terms_table = QTableWidget()
        self._terms_table.setColumnCount(4)
        self._terms_table.setHorizontalHeaderLabels(
            ["ID", "الاسم", "Slug", "عدد المقالات"])
        hh = self._terms_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._terms_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._terms_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._terms_table.setAlternatingRowColors(True)
        rv.addWidget(self._terms_table, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([220, 540])
        vbox.addWidget(splitter, 1)

        btn_ref_tax.clicked.connect(self._load_taxonomies)
        self._tax_list.currentRowChanged.connect(self._on_taxonomy_selected)
        btn_new_term.clicked.connect(self._new_term)
        btn_del_term.clicked.connect(self._delete_term)
        btn_ref_terms.clicked.connect(
            lambda: self._on_taxonomy_selected(self._tax_list.currentRow()))
        return w

    def _load_taxonomies(self):
        if not self.current:
            return
        self._tax_list.clear()
        self._terms_table.setRowCount(0)
        self._run_async(
            ["taxonomy", "list", "--format=json",
             "--fields=name,label,hierarchical,public,show_ui"],
            self._fill_tax_list)

    def _fill_tax_list(self, ok: bool, output: str):
        if not ok:
            QMessageBox.warning(
                self, "خطأ", f"فشل تحميل التصنيفات:\n{output[:400]}")
            return
        try:
            taxs = self._parse_json(output)
            for t in taxs:
                name  = str(t.get("name", ""))
                label = str(t.get("label", name))
                item = QListWidgetItem(f"🏷️  {label}  ({name})")
                item.setData(Qt.ItemDataRole.UserRole, name)
                self._tax_list.addItem(item)
            if taxs:
                self._tax_list.setCurrentRow(0)
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ", f"لا يمكن قراءة التصنيفات:\n{exc}")

    def _on_taxonomy_selected(self, row: int):
        item = self._tax_list.item(row)
        if not item:
            self._terms_table.setRowCount(0)
            return
        taxonomy = item.data(Qt.ItemDataRole.UserRole)
        self._terms_table.setRowCount(0)
        self._run_async(
            ["term", "list", taxonomy, "--format=json",
             "--fields=term_id,name,slug,count"],
            self._fill_terms_table)

    def _fill_terms_table(self, ok: bool, output: str):
        if not ok:
            QMessageBox.warning(
                self, "خطأ", f"فشل تحميل المصطلحات:\n{output[:400]}")
            return
        try:
            terms = self._parse_json(output)
            self._terms_table.setRowCount(len(terms))
            for i, t in enumerate(terms):
                tid = str(t.get("term_id", ""))
                id_item = QTableWidgetItem(tid)
                id_item.setData(Qt.ItemDataRole.UserRole, t)
                self._terms_table.setItem(i, 0, id_item)
                self._terms_table.setItem(
                    i, 1, QTableWidgetItem(str(t.get("name", ""))))
                self._terms_table.setItem(
                    i, 2, QTableWidgetItem(str(t.get("slug", ""))))
                self._terms_table.setItem(
                    i, 3, QTableWidgetItem(str(t.get("count", ""))))
        except Exception as exc:
            QMessageBox.warning(
                self, "خطأ", f"لا يمكن قراءة المصطلحات:\n{exc}")

    def _new_term(self):
        if not self.current:
            return
        row = self._tax_list.currentRow()
        item = self._tax_list.item(row)
        if not item:
            QMessageBox.information(self, "اختر", "اختر تصنيفاً أولاً.")
            return
        taxonomy = item.data(Qt.ItemDataRole.UserRole)
        name, ok = QInputDialog.getText(
            self, "مصطلح جديد",
            f"اسم المصطلح الجديد في '{taxonomy}':")
        if not ok or not name.strip():
            return
        self._run_async(
            ["term", "create", taxonomy, name.strip()],
            lambda ok2, out: (
                self._on_taxonomy_selected(self._tax_list.currentRow()) if ok2 else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم إنشاء المصطلح:\n{out[:400]}")))

    def _delete_term(self):
        if not self.current:
            return
        tax_row  = self._tax_list.currentRow()
        tax_item = self._tax_list.item(tax_row)
        if not tax_item:
            QMessageBox.information(self, "اختر", "اختر تصنيفاً.")
            return
        taxonomy = tax_item.data(Qt.ItemDataRole.UserRole)

        term_row = self._terms_table.currentRow()
        if term_row < 0:
            QMessageBox.information(self, "اختر", "اختر مصطلحاً للحذف.")
            return
        id_item = self._terms_table.item(term_row, 0)
        t: dict = id_item.data(Qt.ItemDataRole.UserRole) if id_item else {}
        term_id   = str(t.get("term_id", ""))
        term_name = str(t.get("name", term_id))

        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"حذف المصطلح '{term_name}' من '{taxonomy}'؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_async(
            ["term", "delete", taxonomy, term_id],
            lambda ok2, out: (
                self._on_taxonomy_selected(self._tax_list.currentRow()) if ok2 else
                QMessageBox.warning(
                    self, "فشل", f"لم يتم حذف المصطلح:\n{out[:400]}")))

    # ═════════════════════════════════════════════════════════════════
    # ██  QUICK ACTIONS TAB  (index 10)
    # ═════════════════════════════════════════════════════════════════

    def _build_quick_actions_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QScrollArea

        outer = QWidget()
        outer_v = QVBoxLayout(outer)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(0)

        # Scrollable area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(8, 12, 8, 8)
        vbox.setSpacing(10)

        title = QLabel("⚡  إجراءات سريعة — تُنفَّذ مباشرةً بضغطة واحدة")
        title.setStyleSheet("color: #F8FAFC; font-size: 16px; font-weight: 800; padding: 10px 4px;")
        vbox.addWidget(title)

        # ── Action cards ──────────────────────────────────────────────
        actions = [
            ("🔄",  "مسح Rewrite Rules",
             "تجديد قواعد الـ URL وإصلاح مشاكل 404",
             self._qa_rewrite_flush, "#6366F1"),
            ("🗑️",  "حذف جميع Transients",
             "تنظيف الـ cache المؤقت المخزن في قاعدة البيانات",
             self._qa_delete_transients, "#EF4444"),
            ("🧹",  "إفراغ سلة المهملات",
             "حذف جميع المقالات والصفحات من سلة المهملات نهائياً",
             self._qa_empty_trash, "#EF4444"),
            ("📊",  "تحسين قاعدة البيانات",
             "تشغيل OPTIMIZE TABLE لتسريع الاستعلامات",
             self._qa_db_optimize, "#10B981"),
            ("🖼️",  "إعادة توليد الصور المصغرة",
             "Regenerate thumbnails للصور المرفوعة",
             self._qa_regen_thumbs, "#3B82F6"),
            ("🔑",  "تغيير كلمة مرور Admin",
             "تغيير كلمة مرور أول مستخدم admin بدون الدخول لـ wp-admin",
             self._qa_reset_admin_pass, "#F59E0B"),
            ("🌐",  "تحديث Site URL",
             "تحديث siteurl و home في قاعدة البيانات",
             self._qa_update_siteurl, "#F59E0B"),
            ("📋",  "عرض معلومات الموقع",
             "إصدار PHP، إصدار WordPress، وعدد الإضافات النشطة",
             self._qa_site_info, "#64748B"),
            ("🔌",  "تفعيل / تعطيل Maintenance Mode",
             "تفعيل وضع الصيانة أو إلغاؤه",
             self._qa_toggle_maintenance, "#F59E0B"),
            ("🔒",  "تحديث Salt Keys",
             "توليد مفاتيح أمان جديدة وتحديثها في قاعدة البيانات",
             self._qa_update_salts, "#EF4444"),
            ("📦",  "تحديث جميع الإضافات",
             "تحديث كل الـ plugins المثبتة دفعة واحدة",
             self._qa_update_all_plugins, "#10B981"),
            ("🛡️",  "فحص ملفات WordPress",
             "التحقق من سلامة ملفات WordPress الأساسية",
             self._qa_verify_checksums, "#6366F1"),
            ("📤",  "تصدير قاعدة البيانات",
             "تصدير نسخة احتياطية من قاعدة البيانات (SQL)",
             self._qa_export_db, "#3B82F6"),
            ("🔍",  "البحث والاستبدال في DB",
             "استبدال نص في قاعدة البيانات (مفيد عند تغيير الـ URL)",
             self._qa_search_replace, "#F59E0B"),
        ]

        # Grid 2 columns
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        for idx, (icon, name, desc, handler, color) in enumerate(actions):
            card = self._make_action_card(icon, name, desc, handler, color)
            grid.addWidget(card, idx // 2, idx % 2)

        vbox.addWidget(grid_widget)
        vbox.addStretch()
        scroll.setWidget(w)
        outer_v.addWidget(scroll, 1)

        # Log area fixed at bottom
        log_lbl = QLabel("سجل العمليات:")
        log_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px; padding: 4px 8px 0 8px;")
        outer_v.addWidget(log_lbl)

        self._qa_log = QTextEdit()
        self._qa_log.setReadOnly(True)
        self._qa_log.setFixedHeight(110)
        self._qa_log.setStyleSheet(
            "background: #0F172A; color: #94A3B8; font-family: monospace; "
            "font-size: 11px; border: 1px solid #334155; border-radius: 6px; margin: 0 8px 8px 8px;")
        self._qa_log.setPlaceholderText("سجل العمليات يظهر هنا…")
        outer_v.addWidget(self._qa_log)

        return outer

    def _make_action_card(self, icon: str, name: str,
                          desc: str, handler, accent_color: str = "#6366F1") -> QWidget:
        card = QFrame()
        card.setObjectName("ActionCard")
        
        # Main layout (Horizontal)
        h = QHBoxLayout(card)
        h.setContentsMargins(0, 0, 12, 0)
        h.setSpacing(12)

        # 1. Accent Bar (Vertical)
        accent = QFrame()
        accent.setFixedWidth(5)
        # Card is laid out in a QHBoxLayout; under the app-wide RTL
        # layoutDirection, Qt auto-mirrors QHBoxLayout child order, so this
        # accent bar (added first) now renders on the card's RIGHT edge —
        # round the right corners to match, instead of the left ones.
        accent.setStyleSheet(f"background: {accent_color}; border-top-right-radius: 12px; border-bottom-right-radius: 12px;")
        h.addWidget(accent)

        # 2. Icon
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        icon_lbl.setFixedWidth(40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(icon_lbl)

        # 3. Text content
        txt_v = QVBoxLayout()
        txt_v.setSpacing(2)
        txt_v.setContentsMargins(0, 10, 0, 10)
        
        name_lbl = QLabel(name)
        name_lbl.setObjectName("ActionTitle")
        
        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("ActionDesc")
        desc_lbl.setWordWrap(True)
        
        txt_v.addWidget(name_lbl)
        txt_v.addWidget(desc_lbl)
        h.addLayout(txt_v, 1)

        # 4. Action Button
        btn = PrimaryButton("تنفيذ")
        btn.setFixedWidth(85)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Apply specialized hover for destructive actions
        if accent_color == "#EF4444":
             btn.setStyleSheet("QPushButton#PrimaryButton { background: #EF4444; border: none; } QPushButton#PrimaryButton:hover { background: #DC2626; }")
             
        btn.clicked.connect(handler)
        h.addWidget(btn)
        
        return card

    def _qa_log_msg(self, msg: str):
        self._qa_log.append(msg)

    def _qa_rewrite_flush(self):
        self._qa_log.clear()
        self._qa_log_msg("⏳ تنفيذ: wp rewrite flush…")
        self._run_async(
            ["rewrite", "flush"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم' if ok else '❌ فشل'}: {out[:300]}"))

    def _qa_delete_transients(self):
        self._qa_log.clear()
        self._qa_log_msg("⏳ حذف جميع transients…")
        self._run_async(
            ["transient", "delete", "--all"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم' if ok else '❌ فشل'}: {out[:300]}"))

    def _qa_empty_trash(self):
        reply = QMessageBox.question(
            self, "تأكيد",
            "هل تريد حذف جميع محتويات سلة المهملات نهائياً؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._qa_log.clear()
        self._qa_log_msg("⏳ إفراغ السلة…")
        self._run_async(
            ["post", "delete", "--all", "--post_status=trash", "--force"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم' if ok else '❌ فشل'}: {out[:300]}"))

    def _qa_db_optimize(self):
        self._qa_log.clear()
        self._qa_log_msg("⏳ تحسين قاعدة البيانات…")
        self._run_async(
            ["db", "optimize"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم' if ok else '❌ فشل'}: {out[:300]}"))

    def _qa_regen_thumbs(self):
        reply = QMessageBox.question(
            self, "تأكيد",
            "إعادة توليد الصور المصغرة قد تستغرق وقتاً طويلاً.\nمتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._qa_log.clear()
        self._qa_log_msg("⏳ جاري توليد الصور… (قد يستغرق دقائق)")
        self._run_async(
            ["media", "regenerate", "--yes"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم' if ok else '❌ فشل'}: {out[:400]}"))

    def _qa_reset_admin_pass(self):
        new_pass, ok = QInputDialog.getText(
            self, "تغيير كلمة مرور Admin",
            "أدخل كلمة المرور الجديدة لأول مستخدم (admin):",
            QLineEdit.EchoMode.Password)
        if not ok or not new_pass.strip():
            return
        if len(new_pass) < 6:
            QMessageBox.warning(
                self, "ضعيفة", "كلمة المرور قصيرة جداً (6 أحرف كحد أدنى).")
            return
        self._qa_log.clear()
        self._qa_log_msg("⏳ تغيير كلمة المرور…")
        # Get first admin user ID first, then update
        self._run_async(
            ["user", "list", "--role=administrator",
             "--format=json", "--fields=ID", "--number=1"],
            lambda ok2, out: self._qa_update_pass_step2(ok2, out, new_pass))

    def _qa_update_pass_step2(self, ok: bool, output: str, new_pass: str):
        if not ok:
            self._qa_log_msg(f"❌ لا يمكن تحديد Admin ID: {output[:200]}")
            return
        try:
            users = self._parse_json(output)
            if not users:
                self._qa_log_msg("❌ لا يوجد مستخدم بصلاحية admin.")
                return
            admin_id = str(users[0].get("ID", "1"))
        except Exception:
            admin_id = "1"
        self._run_async(
            ["user", "update", admin_id, f"--user_pass={new_pass}"],
            lambda ok2, out: self._qa_log_msg(
                f"{'✅ تم تغيير كلمة المرور' if ok2 else '❌ فشل'}: {out[:300]}"))

    def _qa_update_siteurl(self):
        if not self.current:
            return
        current_url = self.current.url or ""
        new_url, ok = QInputDialog.getText(
            self, "تحديث Site URL",
            "أدخل الـ URL الجديد للموقع (بدون / في النهاية):",
            text=current_url)
        if not ok or not new_url.strip():
            return
        new_url = new_url.strip().rstrip("/")
        self._qa_log.clear()
        self._qa_log_msg(f"⏳ تحديث siteurl → {new_url}")
        self._run_async(
            ["option", "update", "siteurl", new_url],
            lambda ok2, out: (
                self._run_async(
                    ["option", "update", "home", new_url],
                    lambda ok3, out3: self._qa_log_msg(
                        f"{'✅ تم تحديث siteurl + home' if ok3 else '❌ فشل home'}"
                    )) if ok2 else
                self._qa_log_msg(f"❌ فشل تحديث siteurl: {out[:200]}")))

    def _qa_site_info(self):
        self._qa_log.clear()
        self._qa_log_msg("⏳ تحميل معلومات الموقع…")
        self._run_async(
            ["core", "version"],
            lambda ok, out: self._qa_log_msg(
                f"🌐 إصدار WordPress: {out.strip() if ok else '?'}"))
        self._run_async(
            ["eval", "echo phpversion();"],
            lambda ok, out: self._qa_log_msg(
                f"🐘 إصدار PHP: {out.strip() if ok else '?'}"))
        self._run_async(
            ["plugin", "list", "--status=active", "--format=count"],
            lambda ok, out: self._qa_log_msg(
                f"🧩 الإضافات النشطة: {out.strip() if ok else '?'}"))
        self._run_async(
            ["theme", "list", "--status=active", "--format=count"],
            lambda ok, out: self._qa_log_msg(
                f"🎨 القوالب النشطة: {out.strip() if ok else '?'}"))

    def _qa_toggle_maintenance(self):
        reply = QMessageBox.question(
            self, "وضع الصيانة",
            "اضغط Yes لتفعيل وضع الصيانة، أو No لإلغائه.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Cancel:
            return
        activate = reply == QMessageBox.StandardButton.Yes
        self._qa_log.clear()
        if activate:
            self._qa_log_msg("⏳ تفعيل وضع الصيانة…")
            self._run_async(
                ["maintenance-mode", "activate"],
                lambda ok, out: self._qa_log_msg(
                    f"{'✅ تم تفعيل وضع الصيانة' if ok else '❌ فشل'}: {out[:200]}"))
        else:
            self._qa_log_msg("⏳ إلغاء وضع الصيانة…")
            self._run_async(
                ["maintenance-mode", "deactivate"],
                lambda ok, out: self._qa_log_msg(
                    f"{'✅ تم إلغاء وضع الصيانة' if ok else '❌ فشل'}: {out[:200]}"))

    def _qa_update_salts(self):
        reply = QMessageBox.question(
            self, "تحديث Salt Keys",
            "سيتم توليد مفاتيح أمان جديدة.\nسيحتاج جميع المستخدمين لتسجيل الدخول مجدداً.\nمتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._qa_log.clear()
        self._qa_log_msg("⏳ تحديث Salt Keys…")
        self._run_async(
            ["config", "shuffle-salts"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم تحديث Salt Keys بنجاح' if ok else '❌ فشل'}: {out[:300]}"))

    def _qa_update_all_plugins(self):
        reply = QMessageBox.question(
            self, "تحديث الإضافات",
            "هل تريد تحديث جميع الإضافات المثبتة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._qa_log.clear()
        self._qa_log_msg("⏳ تحديث جميع الإضافات… (قد يستغرق دقيقة)")
        self._run_async(
            ["plugin", "update", "--all"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم التحديث' if ok else '❌ فشل'}: {out[:400]}"))

    def _qa_verify_checksums(self):
        self._qa_log.clear()
        self._qa_log_msg("⏳ فحص سلامة ملفات WordPress…")
        self._run_async(
            ["core", "verify-checksums"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ الملفات سليمة' if ok else '⚠️ تم اكتشاف تعديلات'}: {out[:400]}"))

    def _qa_export_db(self):
        if not self.current:
            return
        from PyQt6.QtWidgets import QFileDialog
        import datetime
        default_name = (
            f"{self.current.name}_backup_"
            f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "حفظ نسخة احتياطية", default_name, "SQL Files (*.sql)")
        if not path:
            return
        self._qa_log.clear()
        self._qa_log_msg(f"⏳ تصدير قاعدة البيانات إلى: {path}")
        self._run_async(
            ["db", "export", path],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم التصدير بنجاح' if ok else '❌ فشل التصدير'}: {out[:300]}"))

    def _qa_search_replace(self):
        if not self.current:
            return
        search, ok1 = QInputDialog.getText(
            self, "البحث والاستبدال", "النص المراد البحث عنه:")
        if not ok1 or not search.strip():
            return
        replace, ok2 = QInputDialog.getText(
            self, "البحث والاستبدال", f"استبدال '{search}' بـ:")
        if not ok2:
            return
        reply = QMessageBox.warning(
            self, "تأكيد",
            f"سيتم استبدال:\n'{search}'\nبـ:\n'{replace}'\n\n"
            "في قاعدة البيانات. هذا لا يمكن التراجع عنه!\nمتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._qa_log.clear()
        self._qa_log_msg(f"⏳ استبدال '{search}' بـ '{replace}'…")
        self._run_async(
            ["search-replace", search.strip(), replace.strip(), "--all-tables"],
            lambda ok, out: self._qa_log_msg(
                f"{'✅ تم الاستبدال' if ok else '❌ فشل'}: {out[:400]}"))
