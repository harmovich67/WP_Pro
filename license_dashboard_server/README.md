# Harmulizer Pro License Server (Deployment Copy)

نسخة جاهزة للرفع على أي سيرفر (Railway / Render / VPS / PythonAnywhere...).
هذا مجلد منفصل عن `license_dashboard` المحلي حتى لا تتأثر نسخة التطوير عندك.

## 1. قبل الرفع

- افتح `.env.example` وجهّز قيم حقيقية لـ `ADMIN_TOKEN` و `SECRET_KEY` (لا تستخدم القيم الافتراضية في main.py).
- لا ترفع ملف `licenses.db` (لو موجود) ولا `.env` — موجودين في `.gitignore` أصلاً.

## 2. النشر

### Railway / Render (اتصال بـ GitHub)
1. ارفع هذا المجلد (أو المشروع كله) على GitHub.
2. أنشئ Web Service جديد واربطه بالريبو، حدد هذا المجلد كـ Root Directory لو رفعت المشروع كامل.
3. أمر التشغيل جاهز في `Procfile`:
   `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. أضف Environment Variables: `ADMIN_TOKEN`, `SECRET_KEY` (و`DATABASE_URL` لو هتستخدم قاعدة بيانات خارجية بدل SQLite).
5. بعد النشر هتاخد رابط زي: `https://your-app.up.railway.app`

### VPS (Nginx + systemd/pm2)
```bash
pip install -r requirements.txt
export ADMIN_TOKEN="..."
export SECRET_KEY="..."
export PORT=8000
python main.py
```
ثم اعمل reverse proxy بـ Nginx على الدومين بتاعك لبورت 8000، وفعّل SSL (Let's Encrypt).

### PythonAnywhere
ارفع الملفات، ثبت المتطلبات، واربط WSGI بتطبيق `main:app` (يحتاج تعديل بسيط لأن PythonAnywhere يستخدم WSGI وليس ASGI مباشرة — أو استخدم Always-on task بدلاً من ذلك).

## 3. بعد النشر — اربطه بالبرنامج

بمجرد ما يبقى عندك رابط ثابت (دومين/رابط منصة النشر):

1. افتح `app/core/license/license_manager.py` في مشروع `wp_local_installer_pro`.
2. غيّر القيمة الافتراضية لـ `LICENSE_API_URL` من الـ placeholder لرابطك الحقيقي، مثلاً:
   `https://license.yourdomain.com/api`
3. أعد بناء البرنامج (build.ps1) عشان النسخة اللي هتوزّعها تتصل بالسيرفر الجديد تلقائيًا بدون ما المستخدم يحتاج يضبط أي حاجة.

## 4. لوحة التحكم (الأدمن)

بعد النشر، افتح:
```
https://<رابطك>/dashboard
```
سجّل دخول بـ ADMIN_TOKEN اللي حطيته في متغيرات البيئة، ومن هناك تقدر تنشئ/تعدّل/تحذف تراخيص وتشوف الإحصائيات.

## 5. Endpoints المهمة

| Endpoint | الاستخدام |
|---|---|
| `GET /` | health check |
| `GET /dashboard` | لوحة التحكم (admin) |
| `GET /docs` | توثيق API تلقائي |
| `POST /api/verify` | يستخدمه البرنامج نفسه للتفعيل (بدون Authorization) |
| `POST /api/deactivate` | يستخدمه البرنامج لإلغاء التفعيل |
| `GET/POST/PUT/DELETE /api/licenses...` | إدارة التراخيص (تحتاج `Authorization: Bearer <ADMIN_TOKEN>`) |
