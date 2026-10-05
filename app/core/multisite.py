"""
app/core/multisite.py
─────────────────────────────────────────────
One-Click WordPress Multisite — converts a regular WordPress install into a
Multisite network (subdomain or subdirectory) and automatically writes the
matching Apache (.htaccess) and nginx rewrite rules.

WP-CLI's `core multisite-convert` does the heavy lifting (network DB tables +
the wp-config.php network constants); this module handles the pieces WP-CLI
does not touch: pretty-permalink prerequisite, WP_ALLOW_MULTISITE, and the
web-server rewrite rules.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable

from app.core.wp_ops import run_wpcli, get_wp_config_path, update_wp_config_constant, read_wp_config_constants
from app.core.i18n import t as tr

LogFn = Callable[[str], None]

MODE_SUBDOMAIN = "subdomain"
MODE_SUBDIRECTORY = "subdirectory"

# ── Apache rewrite blocks (WordPress Codex canonical multisite rules) ──────
_APACHE_MS_SUBDIRECTORY = """# BEGIN WordPress Multisite (subdirectory) — written by Harmulizer Pro
RewriteEngine On
RewriteBase /
RewriteRule ^index\\.php$ - [L]

# add a trailing slash to /wp-admin
RewriteRule ^([_0-9a-zA-Z-]+/)?wp-admin$ $1wp-admin/ [R=301,L]

RewriteCond %{REQUEST_FILENAME} -f [OR]
RewriteCond %{REQUEST_FILENAME} -d
RewriteRule ^ - [L]
RewriteRule ^([_0-9a-zA-Z-]+/)?(wp-(content|admin|includes).*) $2 [L]
RewriteRule ^([_0-9a-zA-Z-]+/)?(.*\\.php)$ $2 [L]
RewriteRule . index.php [L]
# END WordPress Multisite (subdirectory)
"""

_APACHE_MS_SUBDOMAIN = """# BEGIN WordPress Multisite (subdomain) — written by Harmulizer Pro
RewriteEngine On
RewriteBase /
RewriteRule ^index\\.php$ - [L]

RewriteCond %{REQUEST_FILENAME} -f [OR]
RewriteCond %{REQUEST_FILENAME} -d
RewriteRule ^ - [L]
RewriteRule ^(wp-(content|admin|includes).*) $1 [L]
RewriteRule ^(.*\\.php)$ $1 [L]
RewriteRule . index.php [L]
# END WordPress Multisite (subdomain)
"""

# ── nginx snippets (nginx has no per-directory config file, so these are
# always emitted as a copy-paste-ready file; when a Laragon nginx vhost for
# this project is found we also inject them directly). ─────────────────────
_NGINX_MS_SUBDIRECTORY = """# WordPress Multisite (subdirectory) rules — written by Harmulizer Pro
# Paste inside the site's `server { ... }` block (above the main `location /`).
if (!-e $request_filename) {
    rewrite /wp-admin$ $scheme://$host$uri/ permanent;
    rewrite ^(/[^/]+)?(/wp-.*) $2 last;
    rewrite ^(/[^/]+)?(/.*\\.php)$ $2 last;
}

location / {
    try_files $uri $uri/ /index.php?$args;
}
"""

_NGINX_MS_SUBDOMAIN = """# WordPress Multisite (subdomain) rules — written by Harmulizer Pro
# Requires a wildcard server_name, e.g.:  server_name example.test *.example.test;
location / {
    try_files $uri $uri/ /index.php?$args;
}
"""


def _apache_block(mode: str) -> str:
    return _APACHE_MS_SUBDOMAIN if mode == MODE_SUBDOMAIN else _APACHE_MS_SUBDIRECTORY


def _nginx_block(mode: str) -> str:
    return _NGINX_MS_SUBDOMAIN if mode == MODE_SUBDOMAIN else _NGINX_MS_SUBDIRECTORY


def is_multisite(project_path: Path) -> bool:
    consts = read_wp_config_constants(project_path)
    return str(consts.get("MULTISITE", "")).strip().lower() == "true"


def preflight_multisite(project_path: Path) -> list[tuple[bool, str]]:
    checks: list[tuple[bool, str]] = []
    cfg = get_wp_config_path(project_path)
    checks.append((cfg.exists(), tr("ملف wp-config.php موجود")))
    if cfg.exists():
        checks.append((not is_multisite(project_path), tr("الموقع ليس شبكة متعددة (Multisite) مسبقاً")))
    return checks


def write_apache_multisite_htaccess(project_path: Path, mode: str, log: LogFn) -> Path:
    htaccess = project_path / ".htaccess"
    existing = htaccess.read_text(encoding="utf-8", errors="ignore") if htaccess.exists() else ""
    # A multisite .htaccess supersedes the standard single-site WordPress block.
    existing = re.sub(r"# BEGIN WordPress.*?# END WordPress\s*\n?", "", existing, flags=re.DOTALL)
    new_content = _apache_block(mode) + "\n" + existing.strip() + "\n"
    htaccess.write_text(new_content, encoding="utf-8")
    log(f"{tr('تم تحديث ملف: ')}{htaccess}")
    return htaccess


def write_nginx_multisite_snippet(project_path: Path, mode: str, log: LogFn) -> Path:
    out = project_path / "nginx-multisite.conf"
    out.write_text(_nginx_block(mode), encoding="utf-8")
    log(f"{tr('تم إنشاء ملف قواعد nginx: ')}{out}")
    return out


def try_write_laragon_nginx_vhost(laragon_root: str, project_name: str, mode: str, log: LogFn) -> bool:
    """If Laragon auto-generated an nginx vhost for this project, inject the
    multisite rules directly into it (best-effort; always backs up first)."""
    if not laragon_root.strip() or not project_name.strip():
        return False
    vdir = Path(laragon_root) / "etc" / "nginx" / "sites-enabled"
    if not vdir.exists():
        return False
    matches = sorted(vdir.glob(f"auto.{project_name}*.conf"))
    if not matches:
        return False
    vfile = matches[0]

    backup = vfile.with_suffix(vfile.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(vfile, backup)
        log(f"{tr('تم إنشاء نسخة احتياطية من ملف nginx vhost: ')}{backup}")

    content = vfile.read_text(encoding="utf-8", errors="ignore")
    content = re.sub(
        r"# BEGIN Harmulizer Multisite.*?# END Harmulizer Multisite\n?",
        "", content, flags=re.DOTALL,
    )
    block = f"# BEGIN Harmulizer Multisite\n{_nginx_block(mode)}\n# END Harmulizer Multisite\n"

    idx = content.rstrip().rfind("}")
    if idx != -1:
        content = content[:idx] + block + content[idx:]
    else:
        content = content.rstrip() + "\n\n" + block

    vfile.write_text(content, encoding="utf-8")
    log(f"{tr('تم كتابة قواعد nginx مباشرة في: ')}{vfile}")
    return True


def convert_to_multisite(
    project_path: Path,
    php_path: str, wpcli_path: str, wpcli_is_phar: bool,
    network_title: str,
    mode: str,
    log: LogFn,
) -> dict:
    if mode not in (MODE_SUBDOMAIN, MODE_SUBDIRECTORY):
        raise ValueError("mode must be 'subdomain' or 'subdirectory'")

    cfg_path = get_wp_config_path(project_path)
    if not cfg_path.exists():
        raise RuntimeError(tr("ملف wp-config.php غير موجود."))

    if is_multisite(project_path):
        raise RuntimeError(tr("الموقع مُحوَّل بالفعل إلى شبكة متعددة (Multisite)."))

    # 1) Multisite requires pretty (non-default) permalinks.
    log(tr("جارٍ ضبط الروابط الدائمة (مطلوبة لتفعيل الشبكة المتعددة)..."))
    run_wpcli(project_path, php_path, wpcli_path, wpcli_is_phar,
              ["rewrite", "structure", "/%postname%/", "--hard"], log)

    # 2) WP_ALLOW_MULTISITE must be true before network setup can run.
    update_wp_config_constant(project_path, "WP_ALLOW_MULTISITE", "true", is_string=False)

    # 3) Convert via WP-CLI: creates the network DB tables and writes the
    #    MULTISITE / SUBDOMAIN_INSTALL / DOMAIN_CURRENT_SITE consts block.
    log(tr("جارٍ تحويل الموقع إلى شبكة متعددة (Multisite) عبر WP-CLI..."))
    args = ["core", "multisite-convert", f"--title={network_title}"]
    if mode == MODE_SUBDOMAIN:
        args.append("--subdomains")
    run_wpcli(project_path, php_path, wpcli_path, wpcli_is_phar, args, log)

    # 4) Apache .htaccess (always written — Laragon's default web server).
    log(tr("جارٍ كتابة قواعد .htaccess الخاصة بالشبكة المتعددة..."))
    htaccess_path = write_apache_multisite_htaccess(project_path, mode, log)

    # 5) nginx snippet (always written as a ready-to-paste file).
    log(tr("جارٍ إنشاء ملف قواعد nginx..."))
    nginx_path = write_nginx_multisite_snippet(project_path, mode, log)

    return {
        "mode": mode,
        "htaccess": str(htaccess_path),
        "nginx_snippet": str(nginx_path),
    }
