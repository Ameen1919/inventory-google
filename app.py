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
    
    html, body {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    .stApp, .main, .block-container {{
        direction: rtl !important;
        text-align: right !important;
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


@st.cache_data(ttl=120, show_spinner=False)
def _cache_items_for_outward():
    conn = get_db()
    rows = conn.execute("SELECT id, name, current_balance, unit_id FROM items WHERE is_active=1 ORDER BY name").fetchall()
    return [(r['id'], r['name'], r['current_balance'], r['unit_id']) for r in rows]


@st.cache_data(ttl=120, show_spinner=False)
def _cache_hotels():
    conn = get_db()
    rows = conn.execute("SELECT id, name, contact_person, phone FROM hotels ORDER BY name").fetchall()
    return [(r['id'], r['name'], r['contact_person'], r['phone']) for r in rows]


@st.cache_data(ttl=120, show_spinner=False)
def _cache_units_map():
    conn = get_db()
    rows = conn.execute("SELECT id, unit_symbol FROM units").fetchall()
    return {r['id']: r['unit_symbol'] for r in rows}


@st.cache_data(ttl=120, show_spinner=False)
def _cache_items_basic():
    conn = get_db()
    rows = conn.execute("SELECT id, name, unit_id FROM items WHERE is_active=1 ORDER BY name").fetchall()
    return [(r['id'], r['name'], r['unit_id']) for r in rows]


@st.cache_data(ttl=120, show_spinner=False)
def _cache_suppliers_basic():
    conn = get_db()
    rows = conn.execute("SELECT id, supplier_name FROM suppliers ORDER BY supplier_name").fetchall()
    return [(r['id'], r['supplier_name']) for r in rows]


def _clear_all_caches():
    try:
        _cache_items_for_outward.clear()
        _cache_hotels.clear()
        _cache_units_map.clear()
        _cache_items_basic.clear()
        _cache_suppliers_basic.clear()
    except Exception:
        pass
    for k in ['_out_items_cached', '_out_hotels_cached']:
        st.session_state.pop(k, None)


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
        """, (item_id,)).fetc