# مشروع مخزن النظافة - ملاحظات المشروع

## نظرة عامة
تطبيق Streamlit لإدارة مخزن مستلزمات نظافة، يستخدم:
- **قاعدة البيانات**: Turso (libsql) - cloud
- **المرفقات**: تيليجرام (يتم تخزين file_id في قاعدة البيانات)
- **النسخ الاحتياطي**: ملفات zip على تيليجرام + تحميل يدوي
- **الاستضافة**: Streamlit Community Cloud
- **GitHub**: https://github.com/Ameen1919/inventory-google
- **رابط التطبيق**: https://inventorytelegram.streamlit.app

## البنية التقنية
- **الملف الرئيسي**: `app.py`
- **المكتبات المهمة**: `libsql`, `streamlit`, `pandas`, `fpdf2`, `arabic-reshaper`, `python-bidi`, `requests`
- **الأسرار (Secrets)**: `TURSO_URL`, `TURSO_TOKEN` + قسم `[telegram]` (bot_token, chat_id, file_id)

## التحديات التقنية التي تم حلها
1. **`libsql` لا يدعم `row_factory`** → تم حلّها بأغلفة `DictRow`, `WrappedCursor`, `WrappedConnection`
2. **بطء شديد** بسبب فتح اتصال جديد في كل استدعاء → تم حلها بتخزين الاتصال في `st.session_state` واستخدام `@st.cache_resource` لـ `init_db`
3. **المرفقات تُفقد على Streamlit Cloud** → تم حلها برفعها إلى تيليجرام وتخزين `file_id` فقط

## الميزات الحالية
- تسجيل دخول بـ 5 أدوار (super_admin, purchasing, disbursement, supervisor)
- إدارة أصناف، وحدات، فنادق، موردين
- وارد (مشتريات) + صادر (أذون صرف)
- جرد دوري
- تقارير (حركات + أرصدة) مع تصدير Excel/PDF
- نسخ احتياطي (zip + تيليجرام)
- مرفقات لكل من الحركات والموردين
- دعم RTL والعربية في PDF

## بنية قاعدة البيانات
- `items`, `units`, `hotels`, `suppliers`
- `transactions` (وارد/صادر/تسوية)
- `outward_orders`, `inventory_counts`, `expiry_alerts`, `users`

## قواعد مهمة
- لا تُغلق الاتصال في `get_db` (مُخزّن في session_state)
- استخدم `[list(r) for r in rows]` عند بناء DataFrame من نتائج Turso، وليس `[dict(r) for r in rows]`
- المرفقات الجديدة: `file_id` (يبدأ بـ `AgAC` أو `BQAC` أو `BAAC`)
- المرفقات القديمة: اسم ملف محلي (سيُنبَّه المستخدم أنها غير متوفرة)

## الأفكار المستقبلية
- [ ] تقارير رسومية (Charts)
- [ ] تنبيهات تلقائية على تيليجرام عند نقص المخزون
- [ ] صلاحيات دقيقة لكل مستخدم
- [ ] سجل تدقيق (Audit Log)
- [ ] الباركود / QR للبحث السريع
- [ ] حفظ الشعار في Turso بدل الملف المحلي
- [ ] تواريخ صلاحية وتنبيهات
