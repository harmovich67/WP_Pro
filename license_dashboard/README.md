# Harmulizer Pro License Dashboard

## 🚀 تشغيل الداشبورد

### 1. تثبيت المتطلبات

```bash
cd license_dashboard
pip install -r requirements.txt
```

### 2. تشغيل الخادم

```bash
# Windows
python main.py

# أو باستخدام uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. فتح الداشبورد

افتح الملف `index.html` في المتصفح أو اذهب إلى:

- الداشبورد: `file:///C:/Users/.../license_dashboard/index.html`
- API Docs: `http://localhost:8000/docs`

## 🔐 رمز الأمان الافتراضي

```
admin_secret_token_2024
```

⚠️ **مهم**: غيّر هذا الرمز في الإنتاج عبر متغير البيئة `ADMIN_TOKEN`

## 📋 الميزات

- ✅ إنشاء تراخيص جديدة
- ✅ تعديل/حذف التراخيص
- ✅ إرسال المفتاح عبر واتساب
- ✅ تتبع التفعيلات
- ✅ إحصائيات شاملة

## 💳 الأسعار

| المستوى | السعر    |
| ------- | -------- |
| أساسي   | $50/شهر  |
| احترافي | $200/شهر |
| مؤسسي   | $400/شهر |

## 🔗 API Endpoints

### للمشرف (تحتاج Authorization)

- `GET /api/stats` - الإحصائيات
- `GET /api/licenses` - قائمة التراخيص
- `POST /api/licenses` - إنشاء ترخيص
- `PUT /api/licenses/{id}` - تحديث ترخيص
- `DELETE /api/licenses/{id}` - حذف ترخيص

### للتطبيق (بدون Authorization)

- `POST /api/verify` - التحقق من ترخيص
- `POST /api/deactivate` - إلغاء تفعيل

## 🌐 النشر على الإنترنت

### باستخدام Railway/Render:

1. ارفع المجلد لـ GitHub
2. اربط مع Railway أو Render
3. حدد `main.py` كنقطة البداية
4. أضف متغيرات البيئة:
   - `ADMIN_TOKEN`: رمز أمان قوي
   - `SECRET_KEY`: مفتاح سري للتشفير
