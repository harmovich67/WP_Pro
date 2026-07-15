# Harmulizer Pro License Server — PHP (InfinityFree)

نسخة PHP + MySQL من سيرفر التراخيص، مبنية خصيصًا لأن InfinityFree استضافة PHP فقط
ومش بتدعم Python/FastAPI. نفس الـ endpoints والسلوك بالظبط زي `license_dashboard_server`
(نسخة Python) عشان البرنامج يشتغل من غير أي تعديل تاني غير رابط السيرفر.

الرابط المستهدف: `http://ser.42web.io/tafeal`

## 1. إنشاء قاعدة البيانات

1. من لوحة تحكم InfinityFree (vPanel) → **MySQL Databases** → أنشئي قاعدة بيانات جديدة.
2. هتاخدي: `DB_HOST` (زي `sqlXXX.infinityfree.com`), `DB_NAME`, `DB_USER`, `DB_PASS`.
3. افتحي `config.php` وحطي القيم دي مكان الـ placeholders، وغيّري `ADMIN_TOKEN` لقيمة قوية وعشوائية.

## 2. رفع الملفات

ارفعي **كل محتويات هذا المجلد** (`license_dashboard_php/`) عبر FTP أو File Manager
إلى مسار `htdocs/tafeal/` بحيث يبقى الشكل:

```
htdocs/
  tafeal/
    index.php
    install.php
    config.php
    db.php
    helpers.php
    dashboard.html
    api/
      index.php
      .htaccess
```

## 3. إنشاء الجداول (مرة واحدة فقط)

بعد الرفع، افتحي في المتصفح:

```
http://ser.42web.io/tafeal/install.php
```

هيطلعلك رسالة "Tables created successfully". **بعدها احذفي `install.php` من السيرفر فورًا**
(عشان محدش يقدر يشغّله تاني أو يعمل بيه أي حاجة).

## 4. التأكد إن السيرفر شغال

- `http://ser.42web.io/tafeal/` → لازم يرجع `{"message": "Harmulizer Pro License API", "status": "running"}`
- `http://ser.42web.io/tafeal/dashboard.html` → لوحة التحكم، سجّلي دخول بـ ADMIN_TOKEN اللي حطيتيه في config.php

## 5. ربطه بالبرنامج

في `app/core/license/license_manager.py` (مشروع wp_local_installer_pro)، الرابط اتظبط
تلقائيًا على:

```
http://ser.42web.io/tafeal/api
```

لو غيّرتي الدومين لاحقًا، عدّلي القيمة دي وابنِي البرنامج (`build.ps1`) تاني.

## ملاحظات مهمة عن InfinityFree (الخطة المجانية)

- **الأداء بطيء نسبيًا** ومفيش ضمان uptime عالي — مناسب للتجربة أو عدد تراخيص محدود، مش لمشروع تجاري كبير.
- InfinityFree بتوقف الحسابات اللي مالهاش زيارات لفترة طويلة أحيانًا — افتحي الرابط بين فترة وفترة.
- لو المشروع كبر واحتجتي أداء أفضل، فكري في الانتقال لاستضافة بتدعم Python (Render/Railway) واستخدام نسخة `license_dashboard_server` بدل الـ PHP.

## 6. الـ Endpoints

| Endpoint | الاستخدام |
|---|---|
| `GET /tafeal/` | health check |
| `GET /tafeal/dashboard.html` | لوحة التحكم (admin) |
| `POST /tafeal/api/verify` | يستخدمه البرنامج للتفعيل (بدون Authorization) |
| `POST /tafeal/api/deactivate` | يستخدمه البرنامج لإلغاء التفعيل |
| `GET/POST /tafeal/api/licenses` | قائمة/إنشاء تراخيص (Authorization: Bearer ADMIN_TOKEN) |
| `GET/PUT/DELETE /tafeal/api/licenses/{id}` | عرض/تعديل/حذف ترخيص |
| `GET /tafeal/api/licenses/{id}/activations` | تفعيلات ترخيص معيّن |
| `DELETE /tafeal/api/activations/{id}` | إلغاء تفعيل جهاز معيّن |
| `GET /tafeal/api/stats` | إحصائيات |
