from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal

from app.core.wp_ops import (
    DBParams, WPParams, install_wordpress, backup_bundle, restore_bundle,
    wp_cli_search_replace, clone_project, search_replace_url_in_db
)

# ---------- Worker tasks ----------
class InstallWorker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    done = pyqtSignal(bool, dict, str)  # ok, result, message

    def __init__(self, wp: WPParams, db: DBParams):
        super().__init__()
        self.wp = wp
        self.db = db

    def run(self):
        try:
            self.progress.emit(0)
            res = install_wordpress(self.wp, self.db, log=self.log.emit, progress=self.progress.emit)
            self.done.emit(True, res, "اكتمل التثبيت ✅")
        except Exception as e:
            self.done.emit(False, {}, f"{e}")


class BackupWorker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    done = pyqtSignal(bool, str, str)  # ok, message, backup_dir

    def __init__(self, project_path: str, db: DBParams, backup_root: str, include_files: bool, include_db: bool):
        super().__init__()
        self.project_path = Path(project_path)
        self.db = db
        self.backup_root = Path(backup_root)
        self.include_files = include_files
        self.include_db = include_db

    def run(self):
        try:
            bdir = backup_bundle(
                self.project_path, self.db, self.backup_root,
                log=self.log.emit, progress=self.progress.emit,
                include_files=self.include_files, include_db=self.include_db
            )
            self.done.emit(True, "اكتملت النسخة الاحتياطية ✅", str(bdir))
        except Exception as e:
            self.done.emit(False, str(e), "")

class RestoreWorker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    done = pyqtSignal(bool, str)

    def __init__(self, project_path: str, db: DBParams, backup_dir: str, restore_files: bool, restore_db: bool):
        super().__init__()
        self.project_path = Path(project_path)
        self.db = db
        self.backup_dir = Path(backup_dir)
        self.restore_files = restore_files
        self.restore_db = restore_db

    def run(self):
        try:
            restore_bundle(
                self.project_path, self.db, self.backup_dir,
                log=self.log.emit, progress=self.progress.emit,
                restore_files=self.restore_files, restore_db=self.restore_db
            )
            self.done.emit(True, "اكتملت الاستعادة ✅")
        except Exception as e:
            self.done.emit(False, str(e))

class UrlConvertWorker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    done = pyqtSignal(bool, str, str)  # success, message, new_path

    def __init__(self, project_path: str, db: DBParams, old_url: str, new_url: str,
                 php_path: str, wpcli_path: str, wpcli_is_phar: bool, include_guid: bool, rename_folder: bool = False):
        super().__init__()
        self.project_path = Path(project_path)
        self.db = db
        self.old_url = old_url
        self.new_url = new_url
        self.php_path = php_path
        self.wpcli_path = wpcli_path
        self.wpcli_is_phar = wpcli_is_phar
        self.include_guid = include_guid
        self.rename_folder = rename_folder

    def run(self):
        try:
            self.progress.emit(10)
            
            # WP-CLI / DB Search Replace
            if self.php_path and self.wpcli_path:
                self.log.emit("جارٍ استخدام WP-CLI search-replace (آمن للبيانات المتسلسلة)...")
                
                # Check & Fix hardcoded URLs in wp-config.php BEFORE replace to ensure consistency
                try:
                    config_path = self.project_path / "wp-config.php"
                    config_txt = config_path.read_text(encoding="utf-8", errors="ignore")
                    
                    updated = False
                    import re
                    for key in ["WP_HOME", "WP_SITEURL"]:
                        pattern = re.compile(rf"define\(\s*['\"]{key}['\"]\s*,\s*['\"][^'\"]+['\"]\s*\);", re.IGNORECASE)
                        if pattern.search(config_txt):
                            self.log.emit(f"جارٍ تحديث {key} في wp-config.php...")
                            config_txt = pattern.sub(f"define( '{key}', '{self.new_url}' );", config_txt)
                            updated = True
                    
                    if updated:
                        config_path.write_text(config_txt, encoding="utf-8")
                        self.log.emit("تم إصلاح الروابط الثابتة في wp-config.php ✅")

                except Exception as e:
                    self.log.emit(f"تحذير: تعذر التحقق من wp-config.php: {e}")

                wp_cli_search_replace(
                    self.project_path, self.php_path, self.wpcli_path, self.wpcli_is_phar,
                    self.old_url, self.new_url, self.include_guid, self.log.emit
                )
                
                # Flush Cache
                self.log.emit("جارٍ تفريغ ذاكرة التخزين المؤقت للكائنات...")
                from app.core.wp_ops import run_wpcli
                run_wpcli(
                    self.project_path, self.php_path, self.wpcli_path, self.wpcli_is_phar,
                    ["cache", "flush"], self.log.emit
                )
            else:
                self.log.emit("WP-CLI غير متاح — سيتم تطبيق تحديث محدود لقاعدة البيانات (الخيارات فقط).")
                search_replace_url_in_db(self.db, self.old_url, self.new_url, self.log.emit)
            
            self.progress.emit(80)
            
            # Rename Folder Logic
            final_path = str(self.project_path)
            if self.rename_folder:
                import shutil
                from urllib.parse import urlparse
                
                # Extract slug from new ID
                # e.g. http://localhost/myshop -> myshop
                try:
                    parsed = urlparse(self.new_url)
                    path_slug = parsed.path.strip("/").split("/")[-1]
                    if not path_slug:
                        path_slug = parsed.netloc.split(":")[0] # Fallback to domain if root
                    
                    if path_slug:
                        new_folder_path = self.project_path.parent / path_slug
                        if new_folder_path != self.project_path:
                            if new_folder_path.exists():
                                self.log.emit(f"⚠️ لا يمكن إعادة تسمية المجلد: '{path_slug}' موجود بالفعل.")
                            else:
                                self.log.emit(f"جارٍ إعادة تسمية المجلد إلى: {path_slug} ...")
                                # We need to close any open file handles? Usually ok on Windows if no other app uses it.
                                # But we might need to be careful with logging/python using files.
                                # shutil.move is risky if file is locked.
                                try:
                                    shutil.move(str(self.project_path), str(new_folder_path))
                                    final_path = str(new_folder_path)
                                    self.log.emit("تمت إعادة تسمية المجلد بنجاح ✅")
                                except Exception as ren_err:
                                    self.log.emit(f"❌ فشلت إعادة تسمية المجلد: {ren_err}")
                except Exception as e:
                    self.log.emit(f"خطأ في تحليل الرابط لإعادة التسمية: {e}")

            self.progress.emit(100)
            self.done.emit(True, "اكتمل تحويل الرابط ✅", final_path)

        except Exception as e:
            self.done.emit(False, str(e), str(self.project_path))

class CloneWorker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    done = pyqtSignal(bool, str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            clone_project(
                src_path=Path(self.params["src_path"]),
                dst_path=Path(self.params["dst_path"]),
                src_db=self.params["src_db"],
                dst_db=self.params["dst_db"],
                old_url=self.params["old_url"],
                new_url=self.params["new_url"],
                php_path=self.params["php_path"],
                wpcli_path=self.params["wpcli_path"],
                wpcli_is_phar=self.params["wpcli_is_phar"],
                log=self.log.emit,
                progress=self.progress.emit,
            )
            self.done.emit(True, "اكتمل الاستنساخ ✅")
        except Exception as e:
            self.done.emit(False, f"{e}")

class HealthCheckWorker(QObject):
    done = pyqtSignal(dict)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        from app.core.monitoring import SiteMonitor
        result = SiteMonitor.check_site_health(self.url)
        self.done.emit(result)


class ScanWorker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    done = pyqtSignal(bool, list, str) # ok, results, msg

    def __init__(self, project_path: str):
        super().__init__()
        self.project_path = project_path

    def run(self):
        try:
            from app.core.security import scan_for_malware
            res = scan_for_malware(self.project_path, self.log.emit, self.progress.emit)
            self.done.emit(True, res, "اكتمل الفحص ✅")
        except Exception as e:
            self.done.emit(False, [], str(e))

class ListItemsWorker(QObject):
    """Worker for asynchronously loading plugins or themes using WP-CLI."""
    log = pyqtSignal(str)
    done = pyqtSignal(bool, list, str)  # success, items_list, error_msg
    
    def __init__(self, project_path: str, php: str, wpcli: str, is_phar: bool, item_type: str):
        super().__init__()
        self.project_path = project_path
        self.php = php
        self.wpcli = wpcli
        self.is_phar = is_phar
        self.item_type = item_type
    
    def run(self):
        try:
            from app.core.wp_ops import list_wp_items
            items = list_wp_items(
                Path(self.project_path), 
                self.php, 
                self.wpcli, 
                self.is_phar, 
                self.item_type,
                log=self.log.emit
            )
            self.done.emit(True, items, "")
        except Exception as e:
            self.done.emit(False, [], str(e))

