\
from __future__ import annotations

import os
import re
import shutil
import zipfile
import tempfile
import platform
import secrets
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
import pymysql

from app.core.utils import run_cmd, which_any

WORDPRESS_LATEST_ZIP = "https://wordpress.org/latest.zip"
WP_SALTS_API = "https://api.wordpress.org/secret-key/1.1/salt/"
WPCLI_PHAR_URL = "https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar"

LogFn = Callable[[str], None]
ProgressFn = Callable[[int], None]

@dataclass
class DBParams:
    host: str
    port: int
    root_user: str
    root_pass: str
    db_name: str
    create_user: bool
    user: str
    user_pass: str
    user_host: str
    table_prefix: str

@dataclass
class WPParams:
    doc_root: Path
    project_name: str
    site_title: str
    site_url: str
    admin_user: str
    admin_pass: str
    admin_email: str
    wp_zip_url: str
    wp_zip_local: str
    overwrite: bool

    stack_name: str
    laragon_root: str

    auto_install: bool
    php_path: str
    wpcli_path: str
    download_wpcli: bool

    template_name: str
    install_theme: str
    plugins: list[str]
    dev_mode: bool
    permalinks: str  # e.g. "/%postname%/"

def _ensure_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    return url

def download_file(url: str, out_path: Path, log: LogFn, progress: ProgressFn, start_pct: int = 0, end_pct: int = 30):
    log(f"جارٍ التنزيل: {url}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=90) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        done = 0

        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total > 0:
                    p = done / total
                    pct = start_pct + int((end_pct - start_pct) * p)
                    progress(pct)

    log(f"تم الحفظ: {out_path}")

def extract_wordpress_zip(zip_path: Path, out_dir: Path, log: LogFn, progress: ProgressFn, start_pct: int = 30, end_pct: int = 45) -> Path:
    log("جارٍ استخراج ملف WordPress المضغوط...")
    with zipfile.ZipFile(zip_path, "r") as z:
        infos = z.infolist()
        total = max(1, len(infos))
        for i, info in enumerate(infos, start=1):
            z.extract(info, out_dir)
            pct = start_pct + int((end_pct - start_pct) * (i / total))
            progress(pct)

    wp_dir = out_dir / "wordpress"
    if not wp_dir.exists():
        raise RuntimeError("هيكل الملف المضغوط غير متوقع (مجلد 'wordpress' غير موجود).")
    return wp_dir

def copy_tree_contents(src: Path, dst: Path, log: LogFn, progress: ProgressFn, start_pct: int = 45, end_pct: int = 55):
    log("جارٍ نسخ الملفات...")
    dst.mkdir(parents=True, exist_ok=True)
    items = list(src.iterdir())
    total = max(1, len(items))
    for i, item in enumerate(items, start=1):
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
        pct = start_pct + int((end_pct - start_pct) * (i / total))
        progress(pct)

def mysql_connect(host: str, port: int, user: str, password: str):
    return pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4", autocommit=True)

def test_mysql(db: DBParams) -> tuple[bool, str]:
    try:
        conn = mysql_connect(db.host, db.port, db.root_user, db.root_pass)
        conn.close()
        return True, "الاتصال ناجح"
    except Exception as e:
        return False, f"{e}"

def create_database_and_user(db: DBParams, log: LogFn):
    log("جارٍ الاتصال بـ MySQL/MariaDB...")
    conn = mysql_connect(db.host, db.port, db.root_user, db.root_pass)
    try:
        with conn.cursor() as cur:
            log(f"جارٍ إنشاء قاعدة البيانات: {db.db_name}")
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db.db_name}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )

            if db.create_user:
                log(f"جارٍ إنشاء مستخدم قاعدة البيانات: {db.user}@{db.user_host}")
                cur.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s;", (db.user, db.user_host, db.user_pass))
                log("جارٍ منح الصلاحيات...")
                cur.execute(f"GRANT ALL PRIVILEGES ON `{db.db_name}`.* TO %s@%s;", (db.user, db.user_host))
                cur.execute("FLUSH PRIVILEGES;")
    finally:
        conn.close()

def drop_database(db: DBParams, log: LogFn):
    log("جارٍ الاتصال بـ MySQL/MariaDB للحذف...")
    conn = mysql_connect(db.host, db.port, db.root_user, db.root_pass)
    try:
        with conn.cursor() as cur:
            log(f"جارٍ حذف قاعدة البيانات: {db.db_name}")
            cur.execute(f"DROP DATABASE IF EXISTS `{db.db_name}`;")
            if db.create_user:
                log(f"جارٍ حذف المستخدم: {db.user}@{db.user_host}")
                cur.execute(f"DROP USER IF EXISTS %s@%s;", (db.user, db.user_host))
            cur.execute("FLUSH PRIVILEGES;")
    finally:
        conn.close()

def _generate_random_salts_block() -> str:
    chars = string.ascii_letters + string.digits + string.punctuation

    def rnd():
        return "".join(secrets.choice(chars) for _ in range(64)).replace("\\", "\\\\").replace("'", "\\'")

    keys = [
        "AUTH_KEY", "SECURE_AUTH_KEY", "LOGGED_IN_KEY", "NONCE_KEY",
        "AUTH_SALT", "SECURE_AUTH_SALT", "LOGGED_IN_SALT", "NONCE_SALT",
    ]
    lines = [f"define( '{k}', '{rnd()}' );" for k in keys]
    return "\n".join(lines) + "\n"

def fetch_salts_block(log: LogFn) -> str:
    try:
        log("جارٍ جلب مفاتيح الأمان (Salts) من واجهة WordPress API...")
        r = requests.get(WP_SALTS_API, timeout=20)
        r.raise_for_status()
        return r.text.strip() + "\n"
    except Exception as e:
        log(f"فشل جلب مفاتيح الأمان من الواجهة، سيتم استخدام مفاتيح عشوائية محلية. ({e})")
        return _generate_random_salts_block()

def write_wp_config(target_path: Path, db: DBParams, wp_db_user: str, wp_db_pass: str, log: LogFn):
    log("جارٍ إنشاء ملف wp-config.php ...")
    sample = target_path / "wp-config-sample.php"
    if not sample.exists():
        raise RuntimeError("ملف wp-config-sample.php غير موجود بعد الاستخراج.")

    content = sample.read_text(encoding="utf-8", errors="ignore")
    content = content.replace("database_name_here", db.db_name)
    content = content.replace("username_here", wp_db_user)
    content = content.replace("password_here", wp_db_pass)
    content = content.replace("localhost", f"{db.host}:{db.port}")

    content = re.sub(
        r"^\$table_prefix\s*=\s*'[^']*';",
        f"$table_prefix = '{db.table_prefix}';",
        content,
        flags=re.MULTILINE
    )

    salts = fetch_salts_block(log)
    salt_re = re.compile(r"define\(\s*'AUTH_KEY'.*?define\(\s*'NONCE_SALT'.*?\);\s*", re.DOTALL)
    if salt_re.search(content):
        content = salt_re.sub(salts + "\n", content, count=1)

    (target_path / "wp-config.php").write_text(content, encoding="utf-8")
    log("تم إنشاء ملف wp-config.php.")

def set_dev_mode_in_wp_config(target_path: Path, enabled: bool, log: LogFn):
    cfg = target_path / "wp-config.php"
    if not cfg.exists():
        return
    txt = cfg.read_text(encoding="utf-8", errors="ignore")
    defines = {
        "WP_DEBUG": "true" if enabled else "false",
        "WP_DEBUG_LOG": "true" if enabled else "false",
        "WP_DEBUG_DISPLAY": "false" if enabled else "false",
    }
    for k, v in defines.items():
        # if define exists replace it, else insert near "That's all"
        pat = re.compile(rf"define\(\s*'{re.escape(k)}'\s*,\s*([^)]+)\);")
        if pat.search(txt):
            txt = pat.sub(f"define( '{k}', {v} );", txt)
        else:
            marker = "/* That's all, stop editing! Happy publishing. */"
            if marker in txt:
                txt = txt.replace(marker, f"define( '{k}', {v} );\n{marker}")
    cfg.write_text(txt, encoding="utf-8")
    log("تم تحديث وضع المطوّر في wp-config.php")

def detect_php(user_php: str, stack_php: str) -> str:
    if user_php.strip():
        return user_php.strip()
    if stack_php.strip():
        return stack_php.strip()
    return which_any(["php", "php.exe"])

def detect_wpcli(user_wpcli: str, download_if_missing: bool, php_path: str, tools_dir: Path, log: LogFn, progress: ProgressFn) -> tuple[str, bool]:
    # Returns (path, is_phar)
    if user_wpcli.strip():
        p = user_wpcli.strip()
        return p, p.lower().endswith(".phar")

    w = which_any(["wp", "wp.bat", "wp.cmd"])
    if w:
        return w, False

    if download_if_missing:
        if not php_path:
            raise RuntimeError("أداة WP-CLI غير موجودة و PHP غير متوفر لتشغيل wp-cli.phar.")
        tools_dir.mkdir(parents=True, exist_ok=True)
        phar = tools_dir / "wp-cli.phar"
        download_file(WPCLI_PHAR_URL, phar, log=log, progress=progress, start_pct=60, end_pct=65)
        return str(phar), True

    raise RuntimeError("أداة WP-CLI غير موجودة. الرجاء تحديد المسار أو تفعيل التنزيل التلقائي.")

def wpcli_base_cmd(php_path: str, wpcli_path: str, is_phar: bool) -> list[str]:
    if is_phar:
        return [php_path, wpcli_path]
    return [wpcli_path]

def find_php_executable() -> str:
    """Find PHP executable in common locations (PATH, Laragon, XAMPP)."""
    # 1. Try system PATH first
    php = which_any(["php", "php.exe"])
    if php and os.path.exists(php):
        return php
    
    # 2. Try common Laragon locations
    laragon_roots = ["C:\\laragon", "D:\\laragon"]
    for lr in laragon_roots:
        root = Path(lr)
        php_root = root / "bin" / "php"
        if php_root.exists():
            candidates = []
            for d in php_root.glob("php-*"):
                exe = d / "php.exe"
                if exe.exists():
                    candidates.append(exe)
            if candidates:
                candidates.sort(key=lambda x: x.parent.name)
                return str(candidates[-1])
    
    # 3. Try XAMPP
    xampp_roots = ["C:\\xampp", "D:\\xampp"]
    for xr in xampp_roots:
        php_exe = Path(xr) / "php" / "php.exe"
        if php_exe.exists():
            return str(php_exe)
    
    # 4. Final fallback
    return "php"

def ensure_wpcli_exists(p: ProjectRecord, log: LogFn = None) -> tuple[str, bool]:
    """Checks if WP-CLI exists; if not, downloads wp-cli.phar to .tools folder."""
    # 1. Check if we already have a full path that works
    w = p.wpcli_path or which_any(["wp", "wp.bat", "wp.cmd"])
    if w and os.path.isabs(w) and os.path.exists(w):
        return w, (p.wpcli_is_phar if p.wpcli_path else w.lower().endswith(".phar"))

    # 2. Check if phar already exists in .tools
    target_path = Path(p.path)
    if not target_path.exists():
        if log: log(f"مسار المشروع غير موجود: {target_path}")
        return "", False

    tools_dir = target_path / ".tools"
    phar_path = tools_dir / "wp-cli.phar"
    if phar_path.exists():
        return str(phar_path), True

    # 3. Not found anywhere, download
    return download_wpcli_for_project(p, log)

def download_wpcli_for_project(p: ProjectRecord, log: LogFn = None) -> tuple[str, bool]:
    """Force download of wp-cli.phar for a specific project."""
    target_path = Path(p.path)
    tools_dir = target_path / ".tools"
    phar_path = tools_dir / "wp-cli.phar"

    if log:
        log(f"جارٍ تنزيل WP-CLI للمشروع: {p.name} ...")
        log(f"الوجهة: {phar_path}")

    try:
        tools_dir.mkdir(parents=True, exist_ok=True)
        # Use dummy progress
        download_file(WPCLI_PHAR_URL, phar_path, log if log else (lambda _: None), lambda _: None)
        if log: log("تم تنزيل WP-CLI بنجاح ✅")
        return str(phar_path), True
    except Exception as e:
        if log:
            log(f"خطأ فادح: فشل تنزيل WP-CLI: {e}")
        return "", False

def get_effective_tooling(p: ProjectRecord, log: LogFn = None) -> tuple[str, str, bool]:
    """Returns (php_path, wpcli_path, is_phar) using record or fallbacks + auto-download."""
    # Use recorded path or auto-detect
    php = p.php_path or find_php_executable()
    
    if log and php:
        # Quick validation
        if not os.path.exists(php) and not which_any([php]):
            log(f"تحذير: مسار PHP غير موجود: {php}")
    
    wpcli, is_phar = ensure_wpcli_exists(p, log)
    if not wpcli or not os.path.exists(wpcli):
        # Last-ditch effort: maybe it's just 'wp' in PATH and ensure_wpcli_exists was too strict
        w = which_any(["wp", "wp.bat", "wp.cmd"]) or "wp"
        wpcli = w
        is_phar = w.lower().endswith(".phar")
        
    return php, wpcli, is_phar

def run_wpcli(target_path: Path, php_path: str, wpcli_path: str, is_phar: bool, args: list[str], log: LogFn):
    base = wpcli_base_cmd(php_path, wpcli_path, is_phar)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        base.append("--allow-root")
    cmd = base + [f"--path={str(target_path)}"] + args
    log("جارٍ تنفيذ الأمر: " + " ".join(cmd))
    res = run_cmd(cmd, cwd=target_path)
    if res.out.strip():
        log(res.out.strip())
    if res.err.strip():
        log(res.err.strip())
    if res.code != 0:
        # Include output and error in exception message for better debugging
        error_details = []
        if res.out.strip():
            error_details.append(f"المخرجات: {res.out.strip()}")
        if res.err.strip():
            error_details.append(f"الخطأ: {res.err.strip()}")
        error_msg = f"فشل تنفيذ WP-CLI (رمز الخروج {res.code})"
        if error_details:
            error_msg += "\n" + "\n".join(error_details)
        raise RuntimeError(error_msg)
    return res

def wp_cli_install_core(target_path: Path, wp: WPParams, php_path: str, wpcli_path: str, is_phar: bool, log: LogFn):
    url = _ensure_url(wp.site_url)
    if not url:
        raise RuntimeError("رابط الموقع فارغ.")
    run_wpcli(
        target_path, php_path, wpcli_path, is_phar,
        [
            "core", "install",
            f"--url={url}",
            f"--title={wp.site_title}",
            f"--admin_user={wp.admin_user}",
            f"--admin_password={wp.admin_pass}",
            f"--admin_email={wp.admin_email}",
            "--skip-email",
        ],
        log
    )
    return url

def wp_cli_set_permalinks(target_path: Path, structure: str, php_path: str, wpcli_path: str, is_phar: bool, log: LogFn):
    if not structure.strip():
        return
    run_wpcli(target_path, php_path, wpcli_path, is_phar, ["rewrite", "structure", structure, "--hard"], log)
    run_wpcli(target_path, php_path, wpcli_path, is_phar, ["rewrite", "flush", "--hard"], log)

def wp_cli_install_theme_plugins(target_path: Path, theme: str, plugins: list[str], php_path: str, wpcli_path: str, is_phar: bool, log: LogFn):
    if theme.strip():
        run_wpcli(target_path, php_path, wpcli_path, is_phar, ["theme", "install", theme, "--activate"], log)
    for pl in plugins:
        pl = pl.strip()
        if not pl:
            continue
        run_wpcli(target_path, php_path, wpcli_path, is_phar, ["plugin", "install", pl, "--activate"], log)

def export_db_mysqldump(db: DBParams, out_sql: Path, log: LogFn) -> bool:
    mysqldump = which_any(["mysqldump", "mysqldump.exe"])
    if not mysqldump:
        return False
    cmd = [
        mysqldump,
        f"-h{db.host}",
        f"-P{db.port}",
        f"-u{db.root_user}",
        f"-p{db.root_pass}",
        db.db_name
    ]
    log("جارٍ تصدير قاعدة البيانات باستخدام mysqldump...")
    res = run_cmd(cmd)
    if res.code != 0:
        log(res.err.strip())
        return False
    out_sql.write_text(res.out, encoding="utf-8", errors="ignore")
    log(f"تم تصدير قاعدة البيانات: {out_sql}")
    return True

def import_db_mysql(db: DBParams, in_sql: Path, log: LogFn) -> bool:
    mysql = which_any(["mysql", "mysql.exe"])
    if not mysql:
        return False
    cmd = [
        mysql,
        f"-h{db.host}",
        f"-P{db.port}",
        f"-u{db.root_user}",
        f"-p{db.root_pass}",
        db.db_name
    ]
    log("جارٍ استيراد قاعدة البيانات باستخدام عميل mysql...")
    p = subprocess_run_with_stdin(cmd, in_sql.read_text(encoding="utf-8", errors="ignore"))
    if p["code"] != 0:
        log(p["err"].strip())
        return False
    log("تم استيراد قاعدة البيانات بنجاح.")
    return True

def subprocess_run_with_stdin(cmd: list[str], stdin_text: str) -> dict:
    import subprocess
    p = subprocess.run(cmd, input=stdin_text, text=True, capture_output=True, shell=False)
    return {"code": p.returncode, "out": p.stdout or "", "err": p.stderr or ""}

def export_db_python(db: DBParams, out_sql: Path, log: LogFn):
    log("جارٍ تصدير قاعدة البيانات (وضع بايثون الاحتياطي) ...")
    conn = mysql_connect(db.host, db.port, db.root_user, db.root_pass)
    try:
        with conn.cursor() as cur:
            cur.execute(f"USE `{db.db_name}`;")
            cur.execute("SHOW TABLES;")
            tables = [row[0] for row in cur.fetchall()]
            lines = ["SET FOREIGN_KEY_CHECKS=0;"]
            for t in tables:
                cur.execute(f"SHOW CREATE TABLE `{t}`;")
                create_stmt = cur.fetchone()[1]
                lines.append(f"DROP TABLE IF EXISTS `{t}`;")
                lines.append(create_stmt + ";")

                cur.execute(f"SELECT * FROM `{t}`;")
                rows = cur.fetchall()
                if rows:
                    # build insert
                    cur.execute(f"DESCRIBE `{t}`;")
                    cols = [c[0] for c in cur.fetchall()]
                    cols_sql = ", ".join([f"`{c}`" for c in cols])
                    for r in rows:
                        vals = []
                        for v in r:
                            if v is None:
                                vals.append("NULL")
                            elif isinstance(v, (int, float)):
                                vals.append(str(v))
                            else:
                                s = str(v).replace("\\", "\\\\").replace("'", "\\'")
                                vals.append(f"'{s}'")
                        lines.append(f"INSERT INTO `{t}` ({cols_sql}) VALUES ({', '.join(vals)});")
            lines.append("SET FOREIGN_KEY_CHECKS=1;")
            out_sql.write_text("\n".join(lines), encoding="utf-8")
            log(f"تم تصدير قاعدة البيانات: {out_sql}")
    finally:
        conn.close()

def import_db_python(db: DBParams, in_sql: Path, log: LogFn):
    log("جارٍ استيراد قاعدة البيانات (وضع بايثون الاحتياطي) ...")
    sql = in_sql.read_text(encoding="utf-8", errors="ignore")
    conn = mysql_connect(db.host, db.port, db.root_user, db.root_pass)
    try:
        with conn.cursor() as cur:
            cur.execute(f"USE `{db.db_name}`;")
            # naive split by ; (works for most dumps produced by this app)
            stmts = [s.strip() for s in sql.split(";") if s.strip()]
            for st in stmts:
                cur.execute(st)
        log("تم استيراد قاعدة البيانات بنجاح.")
    finally:
        conn.close()

def backup_project_folder(project_path: Path, out_zip: Path, log: LogFn, progress: ProgressFn, start_pct: int = 0, end_pct: int = 100):
    log("جارٍ ضغط مجلد المشروع...")
    files = []
    for root, _, fnames in os.walk(project_path):
        for f in fnames:
            p = Path(root) / f
            files.append(p)
    total = max(1, len(files))
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for i, p in enumerate(files, start=1):
            rel = p.relative_to(project_path)
            z.write(p, rel.as_posix())
            pct = start_pct + int((end_pct - start_pct) * (i/total))
            progress(pct)
    log(f"تم ضغط مجلد المشروع: {out_zip}")

def preflight_checks(wp: WPParams, db: DBParams) -> list[tuple[bool, str]]:
    checks: list[tuple[bool, str]] = []
    doc_root = wp.doc_root.expanduser().resolve()
    target = (doc_root / wp.project_name).resolve()

    checks.append((doc_root.exists(), f"مجلد الجذر موجود: {doc_root}"))
    if doc_root.exists():
        try:
            test_file = doc_root / ".write_test_tmp"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)  # py3.8+ compatibility uses try/except in UI if needed
            checks.append((True, "مجلد الجذر قابل للكتابة"))
        except Exception:
            checks.append((False, "مجلد الجذر غير قابل للكتابة"))

    if target.exists() and not wp.overwrite:
        checks.append((False, f"المسار موجود مسبقاً والاستبدال معطّل: {target}"))
    else:
        checks.append((True, f"المسار الهدف جاهز: {target}"))

    ok_db, msg = test_mysql(db)
    checks.append((ok_db, f"الاتصال بـ MySQL: {msg}"))

    if wp.auto_install:
        php = detect_php(wp.php_path, "")
        checks.append((bool(php), f"تم العثور على PHP: {php or 'غير موجود'}"))
        if php:
            # wp-cli is optional if we can download
            wpcli_ok = bool(wp.wpcli_path.strip() or which_any(["wp", "wp.bat", "wp.cmd"]) or wp.download_wpcli)
            checks.append((wpcli_ok, "أداة WP-CLI متوفرة أو قابلة للتنزيل"))
    return checks

def install_wordpress(
    wp: WPParams,
    db: DBParams,
    log: LogFn,
    progress: ProgressFn,
) -> dict:
    """
    Returns dict with keys: project_path, url, admin_url, php_path, wpcli_path, wpcli_is_phar
    """
    progress(0)
    doc_root = wp.doc_root.expanduser().resolve()
    target_path = (doc_root / wp.project_name).resolve()

    if target_path.exists():
        if not wp.overwrite:
            raise RuntimeError(f"المسار موجود مسبقاً: {target_path}")
        log("جارٍ استبدال المجلد الموجود...")
        shutil.rmtree(target_path)

    # Acquire zip
    with tempfile.TemporaryDirectory(prefix="wp_installer_") as tmp:
        tmpdir = Path(tmp)
        zip_path = tmpdir / "wordpress.zip"

        if wp.wp_zip_local.strip():
            src = Path(wp.wp_zip_local).expanduser().resolve()
            if not src.exists():
                raise RuntimeError("الملف المضغوط المحلي غير موجود.")
            shutil.copy2(src, zip_path)
            log(f"جارٍ استخدام الملف المضغوط المحلي: {src}")
            progress(15)
        else:
            url = wp.wp_zip_url.strip() or WORDPRESS_LATEST_ZIP
            download_file(url, zip_path, log, progress, start_pct=0, end_pct=25)

        extract_root = tmpdir / "extract"
        extract_root.mkdir(parents=True, exist_ok=True)
        wp_src = extract_wordpress_zip(zip_path, extract_root, log, progress, start_pct=25, end_pct=40)

        copy_tree_contents(wp_src, target_path, log, progress, start_pct=40, end_pct=52)

    # DB
    progress(55)
    create_database_and_user(db, log)
    progress(62)

    wp_db_user = db.user if db.create_user else db.root_user
    wp_db_pass = db.user_pass if db.create_user else db.root_pass
    write_wp_config(target_path, db, wp_db_user, wp_db_pass, log)
    progress(70)

    if db.table_prefix.strip() == "":
        db.table_prefix = "wp_"

    if wp.dev_mode:
        set_dev_mode_in_wp_config(target_path, True, log)

    result = {
        "project_path": str(target_path),
        "url": _ensure_url(wp.site_url),
        "admin_url": _ensure_url(wp.site_url.rstrip("/") + "/wp-admin/"),
        "php_path": "",
        "wpcli_path": "",
        "wpcli_is_phar": False
    }

    if wp.auto_install:
        progress(73)
        php = detect_php(wp.php_path, "")
        if not php:
            raise RuntimeError("التثبيت التلقائي مفعّل، لكن PHP غير موجود.")
        tools_dir = target_path / ".tools"
        wpcli, is_phar = detect_wpcli(wp.wpcli_path, wp.download_wpcli, php, tools_dir, log, progress)

        wp_cli_install_core(target_path, wp, php, wpcli, is_phar, log)
        progress(85)

        # post config
        if wp.permalinks.strip():
            wp_cli_set_permalinks(target_path, wp.permalinks.strip(), php, wpcli, is_phar, log)
        progress(90)

        wp_cli_install_theme_plugins(target_path, wp.install_theme, wp.plugins, php, wpcli, is_phar, log)
        progress(96)

        result["php_path"] = php
        result["wpcli_path"] = wpcli
        result["wpcli_is_phar"] = is_phar

    progress(100)
    return result

def search_replace_url_in_db(db: DBParams, old_url: str, new_url: str, log: LogFn):
    """
    Fallback search-replace without WP-CLI (best effort):
    updates wp_options(siteurl, home) and post content GUIDs won't be fully handled.
    Prefer WP-CLI whenever possible.
    """
    old_url = old_url.rstrip("/")
    new_url = new_url.rstrip("/")
    conn = mysql_connect(db.host, db.port, db.root_user, db.root_pass)
    try:
        with conn.cursor() as cur:
            cur.execute(f"USE `{db.db_name}`;")
            # options table:
            options = f"{db.table_prefix}options"
            cur.execute(f"UPDATE `{options}` SET option_value = REPLACE(option_value, %s, %s) WHERE option_name IN ('siteurl','home');", (old_url, new_url))
            log("تم تحديث siteurl/home في جدول الإعدادات (options).")
    finally:
        conn.close()

def clone_project(
    src_path: Path,
    dst_path: Path,
    src_db: DBParams,
    dst_db: DBParams,
    old_url: str,
    new_url: str,
    php_path: str,
    wpcli_path: str,
    wpcli_is_phar: bool,
    log: LogFn,
    progress: ProgressFn
):
    """
    Clone folder + DB (export/import) + update URL with wp-cli search-replace if available.
    """
    if dst_path.exists():
        raise RuntimeError("المسار الهدف موجود مسبقاً.")
    # 1) copy files
    log("جارٍ استنساخ الملفات...")
    shutil.copytree(src_path, dst_path)
    progress(30)

    # 2) create destination db
    create_database_and_user(dst_db, log)
    progress(40)

    # 3) export src
    tmpdir = Path(tempfile.mkdtemp(prefix="wp_clone_"))
    try:
        dump = tmpdir / "dump.sql"
        ok = export_db_mysqldump(src_db, dump, log)
        if not ok:
            export_db_python(src_db, dump, log)
        progress(55)

        # 4) import dst
        ok2 = import_db_mysql(dst_db, dump, log)
        if not ok2:
            import_db_python(dst_db, dump, log)
        progress(70)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # 5) update wp-config in dst
    wp_db_user = dst_db.user if dst_db.create_user else dst_db.root_user
    wp_db_pass = dst_db.user_pass if dst_db.create_user else dst_db.root_pass
    write_wp_config(dst_path, dst_db, wp_db_user, wp_db_pass, log)
    progress(78)

    # 6) search-replace
    if php_path and wpcli_path:
        run_wpcli(dst_path, php_path, wpcli_path, wpcli_is_phar, ["search-replace", old_url.rstrip("/"), new_url.rstrip("/"), "--all-tables"], log)
        progress(92)
    else:
        search_replace_url_in_db(dst_db, old_url, new_url, log)
        progress(92)

    progress(100)


# ----------------- Backup / Restore / URL convert -----------------

def _timestamp() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def project_meta_dir(project_path: Path) -> Path:
    return project_path / ".wpinst"

def write_project_meta(project_path: Path, meta: dict, log: LogFn | None = None):
    d = project_meta_dir(project_path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "project.json"
    p.write_text(__import__("json").dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if log:
        log(f"تم حفظ بيانات المشروع الوصفية: {p}")

def backup_bundle(
    project_path: Path,
    db: DBParams,
    backup_root: Path,
    log: LogFn,
    progress: ProgressFn,
    include_files: bool = True,
    include_db: bool = True,
) -> Path:
    """
    Creates a backup folder containing:
    - files.zip (optional)
    - db.sql (optional)
    - manifest.json
    Returns backup folder path.
    """
    backup_root.mkdir(parents=True, exist_ok=True)
    bdir = backup_root / f"backup_{_timestamp()}"
    bdir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "created_at": _timestamp(),
        "project_path": str(project_path),
        "db": {
            "host": db.host, "port": db.port, "db_name": db.db_name,
            "table_prefix": db.table_prefix
        },
        "includes": {"files": include_files, "db": include_db},
        "artifacts": {},
    }

    if include_files:
        log("نسخ احتياطي: جارٍ ضغط ملفات المشروع...")
        files_zip = bdir / "files.zip"
        backup_project_folder(project_path, files_zip, log, progress, start_pct=0, end_pct=70)
        manifest["artifacts"]["files_zip"] = files_zip.name
    else:
        progress(70)

    if include_db:
        log("نسخ احتياطي: جارٍ تصدير قاعدة البيانات...")
        dump = bdir / "db.sql"
        ok = export_db_mysqldump(db, dump, log)
        if not ok:
            export_db_python(db, dump, log)
        progress(95)
        manifest["artifacts"]["db_sql"] = dump.name
    else:
        progress(95)

    (bdir / "manifest.json").write_text(__import__("json").dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100)
    log(f"اكتملت النسخة الاحتياطية: {bdir}")
    return bdir

def restore_bundle(
    project_path: Path,
    db: DBParams,
    backup_dir: Path,
    log: LogFn,
    progress: ProgressFn,
    restore_files: bool = True,
    restore_db: bool = True,
):
    """
    Restores a backup folder made by backup_bundle.
    Safety: creates a pre-restore backup inside backup_dir/../pre_restore_...
    """
    if not backup_dir.exists():
        raise RuntimeError("مجلد النسخة الاحتياطية غير موجود.")

    # Pre-restore backup
    pre_root = backup_dir.parent
    log("جارٍ إنشاء نسخة احتياطية وقائية قبل الاستعادة...")
    try:
        backup_bundle(project_path, db, pre_root, log, lambda _: None, include_files=True, include_db=True)
    except Exception as e:
        log(f"تحذير: فشل إنشاء النسخة الاحتياطية الوقائية: {e}")

    progress(10)

    # Restore files
    if restore_files:
        zpath = backup_dir / "files.zip"
        if not zpath.exists():
            raise RuntimeError("الملف files.zip غير موجود في النسخة الاحتياطية.")
        log("جارٍ استعادة الملفات من الأرشيف المضغوط...")
        import tempfile, zipfile, shutil
        with tempfile.TemporaryDirectory(prefix="wp_restore_") as tmp:
            tmpdir = Path(tmp)
            with zipfile.ZipFile(zpath, "r") as z:
                z.extractall(tmpdir)
            for item in tmpdir.iterdir():
                dst = project_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dst)
        progress(55)

    # Restore DB
    if restore_db:
        spath = backup_dir / "db.sql"
        if not spath.exists():
            raise RuntimeError("الملف db.sql غير موجود في النسخة الاحتياطية.")
        log("جارٍ استعادة قاعدة البيانات...")
        ok = import_db_mysql(db, spath, log)
        if not ok:
            import_db_python(db, spath, log)
        progress(95)

    progress(100)
    log("اكتملت الاستعادة بنجاح ✅")

def wp_cli_search_replace(
    target_path: Path,
    php_path: str,
    wpcli_path: str,
    wpcli_is_phar: bool,
    old_url: str,
    new_url: str,
    include_guid: bool,
    log: LogFn
):
    args = ["search-replace", old_url, new_url, "--all-tables", "--precise"]
    if not include_guid:
        args.append("--skip-columns=guid")
    run_wpcli(target_path, php_path, wpcli_path, wpcli_is_phar, args, log)

def list_wp_items(target_path: Path, php_path: str, wpcli_path: str, is_phar: bool, item_type: str = "plugin", log: LogFn = None) -> list[dict]:
    """Lists plugins or themes using WP-CLI in JSON format."""
    import json
    import re
    args = [item_type, "list", "--format=json"]
    try:
        res = run_wpcli(target_path, php_path, wpcli_path, is_phar, args, log if log else lambda _: None)
        raw = res.out.strip()
        
        # WP-CLI sometimes outputs PHP notices before the JSON.
        # Find the first '[' and last ']' to extract just the JSON array.
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            raw = match.group(0)
            
        return json.loads(raw)
    except Exception as e:
        if log:
            log(f"فشل جلب قائمة {item_type}: {e}")
        return []

def toggle_wp_item(target_path: Path, php_path: str, wpcli_path: str, is_phar: bool, item_name: str, action: str, item_type: str = "plugin", log: LogFn = None):
    """Activates, deactivates, or deletes a plugin/theme."""
    args = [item_type, action, item_name]
    run_wpcli(target_path, php_path, wpcli_path, is_phar, args, log if log else lambda _: None)

def get_wp_config_path(project_path: Path) -> Path:
    return project_path / "wp-config.php"

def read_wp_config_constants(project_path: Path) -> dict[str, str]:
    """Simple regex-based parsing of wp-config.php constants."""
    path = get_wp_config_path(project_path)
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    import re
    # matches define('NAME', value); or define("NAME", value);
    pattern = r"define\s*\(\s*['\"](.+?)['\"]\s*,\s*(.+?)\s*\)\s*;"
    matches = re.findall(pattern, content)
    # clean up quotes from value
    return {m[0]: m[1].strip("'\" ") for m in matches}

def update_wp_config_constant(project_path: Path, name: str, value: str, is_string: bool = False):
    """Updates or adds a define() in wp-config.php."""
    path = get_wp_config_path(project_path)
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8")
    import re
    
    val_repr = f"'{value}'" if is_string else str(value)
    new_line = f"define( '{name}', {val_repr} );"
    
    pattern = rf"define\s*\(\s*['\"]{re.escape(name)}['\"]\s*,.+?\)\s*;"
    if re.search(pattern, content):
        content = re.sub(pattern, new_line, content)
    else:
        # insert before "/* That's all, stop editing! Happy publishing. */"
        marker = "/* That's all, stop editing!"
        if marker in content:
            content = content.replace(marker, f"{new_line}\n{marker}")
        else:
            content += f"\n{new_line}\n"
    path.write_text(content, encoding="utf-8")
