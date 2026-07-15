"""
Auto-fix Module for Common WordPress Issues
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable

LogFn = Callable[[str], None]

class AutoFix:
    @staticmethod
    def regenerate_htaccess(project_path: str, log: LogFn) -> bool:
        """Regenerate .htaccess with WordPress defaults"""
        try:
            htaccess_content = """# BEGIN WordPress
<IfModule mod_rewrite.c>
RewriteEngine On
RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]
RewriteBase /
RewriteRule ^index\\.php$ - [L]
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule . /index.php [L]
</IfModule>
# END WordPress"""
            
            htaccess = Path(project_path) / ".htaccess"
            htaccess.write_text(htaccess_content, encoding="utf-8")
            log("✅ تمت إعادة إنشاء ملف .htaccess")
            return True
        except Exception as e:
            log(f"❌ فشل إعادة إنشاء ملف .htaccess: {e}")
            return False
    
    @staticmethod
    def fix_permissions(project_path: str, log: LogFn) -> bool:
        """Fix file permissions (Windows: read-only removal)"""
        try:
            import os
            import stat
            
            path = Path(project_path)
            count = 0
            
            for item in path.rglob("*"):
                if item.is_file():
                    # Remove read-only on Windows
                    os.chmod(item, stat.S_IWRITE | stat.S_IREAD)
                    count += 1
            
            log(f"✅ تم إصلاح الأذونات لعدد {count} من الملفات")
            return True
        except Exception as e:
            log(f"❌ فشل إصلاح الأذونات: {e}")
            return False
    
    @staticmethod
    def clear_cache(project_path: str, log: LogFn) -> bool:
        """Clear WordPress cache directories"""
        try:
            cache_dirs = [
                Path(project_path) / "wp-content" / "cache",
                Path(project_path) / "wp-content" / "uploads" / "cache",
            ]
            
            import shutil
            cleared = 0
            
            for cache_dir in cache_dirs:
                if cache_dir.exists():
                    for item in cache_dir.iterdir():
                        if item.is_file():
                            item.unlink()
                            cleared += 1
                        elif item.is_dir():
                            shutil.rmtree(item)
                            cleared += 1
            
            log(f"✅ تم مسح {cleared} من عناصر ذاكرة التخزين المؤقت")
            return True
        except Exception as e:
            log(f"❌ فشل مسح ذاكرة التخزين المؤقت: {e}")
            return False
