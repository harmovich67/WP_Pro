"""
app/ui/url_sharing_page.py
─────────────────────────────────────────────
Live URL Sharing: exposes the selected local WordPress site to the internet
through a Cloudflare quick tunnel (no account needed) and shows a public
HTTPS link a client can open immediately. While sharing is active, the
site's siteurl/home are optionally rewritten (via WP-CLI search-replace) to
the public URL so generated links/assets resolve correctly, then reverted
automatically when sharing stops.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QThread, QObject, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QCheckBox, QTextEdit,
    QMessageBox, QApplication, QPushButton
)

from app.core.projects_store import ProjectRecord
from app.core import url_sharing as sharing
from app.core.wp_ops import get_effective_tooling, run_wpcli
from app.ui.extra_pages import BaseExtraPage
from app.ui.widgets import make_card, Pill, PrimaryButton, row_buttons
from app.core.i18n import t as tr


def _session_file(project_path: Path) -> Path:
    d = project_path / ".wpinst"
    d.mkdir(parents=True, exist_ok=True)
    return d / "live_share.json"


class _SearchReplaceWorker(QThread):
    """One-shot background WP-CLI search-replace, used to point site URLs at
    the tunnel while sharing and to revert them back when sharing stops."""
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, project_path: Path, php: str, wpcli: str, is_phar: bool,
                 old_url: str, new_url: str, parent=None):
        super().__init__(parent)
        self._path = project_path
        self._php = php
        self._wpcli = wpcli
        self._is_phar = is_phar
        self._old = old_url
        self._new = new_url

    def run(self):
        try:
            old = self._old.rstrip("/")
            new = self._new.rstrip("/")
            run_wpcli(
                self._path, self._php, self._wpcli, self._is_phar,
                ["search-replace", old, new, "--all-tables", "--precise", "--skip-columns=guid"],
                self.log.emit,
            )
            # Flush WordPress cache if possible so old asset URLs are cleared
            try:
                run_wpcli(self._path, self._php, self._wpcli, self._is_phar, ["cache", "flush"], lambda _: None)
            except Exception:
                pass
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, str(e))


class _DownloadCloudflaredWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    done = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            path = sharing.download_cloudflared(self.log.emit, self.progress.emit)
            self.done.emit(True, path)
        except Exception as e:
            self.done.emit(False, str(e))


class UrlSharingPage(BaseExtraPage):
    def __init__(self, store, parent_window):
        super().__init__(store, parent_window)

        card, lay = make_card(
            tr("مشاركة رابط مباشر (Live URL Sharing)"),
            tr("اعرض موقعك المحلي على الإنترنت فوراً برابط HTTPS مؤقت — مثالي لعرض العمل على العميل دون نشر."))

        self.status_pill = Pill(tr("غير مُفعّل"), "neutral")
        lay.addWidget(self.status_pill)

        self.stale_banner = QLabel("")
        self.stale_banner.setWordWrap(True)
        self.stale_banner.setStyleSheet(
            "background:#78350F; color:#FDE68A; border-radius:6px; padding:8px; font-size:11px;")
        self.stale_banner.setVisible(False)
        lay.addWidget(self.stale_banner)

        self.chk_rewrite_urls = QCheckBox(tr("تحديث روابط الموقع مؤقتاً لتعمل الوسائط والروابط عند العميل (يوصى به)"))
        self.chk_rewrite_urls.setChecked(True)
        lay.addWidget(self.chk_rewrite_urls)

        self.btn_start = PrimaryButton(tr("🚀 بدء المشاركة المباشرة"))
        self.btn_stop = QPushButton(tr("⏹ إيقاف المشاركة"))
        self.btn_stop.setEnabled(False)
        lay.addWidget(row_buttons(self.btn_start, self.btn_stop))

        share_row = QHBoxLayout()
        self.share_url_edit = QLineEdit()
        self.share_url_edit.setReadOnly(True)
        self.share_url_edit.setPlaceholderText(tr("سيظهر الرابط العام هنا بعد بدء المشاركة..."))
        self.btn_copy = QPushButton(tr("📋 نسخ"))
        self.btn_open = QPushButton(tr("🌐 فتح"))
        self.btn_copy.setEnabled(False)
        self.btn_open.setEnabled(False)
        share_row.addWidget(self.share_url_edit, 1)
        share_row.addWidget(self.btn_copy)
        share_row.addWidget(self.btn_open)
        lay.addLayout(share_row)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(180)
        self.log_box.document().setMaximumBlockCount(500)  # bound growth during long/busy shares
        lay.addWidget(self.log_box)

        self.content_area.addWidget(card)

        self.btn_start.clicked.connect(self._start_sharing)
        self.btn_stop.clicked.connect(self._stop_sharing)
        self.btn_copy.clicked.connect(self._copy_url)
        self.btn_open.clicked.connect(self._open_url)

        self._tunnel_worker: sharing.TunnelWorker | None = None
        self._sr_worker: _SearchReplaceWorker | None = None
        self._dl_worker: _DownloadCloudflaredWorker | None = None

        self._share_url = ""
        self._active = False

        self._set_enabled(False)

    # ── BaseExtraPage hooks ─────────────────────────────────────────────
    def _on_project_selected(self, p: ProjectRecord):
        self._set_enabled(True)
        self._check_stale_session(p)

    def _on_project_cleared(self):
        self._set_enabled(False)
        self.stale_banner.setVisible(False)

    def _set_enabled(self, val: bool):
        self.btn_start.setEnabled(val and not self._active)
        self.chk_rewrite_urls.setEnabled(val and not self._active)
        if hasattr(self, "combo"):
            self.combo.setEnabled(not self._active)

    def _check_stale_session(self, p: ProjectRecord):
        f = _session_file(Path(p.path))
        if not f.exists():
            self.stale_banner.setVisible(False)
            return
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            f.unlink(missing_ok=True)
            return
        self.stale_banner.setText(
            f"{tr('⚠️ تم العثور على جلسة مشاركة سابقة لم تُغلق بشكل صحيح لهذا المشروع (')}"
            f"{data.get('share_url','')}{tr('). انقر لاستعادة الرابط المحلي.')}")
        self.stale_banner.setVisible(True)
        try:
            self.stale_banner.mousePressEvent = lambda ev: self._restore_stale(p, data)
        except Exception:
            pass

    def _restore_stale(self, p: ProjectRecord, data: dict):
        try:
            php, wpcli, is_phar = get_effective_tooling(p, log=self.log_box.append)
            if wpcli:
                old_url = data.get("share_url", "").rstrip("/")
                orig_url = data.get("original_url", "").rstrip("/")
                run_wpcli(Path(p.path), php, wpcli, is_phar,
                          ["search-replace", old_url, orig_url,
                           "--all-tables", "--precise", "--skip-columns=guid"], self.log_box.append)
            _session_file(Path(p.path)).unlink(missing_ok=True)
            self.stale_banner.setVisible(False)
            self.parent_window.show_toast(tr("✓ تمت استعادة الرابط المحلي"), "success")
        except Exception as e:
            QMessageBox.critical(self, tr("خطأ"), str(e))

    # ── Start / stop ─────────────────────────────────────────────────────
    def _start_sharing(self):
        if not self.current or self._active:
            return

        cf = sharing.find_cloudflared()
        if not cf:
            r = QMessageBox.question(
                self, tr("تنزيل أداة المشاركة"),
                tr("أداة المشاركة المباشرة (cloudflared) غير مثبتة. هل تريد تنزيلها الآن تلقائياً؟"))
            if r != QMessageBox.StandardButton.Yes:
                return
            self._download_then_start()
            return

        self._begin_tunnel(cf)

    def _download_then_start(self):
        self.btn_start.setEnabled(False)
        self.log_box.append(tr("جارٍ تنزيل أداة المشاركة المباشرة..."))

        self._dl_worker = _DownloadCloudflaredWorker(parent=self)
        self._dl_worker.log.connect(self.log_box.append)
        self._dl_worker.done.connect(self._on_download_done)
        self._dl_worker.start()

    def _on_download_done(self, ok: bool, path_or_err: str):
        if self._dl_worker:
            self._dl_worker.wait(1000)
            self._dl_worker = None
        if not ok:
            self.btn_start.setEnabled(True)
            QMessageBox.critical(self, tr("فشل التنزيل"), path_or_err)
            return
        self._begin_tunnel(path_or_err)

    def _begin_tunnel(self, cloudflared_path: str):
        proj_path = Path(self.current.path)
        # Ensure wp-config.php detects SSL reverse proxy so CSS/JS load with HTTPS
        sharing.ensure_reverse_proxy_ssl_config(proj_path, log=self.log_box.append)

        target, host_header = sharing.derive_target_and_host(self.current.url)
        self.log_box.append(f"{tr('جارٍ إنشاء نفق مباشر إلى: ')}{target}"
                             + (f" ({tr('Host')}: {host_header})" if host_header else ""))

        self._active = True
        self._set_enabled(True)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.status_pill.set_state(tr("جارٍ إنشاء رابط المشاركة..."), "warn")

        self._tunnel_worker = sharing.TunnelWorker(cloudflared_path, target, host_header, parent=self)
        self._tunnel_worker.log.connect(self.log_box.append)
        self._tunnel_worker.url_ready.connect(self._on_tunnel_url_ready)
        self._tunnel_worker.tunnel_finished.connect(self._on_tunnel_finished)
        self._tunnel_worker.start()

    def _on_tunnel_url_ready(self, base_url: str):
        if not self.current:
            return
        self._share_url = sharing.build_share_url(base_url, self.current.url)
        self.share_url_edit.setText(self._share_url)
        self.log_box.append(f"{tr('✅ تم إنشاء النفق المباشر: ')}{self._share_url}")

        if self.chk_rewrite_urls.isChecked():
            self.btn_copy.setEnabled(False)
            self.btn_open.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.status_pill.set_state(tr("جارٍ تحديث روابط الموقع..."), "warn")
            self.log_box.append(tr("جارٍ تحديث روابط وقواعد بيانات الموقع لتعمل الاستايلات والوسائط عند العميل..."))

            def _on_rewrite_done():
                self.btn_copy.setEnabled(True)
                self.btn_open.setEnabled(True)
                self.btn_stop.setEnabled(True)
                self.status_pill.set_state(tr("🔴 مباشر — الموقع مشارك الآن"), "ok")
                self.log_box.append(f"{tr('✅ الرابط العام جاهز ومكتمل: ')}{self._share_url}")
                self._save_session()
                self.parent_window.show_toast(tr("✓ تم تجهيز الرابط المباشر بنجاح"), "success")

            self._rewrite_urls(self.current.url, self._share_url, on_done=_on_rewrite_done)
        else:
            self.btn_copy.setEnabled(True)
            self.btn_open.setEnabled(True)
            self.status_pill.set_state(tr("🔴 مباشر — الموقع مشارك الآن"), "ok")
            self._save_session()

    def _save_session(self, *_args):
        if not self.current:
            return
        data = {"original_url": self.current.url, "share_url": self._share_url}
        _session_file(Path(self.current.path)).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _on_tunnel_finished(self, code: int):
        if self._tunnel_worker:
            self._tunnel_worker.wait(1000)
            self._tunnel_worker = None
        if self._active:
            self.log_box.append(f"{tr('انتهت جلسة المشاركة (كود الخروج: ')}{code})")
        self._active = False
        self.btn_stop.setEnabled(False)
        self._set_enabled(True)
        self.status_pill.set_state(tr("غير مُفعّل"), "neutral")

    def _stop_sharing(self):
        if not self._active:
            return
        self.btn_stop.setEnabled(False)
        self.status_pill.set_state(tr("جارٍ إيقاف المشاركة..."), "warn")

        def _after_revert(*_args):
            if self.current:
                _session_file(Path(self.current.path)).unlink(missing_ok=True)
            if self._tunnel_worker:
                self._tunnel_worker.stop()
                self._tunnel_worker.wait(2000)
                self._tunnel_worker = None
            self._active = False
            self.btn_stop.setEnabled(False)
            self._set_enabled(True)
            self.status_pill.set_state(tr("غير مُفعّل"), "neutral")

        if self.chk_rewrite_urls.isChecked() and self._share_url and self.current:
            self._rewrite_urls(self._share_url, self.current.url, on_done=_after_revert)
        else:
            _after_revert()

    def _rewrite_urls(self, old_url: str, new_url: str, on_done):
        if not self.current:
            on_done()
            return
        try:
            php, wpcli, is_phar = get_effective_tooling(self.current, log=self.log_box.append)
        except Exception:
            php, wpcli, is_phar = "", "", False
        if not wpcli:
            self.log_box.append(tr("⚠️ WP-CLI غير متوفر — لن يتم تحديث روابط الموقع تلقائياً."))
            on_done()
            return

        if self._sr_worker and self._sr_worker.isRunning():
            self._sr_worker.wait(2000)

        self._sr_worker = _SearchReplaceWorker(
            Path(self.current.path), php, wpcli, is_phar, old_url, new_url, parent=self
        )
        self._sr_worker.log.connect(self.log_box.append)

        def _cleanup(ok: bool, err: str):
            if not ok and err:
                self.log_box.append(f"{tr('⚠️ تعذّر تحديث روابط الموقع: ')}{err}")
            if self._sr_worker:
                self._sr_worker.wait(1000)
                self._sr_worker = None
            on_done()

        self._sr_worker.done.connect(_cleanup)
        self._sr_worker.start()

    # ── Clipboard / browser ──────────────────────────────────────────────
    def _copy_url(self):
        if self._share_url:
            QApplication.clipboard().setText(self._share_url)
            self.parent_window.show_toast(tr("✓ تم نسخ الرابط"), "success")

    def _open_url(self):
        if self._share_url:
            QDesktopServices.openUrl(QUrl(self._share_url))

    def cleanup(self):
        """Cleanly terminate background processes/threads before shutdown."""
        if self._tunnel_worker and self._tunnel_worker.isRunning():
            self._tunnel_worker.stop()
            self._tunnel_worker.wait(2000)
            self._tunnel_worker = None
        if self._sr_worker and self._sr_worker.isRunning():
            self._sr_worker.wait(2000)
            self._sr_worker = None
        if self._dl_worker and self._dl_worker.isRunning():
            self._dl_worker.wait(2000)
            self._dl_worker = None
