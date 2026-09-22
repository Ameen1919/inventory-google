import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
import io
import os
import urllib.request
from fpdf import FPDF
import shutil
import zipfile
import json
import hashlib
import re
import arabic_reshaper
from bidi.algorithm import get_display
import base64
import requests

try:
    import libsql
    LIBSQL_AVAILABLE = True
except ImportError:
    LIBSQL_AVAILABLE = False

# ======================== إعدادات الصفحة ========================
st.set_page_config(page_title="مخزن النظافة", layout="wide", initial_sidebar_state="collapsed")

APP_CONFIG_FILE = 'app_config.json'

def load_app_config():
    config = {
        'font_size': 100,
        'theme_color': "#00a86b",
        'logo_path': None,
        'store_name': "مخزن النظافة",
        'telegram_bot_token': "",
        'telegram_chat_id': "",
        'telegram_file_id': ""
    }
    if os.path.exists(APP_CONFIG_FILE):
        try:
            with open(APP_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
        except Exception:
            pass
    try:
        if 'telegram' in st.secrets:
            config['telegram_bot_token'] = st.secrets['telegram'].get('bot_token', config['telegram_bot_token'])
            config['telegram_chat_id'] = st.secrets['telegram'].get('chat_id', config['telegram_chat_id'])
            config['telegram_file_id'] = st.secrets['telegram'].get('file_id', config['telegram_file_id'])
    except Exception:
        pass
    return config

def save_app_config(config):
    try:
        with open(APP_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

saved_config = load_app_config()

if 'font_size' not in st.session_state:
    st.session_state.font_size = saved_config.get('font_size', 100)
if 'theme_color' not in st.session_state:
    st.session_state.theme_color = saved_config.get('theme_color', "#00a86b")
if 'logo_path' not in st.session_state:
    st.session_state.logo_path = saved_config.get('logo_path', None)
if 'store_name' not in st.session_state:
    st.session_state.store_name = saved_config.get('store_name', "مخزن النظافة")
if 'telegram_bot_token' not in st.session_state:
    st.session_state.telegram_bot_token = saved_config.get('telegram_bot_token', "")
if 'telegram_chat_id' not in st.session_state:
    st.session_state.telegram_chat_id = saved_config.get('telegram_chat_id', "")
if 'telegram_file_id' not in st.session_state:
    st.session_state.telegram_file_id = saved_config.get('telegram_file_id', "")
if 'logo_base64' not in st.session_state:
    st.session_state.logo_base64 = ""

def apply_theme():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;900&display=swap');
    
    *{{font-family:'Tajawal',sans-serif !important}}
    
    html, body, [class*="css"], .stApp, .main, .block-container {{
        direction: rtl !important;
        text-align: right !important;
        font-size: {st.session_state.font_size}% !important;
    }}
    
    h1, h2, h3, h4, h5, h6,
    .stMarkdown, .stMarkdown p, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 {{
        text-align: right !important;
        direction: rtl !important;
    }}
    
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        direction: rtl !important;
        text-align: center !important;
        width: 100% !important;
    }}
    
    .stTextInput input, .stNumberInput input, .stTextArea textarea {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    .stSelectbox > div > div,
    .stMultiSelect > div > div {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    .stTabs [data-baseweb="tab-list"] {{
        direction: rtl !important;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        direction: rtl !important;
    }}
    
    [data-testid="stDataFrame"],
    [data-testid="stTable"] {{
        direction: rtl !important;
    }}
    
    [data-testid="stDataFrame"] th,
    [data-testid="stTable"] th,
    [data-testid="stDataFrame"] td,
    [data-testid="stTable"] td {{
        text-align: right !important;
        direction: rtl !important;
    }}
    
    [data-testid="stMetric"] {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    [data-testid="stMetric"] > div {{
        text-align: right !important;
    }}
    
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"] {{
        text-align: right !important;
        direction: rtl !important;
    }}
    
    .stAlert {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    .streamlit-expanderHeader, [data-testid="stExpander"] summary {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    @media (max-width: 768px) {{
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] {{
            display: none !important;
        }}
    }}
    
    .stApp {{
        background-color: {st.session_state.theme_color} !important;
        background-image: linear-gradient(135deg, {st.session_state.theme_color} 0%, #ffffff 100%) !important;
    }}
    
    .stock-critical{{background-color:#ff4444;color:white;padding:5px 10px;border-radius:5px}}
    .stock-warning{{background-color:#ffbb33;color:black;padding:5px 10px;border-radius:5px}}
    .stock-good{{background-color:#00C851;color:white;padding:5px 10px;border-radius:5px}}
    </style>""", unsafe_allow_html=True)

apply_theme()

DB_NAME = 'cleaning_inventory.db'
BACKUP_FOLDER = 'backups'
ATTACHMENTS_FOLDER = 'attachments'
CONFIG_FILE = 'backup_config.json'
LOGO_FILE = 'logo.png'

if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER)
if not os.path.exists(ATTACHMENTS_FOLDER):
    os.makedirs(ATTACHMENTS_FOLDER)

# ======================== أغلفة Turso ========================
class DictRow:
    def __init__(self, keys, values):
        self._keys = list(keys)
        self._values = tuple(values)
        self._dict = dict(zip(self._keys, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._dict[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return self._keys

    def values(self):
        return self._values

    def items(self):
        return list(self._dict.items())

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def __contains__(self, item):
        if isinstance(item, str):
            return item in self._dict
        return item in self._values

    def __repr__(self):
        return f"DictRow({self._dict})"


class WrappedCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def description(self):
        return self._cursor.description

    @property
    def lastrowid(self):
        return getattr(self._cursor, 'lastrowid', None)

    def _make_row(self, raw_row):
        if raw_row is None:
            return None
        desc = self._cursor.description
        if not desc:
            return raw_row
        cols = [d[0] for d in desc]
        return DictRow(cols, raw_row)

    def execute(self, *args, **kwargs):
        self._cursor.execute(*args, **kwargs)
        return self

    def executemany(self, *args, **kwargs):
        self._cursor.executemany(*args, **kwargs)
        return self

    def fetchone(self):
        return self._make_row(self._cursor.fetchone())

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        return [self._make_row(r) for r in rows]

    def __iter__(self):
        return iter(self.fetchall())


class WrappedConnection:
    def __init__(self, conn, url=None, token=None):
        self._conn = conn
        self._url = url
        self._token = token
        self._lock = False

    def _reconnect(self):
        if self._lock or not self._url or not self._token:
            return False
        self._lock = True
        try:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = libsql.connect(database=self._url, auth_token=self._token)
            return True
        except Exception:
            return False
        finally:
            self._lock = False

    def execute(self, *args, **kwargs):
        try:
            cursor = self._conn.execute(*args, **kwargs)
            return WrappedCursor(cursor)
        except Exception as e:
            if self._reconnect():
                cursor = self._conn.execute(*args, **kwargs)
                return WrappedCursor(cursor)
            raise e

    def cursor(self):
        return WrappedCursor(self._conn.cursor())

    def commit(self):
        try:
            self._conn.commit()
        except Exception:
            if self._reconnect():
                try:
                    self._conn.commit()
                except Exception:
                    pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()


class SQLiteWrapper:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        try:
            self._conn.commit()
        except Exception:
            pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()


# ======================== دوال مساعدة ========================
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()


def get_db():
    cached = st.session_state.get('_db_conn')
    if cached is not None:
        return cached

    url = ""
    token = ""
    try:
        url = st.secrets.get("TURSO_URL", "")
        token = st.secrets.get("TURSO_TOKEN", "")
    except Exception:
        url = saved_config.get("turso_url", "")
        token = saved_config.get("turso_token", "")

    if LIBSQL_AVAILABLE and url and token:
        try:
            raw = libsql.connect(database=url, auth_token=token)
            conn = WrappedConnection(raw, url=url, token=token)
            st.session_state._db_conn = conn
            return conn
        except Exception as e:
            st.warning(f"فشل الاتصال بـ Turso: {e}")

    raw = sqlite3.connect(DB_NAME, check_same_thread=False)
    raw.row_factory = sqlite3.Row
    conn = SQLiteWrapper(raw)
    st.session_state._db_conn = conn
    return conn


@st.cache_data(ttl=60, show_spinner=False)
def _cache_items_for_outward():
    conn = get_db()
    rows = conn.execute("SELECT id, name, current_balance, unit_id FROM items WHERE is_active=1").fetchall()
    return [(r['id'], r['name'], r['current_balance'], r['unit_id']) for r in rows]


@st.cache_data(ttl=60, show_spinner=False)
def _cache_hotels():
    conn = get_db()
    rows = conn.execute("SELECT id, name, contact_person, phone FROM hotels").fetchall()
    return [(r['id'], r['name'], r['contact_person'], r['phone']) for r in rows]


@st.cache_data(ttl=60, show_spinner=False)
def _cache_units_map():
    conn = get_db()
    rows = conn.execute("SELECT id, unit_symbol FROM units").fetchall()
    return {r['id']: r['unit_symbol'] for r in rows}


@st.cache_resource
def _ensure_db_initialized():
    _url = ""
    _token = ""
    try:
        _url = st.secrets.get("TURSO_URL", "")
        _token = st.secrets.get("TURSO_TOKEN", "")
    except Exception:
        pass

    if LIBSQL_AVAILABLE and _url and _token:
        try:
            raw = libsql.connect(database=_url, auth_token=_token)
            _conn = WrappedConnection(raw, url=_url, token=_token)
        except Exception:
            raw = sqlite3.connect(DB_NAME)
            raw.row_factory = sqlite3.Row
            _conn = raw
    else:
        raw = sqlite3.connect(DB_NAME)
        raw.row_factory = sqlite3.Row
        _conn = raw

    _c = _conn.cursor()
    _c.execute('''CREATE TABLE IF NOT EXISTS units (id INTEGER PRIMARY KEY AUTOINCREMENT, unit_name TEXT UNIQUE, unit_symbol TEXT)''')
    _c.execute('''CREATE TABLE IF NOT EXISTS suppliers (id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_name TEXT UNIQUE, contact_info TEXT, notes TEXT, attachments TEXT)''')
    try:
        _c.execute("ALTER TABLE suppliers ADD COLUMN attachments TEXT")
    except:
        pass
    _c.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT UNIQUE, name TEXT NOT NULL UNIQUE, unit_id INTEGER, min_qty REAL DEFAULT 0, max_qty REAL DEFAULT 100, current_balance REAL DEFAULT 0, primary_supplier_id INTEGER, shelf_life_days INTEGER DEFAULT 365, notes TEXT, is_active BOOLEAN DEFAULT 1, created_date TEXT, last_updated TEXT)''')
    _c.execute('''CREATE TABLE IF NOT EXISTS hotels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, contact_person TEXT, phone TEXT, notes TEXT)''')
    _c.execute('''CREATE TABLE IF NOT EXISTS outward_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_number TEXT UNIQUE, hotel_id INTEGER, recipient_name TEXT, order_date TEXT, notes TEXT, created_by TEXT)''')
    _c.execute('''CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_type TEXT, item_id INTEGER, hotel_id INTEGER, qty REAL, unit_id INTEGER, batch_number TEXT, expiry_date TEXT, transaction_date TEXT, notes TEXT, created_by TEXT DEFAULT 'أمين المخزن', attachment TEXT, order_id INTEGER, supplier_name TEXT, unit_price REAL DEFAULT 0)''')
    _c.execute('''CREATE TABLE IF NOT EXISTS inventory_counts (id INTEGER PRIMARY KEY AUTOINCREMENT, count_date TEXT, item_id INTEGER, expected_qty REAL, actual_qty REAL, difference REAL, notes TEXT, counted_by TEXT)''')
    _c.execute('''CREATE TABLE IF NOT EXISTS expiry_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, batch_number TEXT, expiry_date TEXT, qty_remaining REAL, is_consumed BOOLEAN DEFAULT 0)''')
    _c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT, is_active BOOLEAN DEFAULT 1)''')
    _c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    for u_name, u_sym in [('قطعة','قطعة'),('لتر','لتر'),('كيلو','كجم'),('متر','متر'),('كرتونة','كرتونة'),('رول','رول'),('زجاجة','زجاجة'),('علبة','علبة'),('كيس','كيس')]:
        _c.execute("INSERT OR IGNORE INTO units (unit_name, unit_symbol) VALUES (?,?)", (u_name, u_sym))
    default_users = [
        ('admin', hash_password('admin123'), 'super_admin', 'المدير العام'),
        ('مشتريات', hash_password('buy123'), 'purchasing', 'مسؤول المشتريات'),
        ('صرف', hash_password('out123'), 'disbursement', 'مسؤول الصرف'),
        ('مشرف1', hash_password('sup123'), 'supervisor', 'مشرف أول'),
        ('مشرف2', hash_password('sup456'), 'supervisor', 'مشرف ثاني')
    ]
    for uname, pwd, role, fname in default_users:
        _c.execute("INSERT OR IGNORE INTO users (username,password,role,full_name) VALUES (?,?,?,?)", (uname, pwd, role, fname))
    _conn.commit()
    return True


def init_db():
    try:
        _ensure_db_initialized()
    except Exception:
        pass


def login(username, password):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=? AND password=? AND is_active=1", (username, hash_password(password))).fetchone()
    if user:
        st.session_state.user = dict(zip(user.keys(), user.values()))
        st.session_state.logged_in = True
        return True
    return False


def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()


def check_perm(role=None):
    if not st.session_state.get('logged_in'):
        return False
    if st.session_state.user['role'] == 'super_admin':
        return True
    if role and st.session_state.user['role'] == role:
        return True
    return False


def has_role(role):
    return st.session_state.get('user', {}).get('role') == role


# ======================== الإعدادات عبر Turso ========================
def get_setting(key, default=None):
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row:
            return row['value']
    except Exception:
        pass
    return default


def set_setting(key, value):
    try:
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value) if value is not None else ""))
        conn.commit()
        return True
    except Exception:
        return False


def _load_settings_from_db():
    if st.session_state.get('_settings_loaded'):
        return
    try:
        conn = get_db()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        s = {}
        for r in rows:
            s[r['key']] = r['value']
        if 'font_size' in s:
            try:
                st.session_state.font_size = int(s['font_size'])
            except Exception:
                pass
        if 'theme_color' in s:
            st.session_state.theme_color = s['theme_color']
        if 'store_name' in s:
            st.session_state.store_name = s['store_name']
        if 'logo_base64' in s:
            st.session_state.logo_base64 = s['logo_base64']
        if 'telegram_file_id' in s:
            st.session_state.telegram_file_id = s['telegram_file_id']
    except Exception:
        pass
    st.session_state._settings_loaded = True


# ======================== تنبيهات المخزون ========================
def send_stock_alert(item_name, current_balance, min_qty, unit_symbol):
    token = st.session_state.get('telegram_bot_token', '')
    chat_id = st.session_state.get('telegram_chat_id', '')
    if not token or not chat_id:
        return False
    try:
        msg = f"⚠️ تنبيه نقص مخزون\n\nالصنف: {item_name}\nالرصيد الحالي: {current_balance} {unit_symbol}\nالحد الأدنى: {min_qty}"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={'chat_id': chat_id, 'text': msg}, timeout=10)
        return True
    except Exception:
        return False


def check_and_alert_item(item_id):
    try:
        conn = get_db()
        row = conn.execute("""
            SELECT i.name, i.current_balance, i.min_qty, u.unit_symbol
            FROM items i LEFT JOIN units u ON i.unit_id = u.id
            WHERE i.id = ?
        """, (item_id,)).fetchone()
        if not row:
            return
        if row['current_balance'] > row['min_qty']:
            return
        today = date.today().isoformat()
        alert_key = f"alert_{item_id}_{today}"
        existing = conn.execute("SELECT value FROM settings WHERE key=?", (alert_key,)).fetchone()
        if existing:
            return
        send_stock_alert(row['name'], row['current_balance'], row['min_qty'], row['unit_symbol'] or '')
        set_setting(alert_key, "sent")
    except Exception:
        pass


# ======================== PDF عربي ========================
def get_arabic_font():
    path = "Amiri-Regular.ttf"
    if not os.path.exists(path):
        try:
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf", path)
        except:
            pass
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
    pdf.cell(0, 10, shape_arabic(title), ln=True, align='C')
    pdf.ln(10)
    if df.empty:
        pdf.cell(0, 10, shape_arabic("لا توجد بيانات"), ln=True)
        return bytes(pdf.output())
    if cols_map:
        df = df.rename(columns=cols_map)
    cols = list(df.columns)
    widths = []
    for col in cols:
        m = pdf.get_string_width(shape_arabic(str(col)))
        for _, r in df.iterrows():
            v = str(r[col]) if pd.notnull(r[col]) else '-'
            m = max(m, pdf.get_string_width(shape_arabic(v)))
        widths.append(m + 10)
    total = sum(widths)
    if total > pdf.w - 20:
        scale = (pdf.w - 20) / total
        widths = [w * scale for w in widths]
    pdf.set_fill_color(0, 168, 107)
    pdf.set_text_color(255, 255, 255)
    for i, col in enumerate(cols):
        pdf.cell(widths[i], 10, shape_arabic(str(col)), border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Amiri", size=10) if font_path else pdf.set_font("Helvetica", size=10)
    for _, row in df.iterrows():
        for i, col in enumerate(cols):
            v = str(row[col]) if pd.notnull(row[col]) else '-'
            pdf.cell(widths[i], 8, shape_arabic(v), border=1, align='C')
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Amiri", size=10) if font_path else pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 8, shape_arabic(f"تاريخ الطباعة: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), ln=True, align='L')
    return bytes(pdf.output())


def export_buttons(df, prefix, pdf_title=None):
    c1, c2 = st.columns(2)
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
    last = conn.execute("SELECT order_number FROM outward_orders WHERE order_number LIKE ? ORDER BY id DESC LIMIT 1", (f"OUT-{today_str}-%",)).fetchone()
    if last:
        last_num = int(last['order_number'].split('-')[-1]) + 1
    else:
        last_num = 1
    return f"OUT-{today_str}-{last_num:04d}"


# ======================== المرفقات عبر تيليجرام ========================
def save_attachment_to_telegram(uploaded_file, transaction_id):
    token = st.session_state.telegram_bot_token
    chat_id = st.session_state.telegram_chat_id
    if not token or not chat_id:
        st.error("بيانات تيليجرام غير مكتملة، لا يمكن حفظ المرفق.")
        return None
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        files = {'document': (uploaded_file.name, uploaded_file.getbuffer(), uploaded_file.type)}
        data = {'chat_id': chat_id, 'caption': f"مرفق #{transaction_id}"}
        resp = requests.post(url, files=files, data=data, timeout=60)
        if resp.status_code == 200:
            result = resp.json().get('result', {})
            if 'document' in result:
                return result['document'].get('file_id')
            elif 'photo' in result:
                photos = result.get('photo', [])
                if photos:
                    return photos[-1].get('file_id')
            st.error("لم يتم استلام file_id من تيليجرام.")
            return None
        else:
            st.error(f"فشل رفع الملف إلى تيليجرام: {resp.text}")
            return None
    except Exception as e:
        st.error(f"خطأ أثناء رفع المرفق: {str(e)}")
        return None


def get_attachment_url(file_id):
    token = st.session_state.telegram_bot_token
    if not token or not file_id:
        return None
    try:
        info_url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
        resp = requests.get(info_url, timeout=30)
        if resp.status_code == 200:
            file_path = resp.json().get('result', {}).get('file_path')
            if file_path:
                return f"https://api.telegram.org/file/bot{token}/{file_path}"
        return None
    except Exception:
        return None


def display_attachment(file_id, caption="المرفق"):
    if not file_id:
        return
    if not file_id.startswith("AgAC") and not file_id.startswith("BQAC") and not file_id.startswith("BAAC"):
        local_path = os.path.join(ATTACHMENTS_FOLDER, file_id)
        if os.path.exists(local_path):
            ext = os.path.splitext(file_id)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                st.image(local_path, caption=caption, width=300)
            else:
                with open(local_path, "rb") as f:
                    st.download_button(f"📎 تحميل {caption}", f, file_name=file_id)
        else:
            st.info(f"المرفق القديم '{file_id}' غير متوفر (كان محفوظاً محلياً).")
        return

    file_url = get_attachment_url(file_id)
    if not file_url:
        st.warning("تعذر جلب المرفق من تيليجرام.")
        return
    lower_url = file_url.lower()
    if any(ext in lower_url for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
        st.image(file_url, caption=caption, width=300)
    else:
        st.markdown(f"[📎 تحميل {caption}]({file_url})", unsafe_allow_html=True)


# ======================== مرفقات الموردين ========================
def get_supplier_attachments(supplier_id):
    conn = get_db()
    row = conn.execute("SELECT attachments FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
    if row and row['attachments']:
        try:
            return json.loads(row['attachments'])
        except Exception:
            return []
    return []


def add_supplier_attachment(supplier_id, file_id, file_name):
    atts = get_supplier_attachments(supplier_id)
    atts.append({"file_id": file_id, "name": file_name})
    conn = get_db()
    conn.execute("UPDATE suppliers SET attachments=? WHERE id=?", (json.dumps(atts, ensure_ascii=False), supplier_id))
    conn.commit()


def delete_supplier_attachment(supplier_id, index):
    atts = get_supplier_attachments(supplier_id)
    if 0 <= index < len(atts):
        atts.pop(index)
        conn = get_db()
        conn.execute("UPDATE suppliers SET attachments=? WHERE id=?", (json.dumps(atts, ensure_ascii=False), supplier_id))
        conn.commit()


# ======================== النسخ الاحتياطي ========================
def load_backup_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'backup_history': [], 'last_backup_date': None, 'max_backups': 10}


def save_backup_config(cfg):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


ALL_TABLES = ['units', 'suppliers', 'items', 'hotels', 'outward_orders', 'transactions', 'inventory_counts', 'expiry_alerts', 'users', 'settings']


def create_backup(typ="يدوي", notes=""):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"backup_{ts}"
        path = os.path.join(BACKUP_FOLDER, name)
        os.makedirs(path, exist_ok=True)

        conn = get_db()
        with pd.ExcelWriter(os.path.join(path, 'preview.xlsx'), engine='xlsxwriter') as w:
            for t in ALL_TABLES:
                try:
                    rows = conn.execute(f"SELECT * FROM {t}").fetchall()
                    if rows:
                        df = pd.DataFrame([list(r) for r in rows])
                        df.to_excel(w, sheet_name=t, index=False)
                    else:
                        pd.DataFrame().to_excel(w, sheet_name=t, index=False)
                except Exception:
                    pass

        with open(os.path.join(path, 'data.sql'), 'w', encoding='utf-8') as f:
            for t in ALL_TABLES:
                try:
                    rows = conn.execute(f"SELECT * FROM {t}").fetchall()
                    for r in rows:
                        d = dict(zip(r.keys(), r.values()))
                        cols = ', '.join(d.keys())
                        vals = ', '.join(["NULL" if v is None else "'" + str(v).replace("'", "''") + "'" for v in d.values()])
                        f.write(f"INSERT INTO {t} ({cols}) VALUES ({vals});\n")
                except Exception:
                    pass

        with open(os.path.join(path, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump({'date': ts, 'type': typ, 'notes': notes, 'tables': ALL_TABLES}, f, ensure_ascii=False)

        zipf = os.path.join(BACKUP_FOLDER, f"{name}.zip")
        with zipfile.ZipFile(zipf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(path):
                for file in files:
                    zf.write(os.path.join(root, file), file)
        shutil.rmtree(path)

        cfg = load_backup_config()
        cfg['last_backup_date'] = datetime.now().isoformat()
        cfg['backup_history'].append({'filename': f"{name}.zip", 'date': ts, 'type': typ, 'notes': notes, 'size': os.path.getsize(zipf)})
        if len(cfg['backup_history']) > cfg['max_backups']:
            for old in sorted(cfg['backup_history'], key=lambda x: x['date'])[:-cfg['max_backups']]:
                old_file = os.path.join(BACKUP_FOLDER, old['filename'])
                if os.path.exists(old_file):
                    os.remove(old_file)
                cfg['backup_history'].remove(old)
        save_backup_config(cfg)
        return True, zipf, f"تم إنشاء النسخة {name}.zip"
    except Exception as e:
        return False, None, str(e)


def restore_backup(zip_path):
    try:
        tmp = "tmp_res"
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        os.makedirs(tmp)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmp)

        conn = get_db()

        db_src = os.path.join(tmp, DB_NAME)
        if os.path.exists(db_src):
            src = sqlite3.connect(db_src)
            src.row_factory = sqlite3.Row
            for t in reversed(ALL_TABLES):
                try:
                    conn.execute(f"DELETE FROM {t}")
                except Exception:
                    pass
            for t in ALL_TABLES:
                try:
                    rows = src.execute(f"SELECT * FROM {t}").fetchall()
                    for r in rows:
                        d = dict(r)
                        cols = ', '.join(d.keys())
                        placeholders = ', '.join(['?'] * len(d))
                        vals = list(d.values())
                        try:
                            conn.execute(f"INSERT INTO {t} ({cols}) VALUES ({placeholders})", vals)
                        except Exception:
                            pass
                except Exception:
                    pass
            src.close()
        else:
            excel_path = os.path.join(tmp, 'preview.xlsx')
            if os.path.exists(excel_path):
                xl = pd.ExcelFile(excel_path)
                for t in reversed(ALL_TABLES):
                    try:
                        conn.execute(f"DELETE FROM {t}")
                    except Exception:
                        pass
                for t in ALL_TABLES:
                    if t in xl.sheet_names:
                        try:
                            df = pd.read_excel(xl, sheet_name=t)
                            if df.empty:
                                continue
                            df = df.where(pd.notnull(df), None)
                            cols = ', '.join(df.columns)
                            placeholders = ', '.join(['?'] * len(df.columns))
                            for _, row in df.iterrows():
                                vals = [None if (isinstance(v, float) and pd.isna(v)) else v for v in row.values]
                                try:
                                    conn.execute(f"INSERT INTO {t} ({cols}) VALUES ({placeholders})", vals)
                                except Exception:
                                    pass
                        except Exception:
                            pass
            else:
                shutil.rmtree(tmp)
                return False, "الملف المضغوط لا يحتوي على بيانات صالحة."

        conn.commit()
        shutil.rmtree(tmp)
        recalculate_all_balances()
        return True, "تمت الاستعادة بنجاح"
    except Exception as e:
        return False, str(e)


def delete_transaction(trans_id):
    conn = get_db()
    trans = conn.execute("SELECT * FROM transactions WHERE id=?", (trans_id,)).fetchone()
    if not trans:
        return False, "الحركة غير موجودة"
    item_id = trans['item_id']
    qty = trans['qty']
    typ = trans['transaction_type']
    if typ in ('وارد', 'تسوية إضافة'):
        conn.execute("UPDATE items SET current_balance=current_balance-? WHERE id=?", (qty, item_id))
    elif typ in ('صادر', 'تسوية عجز'):
        conn.execute("UPDATE items SET current_balance=current_balance+? WHERE id=?", (qty, item_id))
    conn.execute("DELETE FROM transactions WHERE id=?", (trans_id,))
    conn.commit()
    return True, "تم حذف الحركة بنجاح"


def delete_outward_order(order_id):
    conn = get_db()
    items = conn.execute("SELECT item_id,qty FROM transactions WHERE order_id=?", (order_id,)).fetchall()
    for it in items:
        conn.execute("UPDATE items SET current_balance=current_balance+? WHERE id=?", (it['qty'], it['item_id']))
    conn.execute("DELETE FROM transactions WHERE order_id=?", (order_id,))
    conn.execute("DELETE FROM outward_orders WHERE id=?", (order_id,))
    conn.commit()
    return True, "تم حذف الإذن وإعادة الكميات"


def recalculate_all_balances():
    conn = get_db()
    items = conn.execute("SELECT id FROM items").fetchall()
    for item in items:
        tin = conn.execute("SELECT COALESCE(SUM(qty),0) FROM transactions WHERE item_id=? AND transaction_type IN ('وارد','تسوية إضافة')", (item['id'],)).fetchone()[0]
        tout = conn.execute("SELECT COALESCE(SUM(qty),0) FROM transactions WHERE item_id=? AND transaction_type IN ('صادر','تسوية عجز')", (item['id'],)).fetchone()[0]
        conn.execute("UPDATE items SET current_balance=? WHERE id=?", (tin - tout, item['id']))
    conn.commit()


# ======================== تيليجرام ========================
def telegram_send_document(file_path, caption=""):
    token = st.session_state.telegram_bot_token
    chat_id = st.session_state.telegram_chat_id
    if not token or not chat_id:
        return False, "يرجى إدخال بيانات تيليجرام أولاً"
    ok, backup_path, msg = create_backup("تيليجرام", caption)
    if not ok:
        return False, msg
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        with open(backup_path, 'rb') as f:
            resp = requests.post(url, files={'document': f}, data={'chat_id': chat_id, 'caption': caption}, timeout=120)
            if resp.status_code == 200:
                file_id = resp.json().get('result', {}).get('document', {}).get('file_id')
                if file_id:
                    st.session_state.telegram_file_id = file_id
                    set_setting('telegram_file_id', file_id)
                return True, "تم إرسال النسخة الاحتياطية إلى تيليجرام"
            else:
                return False, f"فشل: {resp.text}"
    except Exception as e:
        return False, str(e)


def telegram_get_latest_db():
    token = st.session_state.telegram_bot_token
    chat_id = st.session_state.telegram_chat_id
    file_id = st.session_state.telegram_file_id
    if not token or not chat_id:
        return False, "يرجى إدخال بيانات تيليجرام أولاً"
    if not file_id:
        return False, "لا يوجد ملف محفوظ، ارفع أولاً"
    try:
        info_url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
        resp = requests.get(info_url, timeout=30).json()
        if not resp.get('ok'):
            return False, "فشل جلب معلومات الملف"
        file_path = resp['result']['file_path']
        download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        db_resp = requests.get(download_url, timeout=120)
        if db_resp.status_code == 200:
            temp_zip = "temp_telegram_backup.zip"
            with open(temp_zip, 'wb') as f:
                f.write(db_resp.content)
            success, msg = restore_backup(temp_zip)
            try:
                os.remove(temp_zip)
            except:
                pass
            if success:
                return True, "تمت الاستعادة من تيليجرام بنجاح"
            else:
                return False, msg
        else:
            return False, "فشل التنزيل"
    except Exception as e:
        return False, str(e)


# ======================== دوال مساعدة للجداول ========================
def apply_table_styling(font_scale, bg_color):
    return f"""<style>
        div[data-testid="stDataFrame"] div[data-testid="stTable"] {{ font-size: {font_scale}% !important; }}
        div[data-testid="stDataFrame"] table {{ background-color: {bg_color} !important; }}
    </style>"""


def column_selector(label, all_columns, default_order, key):
    if key not in st.session_state:
        st.session_state[key] = default_order
    new_order = st.multiselect(label, options=all_columns, default=st.session_state[key], key=key + "_multiselect")
    if new_order != st.session_state[key]:
        st.session_state[key] = new_order
        st.rerun()
    return st.session_state[key]


# ======================== بدء التشغيل ========================
init_db()
_load_settings_from_db()

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
            else:
                st.error("خطأ")
    st.stop()

# ======================== الواجهة الرئيسية ========================
st.title(f"🧹 {st.session_state.store_name}")
logo_b64 = st.session_state.get('logo_base64', '')
if logo_b64:
    try:
        st.markdown(f'<img src="data:image/png;base64,{logo_b64}" width="150" />', unsafe_allow_html=True)
    except Exception:
        pass
st.write(f"مرحباً {st.session_state.user['full_name']} ({st.session_state.user['role']})")
if st.button("تسجيل الخروج"):
    logout()

with st.expander("⚙️ الإعدادات", expanded=False):
    new_font_size = st.slider("حجم الخط (%)", 50, 200, st.session_state.font_size, step=10, key="global_font")
    theme_color = st.color_picker("لون البرنامج", st.session_state.theme_color, key="global_theme")
    new_store_name = st.text_input("اسم المستودع", value=st.session_state.store_name, key="store_name_input")

    if st.button("تحديث الاسم"):
        st.session_state.store_name = new_store_name
        set_setting('store_name', new_store_name)
        st.success("تم تحديث الاسم")
        st.rerun()

    uploaded_logo = st.file_uploader("رفع شعار", type=["png", "jpg", "jpeg"])
    if uploaded_logo is not None:
        b64 = base64.b64encode(uploaded_logo.getbuffer()).decode()
        st.session_state.logo_base64 = b64
        set_setting('logo_base64', b64)
        st.success("تم حفظ الشعار في السحابة (يبقى بعد Reboot)")
        st.rerun()

    if st.session_state.get('logo_base64'):
        if st.button("مسح الشعار"):
            st.session_state.logo_base64 = ''
            set_setting('logo_base64', '')
            st.rerun()

    if new_font_size != st.session_state.font_size or theme_color != st.session_state.theme_color:
        st.session_state.font_size = new_font_size
        st.session_state.theme_color = theme_color
        set_setting('font_size', new_font_size)
        set_setting('theme_color', theme_color)
        st.rerun()

    st.subheader("📱 إعداد تيليجرام")
    token_input = st.text_input("Bot Token", value=st.session_state.telegram_bot_token, type="password", key="tg_token")
    chat_input = st.text_input("Chat ID", value=st.session_state.telegram_chat_id, key="tg_chat")
    file_id_input = st.text_input("File ID (اختياري)", value=st.session_state.telegram_file_id, key="tg_file_id")

    if st.button("💾 حفظ بيانات تيليجرام"):
        st.session_state.telegram_bot_token = token_input
        st.session_state.telegram_chat_id = chat_input
        st.session_state.telegram_file_id = file_id_input
        set_setting('telegram_file_id', file_id_input)
        save_app_config({
            'font_size': st.session_state.font_size,
            'theme_color': st.session_state.theme_color,
            'logo_path': st.session_state.logo_path,
            'store_name': st.session_state.store_name,
            'telegram_bot_token': st.session_state.telegram_bot_token,
            'telegram_chat_id': st.session_state.telegram_chat_id,
            'telegram_file_id': st.session_state.telegram_file_id
        })
        st.success("تم حفظ بيانات تيليجرام")

# ======================== القائمة ========================
menu = []
if check_perm():
    menu = ["📊 لوحة التحكم", "📦 إدارة الأصناف", "📏 الوحدات", "🏨 الفنادق", "🏢 الموردين",
            "📥 الوارد", "📤 الصادر", "📝 الجرد", "📈 التقارير",
            "🗑️ إدارة الحركات (حذف)", "💾 النسخ الاحتياطي", "👥 المستخدمين"]
elif has_role('purchasing'):
    menu = ["📊 لوحة التحكم", "📥 الوارد", "📈 التقارير"]
elif has_role('disbursement'):
    menu = ["📊 لوحة التحكم", "📤 الصادر", "📈 التقارير"]
elif has_role('supervisor'):
    menu = ["📊 لوحة التحكم", "📝 الجرد", "📈 التقارير"]
elif has_role('auditor'):
    menu = ["📊 لوحة التحكم", "📈 التقارير"]

choice = st.selectbox("القائمة", menu, index=0)

# ======================== الصفحات ========================
if choice == "📊 لوحة التحكم":
    st.header("لوحة التحكم")
    conn = get_db()
    today = date.today()
    total = conn.execute("SELECT COUNT(*) FROM items WHERE is_active=1").fetchone()[0]
    low = conn.execute("SELECT COUNT(*) FROM items WHERE current_balance<=min_qty AND is_active=1").fetchone()[0]
    exp = conn.execute("SELECT COUNT(*) FROM expiry_alerts WHERE is_consumed=0 AND expiry_date<?", (today.isoformat(),)).fetchone()[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("الأصناف", total)
    c2.metric("تحت الحد", low)
    c3.metric("منتهية الصلاحية", exp)
    st.divider()
    low_items = conn.execute("SELECT i.item_code, i.name, i.current_balance, i.min_qty, u.unit_symbol FROM items i LEFT JOIN units u ON i.unit_id=u.id WHERE i.current_balance<=i.min_qty AND i.is_active=1").fetchall()
    if low_items:
        df = pd.DataFrame([list(r) for r in low_items], columns=['كود', 'الصنف', 'الرصيد', 'الحد الأدنى', 'الوحدة'])
        with st.expander("🎨 تنسيق جدول التنبيهات"):
            font_scale = st.slider("حجم الخط (%)", 50, 200, 100, 10, key="dash_font")
            color_option = st.selectbox("لون الجدول", ["افتراضي", "أخضر", "أزرق", "رمادي", "برتقالي"], key="dash_color")
            color_map = {"افتراضي": "#f0f2f6", "أخضر": "#e6ffe6", "أزرق": "#e6f0ff", "رمادي": "#f5f5f5", "برتقالي": "#fff3e6"}
            bg = color_map.get(color_option, "#f0f2f6")
            cols = column_selector("اختر الأعمدة ورتبها", list(df.columns), list(df.columns), "dash_cols")
        df_disp = df[cols]
        st.dataframe(df_disp, use_container_width=True)
        st.markdown(apply_table_styling(font_scale, bg), unsafe_allow_html=True)
        export_buttons(df_disp, "اصناف_منخفضة", "تقرير الأصناف أقل من الحد الأدنى")

elif choice == "📦 إدارة الأصناف":
    if not check_perm():
        st.error("غير مصرح")
        st.stop()
    st.header("إدارة الأصناف")
    conn = get_db()

    units = conn.execute("SELECT id, unit_name, unit_symbol FROM units").fetchall()
    unit_options = [f"{u['unit_name']} ({u['unit_symbol']})" for u in units]
    unit_dict = {opt: u['id'] for opt, u in zip(unit_options, units)}
    unit_id_to_text = {u['id']: f"{u['unit_name']} ({u['unit_symbol']})" for u in units}

    tab_add, tab_edit, tab_view, tab_delete = st.tabs(["➕ إضافة صنف جديد", "✏️ تعديل صنف", "📋 عرض الأصناف", "🗑️ حذف صنف"])

    with tab_add:
        st.subheader("إضافة صنف جديد")
        with st.form("add_item_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("اسم الصنف *", key="new_item_name")
                new_unit = st.selectbox("الوحدة", unit_options, key="new_item_unit")
                new_min = st.number_input("الحد الأدنى", min_value=0.0, value=10.0, step=0.1, key="new_item_min")
            with col2:
                new_max = st.number_input("الحد الأقصى", min_value=0.0, value=100.0, step=0.1, key="new_item_max")
                new_balance = st.number_input("الرصيد الافتتاحي", min_value=0.0, value=0.0, step=0.1, key="new_item_balance")
                new_notes = st.text_input("ملاحظات", key="new_item_notes")

            submitted = st.form_submit_button("💾 حفظ الصنف", type="primary")

            if submitted:
                if not new_name or not new_name.strip():
                    st.error("اسم الصنف مطلوب")
                else:
                    existing = conn.execute("SELECT id FROM items WHERE name=? AND is_active=1", (new_name.strip(),)).fetchone()
                    if existing:
                        st.error(f"الصنف '{new_name}' موجود مسبقاً")
                    else:
                        unit_id = unit_dict.get(new_unit, units[0]['id'] if units else 1)
                        code = f"ITM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        conn.execute("INSERT INTO items (item_code, name, unit_id, min_qty, max_qty, current_balance, is_active, notes, created_date, last_updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                     (code, new_name.strip(), unit_id, new_min, new_max, new_balance, 1, new_notes, date.today().isoformat(), date.today().isoformat()))
                        conn.commit()
                        st.success(f"✅ تم حفظ الصنف '{new_name}' بنجاح")
                        st.rerun()

    with tab_edit:
        st.subheader("تعديل صنف موجود")

        all_items = conn.execute("SELECT id, item_code, name, unit_id, min_qty, max_qty, current_balance, notes FROM items WHERE is_active=1 ORDER BY name").fetchall()
        if not all_items:
            st.info("لا توجد أصناف مسجلة")
        else:
            item_names = [it['name'] for it in all_items]
            selected_name = st.selectbox("اختر الصنف للتعديل", item_names, key="edit_item_select")
            selected = next((it for it in all_items if it['name'] == selected_name), None)

            if selected:
                st.divider()
                with st.form("edit_item_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        edit_name = st.text_input("اسم الصنف *", value=selected['name'], key="edit_item_name")
                        current_unit_text = unit_id_to_text.get(selected['unit_id'], unit_options[0] if unit_options else "")
                        edit_unit = st.selectbox("الوحدة", unit_options, index=unit_options.index(current_unit_text) if current_unit_text in unit_options else 0, key="edit_item_unit")
                        edit_min = st.number_input("الحد الأدنى", min_value=0.0, value=float(selected['min_qty'] or 0), step=0.1, key="edit_item_min")
                    with col2:
                        edit_max = st.number_input("الحد الأقصى", min_value=0.0, value=float(selected['max_qty'] or 0), step=0.1, key="edit_item_max")
                        edit_notes = st.text_input("ملاحظات", value=selected['notes'] or "", key="edit_item_notes")
                        st.info(f"الكود: {selected['item_code']}")
                        st.info(f"الرصيد الحالي: {selected['current_balance']}")

                    submitted = st.form_submit_button("💾 حفظ التعديلات", type="primary")

                    if submitted:
                        if not edit_name or not edit_name.strip():
                            st.error("اسم الصنف مطلوب")
                        else:
                            dup = conn.execute("SELECT id FROM items WHERE name=? AND id!=? AND is_active=1", (edit_name.strip(), selected['id'])).fetchone()
                            if dup:
                                st.error(f"الاسم '{edit_name}' موجود لصنف آخر")
                            else:
                                unit_id = unit_dict.get(edit_unit, units[0]['id'] if units else 1)
                                conn.execute("UPDATE items SET name=?, unit_id=?, min_qty=?, max_qty=?, notes=?, last_updated=? WHERE id=?",
                                             (edit_name.strip(), unit_id, edit_min, edit_max, edit_notes, date.today().isoformat(), selected['id']))
                                conn.commit()
                                st.success(f"✅ تم حفظ التعديلات على '{edit_name}'")
                                st.rerun()

    with tab_view:
        st.subheader("قائمة الأصناف")

        search = st.text_input("🔍 بحث بالاسم أو الكود", key="item_search")

        all_items = conn.execute("SELECT i.id, i.item_code, i.name, i.current_balance, i.min_qty, i.max_qty, i.is_active, i.notes, u.unit_symbol FROM items i LEFT JOIN units u ON i.unit_id=u.id ORDER BY i.name").fetchall()

        if all_items:
            data = []
            for it in all_items:
                if search:
                    if search.lower() not in (it['name'] or '').lower() and search.lower() not in (it['item_code'] or '').lower():
                        continue
                data.append({
                    "كود": it['item_code'],
                    "الصنف": it['name'],
                    "الرصيد": it['current_balance'],
                    "الوحدة": it['unit_symbol'],
                    "الحد الأدنى": it['min_qty'],
                    "الحد الأقصى": it['max_qty'],
                    "الحالة": "نشط" if it['is_active'] else "غير نشط",
                    "ملاحظات": it['notes'] or ''
                })

            if data:
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption(f"إجمالي: {len(data)} صنف")
                export_buttons(df, "الأصناف", "تقرير الأصناف")
            else:
                st.info("لا توجد نتائج مطابقة للبحث")
        else:
            st.info("لا توجد أصناف مسجلة")

    with tab_delete:
        st.subheader("حذف أو تعطيل صنف")
        st.caption("ملاحظة: الصنف اللي فيه حركات سابقة لا يمكن حذفه، لكن يمكن تعطيله فقط.")

        all_items = conn.execute("SELECT id, item_code, name, is_active, current_balance FROM items ORDER BY name").fetchall()

        if not all_items:
            st.info("لا توجد أصناف")
        else:
            item_names = [f"{it['name']} (كود: {it['item_code']})" for it in all_items]
            selected_name = st.selectbox("اختر الصنف", item_names, key="delete_item_select")
            selected = next((it for it in all_items if f"{it['name']} (كود: {it['item_code']})" == selected_name), None)

            if selected:
                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**اسم الصنف:** {selected['name']}")
                    st.write(f"**الكود:** {selected['item_code']}")
                with col2:
                    st.write(f"**الرصيد الحالي:** {selected['current_balance']}")
                    st.write(f"**الحالة:** {'نشط' if selected['is_active'] else 'معطل'}")

                trans_count = conn.execute("SELECT COUNT(*) FROM transactions WHERE item_id=?", (selected['id'],)).fetchone()[0]
                st.info(f"عدد الحركات المرتبطة بالصنف: **{trans_count}**")

                st.divider()
                col_btn1, col_btn2, col_btn3 = st.columns(3)

                with col_btn1:
                    if trans_count == 0:
                        if st.button("🗑️ حذف الصنف نهائياً", key=f"del_item_{selected['id']}", type="primary"):
                            if st.session_state.get(f"confirm_del_{selected['id']}", False):
                                conn.execute("DELETE FROM expiry_alerts WHERE item_id=?", (selected['id'],))
                                conn.execute("DELETE FROM inventory_counts WHERE item_id=?", (selected['id'],))
                                conn.execute("DELETE FROM items WHERE id=?", (selected['id'],))
                                conn.commit()
                                st.success(f"✅ تم حذف الصنف '{selected['name']}' نهائياً")
                                st.session_state[f"confirm_del_{selected['id']}"] = False
                                st.rerun()
                            else:
                                st.session_state[f"confirm_del_{selected['id']}"] = True
                                st.warning("⚠️ اضغط مرة أخرى للتأكيد")
                                st.rerun()
                    else:
                        st.button("🗑️ حذف الصنف نهائياً", disabled=True, key=f"del_item_disabled_{selected['id']}")
                        st.caption("لا يمكن الحذف لوجود حركات مرتبطة")

                with col_btn2:
                    if selected['is_active']:
                        if st.button("⏸️ تعطيل الصنف", key=f"disable_item_{selected['id']}"):
                            conn.execute("UPDATE items SET is_active=0 WHERE id=?", (selected['id'],))
                            conn.commit()
                            st.success(f"تم تعطيل '{selected['name']}'")
                            st.rerun()
                    else:
                        if st.button("▶️ تنشيط الصنف", key=f"enable_item_{selected['id']}"):
                            conn.execute("UPDATE items SET is_active=1 WHERE id=?", (selected['id'],))
                            conn.commit()
                            st.success(f"تم تنشيط '{selected['name']}'")
                            st.rerun()

                with col_btn3:
                    if st.button("🔄 إعادة تحميل", key=f"reload_item_{selected['id']}"):
                        st.rerun()

elif choice == "📏 الوحدات":
    if not check_perm():
        st.error("غير مصرح")
        st.stop()
    st.header("وحدات القياس")
    conn = get_db()
    tab1, tab2 = st.tabs(["➕ إضافة وحدة", "✏️ تعديل الوحدات"])
    with tab1:
        with st.form("add_unit"):
            un = st.text_input("اسم الوحدة")
            us = st.text_input("الرمز")
            if st.form_submit_button("إضافة"):
                if un:
                    conn.execute("INSERT OR IGNORE INTO units (unit_name, unit_symbol) VALUES (?,?)", (un, us))
                    conn.commit()
                    st.success("تم الحفظ بنجاح")
                    st.rerun()
    with tab2:
        units = conn.execute("SELECT id, unit_name, unit_symbol FROM units").fetchall()
        if units:
            df_units = pd.DataFrame([list(u) for u in units], columns=['م', 'الوحدة', 'الرمز'])
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
                st.success("تم حفظ التعديلات بنجاح")
                st.rerun()
        else:
            st.info("لا توجد وحدات")
    if st.button("🔄 إعادة تحميل الصفحة", key="reload_units"):
        st.rerun()

elif choice == "🏨 الفنادق":
    if not check_perm():
        st.error("غير مصرح")
        st.stop()
    st.header("الفنادق")
    conn = get_db()
    tab1, tab2 = st.tabs(["إضافة", "تعديل"])
    with tab1:
        with st.form("add_hotel"):
            name = st.text_input("اسم الفندق")
            contact = st.text_input("الشخص المسؤول")
            phone = st.text_input("الهاتف")
            if st.form_submit_button("إضافة"):
                conn.execute("INSERT OR IGNORE INTO hotels (name,contact_person,phone) VALUES (?,?,?)", (name, contact, phone))
                conn.commit()
                st.success("تم الحفظ بنجاح")
                st.rerun()
    with tab2:
        hotels = conn.execute("SELECT * FROM hotels").fetchall()
        if hotels:
            hotel_names = [h['name'] for h in hotels]
            selected = st.selectbox("اختر الفندق", hotel_names)
            h = [h for h in hotels if h['name'] == selected][0]
            new_name = st.text_input("الاسم الجديد", value=h['name'])
            new_contact = st.text_input("الشخص المسؤول", value=h['contact_person'] or "")
            new_phone = st.text_input("الهاتف", value=h['phone'] or "")
            if st.button("حفظ التعديلات"):
                if new_name and new_name != selected:
                    exists = conn.execute("SELECT id FROM hotels WHERE name=? AND id!=?", (new_name, h['id'])).fetchone()
                    if exists:
                        st.error("الاسم موجود")
                    else:
                        conn.execute("UPDATE hotels SET name=?, contact_person=?, phone=? WHERE id=?", (new_name, new_contact, new_phone, h['id']))
                        conn.commit()
                        st.success("تم الحفظ بنجاح")
                        st.rerun()
                else:
                    conn.execute("UPDATE hotels SET name=?, contact_person=?, phone=? WHERE id=?", (new_name, new_contact, new_phone, h['id']))
                    conn.commit()
                    st.success("تم الحفظ بنجاح")
                    st.rerun()
        else:
            st.info("لا توجد فنادق")
    if st.button("🔄 إعادة تحميل الصفحة", key="reload_hotels"):
        st.rerun()

elif choice == "🏢 الموردين":
    if not check_perm():
        st.error("غير مصرح")
        st.stop()
    st.header("الموردين")
    conn = get_db()
    tab1, tab2, tab3 = st.tabs(["إضافة", "تعديل", "📎 مرفقات الموردين"])
    with tab1:
        with st.form("add_sup"):
            name = st.text_input("اسم المورد")
            info = st.text_input("معلومات الاتصال")
            if st.form_submit_button("إضافة"):
                conn.execute("INSERT OR IGNORE INTO suppliers (supplier_name,contact_info) VALUES (?,?)", (name, info))
                conn.commit()
                st.success("تم الحفظ بنجاح")
                st.rerun()
    with tab2:
        supps = conn.execute("SELECT * FROM suppliers").fetchall()
        if supps:
            supp_names = [s['supplier_name'] for s in supps]
            selected = st.selectbox("اختر المورد", supp_names)
            s = [s for s in supps if s['supplier_name'] == selected][0]
            new_name = st.text_input("الاسم الجديد", value=s['supplier_name'])
            new_info = st.text_input("معلومات الاتصال", value=s['contact_info'] or "")
            if st.button("حفظ التعديلات"):
                if new_name and new_name != selected:
                    exists = conn.execute("SELECT id FROM suppliers WHERE supplier_name=? AND id!=?", (new_name, s['id'])).fetchone()
                    if exists:
                        st.error("الاسم موجود")
                    else:
                        conn.execute("UPDATE suppliers SET supplier_name=?, contact_info=? WHERE id=?", (new_name, new_info, s['id']))
                        conn.commit()
                        st.success("تم الحفظ بنجاح")
                        st.rerun()
                else:
                    conn.execute("UPDATE suppliers SET supplier_name=?, contact_info=? WHERE id=?", (new_name, new_info, s['id']))
                    conn.commit()
                    st.success("تم الحفظ بنجاح")
                    st.rerun()
        else:
            st.info("لا يوجد موردين")
    with tab3:
        st.subheader("📎 مرفقات الموردين")
        st.caption("يمكنك رفع بيانات المورد، رقم الحساب، صور بطاقات، أي مستندات.")

        supps_for_att = conn.execute("SELECT id, supplier_name, attachments FROM suppliers ORDER BY supplier_name").fetchall()
        if not supps_for_att:
            st.info("لا يوجد موردين بعد. أضف مورداً أولاً.")
        else:
            supplier_names_att = [s['supplier_name'] for s in supps_for_att]
            selected_sup_name = st.selectbox("اختر المورد", supplier_names_att, key="sup_att_select")
            selected_sup = next(s for s in supps_for_att if s['supplier_name'] == selected_sup_name)
            sup_id = selected_sup['id']

            st.markdown("### المرفقات الحالية")
            atts = get_supplier_attachments(sup_id)
            if atts:
                for i, att in enumerate(atts):
                    col_a, col_b = st.columns([5, 1])
                    with col_a:
                        display_attachment(att['file_id'], att.get('name', 'مرفق'))
                    with col_b:
                        if st.button("🗑️ حذف", key=f"del_sup_att_{sup_id}_{i}"):
                            delete_supplier_attachment(sup_id, i)
                            st.success("تم الحذف")
                            st.rerun()
            else:
                st.info("لا توجد مرفقات لهذا المورد بعد.")

            st.divider()
            st.markdown("### ➕ إضافة مرفق جديد")
            up_sup = st.file_uploader("اختر ملف", type=["png", "jpg", "jpeg", "pdf", "doc", "docx", "xlsx"], key=f"sup_up_{sup_id}")
            if up_sup is not None:
                if st.button("💾 حفظ المرفق", key=f"save_sup_att_{sup_id}", type="primary"):
                    with st.spinner("جاري رفع المرفق إلى تيليجرام..."):
                        fid = save_attachment_to_telegram(up_sup, f"supplier_{sup_id}")
                    if fid:
                        add_supplier_attachment(sup_id, fid, up_sup.name)
                        st.success("تم حفظ المرفق بنجاح")
                        st.rerun()
                    else:
                        st.error("فشل رفع المرفق")
    if st.button("🔄 إعادة تحميل الصفحة", key="reload_suppliers"):
        st.rerun()

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
                }
            if 'inward_form_values' not in st.session_state:
                st.session_state.inward_form_values = st.session_state.inward_defaults.copy()

            with st.form("inward"):
                item = st.selectbox("الصنف", [i['name'] for i in items],
                                    index=[i['name'] for i in items].index(st.session_state.inward_form_values['item']) if st.session_state.inward_form_values['item'] in [i['name'] for i in items] else 0)
                qty = st.number_input("الكمية", 0.1, 100000.0, st.session_state.inward_form_values['qty'])
                supplier = st.selectbox("المورد", supplier_options,
                                        index=supplier_options.index(st.session_state.inward_form_values['supplier']) if st.session_state.inward_form_values['supplier'] in supplier_options else 0)
                unit_price = st.number_input("سعر الوحدة", min_value=0.0, value=st.session_state.inward_form_values['unit_price'], step=0.01)
                invoice_date = st.date_input("تاريخ الفاتورة", value=st.session_state.inward_form_values['invoice_date'])
                notes = st.text_input("ملاحظات", value=st.session_state.inward_form_values['notes'])
                uploaded_file = st.file_uploader("📎 إرفاق ملف (صورة أو PDF)", type=["png", "jpg", "jpeg", "pdf"])

                col_submit, col_undo, col_redo = st.columns([2, 1, 1])
                with col_submit:
                    submitted = st.form_submit_button("تسجيل")
                with col_undo:
                    undo = st.form_submit_button("↩️ تراجع")
                with col_redo:
                    redo = st.form_submit_button("↪️ تقديم")

                if submitted:
                    it = [i for i in items if i['name'] == item][0]
                    conn.execute("""INSERT INTO transactions (transaction_type,item_id,qty,unit_id,supplier_name,unit_price,expiry_date,transaction_date,notes,created_by)
                                  VALUES (?,?,?,?,?,?,NULL,?,?,?)""",
                                 ('وارد', it['id'], qty, it['unit_id'], supplier if supplier != "لا يوجد موردين مسجلين" else "", unit_price, invoice_date.isoformat(), notes, st.session_state.user['full_name']))
                    row = conn.execute("SELECT last_insert_rowid()").fetchone()
                    trans_id = row[0] if row else None
                    if uploaded_file and trans_id:
                        att = save_attachment_to_telegram(uploaded_file, trans_id)
                        if att:
                            conn.execute("UPDATE transactions SET attachment=? WHERE id=?", (att, trans_id))
                    conn.execute("UPDATE items SET current_balance=current_balance+?, last_updated=? WHERE id=?", (qty, date.today().isoformat(), it['id']))
                    conn.commit()
                    check_and_alert_item(it['id'])
                    st.success(f"تم الحفظ بنجاح (تاريخ الفاتورة: {invoice_date.isoformat()})")
                    st.session_state.inward_defaults = {
                        'item': item, 'qty': qty, 'supplier': supplier,
                        'unit_price': unit_price, 'invoice_date': invoice_date, 'notes': notes
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

    with tab_in2:
        st.subheader("سجل المشتريات")
        conn = get_db()

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            start_date = st.date_input("من تاريخ", date.today() - timedelta(days=30), key="in_start")
        with col_f2:
            end_date = st.date_input("إلى تاريخ", date.today(), key="in_end")

        inward_records = conn.execute("""
            SELECT t.id, t.transaction_date, t.item_id, i.name as item_name, t.qty, u.unit_symbol, t.notes, t.attachment, t.supplier_name, t.unit_price
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
                        display_attachment(rec['attachment'], "المرفق")
                    else:
                        st.caption("لا يوجد مرفق لهذه الحركة")

                    with st.expander("📎 إضافة / تحديث المرفق", expanded=False):
                        up_att = st.file_uploader("اختر ملف (صورة أو PDF)", type=["png", "jpg", "jpeg", "pdf"], key=f"late_att_{rec['id']}")
                        if up_att is not None:
                            if st.button("💾 حفظ المرفق", key=f"save_late_att_{rec['id']}", type="primary"):
                                with st.spinner("جاري رفع المرفق..."):
                                    new_fid = save_attachment_to_telegram(up_att, rec['id'])
                                if new_fid:
                                    conn.execute("UPDATE transactions SET attachment=? WHERE id=?", (new_fid, rec['id']))
                                    conn.commit()
                                    st.success("تم حفظ المرفق بنجاح")
                                    st.rerun()
                                else:
                                    st.error("فشل رفع المرفق")

                    col_btn_print, col_btn_delete = st.columns(2)
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
                            pdf.set_font("Amiri", size=12) if font_path else pdf.set_font("Helvetica", size=12)
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

elif choice == "📤 الصادر":
    tab_out1, tab_out2 = st.tabs(["📝 إنشاء إذن صرف", "📋 سجل أذون الصرف"])

    with tab_out1:
        st.subheader("إنشاء إذن صرف جديد")
        conn = get_db()

        col_refresh, _ = st.columns([1, 4])
        with col_refresh:
            if st.button("🔄 تحديث البيانات", key="refresh_outward_data"):
                _cache_items_for_outward.clear()
                _cache_hotels.clear()
                _cache_units_map.clear()
                st.success("تم التحديث")
                st.rerun()

        _cached_items = _cache_items_for_outward()
        _cached_hotels = _cache_hotels()
        items = [{'id': r[0], 'name': r[1], 'current_balance': r[2], 'unit_id': r[3]} for r in _cached_items]
        hotels = [{'id': r[0], 'name': r[1], 'contact_person': r[2], 'phone': r[3]} for r in _cached_hotels]

        if not items or not hotels:
            st.warning("يجب إضافة أصناف وفنادق أولاً")
        else:
            added_qty = {}
            for entry in st.session_state.get('outward_items', []):
                added_qty[entry['item_id']] = added_qty.get(entry['item_id'], 0) + entry['qty']

            item_options = []
            for it in items:
                effective_balance = it['current_balance'] - added_qty.get(it['id'], 0)
                item_options.append(f"{it['name']} (المتاح: {effective_balance})")

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
                        item_name = selected_item_str.split(" (المتاح:")[0]
                        it = next((i for i in items if i['name'] == item_name), None)
                        if it:
                            effective = it['current_balance'] - added_qty.get(it['id'], 0)
                            if qty > effective:
                                st.error(f"الرصيد غير كافٍ (المتاح: {effective})")
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
                unit_dict_out = _cache_units_map()
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

                col_submit, col_undo, col_redo = st.columns([2, 1, 1])
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
                            row = conn.execute("SELECT last_insert_rowid()").fetchone()
                            order_id = row[0] if row else None

                            for item_entry in st.session_state.outward_items:
                                conn.execute("""INSERT INTO transactions (transaction_type, item_id, hotel_id, qty, unit_id, transaction_date, notes, created_by, order_id)
                                              VALUES (?,?,?,?,?,?,?,?,?)""",
                                             ('صادر', item_entry['item_id'], hotel_id, item_entry['qty'], item_entry['unit_id'],
                                              order_date.isoformat(), f"إذن رقم {order_number}", st.session_state.user['full_name'], order_id))
                                conn.execute("UPDATE items SET current_balance = current_balance - ?, last_updated=? WHERE id=?",
                                             (item_entry['qty'], date.today().isoformat(), item_entry['item_id']))

                            conn.commit()
                            for item_entry in st.session_state.outward_items:
                                check_and_alert_item(item_entry['item_id'])
                            _cache_items_for_outward.clear()
                            _cache_hotels.clear()
                            _cache_units_map.clear()
                            st.success(f"تم الحفظ بنجاح (تاريخ الإذن: {order_date.isoformat()})")
                            st.session_state.outward_form_defaults = {
                                'hotel': selected_hotel,
                                'recipient': recipient,
                                'order_date': order_date,
                                'notes': notes
                            }
                            st.session_state.outward_form_values = st.session_state.outward_form_defaults.copy()
                            st.session_state.outward_items = []
                            st.rerun()

                if undo:
                    st.session_state.outward_form_values = st.session_state.outward_form_defaults.copy()
                    st.rerun()

    with tab_out2:
        st.subheader("سجل أذون الصرف")
        conn = get_db()

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            start_date = st.date_input("من تاريخ", date.today() - timedelta(days=30), key="out_start")
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
                        df_items = pd.DataFrame([list(r) for r in items_in_order], columns=['الصنف', 'الكمية', 'الوحدة'])
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
                            pdf.set_font("Amiri", size=12) if font_path else pdf.set_font("Helvetica", size=12)
                            pdf.cell(0, 8, shape_arabic(f"رقم الإذن: {order['order_number']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"التاريخ: {order['order_date']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"الفندق: {order['hotel_name']}"), ln=True, align='R')
                            pdf.cell(0, 8, shape_arabic(f"مسؤول الاستلام: {order['recipient_name']}"), ln=True, align='R')
                            pdf.ln(5)
                            pdf.set_fill_color(0, 168, 107)
                            pdf.set_text_color(255, 255, 255)
                            pdf.cell(30, 10, shape_arabic("الوحدة"), border=1, fill=True, align='C')
                            pdf.cell(30, 10, shape_arabic("الكمية"), border=1, fill=True, align='C')
                            pdf.cell(100, 10, shape_arabic("الصنف"), border=1, fill=True, align='C')
                            pdf.ln()
                            pdf.set_text_color(0, 0, 0)
                            pdf.set_font("Amiri", size=10) if font_path else pdf.set_font("Helvetica", size=10)
                            for item in items_in_order:
                                pdf.cell(30, 8, shape_arabic(item['unit_symbol'] or ''), border=1, align='C')
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

elif choice == "📝 الجرد":
    st.header("الجرد الدوري")
    conn = get_db()
    items = conn.execute("SELECT id,name,current_balance,unit_id FROM items WHERE is_active=1").fetchall()
    if items:
        item = st.selectbox("الصنف", [i['name'] for i in items])
        it = [i for i in items if i['name'] == item][0]
        st.info(f"الرصيد المسجل: {it['current_balance']}")
        actual = st.number_input("الكمية الفعلية", value=float(it['current_balance']), step=0.1, key="actual_qty")
        notes = st.text_input("ملاحظات")
        if st.button("حفظ الجرد"):
            diff = actual - it['current_balance']
            if diff != 0:
                conn.execute("INSERT INTO transactions (transaction_type,item_id,qty,unit_id,transaction_date,notes,created_by) VALUES (?,?,?,?,?,?,?)",
                             ('تسوية إضافة' if diff > 0 else 'تسوية عجز', it['id'], abs(diff), it['unit_id'], date.today().isoformat(), notes, st.session_state.user['full_name']))
                st.success(f"تم إضافة حركة {'تسوية إضافة' if diff > 0 else 'تسوية عجز'} بمقدار {abs(diff)}.")
            conn.execute("UPDATE items SET current_balance=?, last_updated=? WHERE id=?", (actual, date.today().isoformat(), it['id']))
            conn.execute("INSERT INTO inventory_counts (count_date,item_id,expected_qty,actual_qty,difference,notes,counted_by) VALUES (?,?,?,?,?,?,?)",
                         (date.today().isoformat(), it['id'], it['current_balance'], actual, diff, notes, st.session_state.user['full_name']))
            conn.commit()
            check_and_alert_item(it['id'])
            st.success("تم حفظ الجرد بنجاح")
            st.rerun()

elif choice == "📈 التقارير":
    st.header("التقارير")
    conn = get_db()
    tab1, tab2 = st.tabs(["حركات", "أرصدة"])
    with tab1:
        st.subheader("تقرير الحركات")
        col1, col2, col3 = st.columns(3)
        with col1:
            d1 = st.date_input("من", date.today() - timedelta(days=30))
        with col2:
            d2 = st.date_input("إلى", date.today())
        with col3:
            typ = st.selectbox("النوع", ["الكل", "وارد", "صادر", "تسوية إضافة", "تسوية عجز"])
        hotels = conn.execute("SELECT id, name FROM hotels").fetchall()
        hotel_names = ["الكل"] + [h['name'] for h in hotels]
        selected_hotel = st.selectbox("الفندق", hotel_names)
        items_filter = conn.execute("SELECT id, name FROM items WHERE is_active=1").fetchall()
        item_names = ["الكل"] + [it['name'] for it in items_filter]
        selected_item = st.selectbox("الصنف", item_names)

        with st.expander("🎨 تنسيق الجدول"):
            font_scale = st.slider("حجم الخط (%)", 50, 200, 100, step=10, key="report_font")
            color_option = st.selectbox("لون الجدول", ["افتراضي", "أخضر", "أزرق", "رمادي", "برتقالي"], key="report_color")
            color_map = {"افتراضي": "#f0f2f6", "أخضر": "#e6ffe6", "أزرق": "#e6f0ff", "رمادي": "#f5f5f5", "برتقالي": "#fff3e6"}
            bg_color = color_map.get(color_option, "#f0f2f6")

            all_columns = ['رقم الحركة', 'التاريخ', 'الصنف', 'النوع', 'الكمية', 'الوحدة', 'الفندق', 'المورد', 'سعر الوحدة', 'ملاحظات', 'مرفق']
            cols_order = column_selector("اختر الأعمدة ورتبها", all_columns, ['رقم الحركة', 'التاريخ', 'الصنف', 'النوع', 'الكمية', 'الوحدة', 'الفندق', 'المورد', 'ملاحظات', 'مرفق'], "trans_cols")

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
        if typ != "الكل":
            query += " AND t.transaction_type = ?"
            params.append(typ)
        if selected_hotel != "الكل":
            hotel_id = [h['id'] for h in hotels if h['name'] == selected_hotel][0]
            query += " AND t.hotel_id = ?"
            params.append(hotel_id)
        if selected_item != "الكل":
            item_id = [it['id'] for it in items_filter if it['name'] == selected_item][0]
            query += " AND t.item_id = ?"
            params.append(item_id)
        query += " ORDER BY t.id DESC"
        data = conn.execute(query, params).fetchall()
        if data:
            df = pd.DataFrame([list(r) for r in data], columns=['رقم الحركة', 'التاريخ', 'الصنف', 'النوع', 'الكمية', 'الوحدة', 'الفندق', 'المورد', 'سعر الوحدة', 'ملاحظات', 'مرفق'])

            def attachment_status(fid):
                if fid:
                    return "📎 موجود"
                return ""
            if 'مرفق' in df.columns:
                df['مرفق'] = df['مرفق'].apply(attachment_status)

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
            font_scale2 = st.slider("حجم الخط (%)", 50, 200, 100, 10, key="bal_font")
            color_option2 = st.selectbox("لون الجدول", ["افتراضي", "أخضر", "أزرق", "رمادي", "برتقالي"], key="bal_color")
            color_map2 = {"افتراضي": "#f0f2f6", "أخضر": "#e6ffe6", "أزرق": "#e6f0ff", "رمادي": "#f5f5f5", "برتقالي": "#fff3e6"}
            bg2 = color_map2.get(color_option2, "#f0f2f6")
            bal_cols = column_selector("اختر الأعمدة ورتبها (للأرصدة)", ['كود', 'الصنف', 'الرصيد', 'الوحدة'], ['كود', 'الصنف', 'الرصيد', 'الوحدة'], "bal_cols")

        items = conn.execute("SELECT i.item_code, i.name, i.current_balance, u.unit_symbol FROM items i LEFT JOIN units u ON i.unit_id=u.id WHERE i.is_active=1").fetchall()
        if items:
            df = pd.DataFrame([list(r) for r in items], columns=['كود', 'الصنف', 'الرصيد', 'الوحدة'])
            ordered = [c for c in bal_cols if c in df.columns]
            remaining = [c for c in df.columns if c not in ordered]
            df_disp = df[ordered + remaining]
            st.dataframe(df_disp, use_container_width=True)
            st.markdown(apply_table_styling(font_scale2, bg2), unsafe_allow_html=True)
            report_title = f"تقرير الأرصدة - {date.today().strftime('%Y-%m-%d')}"
            export_buttons(df_disp, "ارصدة", report_title)
        else:
            st.info("لا توجد أصناف نشطة")

elif choice == "🗑️ إدارة الحركات (حذف)":
    if not has_role('super_admin'):
        st.error("فقط المدير العام")
        st.stop()
    st.header("حذف حركة")
    conn = get_db()
    trans = conn.execute("""SELECT t.id, t.transaction_type, i.name, COALESCE(h.name,'-'), t.qty, t.transaction_date, t.notes
                           FROM transactions t JOIN items i ON t.item_id=i.id LEFT JOIN hotels h ON t.hotel_id=h.id
                           ORDER BY t.id DESC LIMIT 50""").fetchall()
    if trans:
        df = pd.DataFrame([list(r) for r in trans], columns=['رقم', 'النوع', 'الصنف', 'الفندق', 'الكمية', 'التاريخ', 'ملاحظات'])
        st.dataframe(df)
        trans_id = st.number_input("أدخل رقم الحركة للحذف", min_value=1, step=1)
        if st.button("حذف الحركة واسترجاع تأثيرها"):
            ok, msg = delete_transaction(trans_id)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("لا توجد حركات")

elif choice == "💾 النسخ الاحتياطي":
    st.header("النسخ الاحتياطي")
    notes = st.text_input("ملاحظات")
    if st.button("إنشاء نسخة"):
        with st.spinner("جاري إنشاء النسخة..."):
            ok, path, msg = create_backup("يدوي", notes)
        if ok:
            st.success(msg)
            with open(path, "rb") as f:
                st.download_button("⬇️ تحميل النسخة", f, file_name=os.path.basename(path))
        else:
            st.error(msg)

    st.subheader("استعادة نسخة")
    up = st.file_uploader("اختر ملف zip", type="zip")
    if up is not None:
        tmp = f"tmp_{datetime.now().timestamp()}.zip"
        with open(tmp, "wb") as f:
            f.write(up.read())
        if st.button("استعادة"):
            with st.spinner("جاري الاستعادة..."):
                ok, msg = restore_backup(tmp)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.divider()
    st.subheader("📱 النسخ الاحتياطي عبر تيليجرام")
    if st.button("⬆️ رفع قاعدة البيانات إلى تيليجرام"):
        with st.spinner("جاري الرفع..."):
            success, msg = telegram_send_document(DB_NAME, caption=f"نسخة احتياطية {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if success:
            st.success(msg)
            st.info(f"📎 معرّف الملف (File ID) الحالي: `{st.session_state.telegram_file_id}`")
        else:
            st.error(msg)
    if st.button("⬇️ استعادة قاعدة البيانات من تيليجرام"):
        with st.spinner("جاري الاستعادة..."):
            success, msg = telegram_get_latest_db()
        if success:
            st.success(msg)
            recalculate_all_balances()
            st.rerun()
        else:
            st.error(msg)

elif choice == "👥 المستخدمين":
    if not has_role('super_admin'):
        st.error("غير مصرح")
        st.stop()
    st.header("المستخدمين")
    conn = get_db()
    users = conn.execute("SELECT username, role, full_name FROM users").fetchall()
    if users:
        df = pd.DataFrame([list(u) for u in users], columns=['مستخدم', 'دور', 'اسم'])
        st.dataframe(df, use_container_width=True)
    with st.form("add_user"):
        un = st.text_input("اسم المستخدم")
        pw = st.text_input("كلمة المرور", type="password")
        fn = st.text_input("الاسم الكامل")
        role = st.selectbox("الدور", ['super_admin', 'purchasing', 'disbursement', 'supervisor', 'auditor'])
        if st.form_submit_button("إضافة"):
            try:
                conn.execute("INSERT INTO users (username,password,role,full_name) VALUES (?,?,?,?)", (un, hash_password(pw), role, fn))
                conn.commit()
                st.success("تم الحفظ بنجاح")
                st.rerun()
            except:
                st.error("مستخدم موجود")