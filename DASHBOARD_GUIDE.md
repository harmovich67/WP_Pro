# تشغيل الداشبورد

## طريقة سريعة:

قم بتشغيل الملف: `start_dashboard.bat`

## أو يدوياً:

```bash
cd license_dashboard
python main.py
```

الخادم سيعمل على: `http://localhost:8000`

افتح `license_dashboard/index.html` في المتصفح

رمز الأمان: `admin_secret_token_2024`

---

## إلغاء التجربة وإعادة الضبط

### من Windows Explorer:

اذهب إلى: `%APPDATA%\HarmulizerPro\license\`
واحذف الملفات: `license.dat` و `offline.dat`

### من الكود:

```python
from app.core.license import LicenseManager
lm = LicenseManager()
lm.reset_license()
```
