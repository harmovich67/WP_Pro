# WP Local Installer Pro (PyQt6)

A modern cross-platform WordPress local installer with:
- Wizard UI + project dashboard
- Download/Offline WordPress ZIP
- DB create + optional DB user + test connection
- wp-config generation with salts
- Optional full install with WP-CLI (auto-download wp-cli.phar)
- Templates: plugin/theme bundles + dev mode + permalinks
- Project list + quick actions + backup/clone/reset
- WP-CLI console

## Run
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux:
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```
