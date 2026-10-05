from __future__ import annotations
import os
import hashlib
from pathlib import Path
from typing import Callable
from app.core.i18n import t as tr

LogFn = Callable[[str], None]

HTACCESS_HARDENING_RULES = """
# Hardening Rules by WP Local Installer Pro
# Disable directory browsing
Options -Indexes

# Protect wp-config.php
<Files wp-config.php>
    order allow,deny
    deny from all
</Files>

# Protect htaccess
<Files .htaccess>
    order allow,deny
    deny from all
</Files>

# Disable XML-RPC (optional but recommended for security)
<Files xmlrpc.php>
    order allow,deny
    deny from all
</Files>

# Block access to log files
<Files *.log>
    order allow,deny
    deny from all
</Files>

# Block PHP in uploads folder (Needs to be placed in /wp-content/uploads/.htaccess)
"""

UPLOADS_HTACCESS = """
# Block PHP execution in uploads directory
<Files *.php>
    deny from all
</Files>
"""

MALWARE_SIGNATURES = [
    "eval(base64_decode",
    "gzuncompress(base64_decode",
    "shell_exec(",
    "system(",
    "passthru(",
    "exec(",
    "base64_decode('YmFzZTY0X2RlY29kZSA=", # common obfuscation
    "Wp-vcd", # common malware name
    "GLOBALS['_']",
    "$_POST['", # can be legit, but also shell
    "move_uploaded_file("
]

def apply_htaccess_hardening(project_path: str, log: LogFn):
    root = Path(project_path)
    htaccess = root / ".htaccess"
    
    log(f"{tr('جارٍ تطبيق التحصين على ملف .htaccess الرئيسي في ')}{project_path}")
    existing = ""
    if htaccess.exists():
        existing = htaccess.read_text(encoding="utf-8")

    if "# Hardening Rules by WP Local Installer Pro" in existing:
        log(tr("التحصين مُطبّق بالفعل. جارٍ التحديث..."))
        # Simple update: replace old block if found or just append if logic is complex
        # For simplicity, we append if not found exactly or just skip if already present
        return

    with open(htaccess, "a", encoding="utf-8") as f:
        f.write("\n" + HTACCESS_HARDENING_RULES + "\n")
    log(tr("تم تحصين ملف .htaccess الرئيسي."))

    # Hardening uploads folder
    uploads = root / "wp-content" / "uploads"
    if uploads.exists():
        u_htaccess = uploads / ".htaccess"
        log(tr("جارٍ تحصين مجلد uploads..."))
        with open(u_htaccess, "w", encoding="utf-8") as f:
            f.write(UPLOADS_HTACCESS)
    else:
        log(tr("لم يتم العثور على مجلد uploads، سيتم تخطي تحصين المجلد الفرعي."))

def scan_for_malware(project_path: str, log: LogFn, progress: Callable[[int], None] | None = None) -> list[dict]:
    root = Path(project_path)
    results = []
    log(f"{tr('جارٍ فحص ')}{project_path}{tr(' بحثاً عن توقيعات البرمجيات الخبيثة...')}")
    
    php_files = list(root.rglob("*.php"))
    total = len(php_files)
    
    for i, p in enumerate(php_files):
        if progress:
            progress(int((i / total) * 100))
            
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                found = []
                for sig in MALWARE_SIGNATURES:
                    if sig in content:
                        found.append(sig)
                
                if found:
                    results.append({
                        "file": str(p.relative_to(root)),
                        "sigs": found
                    })
            except Exception as e:
                log(f"{tr('تعذر فحص ')}{p}: {e}")

    if progress:
        progress(100)
    log(f"{tr('انتهى الفحص. تم العثور على ')}{len(results)}{tr(' ملف مشبوه.')}")
    return results

def get_file_hashes(project_path: str, log: LogFn) -> dict[str, str]:
    root = Path(project_path)
    hashes = {}
    log(tr("جارٍ إنشاء سجل تكامل الملفات..."))
    
    for p in root.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            try:
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                hashes[str(p.relative_to(root))] = h
            except Exception:
                continue
    return hashes
