import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
import io
import os
import json
import hashlib
import re
import base64
import shutil
import zipfile
import urllib.request
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# مكتبات Google Drive
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# ======================== إعدادات الصفحة ========================
st.set_page_config(page_title="مخزن النظافة", layout="wide", initial_sidebar_state="collapsed")

# ======================== إعدادات عامة ========================
APP_CONFIG_FILE = 'app_config.json'
DB_NAME = 'cleaning_inventory.db'
BACKUP_FOLDER = 'backups'
ATTACHMENTS_FOLDER = 'attachments'
LOGO_FILE = 'logo.png'

# إعدادات Google Drive من الأسرار
GDRIVE_ENABLED = st.secrets.get("google_drive", {}).get("enabled", False)
GDRIVE_FOLDER_ID = st.secrets.get("google_drive", {}).get("folder_id", "")
SERVICE_ACCOUNT_FILE = st.secrets.get("google_drive", {}).get("service_account_file", "service_account.json")

# إنشاء المجلدات
os.makedirs(BACKUP_FOLDER, exist_ok=True)
os.makedirs(ATTACHMENTS_FOLDER, exist_ok=True)

# ======================== دوال Google Drive ========================
def get_drive_service():
    """إنشاء خدمة Google Drive مع دعم الأسرار أو الملف المحلي"""
    if not GDRIVE_ENABLED:
        return None
    try:
        # 1) محاولة قراءة بيانات الحساب من الأسرار (للاستخدام السحابي)
        service_account_info_str = st.secrets.get("google_drive", {}).get("service_account_info")
        if service_account_info_str:
            service_account_info = json.loads(service_account_info_str)
            creds = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/drive']
            )
        else:
            # 2) الرجوع إلى ملف محلي (للاستخدام المحلي)
            if os.path.exists(SERVICE_ACCOUNT_FILE):
                creds = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE,
                    scopes=['https://www.googleapis.com/auth/drive']
                )
            else:
                st.error("لا توجد بيانات اعتماد Google Drive. أضف service_account_info في الأسرار أو service_account.json محليًا.")
                return None
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"خطأ في الاتصال بـ Google Drive: {str(e)}")
        return None

def upload_db_to_drive():
    """رفع قاعدة البيانات إلى Google Drive (استبدال أو إنشاء)"""
    if not GDRIVE_ENABLED or not os.path.exists(DB_NAME):
        return False
    service = get_drive_service()
    if not service:
        return False
    try:
        query = f"'{GDRIVE_FOLDER_ID}' in parents and name = '{DB_NAME}' and trashed = false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])
        media = MediaFileUpload(DB_NAME, mimetype='application/x-sqlite3')
        if files:
            file_id = files[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
        else:
            file_metadata = {
                'name': DB_NAME,
                'parents': [GDRIVE_FOLDER_ID]
            }
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return True
    except Exception as e:
        st.error(f"فشل رفع قاعدة البيانات: {str(e)}")
        return False

def download_db_from_drive():
    """تنزيل قاعدة البيانات من Google Drive إذا كانت موجودة"""
    if not GDRIVE_ENABLED:
        return False
    service = get_drive_service()
    if not service:
        return False
    try:
        query = f"'{GDRIVE_FOLDER_ID}' in parents and name = '{DB_NAME}' and trashed = false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])
        if not files:
            return False
        file_id = files[0]['id']
        request = service.files().get_media(fileId=file_id)
        with open(DB_NAME, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        return True
    except Exception as e:
        st.error(f"فشل تنزيل قاعدة البيانات: {str(e)}")
        return False

def sync_db_to_drive():
    """مزامنة تلقائية بعد أي تغيير"""
    if GDRIVE_ENABLED:
        return upload_db_to_drive()
    return False

# ======================== إعدادات عامة للثيم ========================
def load_app_config():
    if os.path.exists(APP_CONFIG_FILE):
        with open(APP_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'font_size': 100,
        'theme_color': "#00a86b",
        'logo_path': None,
        'store_name': "مخزن النظافة"
    }

def save_app_config(config):
    with open(APP_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

saved_config = load_app_config()
if 'font_size' not in st.session_state:
    st.session_state.font_size = saved_config.get('font_size', 100)
if 'theme_color' not in st.session_state:
    st.session_state.theme_color = saved_config.get('theme_color', "#00a86b")
if 'logo_path' not in st.session_state:
    st.session_state.logo_path = saved_config.get('logo_path', None)
if 'store_name' not in st.session_state:
    st.session_state.store_name = saved_config.get('store_name', "مخزن النظافة")

def apply_theme():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;900&display=swap');
    *{{font-family:'Tajawal',sans-serif}}
    html,body,[class*="css"]{{direction:rtl;text-align:right;font-size:{st.session_state.font_size}% !important}}
    .stApp {{
        background-color: {st.session_state.theme_color} !important;
        background-image: linear-gradient(135deg, {st.session_state.theme_color} 0%, #ffffff 100%) !important;
    }}
    .stock-critical{{background-color:#ff4444;color:white;padding:5px 10px;border-radius:5px}}
    .stock-warning{{background-color:#ffbb33;color:black;padding:5px 10px;border-radius:5px}}
    .stock-good{{background-color:#00C851;color:white;padding:5px 10px;border-radius:5px}}
    </style>""", unsafe_allow_html=True)

apply_theme()

# ======================== دوال مساعدة ========================
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS units (id INTEGER PRIMARY KEY AUTOINCREMENT, unit_name TEXT UNIQUE, unit_symbol TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS suppliers (id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_name TEXT UNIQUE, contact_info TEXT, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_code TEXT UNIQUE,
        name TEXT NOT NULL UNIQUE,
        unit_id INTEGER,
        min_qty REAL DEFAULT 0,
        max_qty REAL DEFAULT 100,
        current_balance REAL DEFAULT 0,
        primary_supplier_id INTEGER,
        shelf_life_days INTEGER DEFAULT 365,
        notes TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_date TEXT,
        last_updated TEXT,
        FOREIGN KEY (unit_id) REFERENCES units(id),
        FOREIGN KEY (primary_supplier_id) REFERENCES suppliers(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS hotels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, contact_person TEXT, phone TEXT, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS outward_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE,
        hotel_id INTEGER,
        recipient_name TEXT,
        order_date TEXT,
        notes TEXT,
        created_by TEXT,
        FOREIGN KEY (hotel_id) REFERENCES hotels(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_type TEXT,
        item_id INTEGER,
        hotel_id INTEGER,
        qty REAL,
        unit_id INTEGER,
        batch_number TEXT,
        expiry_date TEXT,
        transaction_date TEXT,
        notes TEXT,
        created_by TEXT DEFAULT 'أمين المخزن',
        attachment TEXT,
        order_id INTEGER,
        supplier_name TEXT,
        unit_price REAL DEFAULT 0,
        FOREIGN KEY (item_id) REFERENCES items(id),
        FOREIGN KEY (hotel_id) REFERENCES hotels(id),
        FOREIGN KEY (unit_id) REFERENCES units(id),
        FOREIGN KEY (order_id) REFERENCES outward_orders(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory_counts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        count_date TEXT,
        item_id INTEGER,
        expected_qty REAL,
        actual_qty REAL,
        difference REAL,
        notes TEXT,
        counted_by TEXT,
        FOREIGN KEY (item_id) REFERENCES items(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS expiry_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        batch_number TEXT,
        expiry_date TEXT,
        qty_remaining REAL,
        is_consumed BOOLEAN DEFAULT 0,
        FOREIGN KEY (item_id) REFERENCES items(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('super_admin', 'purchasing', 'disbursement', 'supervisor')),
        full_name TEXT,
        is_active BOOLEAN DEFAULT 1
    )''')

    # وحدات افتراضية
    for u_name, u_sym in [('قطعة','قطعة'),('لتر','لتر'),('كيلو','كجم'),('متر','متر'),
                         ('كرتونة','كرتونة'),('رول','رول'),('زجاجة','زجاجة'),('علبة','علبة'),('كيس','كيس')]:
        c.execute("INSERT OR IGNORE INTO units (unit_name, unit_symbol) VALUES (?,?)",(u_name,u_sym))
    # مستخدمون افتراضيون
    default_users = [
        ('admin',hash_password('admin123'),'super_admin','المدير العام'),
        ('مشتريات',hash_password('buy123'),'purchasing','مسؤول المشتريات'),
        ('صرف',hash_password('out123'),'disbursement','مسؤول الصرف'),
        ('مشرف1',hash_password('sup123'),'supervisor','مشرف أول'),
        ('مشرف2',hash_password('sup456'),'supervisor','مشرف ثاني')
    ]
    for uname,pwd,role,fname in default_users:
        c.execute("INSERT OR IGNORE INTO users (username,password,role,full_name) VALUES (?,?,?,?)",(uname,pwd,role,fname))
    conn.commit()
    conn.close()

def login(username, password):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=? AND password=? AND is_active=1",
                        (username,hash_password(password))).fetchone()
    conn.close()
    if user:
        st.session_state.user = dict(user)
        st.session_state.logged_in = True
        return True
    return False

def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()

def check_perm(role=None):
    if not st.session_state.get('logged_in'): return False
    if st.session_state.user['role']=='super_admin': return True
    if role and st.session_state.user['role']==role: return True
    return False

def has_role(role):
    return st.session_state.get('user',{}).get('role')==role

# ======================== PDF عربي ========================
def get_arabic_font():
    path = "Amiri-Regular.ttf"
    if not os.path.exists(path):
        try:
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf", path)
        except: pass
    return path if os.path.exists(path) else None

def shape_arabic(text):
    if not re.search('[\u0600-\u06FF]', str(text)):
        return text
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)

def generate_pdf(title, df, cols_map=None):
    font_path = get_arabic_font()
    pdf = FPDF()
    pdf.add_page()
    if font_path:
        pdf.add_font("Amiri", fname=font_path)
        pdf.set_font("Amiri", size=14)
    else:
        pdf.set_font("Helvetica", size=14)
    pdf.cell(0,10, shape_arabic(title), ln=True, align='C')
    pdf.ln(10)
    if df.empty:
        pdf.cell(0,10,shape_arabic("لا توجد بيانات"), ln=True)
        return bytes(pdf.output())
    if cols_map: df = df.rename(columns=cols_map)
    cols = list(df.columns)
    widths = []
    for col in cols:
        m = pdf.get_string_width(shape_arabic(str(col)))
        for _,r in df.iterrows():
            v = str(r[col]) if pd.notnull(r[col]) else '-'
            m = max(m, pdf.get_string_width(shape_arabic(v)))
        widths.append(m+10)
    total = sum(widths)
    if total > pdf.w-20:
        scale = (pdf.w-20)/total
        widths = [w*scale for w in widths]
    pdf.set_fill_color(0,168,107); pdf.set_text_color(255,255,255)
    for i,col in enumerate(cols):
        pdf.cell(widths[i],10, shape_arabic(str(col)), border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_text_color(0,0,0)
    if font_path:
        pdf.set_font("Amiri", size=10)
    else:
        pdf.set_font("Helvetica", size=10)
    for _,row in df.iterrows():
        for i,col in enumerate(cols):
            v = str(row[col]) if pd.notnull(row[col]) else '-'
            pdf.cell(widths[i],8, shape_arabic(v), border=1, align='C')
        pdf.ln()
    return bytes(pdf.output())

def export_buttons(df, prefix, pdf_title=None):
    c1,c2 = st.columns(2)
    with c1:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as w:
            df.to_excel(w, sheet_name='report', index=False)
        st.download_button("📥 Excel", data=out.getvalue(), file_name=f"{prefix}_{date.today()}.xlsx")
    with c2:
        if pdf_title:
            pdf_bytes = generate_pdf(pdf_title, df)
            st.download_button("📄 PDF", data=pdf_bytes, file_name=f"{prefix}_{date.today()}.pdf")

def generate_outward_order_number():
    conn = get_db()
    today_str = date.today().strftime("%Y%m%d")
    last = conn.execute("SELECT order_number FROM outward_orders WHERE order_number LIKE ? ORDER BY id DESC LIMIT 1",
                        (f"OUT-{today_str}-%",)).fetchone()
    conn.close()
    if last:
        last_num = int(last['order_number'].split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1
    return f"OUT-{today_str}-{new_num:04d}"

# ======================== حذف وتعديل ========================
def delete_transaction(trans_id):
    conn = get_db()
    trans = conn.execute("SELECT * FROM transactions WHERE id=?", (trans_id,)).fetchone()
    if not trans:
        conn.close()
        return False, "الحركة غير موجودة"
    item_id = trans['item_id']
    qty = trans['qty']
    typ = trans['transaction_type']
    if typ == 'وارد' or typ == 'تسوية إضافة':
        conn.execute("UPDATE items SET current_balance = current_balance - ?, last_updated=? WHERE id=?", (qty, date.today().isoformat(), item_id))
    elif typ == 'صادر' or typ == 'تسوية عجز':
        conn.execute("UPDATE items SET current_balance = current_balance + ?, last_updated=? WHERE id=?", (qty, date.today().isoformat(), item_id))
    conn.execute("DELETE FROM transactions WHERE id=?", (trans_id,))
    conn.commit()
    conn.close()
    sync_db_to_drive()
    return True, "تم حذف الحركة بنجاح"

def delete_outward_order(order_id):
    conn = get_db()
    trans_items = conn.execute("SELECT item_id, qty FROM transactions WHERE order_id=? AND transaction_type='صادر'", (order_id,)).fetchall()
    for t in trans_items:
        conn.execute("UPDATE items SET current_balance = current_balance + ?, last_updated=? WHERE id=?", (t['qty'], date.today().isoformat(), t['item_id']))
    conn.execute("DELETE FROM transactions WHERE order_id=?", (order_id,))
    conn.execute("DELETE FROM outward_orders WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    sync_db_to_drive()
    return True, "تم حذف الإذن وإعادة الكميات إلى المخزون"

def save_attachment(uploaded_file, transaction_id):
    if uploaded_file is None: return None
    file_ext = os.path.splitext(uploaded_file.name)[1]
    safe_name = f"trans_{transaction_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{file_ext}"
    file_path = os.path.join(ATTACHMENTS_FOLDER, safe_name)
    with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return safe_name

def recalculate_all_balances():
    conn = get_db()
    items = conn.execute("SELECT id FROM items").fetchall()
    for item in items:
        total_in = conn.execute("SELECT COALESCE(SUM(qty),0) FROM transactions WHERE item_id=? AND transaction_type IN ('وارد','تسوية إضافة')", (item['id'],)).fetchone()[0]
        total_out = conn.execute("SELECT COALESCE(SUM(qty),0) FROM transactions WHERE item_id=? AND transaction_type IN ('صادر','تسوية عجز')", (item['id'],)).fetchone()[0]
        new_balance = total_in - total_out
        conn.execute("UPDATE items SET current_balance = ?, last_updated = ? WHERE id = ?", (new_balance, date.today().isoformat(), item['id']))
    conn.commit()
    conn.close()
    sync_db_to_drive()

# ======================== تشغيل أولي ========================
init_db()
# محاولة تحميل قاعدة البيانات من Google Drive إذا كانت المزامنة مفعلة
if GDRIVE_ENABLED:
    if download_db_from_drive():
        st.success("✅ تم تحميل قاعدة البيانات من Google Drive")
    else:
        st.warning("⚠️ لم يتم العثور على قاعدة بيانات في Drive، سيتم استخدام قاعدة محلية جديدة")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if not st.session_state.logged_in:
    st.title("🔐 تسجيل الدخول")
    with st.form("login"):
        uname = st.text_input("اسم المستخدم")
        pwd = st.text_input("كلمة المرور", type="password")
        if st.form_submit_button("دخول"):
            if login(uname, pwd):
                st.success("تم الدخول")
                st.rerun()
            else: st.error("خطأ")
    st.stop()

# ======================== الواجهة الرئيسية ========================
st.title(f"🧹 {st.session_state.store_name}")
if st.session_state.logo_path and os.path.exists(st.session_state.logo_path):
    st.image(st.session_state.logo_path, width=150)
st.write(f"مرحباً {st.session_state.user['full_name']} ({st.session_state.user['role']})")
if st.button("تسجيل الخروج"):
    logout()

with st.expander("⚙️ الإعدادات", expanded=False):
    new_font_size = st.slider("حجم الخط (%)", 50, 200, st.session_state.font_size, step=10, key="global_font")
    theme_color = st.color_picker("لون البرنامج", st.session_state.theme_color, key="global_theme")
    new_store_name = st.text_input("اسم المستودع", value=st.session_state.store_name, key="store_name_input")
    if st.button("تحديث الاسم", key="update_name"):
        if new_store_name.strip():
            st.session_state.store_name = new_store_name.strip()
            save_app_config({
                'font_size': st.session_state.font_size,
                'theme_color': st.session_state.theme_color,
                'logo_path': st.session_state.logo_path,
                'store_name': st.session_state.store_name
            })
            st.success("✅ تم تحديث اسم المستودع")
            st.rerun()
        else:
            st.error("الاسم لا يمكن أن يكون فارغاً")
    uploaded_logo = st.file_uploader("📷 رفع شعار", type=["png","jpg","jpeg"], key="logo_uploader")
    if uploaded_logo is not None:
        with open(LOGO_FILE, "wb") as f:
            f.write(uploaded_logo.getbuffer())
        st.session_state.logo_path = LOGO_FILE
        st.success("✅ تم رفع الشعار بنجاح")
        save_app_config({
            'font_size': st.session_state.font_size,
            'theme_color': st.session_state.theme_color,
            'logo_path': st.session_state.logo_path,
            'store_name': st.session_state.store_name
        })
        st.rerun()
    if st.session_state.logo_path and os.path.exists(st.session_state.logo_path):
        if st.button("🗑️ مسح الشعار"):
            os.remove(st.session_state.logo_path)
            st.session_state.logo_path = None
            st.success("تم مسح الشعار")
            save_app_config({
                'font_size': st.session_state.font_size,
                'theme_color': st.session_state.theme_color,
                'logo_path': st.session_state.logo_path,
                'store_name': st.session_state.store_name
            })
            st.rerun()
    if new_font_size != st.session_state.font_size or theme_color != st.session_state.theme_color:
        st.session_state.font_size = new_font_size
        st.session_state.theme_color = theme_color
        save_app_config({
            'font_size': st.session_state.font_size,
            'theme_color': st.session_state.theme_color,
            'logo_path': st.session_state.logo_path,
            'store_name': st.session_state.store_name
        })
        st.rerun()

menu = []
if check_perm():
    menu = ["📊 لوحة التحكم","📦 إدارة الأصناف","📏 الوحدات","🏨 الفنادق","🏢 الموردين",
            "📥 الوارد","📤 الصادر","📝 الجرد","📈 التقارير",
            "🗑️ إدارة الحركات (حذف)","💾 النسخ الاحتياطي","👥 المستخدمين"]
elif has_role('purchasing'):
    menu = ["📊 لوحة التحكم","📥 الوارد","📈 التقارير"]
elif has_role('disbursement'):
    menu = ["📊 لوحة التحكم","📤 الصادر","📈 التقارير"]
elif has_role('supervisor'):
    menu = ["📊 لوحة التحكم","📝 الجرد","📈 التقارير"]

choice = st.selectbox("القائمة", menu, index=0)

# ======================== دوال مساعدة للجداول ========================
def apply_table_styling(font_scale, bg_color):
    return f"""<style>
        div[data-testid="stDataFrame"] div[data-testid="stTable"] {{ font-size: {font_scale}% !important; }}
        div[data-testid="stDataFrame"] table {{ background-color: {bg_color} !important; }}
    </style>"""

def column_selector(label, all_columns, default_order, key):
    if key not in st.session_state:
        st.session_state[key] = default_order
    new_order = st.multiselect(label, options=all_columns, default=st.session_state[key], key=key+"_multiselect")
    if new_order != st.session_state[key]:
        st.session_state[key] = new_order
        st.rerun()
    return st.session_state[key]

# ======================== الصفحات ========================
if choice == "📊 لوحة التحكم":
    st.header("لوحة التحكم")
    conn = get_db()
    today = date.today()
    total = conn.execute("SELECT COUNT(*) FROM items WHERE is_active=1").fetchone()[0]
    low = conn.execute("SELECT COUNT(*) FROM items WHERE current_balance<=min_qty AND is_active=1").fetchone()[0]
    exp = conn.execute("SELECT COUNT(*) FROM expiry_alerts WHERE is_consumed=0 AND expiry_date<?",(today.isoformat(),)).fetchone()[0]
    c1,c2,c3 = st.columns(3)
    c1.metric("الأصناف", total); c2.metric("تحت الحد", low); c3.metric("منتهية الصلاحية", exp)
    st.divider()
    low_items = conn.execute("SELECT i.item_code, i.name, i.current_balance, i.min_qty, u.unit_symbol FROM items i LEFT JOIN units u ON i.unit_id=u.id WHERE i.current_balance<=i.min_qty AND i.is_active=1").fetchall()
    if low_items:
        df = pd.DataFrame(low_items, columns=['كود','الصنف','الرصيد','الحد الأدنى','الوحدة'])
        with st.expander("🎨 تنسيق جدول التنبيهات"):
            font_scale = st.slider("حجم الخط (%)", 50,200,100,10, key="dash_font")
            color_option = st.selectbox("لون الجدول", ["افتراضي","أخضر","أزرق","رمادي","برتقالي"], key="dash_color")
            color_map = {"افتراضي":"#f0f2f6","أخضر":"#e6ffe6","أزرق":"#e6f0ff","رمادي":"#f5f5f5","برتقالي":"#fff3e6"}
            bg = color_map.get(color_option,"#f0f2f6")
            cols = column_selector("اختر الأعمدة ورتبها", list(df.columns), list(df.columns), "dash_cols")
        df_disp = df[cols]
        st.dataframe(df_disp, use_container_width=True)
        st.markdown(apply_table_styling(font_scale, bg), unsafe_allow_html=True)
        export_buttons(df_disp, "اصناف_منخفضة", "تقرير الأصناف أقل من الحد الأدنى")
    conn.close()

elif choice == "📦 إدارة الأصناف":
    if not check_perm(): st.error("غير مصرح"); st.stop()
    st.header("إدارة الأصناف")
    conn = get_db()
    units = conn.execute("SELECT id, unit_name, unit_symbol FROM units").fetchall()
    unit_options = [f"{u['unit_name']} ({u['unit_symbol']})" for u in units]
    unit_dict = {opt: u['id'] for opt, u in zip(unit_options, units)}
    unit_id_to_text = {u['id']: f"{u['unit_name']} ({u['unit_symbol']})" for u in units}
    show_inactive = st.checkbox("إظهار الأصناف غير النشطة", value=False)
    condition = "" if show_inactive else "WHERE is_active = 1"
    items = conn.execute(f"SELECT id, item_code, name, unit_id, current_balance, min_qty, max_qty, is_active, notes FROM items {condition} ORDER BY name").fetchall()
    data = []
    for it in items:
        data.append({
            "id": it["id"],
            "item_code": it["item_code"],
            "name": it["name"],
            "unit_text": unit_id_to_text.get(it["unit_id"], unit_options[0]),
            "current_balance": it["current_balance"],
            "min_qty": it["min_qty"],
            "max_qty": it["max_qty"],
            "is_active": bool(it["is_active"]),
            "notes": it["notes"],
            "delete": False
        })
    df = pd.DataFrame(data)
    if 'edited_df' not in st.session_state:
        st.session_state.edited_df = df.copy()
    if 'redo_df' not in st.session_state:
        st.session_state.redo_df = None
    if st.session_state.edited_df is not None:
        df = st.session_state.edited_df.copy()
    else:
        st.session_state.edited_df = df.copy()
    edited_df = st.data_editor(
        df,
        column_config={
            "id": st.column_config.NumberColumn("المعرف", disabled=True),
            "item_code": st.column_config.TextColumn("الكود", disabled=True),
            "name": st.column_config.TextColumn("اسم الصنف", required=True),
            "unit_text": st.column_config.SelectboxColumn("الوحدة", options=unit_options),
            "current_balance": st.column_config.NumberColumn("الرصيد الحالي", disabled=True),
            "min_qty": st.column_config.NumberColumn("الحد الأدنى", min_value=0.0, step=0.1),
            "max_qty": st.column_config.NumberColumn("الحد الأقصى", min_value=0.0, step=0.1),
            "is_active": st.column_config.CheckboxColumn("نشط"),
            "notes": st.column_config.TextColumn("ملاحظات"),
            "delete": st.column_config.CheckboxColumn("حذف")
        },
        disabled=["id", "item_code", "current_balance"],
        hide_index=True,
        num_rows="dynamic",
        key="items_editor"
    )
    st.session_state.edited_df = edited_df.copy()
    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
    with col_btn1:
        if st.button("💾 حفظ جميع التعديلات", type="primary"):
            with conn:
                ids_to_delete = edited_df[edited_df["delete"] == True]["id"].dropna().astype(int).tolist()
                for item_id in ids_to_delete:
                    trans_count = conn.execute("SELECT COUNT(*) FROM transactions WHERE item_id=?", (item_id,)).fetchone()[0]
                    if trans_count > 0:
                        st.warning(f"الصنف رقم {item_id} لا يمكن حذفه لوجود حركات مرتبطة.")
                    else:
                        conn.execute("DELETE FROM expiry_alerts WHERE item_id=?", (item_id,))
                        conn.execute("DELETE FROM inventory_counts WHERE item_id=?", (item_id,))
                        conn.execute("DELETE FROM items WHERE id=?", (item_id,))
                for _, row in edited_df.iterrows():
                    if pd.isna(row["id"]):
                        if pd.isna(row["name"]) or str(row["name"]).strip() == "":
                            continue
                        exists = conn.execute("SELECT id FROM items WHERE name=? AND is_active=1", (row["name"].strip(),)).fetchone()
                        if exists:
                            st.warning(f"الصنف '{row['name']}' موجود مسبقاً، تم تخطيه.")
                            continue
                        unit_id = unit_dict.get(row["unit_text"], units[0]["id"])
                        code = f"ITM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        conn.execute("INSERT INTO items (item_code, name, unit_id, min_qty, max_qty, current_balance, is_active, notes, created_date, last_updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                     (code, row["name"].strip(), unit_id, row["min_qty"], row["max_qty"],
                                      0.0, int(row["is_active"]), row.get("notes", ""),
                                      date.today().isoformat(), date.today().isoformat()))
                    else:
                        item_id = int(row["id"])
                        unit_id = unit_dict.get(row["unit_text"], units[0]["id"])
                        new_name = row["name"].strip() if pd.notna(row["name"]) else ""
                        if new_name == "":
                            continue
                        duplicate = conn.execute("SELECT id FROM items WHERE name=? AND id!=? AND is_active=1", (new_name, item_id)).fetchone()
                        if duplicate:
                            st.warning(f"الاسم '{new_name}' موجود بالفعل لصنف آخر، لم يتم تحديث الصنف {item_id}.")
                            continue
                        conn.execute("""UPDATE items SET name=?, unit_id=?, min_qty=?, max_qty=?, is_active=?, notes=?, last_updated=?
                                      WHERE id=?""",
                                     (new_name, unit_id, row["min_qty"], row["max_qty"],
                                      int(row["is_active"]), row.get("notes", ""),
                                      date.today().isoformat(), item_id))
            conn.commit()
            sync_db_to_drive()
            st.success("تم حفظ التعديلات بنجاح")
            items_updated = conn.execute(f"SELECT id, item_code, name, unit_id, current_balance, min_qty, max_qty, is_active, notes FROM items {condition} ORDER BY name").fetchall()
            new_data = []
            for it in items_updated:
                new_data.append({
                    "id": it["id"],
                    "item_code": it["item_code"],
                    "name": it["name"],
                    "unit_text": unit_id_to_text.get(it["unit_id"], unit_options[0]),
                    "current_balance": it["current_balance"],
                    "min_qty": it["min_qty"],
                    "max_qty": it["max_qty"],
                    "is_active": bool(it["is_active"]),
                    "notes": it["notes"],
                    "delete": False
                })
            st.session_state.edited_df = pd.DataFrame(new_data)
            st.session_state.redo_df = None
            st.rerun()
    with col_btn2:
        if st.button("↩️ تراجع"):
            st.session_state.redo_df = st.session_state.edited_df.copy()
            items_orig = conn.execute(f"SELECT id, item_code, name, unit_id, current_balance, min_qty, max_qty, is_active, notes FROM items {condition} ORDER BY name").fetchall()
            orig_data = []
            for it in items_orig:
                orig_data.append({
                    "id": it["id"],
                    "item_code": it["item_code"],
                    "name": it["name"],
                    "unit_text": unit_id_to_text.get(it["unit_id"], unit_options[0]),
                    "current_balance": it["current_balance"],
                    "min_qty": it["min_qty"],
                    "max_qty": it["max_qty"],
                    "is_active": bool(it["is_active"]),
                    "notes": it["notes"],
                    "delete": False
                })
            st.session_state.edited_df = pd.DataFrame(orig_data)
            st.rerun()
    with col_btn3:
        if st.button("↪️ تقديم"):
            if st.session_state.redo_df is not None:
                st.session_state.edited_df = st.session_state.redo_df.copy()
                st.session_state.redo_df = None
                st.rerun()
            else:
                st.info("لا توجد تعديلات متراجع عنها لتقديمها")
    with col_btn4:
        if st.button("🔄 إعادة تحميل البيانات"):
            st.session_state.edited_df = None
            st.session_state.redo_df = None
            st.rerun()
    st.divider()
    if st.button("🔁 إعادة حساب جميع الأرصدة (من الحركات)"):
        with st.spinner("جاري إعادة حساب الأرصدة..."):
            recalculate_all_balances()
        st.success("تمت إعادة حساب جميع الأرصدة بنجاح. الأرصدة الآن مطابقة للحركات الفعلية.")
        st.rerun()
    conn.close()

elif choice == "📏 الوحدات":
    if not check_perm(): st.error("غير مصرح"); st.stop()
    st.header("وحدات القياس")
    conn = get_db()
    tab1, tab2 = st.tabs(["➕ إضافة وحدة", "✏️ تعديل الوحدات"])
    with tab1:
        with st.form("add_unit"):
            un = st.text_input("اسم الوحدة")
            us = st.text_input("الرمز")
            if st.form_submit_button("إضافة"):
                if un:
                    conn.execute("INSERT OR IGNORE INTO units (unit_name, unit_symbol) VALUES (?,?)",(un,us))
                    conn.commit()
                    sync_db_to_drive()
                    st.success("تم الحفظ بنجاح")
                    st.rerun()
    with tab2:
        units = conn.execute("SELECT id, unit_name, unit_symbol FROM units").fetchall()
        if units:
            df_units = pd.DataFrame(units, columns=['م','الوحدة','الرمز'])
            edited_units = st.data_editor(df_units, num_rows="dynamic", key="units_editor", use_container_width=True)
            if st.button("💾 حفظ تعديلات الوحدات", key="save_units"):
                with conn:
                    for _, row in edited_units.iterrows():
                        if pd.notna(row['م']):
                            conn.execute("UPDATE units SET unit_name=?, unit_symbol=? WHERE id=?", (row['الوحدة'], row['الرمز'], int(row['م'])))
                        else:
                            if pd.notna(row['الوحدة']) and str(row['الوحدة']).strip():
                                conn.execute("INSERT OR IGNORE INTO units (unit_name, unit_symbol) VALUES (?,?)", (row['الوحدة'], row['الرمز']))
                conn.commit()
                sync_db_to_drive()
                st.success("تم حفظ التعديلات بنجاح")
                st.rerun()
        else:
            st.info("لا توجد وحدات")
    conn.close()

elif choice == "🏨 الفنادق":
    if not check_perm(): st.error("غير مصرح"); st.stop()
    st.header("الفنادق")
    conn = get_db()
    tab1, tab2 = st.tabs(["إضافة","تعديل"])
    with tab1:
        with st.form("add_hotel"):
            name = st.text_input("اسم الفندق")
            contact = st.text_input("الشخص المسؤول")
            phone = st.text_input("الهاتف")
            if st.form_submit_button("إضافة"):
                conn.execute("INSERT OR IGNORE INTO hotels (name,contact_person,phone) VALUES (?,?,?)",(name,contact,phone))
                conn.commit()
                sync_db_to_drive()
                st.success("تم الحفظ بنجاح")
                st.rerun()
    with tab2:
        hotels = conn.execute("SELECT * FROM hotels").fetchall()
        if hotels:
            hotel_names = [h['name'] for h in hotels]
            selected = st.selectbox("اختر الفندق", hotel_names)
            h = [h for h in hotels if h['name']==selected][0]
            new_name = st.text_input("الاسم الجديد", value=h['name'])
            new_contact = st.text_input("الشخص المسؤول", value=h['contact_person'] or "")
            new_phone = st.text_input("الهاتف", value=h['phone'] or "")
            if st.button("حفظ التعديلات"):
                if new_name and new_name != selected:
                    exists = conn.execute("SELECT id FROM hotels WHERE name=? AND id!=?",(new_name,h['id'])).fetchone()
                    if exists: st.error("الاسم موجود")
                    else:
                        conn.execute("UPDATE hotels SET name=?, contact_person=?, phone=? WHERE id=?",(new_name, new_contact, new_phone, h['id']))
                        conn.commit()
                        sync_db_to_drive()
                        st.success("تم الحفظ بنجاح"); st.rerun()
                else:
                    conn.execute("UPDATE hotels SET name=?, contact_person=?, phone=? WHERE id=?",(new_name, new_contact, new_phone, h['id']))
                    conn.commit()
                    sync_db_to_drive()
                    st.success("تم الحفظ بنجاح"); st.rerun()
        else: st.info("لا توجد فنادق")
    conn.close()

elif choice == "🏢 الموردين":
    if not check_perm(): st.error("غير مصرح"); st.stop()
    st.header("الموردين")
    conn = get_db()
    tab1, tab2 = st.tabs(["إضافة","تعديل"])
    with tab1:
        with st.form("add_sup"):
            name = st.text_input("اسم المورد")
            info = st.text_input("معلومات الاتصال")
            if st.form_submit_button("إضافة"):
                conn.execute("INSERT OR IGNORE INTO suppliers (supplier_name,contact_info) VALUES (?,?)",(name,info))
                conn.commit()
                sync_db_to_drive()
                st.success("تم الحفظ بنجاح"); st.rerun()
    with tab2:
        supps = conn.execute("SELECT * FROM suppliers").fetchall()
        if supps:
            supp_names = [s['supplier_name'] for s in supps]
            selected = st.selectbox("اختر المورد", supp_names)
            s = [s for s in supps if s['supplier_name']==selected][0]
            new_name = st.text_input("الاسم الجديد", value=s['supplier_name'])
            new_info = st.text_input("معلومات الاتصال", value=s['contact_info'] or "")
            if st.button("حفظ التعديلات"):
                if new_name and new_name != selected:
                    exists = conn.execute("SELECT id FROM suppliers WHERE supplier_name=? AND id!=?",(new_name,s['id'])).fetchone()
                    if exists: st.error("الاسم موجود")
                    else:
                        conn.execute("UPDATE suppliers SET supplier_name=?, contact_info=? WHERE id=?",(new_name, new_info, s['id']))
                        conn.commit(); sync_db_to_drive(); st.success("تم الحفظ بنجاح"); st.rerun()
                else:
                    conn.execute("UPDATE suppliers SET supplier_name=?, contact_info=? WHERE id=?",(new_name, new_info, s['id']))
                    conn.commit(); sync_db_to_drive(); st.success("تم الحفظ بنجاح"); st.rerun()
        else: st.info("لا يوجد موردين")
    conn.close()

elif choice == "📥 الوارد":
    tab_in1, tab_in2 = st.tabs(["📝 تسجيل مشتريات", "📋 سجل المشتريات"])
    with tab_in1:
        st.subheader("تسجيل مشتريات جديدة")
        conn = get_db()
        items = conn.execute("SELECT id,name,unit_id FROM items WHERE is_active=1").fetchall()
        suppliers = conn.execute("SELECT id, supplier_name FROM suppliers ORDER BY supplier_name").fetchall()
        supplier_options = [s['supplier_name'] for s in suppliers]
        if not supplier_options:
            supplier_options = ["لا يوجد موردين مسجلين"]
        if items:
            if 'inward_defaults' not in st.session_state:
                st.session_state.inward_defaults = {
                    'item': items[0]['name'] if items else "",
                    'qty': 1.0,
                    'supplier': supplier_options[0] if supplier_options else "",
                    'unit_price': 0.0,
                    'invoice_date': date.today(),
                    'notes': "",
                    'attachment': None
                }
            if 'inward_form_values' not in st.session_state:
                st.session_state.inward_form_values = st.session_state.inward_defaults.copy()
            with st.form("inward"):
                item = st.selectbox("الصنف", [i['name'] for i in items], 
                                    index=[i['name'] for i in items].index(st.session_state.inward_form_values['item']) if st.session_state.inward_form_values['item'] in [i['name'] for i in items] else 0)
                qty = st.number_input("الكمية",0.1,100000.0, st.session_state.inward_form_values['qty'])
                supplier = st.selectbox("المورد", supplier_options, 
                                        index=supplier_options.index(st.session_state.inward_form_values['supplier']) if st.session_state.inward_form_values['supplier'] in supplier_options else 0)
                unit_price = st.number_input("سعر الوحدة", min_value=0.0, value=st.session_state.inward_form_values['unit_price'], step=0.01)
                invoice_date = st.date_input("تاريخ الفاتورة", value=st.session_state.inward_form_values['invoice_date'])
                notes = st.text_input("ملاحظات", value=st.session_state.inward_form_values['notes'])
                uploaded_file = st.file_uploader("📎 إرفاق ملف (صورة أو PDF)", type=["png","jpg","jpeg","pdf"])
                col_submit, col_undo, col_redo = st.columns([2,1,1])
                with col_submit:
                    submitted = st.form_submit_button("تسجيل")
                with col_undo:
                    undo = st.form_submit_button("↩️ تراجع")
                with col_redo:
                    redo = st.form_submit_button("↪️ تقديم")
                if submitted:
                    it = [i for i in items if i['name']==item][0]
                    conn.execute("""INSERT INTO transactions (transaction_type,item_id,qty,unit_id,supplier_name,unit_price,transaction_date,notes,created_by)
                                  VALUES (?,?,?,?,?,?,?,?,?)""",
                                 ('وارد',it['id'],qty,it['unit_id'],supplier if supplier != "لا يوجد موردين مسجلين" else "", unit_price, invoice_date.isoformat(),notes,st.session_state.user['full_name']))
                    trans_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    if uploaded_file:
                        att = save_attachment(uploaded_file, trans_id)
                        conn.execute("UPDATE transactions SET attachment=? WHERE id=?", (att, trans_id))
                    conn.execute("UPDATE items SET current_balance=current_balance+?, last_updated=? WHERE id=?",(qty,date.today().isoformat(),it['id']))
                    conn.commit()
                    sync_db_to_drive()
                    st.success(f"تم الحفظ بنجاح (تاريخ الفاتورة: {invoice_date.isoformat()})")
                    st.session_state.inward_defaults = {
                        'item': item,
                        'qty': qty,
                        'supplier': supplier,
                        'unit_price': unit_price,
                        'invoice_date': invoice_date,
                        'notes': notes,
                        'attachment': uploaded_file
                    }
                    st.session_state.inward_form_values = st.session_state.inward_defaults.copy()
                    st.rerun()
                if undo:
                    st.session_state.inward_form_values = st.session_state.inward_defaults.copy()
                    st.rerun()
                if redo:
                    if 'inward_redo_values' in st.session_state:
                        st.session_state.inward_form_values = st.session_state.inward_redo_values.copy()
                        st.session_state.inward_redo_values = None
                        st.rerun()
                    else:
                        st.info("لا توجد تعديلات متراجع عنها لتقديمها")
        conn.close()
    with tab_in2:
        st.subheader("سجل المشتريات")
        conn = get_db()
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            start_date = st.date_input("من تاريخ", date.today()-timedelta(days=30), key="in_start")
        with col_f2:
            end_date = st.date_input("إلى تاريخ", date.today(), key="in_end")
        inward_records = conn.execute("""
            SELECT t.id, t.transaction_date, i.name as item_name, t.qty, u.unit_symbol, t.notes, t.attachment, t.supplier_name, t.unit_price
            FROM transactions t
            JOIN items i ON t.item_id = i.id
            LEFT JOIN units u ON t.unit_id = u.id
            WHERE t.transaction_type = 'وارد' 
            AND t.transaction_date BETWEEN ? AND ?
            ORDER BY t.id DESC
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()
        if inward_records:
            for rec in inward_records:
                with st.expander(f"📦 وارد #{rec['id']} - {rec['item_name']} ({rec['qty']} {rec['unit_symbol']}) - {rec['transaction_date']}"):
                    col_det1, col_det2 = st.columns(2)
                    with col_det1:
                        st.write(f"**رقم الحركة:** {rec['id']}")
                        st.write(f"**الصنف:** {rec['item_name']}")
                        st.write(f"**الكمية:** {rec['qty']} {rec['unit_symbol']}")
                        if rec['supplier_name']:
                            st.write(f"**المورد:** {rec['supplier_name']}")
                        if rec['unit_price']:
                            st.write(f"**سعر الوحدة:** {rec['unit_price']:.2f}")
                    with col_det2:
                        st.write(f"**التاريخ:** {rec['transaction_date']}")
                        st.write(f"**ملاحظات:** {rec['notes'] or 'لا يوجد'}")
                    if rec['attachment']:
                        att_path = os.path.join(ATTACHMENTS_FOLDER, rec['attachment'])
                        if os.path.exists(att_path):
                            file_ext = os.path.splitext(rec['attachment'])[1].lower()
                            if file_ext in ['.jpg', '.jpeg', '.png']:
                                st.image(att_path, caption="المرفق", width=300)
                            elif file_ext == '.pdf':
                                with open(att_path, "rb") as f:
                                    st.download_button("📄 تحميل PDF المرفق", f, file_name=rec['attachment'])
                            else:
                                with open(att_path, "rb") as f:
                                    st.download_button("📎 تحميل المرفق", f, file_name=rec['attachment'])
                    col_btn_print, col_btn_edit, col_btn_delete = st.columns(3)
                    with col_btn_print:
                        if st.button(f"🖨️ طباعة #{rec['id']}", key=f"print_in_{rec['id']}"):
                            font_path = get_arabic_font()
                            pdf = FPDF()
                            pdf.add_page()
                            if font_path:
                                pdf.add_font("Amiri", fname=font_path)
                                pdf.set_font("Amiri", size=16)
                            else:
                                pdf.set_font("Helvetica", size=16)
                            pdf.cell(0, 10, shape_arabic("إذن استلام مشتريات"), ln=True, align='C')
                            pdf.ln(10)
                            if font_path:
                                pdf.set_font("Amiri", size=12)
                            else:
                                pdf.set_font("Helvetica", size=12)
                            pdf.cell(0, 8, shape_arabic(f"رقم الإذن: IN-{rec['id']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"التاريخ: {rec['transaction_date']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"الصنف: {rec['item_name']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"الكمية: {rec['qty']} {rec['unit_symbol']}"), ln=True, align='R')
                            if rec['supplier_name']:
                                pdf.cell(0, 8, shape_arabic(f"المورد: {rec['supplier_name']}"), ln=True, align='R')
                            if rec['unit_price']:
                                pdf.cell(0, 8, shape_arabic(f"سعر الوحدة: {rec['unit_price']:.2f}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"ملاحظات: {rec['notes'] or 'لا يوجد'}"), ln=True, align='R')
                            pdf.ln(10)
                            pdf.cell(0, 10, shape_arabic("توقيع أمين المخزن: ________________"), ln=True, align='R')
                            pdf_bytes = bytes(pdf.output())
                            st.download_button(f"📥 تحميل PDF الإذن #{rec['id']}", data=pdf_bytes,
                                               file_name=f"Purchase_Order_{rec['id']}.pdf", mime="application/pdf")
                    with col_btn_delete:
                        if st.button(f"🗑️ حذف #{rec['id']}", key=f"del_in_{rec['id']}"):
                            if st.session_state.get(f"confirm_del_in_{rec['id']}", False):
                                success, msg = delete_transaction(rec['id'])
                                if success:
                                    st.success(msg)
                                    st.session_state[f"confirm_del_in_{rec['id']}"] = False
                                    st.rerun()
                                else:
                                    st.error(msg)
                            else:
                                st.session_state[f"confirm_del_in_{rec['id']}"] = True
                                st.warning("⚠️ اضغط مرة أخرى لتأكيد الحذف (سيتم خصم الكمية من المخزون).")
                                st.rerun()
        else:
            st.info("لا توجد مشتريات في هذه الفترة")
        conn.close()

elif choice == "📤 الصادر":
    tab_out1, tab_out2 = st.tabs(["📝 إنشاء إذن صرف", "📋 سجل أذون الصرف"])
    with tab_out1:
        st.subheader("إنشاء إذن صرف جديد")
        conn = get_db()
        items = conn.execute("SELECT id, name, current_balance, unit_id FROM items WHERE is_active=1").fetchall()
        hotels = conn.execute("SELECT id, name, contact_person, phone FROM hotels").fetchall()
        if not items or not hotels:
            st.warning("يجب إضافة أصناف وفنادق أولاً")
        else:
            item_options = [f"{it['name']} (الرصيد: {it['current_balance']})" for it in items]
            if 'outward_items' not in st.session_state:
                st.session_state.outward_items = []
            if 'outward_form_defaults' not in st.session_state:
                st.session_state.outward_form_defaults = {
                    'hotel': hotels[0]['name'],
                    'recipient': hotels[0]['contact_person'] if hotels[0]['contact_person'] else "",
                    'order_date': date.today(),
                    'notes': ""
                }
            if 'outward_form_values' not in st.session_state:
                st.session_state.outward_form_values = st.session_state.outward_form_defaults.copy()
            st.subheader("إضافة أصناف للإذن")
            col1, col2 = st.columns(2)
            with col1:
                selected_item_str = st.selectbox("الصنف", item_options, key="item_select")
            with col2:
                qty = st.number_input("الكمية", min_value=0.1, value=1.0, step=0.1, key="qty_input")
            col_add, col_undo_items = st.columns(2)
            with col_add:
                if st.button("➕ أضف إلى الإذن"):
                    if qty <= 0:
                        st.error("الكمية يجب أن تكون أكبر من صفر")
                    else:
                        item_name = selected_item_str.split(" (الرصيد:")[0]
                        it = next((i for i in items if i['name'] == item_name), None)
                        if it:
                            if qty > it['current_balance']:
                                st.error(f"الرصيد غير كافٍ ({it['current_balance']})")
                            else:
                                st.session_state.outward_items.append({
                                    'item_id': it['id'],
                                    'item_name': it['name'],
                                    'qty': qty,
                                    'unit_id': it['unit_id']
                                })
                                st.success(f"تمت إضافة {item_name} ({qty})")
                                st.rerun()
            with col_undo_items:
                if st.button("↩️ تراجع آخر إضافة"):
                    if st.session_state.outward_items:
                        removed = st.session_state.outward_items.pop()
                        st.success(f"تم إزالة {removed['item_name']} من الإذن")
                        st.rerun()
                    else:
                        st.info("لا توجد أصناف في القائمة")
            if st.session_state.outward_items:
                st.subheader("الأصناف في الإذن الحالي")
                df_current = pd.DataFrame(st.session_state.outward_items)
                units = conn.execute("SELECT id, unit_symbol FROM units").fetchall()
                unit_dict_out = {u['id']: u['unit_symbol'] for u in units}
                df_current['الوحدة'] = df_current['unit_id'].map(unit_dict_out)
                df_display = df_current[['item_name', 'qty', 'الوحدة']].copy()
                df_display.columns = ['الصنف', 'الكمية', 'الوحدة']
                st.dataframe(df_display, use_container_width=True)
                if st.button("🗑️ مسح القائمة"):
                    st.session_state.outward_items = []
                    st.rerun()
                st.divider()
                st.subheader("بيانات الإذن")
                col_order1, col_order2 = st.columns(2)
                with col_order1:
                    hotel_names = [h['name'] for h in hotels]
                    selected_hotel = st.selectbox("الفندق", hotel_names, 
                                                  index=hotel_names.index(st.session_state.outward_form_values['hotel']) if st.session_state.outward_form_values['hotel'] in hotel_names else 0,
                                                  key="hotel_select")
                    current_hotel = next((h for h in hotels if h['name'] == selected_hotel), None)
                with col_order2:
                    recipient = st.text_input("اسم مسؤول الاستلام (للتوقيع)", 
                                              value=st.session_state.outward_form_values['recipient'],
                                              key="recipient")
                    order_date = st.date_input("تاريخ الإذن", 
                                               value=st.session_state.outward_form_values['order_date'],
                                               key="order_date")
                notes = st.text_area("ملاحظات الإذن", value=st.session_state.outward_form_values['notes'], key="notes")
                col_submit, col_undo, col_redo = st.columns([2,1,1])
                with col_submit:
                    submitted = st.button("✅ تأكيد الصرف وإنشاء الإذن", type="primary")
                with col_undo:
                    undo = st.button("↩️ تراجع")
                with col_redo:
                    redo = st.button("↪️ تقديم")
                if submitted:
                    if not recipient:
                        st.error("يرجى إدخال اسم مسؤول الاستلام")
                    elif len(st.session_state.outward_items) == 0:
                        st.error("لم تتم إضافة أي صنف")
                    else:
                        valid = True
                        for item_entry in st.session_state.outward_items:
                            it = conn.execute("SELECT current_balance FROM items WHERE id=?", (item_entry['item_id'],)).fetchone()
                            if it['current_balance'] < item_entry['qty']:
                                st.error(f"الرصيد غير كافٍ للصنف {item_entry['item_name']}")
                                valid = False
                                break
                        if valid:
                            order_number = generate_outward_order_number()
                            hotel_id = current_hotel['id']
                            conn.execute("""INSERT INTO outward_orders (order_number, hotel_id, recipient_name, order_date, notes, created_by)
                                          VALUES (?,?,?,?,?,?)""",
                                         (order_number, hotel_id, recipient, order_date.isoformat(), notes, st.session_state.user['full_name']))
                            order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                            for item_entry in st.session_state.outward_items:
                                conn.execute("""INSERT INTO transactions (transaction_type, item_id, hotel_id, qty, unit_id, transaction_date, notes, created_by, order_id)
                                              VALUES (?,?,?,?,?,?,?,?,?)""",
                                             ('صادر', item_entry['item_id'], hotel_id, item_entry['qty'], item_entry['unit_id'],
                                              order_date.isoformat(), f"إذن رقم {order_number}", st.session_state.user['full_name'], order_id))
                                conn.execute("UPDATE items SET current_balance = current_balance - ?, last_updated=? WHERE id=?",
                                             (item_entry['qty'], date.today().isoformat(), item_entry['item_id']))
                            conn.commit()
                            sync_db_to_drive()
                            st.success(f"تم الحفظ بنجاح (تاريخ الإذن: {order_date.isoformat()})")
                            st.session_state.outward_form_defaults = {
                                'hotel': selected_hotel,
                                'recipient': recipient,
                                'order_date': order_date,
                                'notes': notes
                            }
                            st.session_state.outward_form_values = st.session_state.outward_form_defaults.copy()
                            st.session_state.outward_items = []
                            
                            # طباعة PDF
                            pdf_items = []
                            for item_entry in st.session_state.outward_items:
                                unit_symbol = unit_dict_out.get(item_entry['unit_id'], '')
                                pdf_items.append([item_entry['item_name'], str(item_entry['qty']), unit_symbol])
                            font_path = get_arabic_font()
                            pdf = FPDF()
                            pdf.add_page()
                            if font_path:
                                pdf.add_font("Amiri", fname=font_path)
                                pdf.set_font("Amiri", size=16)
                            else:
                                pdf.set_font("Helvetica", size=16)
                            pdf.cell(0, 10, shape_arabic("إذن صرف مخزني"), ln=True, align='C')
                            pdf.ln(5)
                            if font_path:
                                pdf.set_font("Amiri", size=12)
                            else:
                                pdf.set_font("Helvetica", size=12)
                            pdf.cell(0, 8, shape_arabic(f"رقم الإذن: {order_number}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"التاريخ: {order_date.isoformat()}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"الفندق: {selected_hotel}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"مسؤول الاستلام: {recipient}"), ln=True, align='R')
                            pdf.ln(5)
                            pdf.set_fill_color(0,168,107); pdf.set_text_color(255,255,255)
                            pdf.cell(30, 10, shape_arabic("الوحدة"), border=1, fill=True, align='C')
                            pdf.cell(30, 10, shape_arabic("الكمية"), border=1, fill=True, align='C')
                            pdf.cell(100, 10, shape_arabic("الصنف"), border=1, fill=True, align='C')
                            pdf.ln()
                            pdf.set_text_color(0,0,0)
                            if font_path:
                                pdf.set_font("Amiri", size=10)
                            else:
                                pdf.set_font("Helvetica", size=10)
                            for row in pdf_items:
                                pdf.cell(30, 8, shape_arabic(row[2]), border=1, align='C')
                                pdf.cell(30, 8, shape_arabic(row[1]), border=1, align='C')
                                pdf.cell(100, 8, shape_arabic(row[0]), border=1, align='C')
                                pdf.ln()
                            pdf.ln(10)
                            pdf.cell(0, 10, shape_arabic("توقيع مسؤول الاستلام: ________________"), ln=True, align='R')
                            pdf.cell(0, 10, shape_arabic("توقيع أمين المخزن: ________________"), ln=True, align='R')
                            pdf_bytes = bytes(pdf.output())
                            st.download_button("📄 تحميل إذن الصرف PDF", data=pdf_bytes,
                                               file_name=f"{order_number}.pdf", mime="application/pdf")
                            st.rerun()
                if undo:
                    st.session_state.outward_form_values = st.session_state.outward_form_defaults.copy()
                    st.rerun()
                if redo:
                    if 'outward_redo_values' in st.session_state:
                        st.session_state.outward_form_values = st.session_state.outward_redo_values.copy()
                        st.session_state.outward_redo_values = None
                        st.rerun()
                    else:
                        st.info("لا توجد تعديلات متراجع عنها لتقديمها")
        conn.close()
    with tab_out2:
        st.subheader("سجل أذون الصرف")
        conn = get_db()
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            start_date = st.date_input("من تاريخ", date.today()-timedelta(days=30), key="out_start")
        with col_f2:
            end_date = st.date_input("إلى تاريخ", date.today(), key="out_end")
        orders = conn.execute("""
            SELECT o.id, o.order_number, o.order_date, h.name as hotel_name, o.recipient_name, o.notes
            FROM outward_orders o
            JOIN hotels h ON o.hotel_id = h.id
            WHERE o.order_date BETWEEN ? AND ?
            ORDER BY o.id DESC
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()
        if orders:
            for order in orders:
                with st.expander(f"📋 إذن {order['order_number']} - {order['hotel_name']} - {order['order_date']}"):
                    st.write(f"**رقم الإذن:** {order['order_number']}")
                    st.write(f"**التاريخ:** {order['order_date']}")
                    st.write(f"**الفندق:** {order['hotel_name']}")
                    st.write(f"**مسؤول الاستلام:** {order['recipient_name']}")
                    st.write(f"**ملاحظات:** {order['notes'] or 'لا يوجد'}")
                    items_in_order = conn.execute("""
                        SELECT i.name, t.qty, u.unit_symbol
                        FROM transactions t
                        JOIN items i ON t.item_id = i.id
                        LEFT JOIN units u ON t.unit_id = u.id
                        WHERE t.order_id = ? AND t.transaction_type = 'صادر'
                    """, (order['id'],)).fetchall()
                    if items_in_order:
                        st.write("**الأصناف المصروفة:**")
                        df_items = pd.DataFrame(items_in_order, columns=['الصنف', 'الكمية', 'الوحدة'])
                        st.dataframe(df_items, use_container_width=True)
                    col_btn_print, col_btn_delete = st.columns(2)
                    with col_btn_print:
                        if st.button(f"🖨️ طباعة PDF {order['order_number']}", key=f"print_out_{order['id']}"):
                            font_path = get_arabic_font()
                            pdf = FPDF()
                            pdf.add_page()
                            if font_path:
                                pdf.add_font("Amiri", fname=font_path)
                                pdf.set_font("Amiri", size=16)
                            else:
                                pdf.set_font("Helvetica", size=16)
                            pdf.cell(0, 10, shape_arabic("إذن صرف مخزني"), ln=True, align='C')
                            pdf.ln(5)
                            if font_path:
                                pdf.set_font("Amiri", size=12)
                            else:
                                pdf.set_font("Helvetica", size=12)
                            pdf.cell(0, 8, shape_arabic(f"رقم الإذن: {order['order_number']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"التاريخ: {order['order_date']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"الفندق: {order['hotel_name']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"مسؤول الاستلام: {order['recipient_name']}"), ln=True, align='R')
                            pdf.ln(5)
                            pdf.set_fill_color(0,168,107); pdf.set_text_color(255,255,255)
                            pdf.cell(30, 10, shape_arabic("الوحدة"), border=1, fill=True, align='C')
                            pdf.cell(30, 10, shape_arabic("الكمية"), border=1, fill=True, align='C')
                            pdf.cell(100, 10, shape_arabic("الصنف"), border=1, fill=True, align='C')
                            pdf.ln()
                            pdf.set_text_color(0,0,0)
                            if font_path:
                                pdf.set_font("Amiri", size=10)
                            else:
                                pdf.set_font("Helvetica", size=10)
                            for item in items_in_order:
                                pdf.cell(30, 8, shape_arabic(item['unit_symbol']), border=1, align='C')
                                pdf.cell(30, 8, shape_arabic(str(item['qty'])), border=1, align='C')
                                pdf.cell(100, 8, shape_arabic(item['name']), border=1, align='C')
                                pdf.ln()
                            pdf.ln(10)
                            pdf.cell(0, 10, shape_arabic(f"توقيع مسؤول الاستلام ({order['recipient_name']}): ________________"), ln=True, align='R')
                            pdf.cell(0, 10, shape_arabic("توقيع أمين المخزن: ________________"), ln=True, align='R')
                            pdf_bytes = bytes(pdf.output())
                            st.download_button(f"📥 تحميل PDF {order['order_number']}", data=pdf_bytes,
                                               file_name=f"{order['order_number']}.pdf", mime="application/pdf")
                    with col_btn_delete:
                        if st.button(f"🗑️ حذف الإذن {order['order_number']}", key=f"del_out_{order['id']}"):
                            if st.session_state.get(f"confirm_del_out_{order['id']}", False):
                                success, msg = delete_outward_order(order['id'])
                                if success:
                                    st.success(msg)
                                    st.session_state[f"confirm_del_out_{order['id']}"] = False
                                    st.rerun()
                                else:
                                    st.error(msg)
                            else:
                                st.session_state[f"confirm_del_out_{order['id']}"] = True
                                st.warning("⚠️ اضغط مرة أخرى لتأكيد الحذف (ستُعاد الكميات إلى المخزون).")
                                st.rerun()
        else:
            st.info("لا توجد أذون صرف في هذه الفترة")
        conn.close()

elif choice == "📝 الجرد":
    st.header("الجرد الدوري")
    conn = get_db()
    items = conn.execute("SELECT id,name,current_balance,unit_id FROM items WHERE is_active=1").fetchall()
    if items:
        item = st.selectbox("الصنف", [i['name'] for i in items])
        it = [i for i in items if i['name']==item][0]
        st.info(f"الرصيد المسجل: {it['current_balance']}")
        actual = st.number_input("الكمية الفعلية", value=float(it['current_balance']), step=0.1, key="actual_qty")
        notes = st.text_input("ملاحظات")
        if st.button("حفظ الجرد"):
            diff = actual - it['current_balance']
            if diff != 0:
                conn.execute("INSERT INTO transactions (transaction_type,item_id,qty,unit_id,transaction_date,notes,created_by) VALUES (?,?,?,?,?,?,?)",
                             ('تسوية إضافة' if diff>0 else 'تسوية عجز', it['id'], abs(diff), it['unit_id'], date.today().isoformat(), notes, st.session_state.user['full_name']))
                st.success(f"تم إضافة حركة {'تسوية إضافة' if diff>0 else 'تسوية عجز'} بمقدار {abs(diff)}.")
            conn.execute("UPDATE items SET current_balance=?, last_updated=? WHERE id=?",(actual,date.today().isoformat(),it['id']))
            conn.execute("INSERT INTO inventory_counts (count_date,item_id,expected_qty,actual_qty,difference,notes,counted_by) VALUES (?,?,?,?,?,?,?)",
                         (date.today().isoformat(),it['id'],it['current_balance'],actual,diff,notes,st.session_state.user['full_name']))
            conn.commit()
            sync_db_to_drive()
            st.success("تم حفظ الجرد بنجاح")
            st.info("💡 حركات التسوية تظهر في التقارير عند اختيار 'الكل' أو 'تسوية إضافة/عجز'.")
            st.rerun()
    conn.close()

elif choice == "📈 التقارير":
    st.header("التقارير")
    conn = get_db()
    tab1, tab2 = st.tabs(["حركات", "أرصدة"])
    with tab1:
        st.subheader("تقرير الحركات")
        col1, col2, col3 = st.columns(3)
        with col1: d1 = st.date_input("من", date.today()-timedelta(days=30))
        with col2: d2 = st.date_input("إلى", date.today())
        with col3: typ = st.selectbox("النوع",["الكل","وارد","صادر","تسوية إضافة","تسوية عجز"])
        hotels = conn.execute("SELECT id, name FROM hotels").fetchall()
        hotel_names = ["الكل"] + [h['name'] for h in hotels]
        selected_hotel = st.selectbox("الفندق", hotel_names)
        items_filter = conn.execute("SELECT id, name FROM items WHERE is_active=1").fetchall()
        item_names = ["الكل"] + [it['name'] for it in items_filter]
        selected_item = st.selectbox("الصنف", item_names)
        with st.expander("🎨 تنسيق الجدول"):
            font_scale = st.slider("حجم الخط (%)", 50, 200, 100, step=10, key="report_font")
            color_option = st.selectbox("لون الجدول", ["افتراضي","أخضر","أزرق","رمادي","برتقالي"], key="report_color")
            color_map = {"افتراضي":"#f0f2f6","أخضر":"#e6ffe6","أزرق":"#e6f0ff","رمادي":"#f5f5f5","برتقالي":"#fff3e6"}
            bg_color = color_map.get(color_option, "#f0f2f6")
            all_columns = ['رقم الحركة','التاريخ','الصنف','النوع','الكمية','الوحدة','الفندق','المورد','سعر الوحدة','ملاحظات','مرفق']
            cols_order = column_selector("اختر الأعمدة ورتبها", all_columns, ['رقم الحركة','التاريخ','الصنف','النوع','الكمية','الوحدة','الفندق','المورد','ملاحظات','مرفق'], "trans_cols")
        query = """
            SELECT t.id, t.transaction_date, i.name AS item_name, t.transaction_type, t.qty, u.unit_symbol,
                   COALESCE(h.name, '-') AS hotel_name, t.supplier_name, t.unit_price, t.notes, t.attachment
            FROM transactions t
            JOIN items i ON t.item_id = i.id
            LEFT JOIN hotels h ON t.hotel_id = h.id
            LEFT JOIN units u ON t.unit_id = u.id
            WHERE t.transaction_date BETWEEN ? AND ?
        """
        params = [d1.isoformat(), d2.isoformat()]
        if typ != "الكل": query += " AND t.transaction_type = ?"; params.append(typ)
        if selected_hotel != "الكل":
            hotel_id = [h['id'] for h in hotels if h['name']==selected_hotel][0]
            query += " AND t.hotel_id = ?"; params.append(hotel_id)
        if selected_item != "الكل":
            item_id = [it['id'] for it in items_filter if it['name']==selected_item][0]
            query += " AND t.item_id = ?"; params.append(item_id)
        query += " ORDER BY t.id DESC"
        data = conn.execute(query, params).fetchall()
        if data:
            df = pd.DataFrame(data, columns=['رقم الحركة','التاريخ','الصنف','النوع','الكمية','الوحدة','الفندق','المورد','سعر الوحدة','ملاحظات','مرفق'])
            def attachment_link(fname):
                if fname and isinstance(fname, str) and fname.strip():
                    path = os.path.join(ATTACHMENTS_FOLDER, fname)
                    if os.path.exists(path):
                        with open(path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        return f'<a href="data:application/octet-stream;base64,{b64}" download="{fname}">📎 تحميل</a>'
                return ""
            if 'مرفق' in df.columns:
                df['مرفق'] = df['مرفق'].apply(attachment_link)
            ordered = [c for c in cols_order if c in df.columns]
            remaining = [c for c in df.columns if c not in ordered]
            df_display = df[ordered + remaining]
            st.dataframe(df_display, use_container_width=True)
            st.markdown(apply_table_styling(font_scale, bg_color), unsafe_allow_html=True)
            export_df = df.drop(columns=['مرفق'], errors='ignore')
            export_df = export_df[[c for c in ordered if c in export_df.columns]]
            export_buttons(export_df, "حركات", "تقرير الحركات")
            total_qty = df['الكمية'].sum()
            st.markdown(f"**📊 إجمالي الكمية خلال الفترة:** `{total_qty}`")
        else:
            st.info("لا توجد حركات")
    with tab2:
        st.subheader("تقرير الأرصدة")
        with st.expander("🎨 تنسيق جدول الأرصدة"):
            font_scale2 = st.slider("حجم الخط (%)", 50,200,100,10, key="bal_font")
            color_option2 = st.selectbox("لون الجدول", ["افتراضي","أخضر","أزرق","رمادي","برتقالي"], key="bal_color")
            color_map2 = {"افتراضي":"#f0f2f6","أخضر":"#e6ffe6","أزرق":"#e6f0ff","رمادي":"#f5f5f5","برتقالي":"#fff3e6"}
            bg2 = color_map2.get(color_option2,"#f0f2f6")
            bal_cols = column_selector("اختر الأعمدة ورتبها (للأرصدة)", ['كود','الصنف','الرصيد','الوحدة'], ['كود','الصنف','الرصيد','الوحدة'], "bal_cols")
        items = conn.execute("SELECT i.item_code, i.name, i.current_balance, u.unit_symbol FROM items i LEFT JOIN units u ON i.unit_id=u.id WHERE i.is_active=1").fetchall()
        if items:
            df = pd.DataFrame(items, columns=['كود','الصنف','الرصيد','الوحدة'])
            ordered = [c for c in bal_cols if c in df.columns]
            remaining = [c for c in df.columns if c not in ordered]
            df_disp = df[ordered + remaining]
            st.dataframe(df_disp, use_container_width=True)
            st.markdown(apply_table_styling(font_scale2, bg2), unsafe_allow_html=True)
            report_title = f"تقرير الأرصدة - {date.today().strftime('%Y-%m-%d')}"
            export_buttons(df_disp, "ارصدة", report_title)
        else:
            st.info("لا توجد أصناف نشطة")
    conn.close()

elif choice == "🗑️ إدارة الحركات (حذف)":
    if not has_role('super_admin'): st.error("فقط المدير العام"); st.stop()
    st.header("حذف حركة")
    conn = get_db()
    trans = conn.execute("""SELECT t.id, t.transaction_type, i.name, COALESCE(h.name,'-'), t.qty, t.transaction_date, t.notes
                           FROM transactions t JOIN items i ON t.item_id=i.id LEFT JOIN hotels h ON t.hotel_id=h.id
                           ORDER BY t.id DESC LIMIT 50""").fetchall()
    if trans:
        df = pd.DataFrame(trans, columns=['رقم','النوع','الصنف','الفندق','الكمية','التاريخ','ملاحظات'])
        st.dataframe(df)
        trans_id = st.number_input("أدخل رقم الحركة للحذف", min_value=1, step=1)
        if st.button("حذف الحركة واسترجاع تأثيرها"):
            ok, msg = delete_transaction(trans_id)
            if ok: st.success(msg); st.rerun()
            else: st.error(msg)
    else:
        st.info("لا توجد حركات")
    conn.close()

elif choice == "💾 النسخ الاحتياطي":
    st.header("النسخ الاحتياطي")
    notes = st.text_input("ملاحظات")
    if st.button("إنشاء نسخة"):
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"backup_{ts}.db"
            shutil.copy2(DB_NAME, backup_file)
            with open(backup_file, "rb") as f:
                st.download_button("تحميل النسخة", f, file_name=backup_file)
            st.success(f"تم إنشاء نسخة محلية: {backup_file}")
            os.remove(backup_file)  # حذف الملف المؤقت بعد التحميل
        except Exception as e:
            st.error(f"فشل النسخ: {str(e)}")
    st.subheader("مزامنة مع Google Drive")
    if GDRIVE_ENABLED:
        if st.button("📤 رفع قاعدة البيانات الآن"):
            if upload_db_to_drive():
                st.success("تم الرفع بنجاح")
        if st.button("📥 تنزيل قاعدة البيانات"):
            if download_db_from_drive():
                st.success("تم التنزيل والاستعادة")
                st.rerun()
    else:
        st.info("لم يتم تفعيل المزامنة مع Google Drive. أضف الإعدادات في ملف secrets.toml")

elif choice == "👥 المستخدمين":
    if not has_role('super_admin'): st.error("غير مصرح"); st.stop()
    st.header("المستخدمين")
    conn = get_db()
    users = conn.execute("SELECT username, role, full_name FROM users").fetchall()
    if users:
        df = pd.DataFrame(users, columns=['مستخدم','دور','اسم'])
        st.dataframe(df, use_container_width=True)
    with st.form("add_user"):
        un = st.text_input("اسم المستخدم")
        pw = st.text_input("كلمة المرور", type="password")
        fn = st.text_input("الاسم الكامل")
        role = st.selectbox("الدور", ['super_admin','purchasing','disbursement','supervisor'])
        if st.form_submit_button("إضافة"):
            try:
                conn.execute("INSERT INTO users (username,password,role,full_name) VALUES (?,?,?,?)",(un, hash_password(pw), role, fn))
                conn.commit()
                sync_db_to_drive()
                st.success("تم الحفظ بنجاح")
                st.rerun()
            except: st.error("مستخدم موجود")
    conn.close()