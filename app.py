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
import time

st.set_page_config(page_title="مخزن النظافة", layout="wide", initial_sidebar_state="collapsed")

APP_CONFIG_FILE = 'app_config.json'

def load_app_config():
    config = {
        'font_size': 100, 'theme_color': "#00a86b", 'logo_path': None,
        'store_name': "مخزن النظافة", 'telegram_bot_token': "",
        'telegram_chat_id': "", 'telegram_file_id': ""
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

for _k, _v in [('font_size', 100), ('theme_color', "#00a86b"), ('logo_path', None),
               ('store_name', "مخزن النظافة"), ('telegram_bot_token', ""),
               ('telegram_chat_id', ""), ('telegram_file_id', ""), ('logo_base64', "")]:
    if _k not in st.session_state:
        st.session_state[_k] = saved_config.get(_k, _v) if _v is None or isinstance(_v, str) or isinstance(_v, int) else _v

def apply_theme():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;900&display=swap');
    
    *{{font-family:'Tajawal',sans-serif !important}}
    
    html, body, [class*="css"] {{
        direction: rtl !important;
        text-align: right !important;
    }}
    .stApp {{
        direction: rtl !important;
    }}
    .stTabs [data-baseweb="tab-list"] {{
        direction: rtl !important;
    }}
    
    .stButton, .stSelectbox, .stTextInput, .stNumberInput, .stDateInput, .stRadio, .stCheckbox {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    h1, h2, h3, h4, h5, h6 {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    input, textarea {{
        direction: rtl !important;
        text-align: right !important;
    }}
    
    /* إخفاء keyboard_ar */
    [data-testid="InputInstructions"],
    [data-testid="stTextInputRootElement"] small,
    [data-testid="stNumberInputRootElement"] small,
    [data-baseweb="input"] small,
    [data-baseweb="base-input"] small,
    [data-baseweb="textarea"] small,
    .stTextInput div small,
    .stNumberInput div small,
    .stTextArea div small,
    input ~ small, input + small, textarea ~ small, textarea + small,
    div:has(> input) > small, div:has(> textarea) > small,
    [class*="keyboard"], [class*="Keyboard"],
    [class*="shortcut"], [class*="Shortcut"] {{
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        height: 0 !important;
        width: 0 !important;
        max-height: 0 !important;
        overflow: hidden !important;
        pointer-events: none !important;
    }}
    
    [data-testid="stDataFrame"] {{
        direction: rtl !important;
    }}
    
    .stApp {{
        background-color: {st.session_state.theme_color} !important;
        background-image: linear-gradient(135deg, {st.session_state.theme_color} 0%, #ffffff 100%) !important;
    }}
    
    @media (max-width: 768px) {{
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] {{
            display: none !important;
        }}
    }}
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

try:
    TURSO_URL = st.secrets.get("TURSO_URL", "")
    TURSO_TOKEN = st.secrets.get("TURSO_TOKEN", "")
except Exception:
    TURSO_URL = saved_config.get("turso_url", "")
    TURSO_TOKEN = saved_config.get("turso_token", "")

def _clean_turso_url(u):
    u = u.strip().rstrip("/").replace("libsql://", "https://").replace("wss://", "https://")
    u = u.replace(".aws-us-east-1.", ".").replace(".aws-eu-west-1.", ".").replace(".aws-ap-northeast-1.", ".")
    if not u.startswith("http"):
        u = "https://" + u
    return u

TURSO_URL_CLEAN = _clean_turso_url(TURSO_URL) if TURSO_URL else ""
TURSO_PIPELINE = f"{TURSO_URL_CLEAN}/v2/pipeline" if TURSO_URL_CLEAN else ""
TURSO_AVAILABLE = bool(TURSO_PIPELINE and TURSO_TOKEN)


class DictRow:
    def __init__(self, columns, values):
        self._columns = list(columns)
        self._values = list(values)
        self._map = dict(zip(self._columns, self._values))

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, int) else self._map.get(key)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        if name in self._map:
            return self._map[name]
        raise AttributeError(f"no column {name}")

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, k):
        return k in self._map

    def keys(self):
        return self._columns

    def values(self):
        return self._values

    def items(self):
        return self._map.items()

    def get(self, k, d=None):
        return self._map.get(k, d)

    def to_dict(self):
        return dict(self._map)


def _encode_arg(p):
    if p is None:
        return {"type": "null"}
    if isinstance(p, bool):
        return {"type": "integer", "value": "1" if p else "0"}
    if isinstance(p, int):
        return {"type": "integer", "value": str(p)}
    if isinstance(p, float):
        return {"type": "float", "value": p}
    if isinstance(p, bytes):
        return {"type": "blob", "base64": base64.b64encode(p).decode()}
    return {"type": "text", "value": str(p)}


def _decode_cell(cell):
    if cell is None:
        return None
    t = cell.get("type")
    if t == "null":
        return None
    if t == "integer":
        v = cell.get("value")
        return int(v) if v is not None else None
    if t == "float":
        v = cell.get("value")
        return float(v) if v is not None else None
    if t == "text":
        return cell.get("value")
    if t == "blob":
        return base64.b64decode(cell.get("base64", ""))
    return cell.get("value")


class WrappedCursor:
    def __init__(self, conn):
        self._conn = conn
        self._rows = []
        self._idx = 0
        self._columns = []
        self.lastrowid = None
        self.rowcount = 0
        self.description = None

    def execute(self, sql, params=None):
        params = params or []
        if not isinstance(params, (list, tuple)):
            params = [params]
        sql_str = sql.strip()
        sql_upper = sql_str.upper()

        if sql_upper.startswith("PRAGMA"):
            self._rows = []
            self._columns = []
            self._idx = 0
            self.lastrowid = None
            return self

        args = [_encode_arg(p) for p in params]
        payload = {"requests": [
            {"type": "execute", "stmt": {"sql": sql_str, "args": args, "want_rows": True}},
            {"type": "close"}
        ]}
        is_insert = sql_upper.startswith("INSERT")
        r = self._conn._safe_post(payload, timeout=120, is_write=is_insert)
        if not r.ok:
            try:
                err_data = r.json()
            except:
                err_data = r.text[:300]
            raise Exception(f"Turso HTTP {r.status_code}: {err_data}")

        try:
            data = r.json()
        except:
            raise Exception("رد غير صالح من Turso")

        results = data.get("results", [])
        if not results:
            raise Exception("رد Turso فاضي")
        first = results[0]
        if first.get("type") == "error":
            raise Exception(f"Turso: {first.get('error', {}).get('message', 'خطأ')}")

        resp = first.get("response", {}).get("result", {})
        cols_info = resp.get("cols", [])
        self._columns = [c.get("name") for c in cols_info]
        self.description = [(c.get("name"),) for c in cols_info]
        self._rows = [DictRow(self._columns, [_decode_cell(c) for c in row]) for row in resp.get("rows", [])]
        self._idx = 0

        if is_insert and "RETURNING" in sql_upper and self._rows and 'id' in self._rows[0].keys():
            self.lastrowid = self._rows[0]['id']
        return self

    def executemany(self, sql, params_list):
        for p in params_list:
            self.execute(sql, p)
        return self

    def fetchone(self):
        if self._idx < len(self._rows):
            r = self._rows[self._idx]
            self._idx += 1
            return r
        return None

    def fetchall(self):
        rows = self._rows[self._idx:]
        self._idx = len(self._rows)
        return rows

    def fetchmany(self, size=1):
        rows = self._rows[self._idx:self._idx + size]
        self._idx += len(rows)
        return rows

    def close(self):
        pass

    def __iter__(self):
        return iter(self._rows)


class WrappedConnection:
    def __init__(self, url, auth_token):
        self._url = url
        self._token = auth_token
        self._session = None
        self._create_session()

    def _create_session(self):
        if self._session:
            try:
                self._session.close()
            except:
                pass
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Connection": "keep-alive"
        })
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=20, max_retries=0, pool_block=False
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def _safe_post(self, payload, timeout=120, max_retries=3, is_write=False):
        if is_write:
            max_retries = 1
        last_err = None
        for attempt in range(max_retries):
            try:
                return self._session.post(self._url, json=payload, timeout=timeout)
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                retryable = any(x in err_str for x in ['protocol', 'connection', 'timeout', 'reset', 'broken', 'eof', 'ssl', 'chunked', 'incomplete'])
                if not retryable:
                    raise
                if attempt < max_retries - 1:
                    if any(x in err_str for x in ['protocol', 'reset', 'broken', 'eof']):
                        try:
                            self._create_session()
                        except:
                            pass
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise Exception(f"فشل الاتصال بعد {max_retries} محاولات: {last_err}")

    def cursor(self):
        return WrappedCursor(self)

    def execute(self, sql, params=None):
        cur = WrappedCursor(self)
        cur.execute(sql, params)
        return cur

    def executescript(self, script):
        for stmt in script.split(';'):
            s = stmt.strip()
            if s:
                try:
                    self.execute(s)
                except:
                    pass

    def execute_batch(self, queries):
        stmts = []
        for sql, params in queries:
            args = [_encode_arg(p) for p in (params or [])]
            stmts.append({"type": "execute", "stmt": {"sql": sql, "args": args, "want_rows": True}})
        stmts.append({"type": "close"})
        r = self._safe_post({"requests": stmts}, timeout=120, is_write=False)
        if not r.ok:
            raise Exception(f"Turso HTTP {r.status_code}")
        data = r.json()
        results = data.get("results", [])
        output = []
        for res in results[:-1]:
            if res.get("type") == "error":
                output.append([])
                continue
            resp = res.get("response", {}).get("result", {})
            cols = [c.get("name") for c in resp.get("cols", [])]
            output.append([DictRow(cols, [_decode_cell(c) for c in row]) for row in resp.get("rows", [])])
        return output

    def execute_write_batch(self, queries, is_insert=False):
        if not queries:
            return 0
        stmts = []
        for sql, params in queries:
            args = [_encode_arg(p) for p in (params or [])]
            stmts.append({"type": "execute", "stmt": {"sql": sql, "args": args, "want_rows": False}})
        stmts.append({"type": "close"})
        r = self._safe_post({"requests": stmts}, timeout=180, is_write=is_insert)
        if not r.ok:
            try:
                err_data = r.json()
            except:
                err_data = r.text[:300]
            raise Exception(f"Turso HTTP {r.status_code}: {err_data}")
        results = r.json().get("results", [])
        for res in results[:-1]:
            if res.get("type") == "error":
                raise Exception(f"Turso: {res.get('error', {}).get('message', 'خطأ')}")
        return len(queries)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class SQLiteWrapper:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def cursor(self):
        return self._conn.cursor()

    def execute_batch(self, queries):
        output = []
        for sql, params in queries:
            cur = self._conn.execute(sql, params or [])
            rows = cur.fetchall() if cur.description else []
            cols = [d[0] for d in cur.description] if cur.description else []
            output.append([DictRow(cols, list(r)) for r in rows])
        return output

    def execute_write_batch(self, queries, is_insert=False):
        for sql, params in queries:
            self._conn.execute(sql, params or [])
        return len(queries)

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


def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()


def get_db():
    cached = st.session_state.get('_db_conn')
    if cached is not None:
        return cached

    if TURSO_AVAILABLE:
        try:
            conn = WrappedConnection(TURSO_PIPELINE, TURSO_TOKEN)
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
    if TURSO_AVAILABLE:
        try:
            _conn = WrappedConnection(TURSO_PIPELINE, TURSO_TOKEN)
        except Exception:
            raw = sqlite3.connect(DB_NAME)
            raw.row_factory = sqlite3.Row
            _conn = SQLiteWrapper(raw)
    else:
        raw = sqlite3.connect(DB_NAME)
        raw.row_factory = sqlite3.Row
        _conn = SQLiteWrapper(raw)

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
    for uname, pwd, role, fname in [
        ('admin', hash_password('admin123'), 'super_admin', 'المدير العام'),
        ('مشتريات', hash_password('buy123'), 'purchasing', 'مسؤول المشتريات'),
        ('صرف', hash_password('out123'), 'disbursement', 'مسؤول الصرف'),
        ('مشرف1', hash_password('sup123'), 'supervisor', 'مشرف أول'),
        ('مشرف2', hash_password('sup456'), 'supervisor', 'مشرف ثاني')
    ]:
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


def show_rtl_table(df, **kwargs):
    if df is None or df.empty:
        return
    df_rev = df[df.columns[::-1]]
    st.dataframe(df_rev, **kwargs)
    return df_rev


init_db()
_load_settings_from_db()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
if 'show_settings' not in st.session_state:
    st.session_state.show_settings = False

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

# ======================== الهيدر الجديد ========================
col_logo, col_info, col_actions = st.columns([1, 4, 2])

with col_logo:
    logo_b64 = st.session_state.get('logo_base64', '')
    if logo_b64:
        try:
            st.markdown(f'<img src="data:image/png;base64,{logo_b64}" width="90" />', unsafe_allow_html=True)
        except Exception:
            pass

with col_info:
    st.markdown(f"### 🧹 {st.session_state.store_name}")
    st.caption(f"مرحباً **{st.session_state.user['full_name']}** ({st.session_state.user['role']})")

with col_actions:
    st.write("")
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("⚙️ الإعدادات", use_container_width=True, key="btn_toggle_settings"):
            st.session_state.show_settings = not st.session_state.get('show_settings', False)
            st.rerun()
    with col_btn2:
        if st.button("🚪 خروج", use_container_width=True, key="btn_logout_top"):
            logout()

# ======================== الإعدادات (تظهر عند الطلب) ========================
if st.session_state.get('show_settings', False):
    with st.container(border=True):
        st.markdown("### ⚙️ الإعدادات")

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
            st.success("تم حفظ الشعار")
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
            st.success("تم حفظ بيانات تيليجرام")

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

if choice == "📊 لوحة التحكم":
    st.header("لوحة التحكم")
    conn = get_db()
    today = date.today()
    try:
        batch = conn.execute_batch([
            ("SELECT COUNT(*) as c FROM items WHERE is_active=1", []),
            ("SELECT COUNT(*) as c FROM items WHERE current_balance<=min_qty AND is_active=1", []),
            ("SELECT COUNT(*) as c FROM expiry_alerts WHERE is_consumed=0 AND expiry_date<?", [today.isoformat()])
        ])
        total = batch[0][0]['c'] if batch[0] else 0
        low = batch[1][0]['c'] if batch[1] else 0
        exp = batch[2][0]['c'] if batch[2] else 0
    except Exception:
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
        show_rtl_table(df_disp, use_container_width=True)
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
                        _clear_all_caches()
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
                                _clear_all_caches()
                                st.success(f"✅ تم حفظ التعديلات")
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
                    "كود": it['item_code'], "الصنف": it['name'], "الرصيد": it['current_balance'],
                    "الوحدة": it['unit_symbol'], "الحد الأدنى": it['min_qty'], "الحد الأقصى": it['max_qty'],
                    "الحالة": "نشط" if it['is_active'] else "غير نشط", "ملاحظات": it['notes'] or ''
                })
            if data:
                df = pd.DataFrame(data)
                show_rtl_table(df, use_container_width=True, hide_index=True)
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
                                _clear_all_caches()
                                st.success(f"✅ تم حذف الصنف")
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
                            _clear_all_caches()
                            st.success(f"تم تعطيل '{selected['name']}'")
                            st.rerun()
                    else:
                        if st.button("▶️ تنشيط الصنف", key=f"enable_item_{selected['id']}"):
                            conn.execute("UPDATE items SET is_active=1 WHERE id=?", (selected['id'],))
                            conn.commit()
                            _clear_all_caches()
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
                    _clear_all_caches()
                    st.success("تم الحفظ بنجاح")
                    st.rerun()
    with tab2:
        units = conn.execute("SELECT id, unit_name, unit_symbol FROM units").fetchall()
        if units:
            df_units = pd.DataFrame([list(u) for u in units], columns=['م', 'الوحدة', 'الرمز'])
            edited_units = st.data_editor(df_units[df_units.columns[::-1]], num_rows="dynamic", key="units_editor", use_container_width=True)
            if st.button("💾 حفظ تعديلات الوحدات", key="save_units"):
                with conn:
                    for _, row in edited_units.iterrows():
                        if pd.notna(row['م']):
                            conn.execute("UPDATE units SET unit_name=?, unit_symbol=? WHERE id=?", (row['الوحدة'], row['الرمز'], int(row['م'])))
                        else:
                            if pd.notna(row['الوحدة']) and str(row['الوحدة']).strip():
                                conn.execute("INSERT OR IGNORE INTO units (unit_name, unit_symbol) VALUES (?,?)", (row['الوحدة'], row['الرمز']))
                conn.commit()
                _clear_all_caches()
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
                _clear_all_caches()
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
                        _clear_all_caches()
                        st.success("تم الحفظ بنجاح")
                        st.rerun()
                else:
                    conn.execute("UPDATE hotels SET name=?, contact_person=?, phone=? WHERE id=?", (new_name, new_contact, new_phone, h['id']))
                    conn.commit()
                    _clear_all_caches()
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
                _clear_all_caches()
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
                        _clear_all_caches()
                        st.success("تم الحفظ بنجاح")
                        st.rerun()
                else:
                    conn.execute("UPDATE suppliers SET supplier_name=?, contact_info=? WHERE id=?", (new_name, new_info, s['id']))
                    conn.commit()
                    _clear_all_caches()
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
                    with st.spinner("جاري رفع المرفق..."):
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
        _cached_items_in = _cache_items_basic()
        _cached_suppliers_in = _cache_suppliers_basic()
        items = [{'id': r[0], 'name': r[1], 'unit_id': r[2]} for r in _cached_items_in]
        supplier_options = [r[1] for r in _cached_suppliers_in]
        if not supplier_options:
            supplier_options = ["لا يوجد موردين مسجلين"]
        if items:
            if 'inward_defaults' not in st.session_state:
                st.session_state.inward_defaults = {
                    'item': items[0]['name'] if items else "", 'qty': 1.0,
                    'supplier': supplier_options[0] if supplier_options else "",
                    'unit_price': 0.0, 'invoice_date': date.today(), 'notes': "",
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
                    result = conn.execute("""INSERT INTO transactions (transaction_type,item_id,qty,unit_id,supplier_name,unit_price,expiry_date,transaction_date,notes,created_by)
                                  VALUES (?,?,?,?,?,?,NULL,?,?,?) RETURNING id""",
                                 ('وارد', it['id'], qty, it['unit_id'], supplier if supplier != "لا يوجد موردين مسجلين" else "", unit_price, invoice_date.isoformat(), notes, st.session_state.user['full_name']))
                    row = result.fetchone()
                    trans_id = row['id'] if row else None
                    if uploaded_file and trans_id:
                        att = save_attachment_to_telegram(uploaded_file, trans_id)
                        if att:
                            conn.execute("UPDATE transactions SET attachment=? WHERE id=?", (att, trans_id))
                    conn.execute("UPDATE items SET current_balance=current_balance+?, last_updated=? WHERE id=?", (qty, date.today().isoformat(), it['id']))
                    conn.commit()
                    check_and_alert_item(it['id'])
                    _clear_all_caches()
                    st.success(f"تم الحفظ بنجاح")
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
        st.subheader("📋 سجل المشتريات")
        conn = get_db()
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            start_date = st.date_input("من تاريخ", date.today() - timedelta(days=30), key="in_start")
        with col_f2:
            end_date = st.date_input("إلى تاريخ", date.today(), key="in_end")
        inward_records = conn.execute("""
            SELECT t.id, t.transaction_date, t.item_id, i.name as item_name, t.qty, u.unit_symbol, t.notes, t.attachment, t.supplier_name, t.unit_price
            FROM transactions t JOIN items i ON t.item_id = i.id
            LEFT JOIN units u ON t.unit_id = u.id
            WHERE t.transaction_type = 'وارد' AND t.transaction_date BETWEEN ? AND ? ORDER BY t.id DESC
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()
        if not inward_records:
            st.info("لا توجد مشتريات في هذه الفترة")
        else:
            table_data = []
            total_value = 0
            for rec in inward_records:
                has_attach = "📎" if rec['attachment'] else ""
                value = (rec['qty'] or 0) * (rec['unit_price'] or 0)
                total_value += value
                table_data.append({
                    'الرقم': rec['id'], 'التاريخ': rec['transaction_date'], 'الصنف': rec['item_name'],
                    'الكمية': f"{rec['qty']} {rec['unit_symbol'] or ''}", 'المورد': rec['supplier_name'] or '-',
                    'سعر الوحدة': f"{rec['unit_price']:.2f}" if rec['unit_price'] else '-',
                    'الإجمالي': f"{value:.2f}" if value else '-', 'مرفق': has_attach,
                })
            df_summary = pd.DataFrame(table_data)
            with st.expander("🎨 تنسيق الجدول", expanded=False):
                font_scale_in = st.slider("حجم الخط (%)", 50, 200, 100, 10, key="in_log_font")
                color_in = st.selectbox("لون الجدول", ["افتراضي", "أخضر", "أزرق", "رمادي", "برتقالي"], key="in_log_color")
                color_map_in = {"افتراضي": "#f0f2f6", "أخضر": "#e6ffe6", "أزرق": "#e6f0ff", "رمادي": "#f5f5f5", "برتقالي": "#fff3e6"}
                bg_in = color_map_in.get(color_in, "#f0f2f6")
            show_rtl_table(df_summary, use_container_width=True, hide_index=True)
            st.markdown(apply_table_styling(font_scale_in, bg_in), unsafe_allow_html=True)
            col_sum1, col_sum2 = st.columns(2)
            with col_sum1:
                st.markdown(f"**📊 عدد الحركات:** `{len(inward_records)}`")
            with col_sum2:
                st.markdown(f"**💰 إجمالي القيمة:** `{total_value:.2f}`")
            export_buttons(df_summary, "سجل_المشتريات", "تقرير سجل المشتريات")
            st.divider()
            st.subheader("🔍 عرض تفاصيل حركة")
            record_options = [f"#{rec['id']} - {rec['item_name']} - {rec['transaction_date']} ({rec['qty']} {rec['unit_symbol'] or ''})" for rec in inward_records]
            selected_option = st.selectbox("اختر الحركة لعرض التفاصيل", record_options, key="inward_detail_select")
            selected_idx = record_options.index(selected_option)
            rec = inward_records[selected_idx]
            st.divider()
            col_det1, col_det2 = st.columns(2)
            with col_det1:
                st.write(f"**رقم الحركة:** {rec['id']}")
                st.write(f"**الصنف:** {rec['item_name']}")
                st.write(f"**الكمية:** {rec['qty']} {rec['unit_symbol'] or ''}")
                if rec['supplier_name']:
                    st.write(f"**المورد:** {rec['supplier_name']}")
                if rec['unit_price']:
                    st.write(f"**سعر الوحدة:** {rec['unit_price']:.2f}")
                    st.write(f"**الإجمالي:** {rec['qty'] * rec['unit_price']:.2f}")
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
            st.divider()
            col_btn_print, col_btn_delete = st.columns(2)
            with col_btn_print:
                if st.button(f"🖨️ طباعة PDF", key=f"print_in_{rec['id']}", type="primary"):
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
                    pdf.cell(0, 8, shape_arabic(f"الكمية: {rec['qty']} {rec['unit_symbol'] or ''}"), ln=True, align='R')
                    if rec['supplier_name']:
                        pdf.cell(0, 8, shape_arabic(f"المورد: {rec['supplier_name']}"), ln=True, align='R')
                    if rec['unit_price']:
                        pdf.cell(0, 8, shape_arabic(f"سعر الوحدة: {rec['unit_price']:.2f}"), ln=True, align='R')
                        pdf.cell(0, 8, shape_arabic(f"الإجمالي: {rec['qty'] * rec['unit_price']:.2f}"), ln=True, align='R')
                    pdf.cell(0, 8, shape_arabic(f"ملاحظات: {rec['notes'] or 'لا يوجد'}"), ln=True, align='R')
                    pdf.ln(10)
                    pdf.cell(0, 10, shape_arabic("توقيع أمين المخزن: ________________"), ln=True, align='R')
                    st.download_button(f"📥 تحميل PDF", data=bytes(pdf.output()), file_name=f"Purchase_Order_{rec['id']}.pdf", mime="application/pdf")
            with col_btn_delete:
                if st.button(f"🗑️ حذف #{rec['id']}", key=f"del_in_{rec['id']}"):
                    if st.session_state.get(f"confirm_del_in_{rec['id']}", False):
                        success, msg = delete_transaction(rec['id'])
                        if success:
                            st.success(msg)
                            _clear_all_caches()
                            st.session_state[f"confirm_del_in_{rec['id']}"] = False
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.session_state[f"confirm_del_in_{rec['id']}"] = True
                        st.warning("⚠️ اضغط مرة أخرى لتأكيد الحذف")
                        st.rerun()

elif choice == "📤 الصادر":
    tab_out1, tab_out2 = st.tabs(["📝 إنشاء إذن صرف", "📋 سجل أذون الصرف"])

    with tab_out1:
        st.subheader("إنشاء إذن صرف جديد")
        conn = get_db()
        col_refresh, _ = st.columns([1, 4])
        with col_refresh:
            if st.button("🔄 تحديث البيانات", key="refresh_outward_data"):
                _clear_all_caches()
                st.success("تم التحديث")
                st.rerun()
        if '_out_items_cached' not in st.session_state:
            _ci = _cache_items_for_outward()
            st.session_state._out_items_cached = [{'id': r[0], 'name': r[1], 'current_balance': r[2], 'unit_id': r[3]} for r in _ci]
        if '_out_hotels_cached' not in st.session_state:
            _ch = _cache_hotels()
            st.session_state._out_hotels_cached = [{'id': r[0], 'name': r[1], 'contact_person': r[2], 'phone': r[3]} for r in _ch]
        items = st.session_state._out_items_cached
        hotels = st.session_state._out_hotels_cached
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
                    'order_date': date.today(), 'notes': ""
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
                                    'item_id': it['id'], 'item_name': it['name'], 'qty': qty, 'unit_id': it['unit_id']
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
                show_rtl_table(df_display, use_container_width=True, hide_index=True)
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
                                              value=st.session_state.outward_form_values['recipient'], key="recipient")
                    order_date = st.date_input("تاريخ الإذن",
                                               value=st.session_state.outward_form_values['order_date'], key="order_date")
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
                            result = conn.execute("""INSERT INTO outward_orders (order_number, hotel_id, recipient_name, order_date, notes, created_by)
                                          VALUES (?,?,?,?,?,?) RETURNING id""",
                                         (order_number, hotel_id, recipient, order_date.isoformat(), notes, st.session_state.user['full_name']))
                            row = result.fetchone()
                            order_id = row['id'] if row else None
                            batch_queries = []
                            for item_entry in st.session_state.outward_items:
                                batch_queries.append(("""INSERT INTO transactions (transaction_type, item_id, hotel_id, qty, unit_id, transaction_date, notes, created_by, order_id)
                                              VALUES (?,?,?,?,?,?,?,?,?)""",
                                             ('صادر', item_entry['item_id'], hotel_id, item_entry['qty'], item_entry['unit_id'],
                                              order_date.isoformat(), f"إذن رقم {order_number}", st.session_state.user['full_name'], order_id)))
                                batch_queries.append(("UPDATE items SET current_balance = current_balance - ?, last_updated=? WHERE id=?",
                                                     (item_entry['qty'], date.today().isoformat(), item_entry['item_id'])))
                            try:
                                conn.execute_write_batch(batch_queries, is_insert=True)
                            except Exception:
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
                            _clear_all_caches()
                            st.success(f"تم الحفظ بنجاح")
                            st.session_state.outward_form_defaults = {
                                'hotel': selected_hotel, 'recipient': recipient,
                                'order_date': order_date, 'notes': notes
                            }
                            st.session_state.outward_form_values = st.session_state.outward_form_defaults.copy()
                            st.session_state.outward_items = []
                            st.rerun()
                if undo:
                    st.session_state.outward_form_values = st.session_state.outward_form_defaults.copy()
                    st.rerun()

    with tab_out2:
        st.subheader("📋 سجل أذون الصرف")
        conn = get_db()
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            start_date = st.date_input("من تاريخ", date.today() - timedelta(days=30), key="out_start")
        with col_f2:
            end_date = st.date_input("إلى تاريخ", date.today(), key="out_end")
        orders = conn.execute("""
            SELECT o.id, o.order_number, o.order_date, h.name as hotel_name, o.recipient_name, o.notes
            FROM outward_orders o JOIN hotels h ON o.hotel_id = h.id
            WHERE o.order_date BETWEEN ? AND ? ORDER BY o.id DESC
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()
        if not orders:
            st.info("لا توجد أذون صرف في هذه الفترة")
        else:
            table_orders = []
            for order in orders:
                items_count = conn.execute("SELECT COUNT(*) FROM transactions WHERE order_id=? AND transaction_type='صادر'", (order['id'],)).fetchone()[0]
                table_orders.append({
                    'رقم الإذن': order['order_number'], 'التاريخ': order['order_date'],
                    'الفندق': order['hotel_name'], 'مسؤول الاستلام': order['recipient_name'],
                    'عدد الأصناف': items_count, 'ملاحظات': order['notes'] or '-',
                })
            df_orders = pd.DataFrame(table_orders)
            with st.expander("🎨 تنسيق الجدول", expanded=False):
                font_scale_out = st.slider("حجم الخط (%)", 50, 200, 100, 10, key="out_log_font")
                color_out = st.selectbox("لون الجدول", ["افتراضي", "أخضر", "أزرق", "رمادي", "برتقالي"], key="out_log_color")
                color_map_out = {"افتراضي": "#f0f2f6", "أخضر": "#e6ffe6", "أزرق": "#e6f0ff", "رمادي": "#f5f5f5", "برتقالي": "#fff3e6"}
                bg_out = color_map_out.get(color_out, "#f0f2f6")
            show_rtl_table(df_orders, use_container_width=True, hide_index=True)
            st.markdown(apply_table_styling(font_scale_out, bg_out), unsafe_allow_html=True)
            st.caption(f"📊 إجمالي الأذون: {len(orders)}")
            export_buttons(df_orders, "سجل_أذون_الصرف", "تقرير أذون الصرف")
            st.divider()
            st.subheader("🔍 عرض تفاصيل إذن")
            order_options = [f"{o['order_number']} - {o['hotel_name']} - {o['order_date']}" for o in orders]
            selected_order_option = st.selectbox("اختر الإذن", order_options, key="out_detail_select")
            selected_idx = order_options.index(selected_order_option)
            order = orders[selected_idx]
            st.divider()
            col_det1, col_det2 = st.columns(2)
            with col_det1:
                st.write(f"**رقم الإذن:** {order['order_number']}")
                st.write(f"**التاريخ:** {order['order_date']}")
                st.write(f"**الفندق:** {order['hotel_name']}")
                st.write(f"**مسؤول الاستلام:** {order['recipient_name']}")
            with col_det2:
                st.write(f"**ملاحظات:** {order['notes'] or 'لا يوجد'}")
            items_in_order = conn.execute("""
                SELECT i.name, t.qty, u.unit_symbol FROM transactions t
                JOIN items i ON t.item_id = i.id LEFT JOIN units u ON t.unit_id = u.id
                WHERE t.order_id = ? AND t.transaction_type = 'صادر'
            """, (order['id'],)).fetchall()
            if items_in_order:
                st.markdown("### الأصناف المصروفة")
                df_items = pd.DataFrame([list(r) for r in items_in_order], columns=['الصنف', 'الكمية', 'الوحدة'])
                show_rtl_table(df_items, use_container_width=True, hide_index=True)
            st.divider()
            col_btn_print, col_btn_delete = st.columns(2)
            with col_btn_print:
                if st.button(f"🖨️ طباعة PDF", key=f"print_out_{order['id']}", type="primary"):
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
                    st.download_button(f"📥 تحميل PDF", data=bytes(pdf.output()), file_name=f"{order['order_number']}.pdf", mime="application/pdf")
            with col_btn_delete:
                if st.button(f"🗑️ حذف الإذن {order['order_number']}", key=f"del_out_{order['id']}"):
                    if st.session_state.get(f"confirm_del_out_{order['id']}", False):
                        success, msg = delete_outward_order(order['id'])
                        if success:
                            st.success(msg)
                            _clear_all_caches()
                            st.session_state[f"confirm_del_out_{order['id']}"] = False
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.session_state[f"confirm_del_out_{order['id']}"] = True
                        st.warning("⚠️ اضغط مرة أخرى لتأكيد الحذف")
                        st.rerun()

elif choice == "📝 الجرد":
    st.header("الجرد الدوري")
    conn = get_db()
    items_full = conn.execute("SELECT id, name, current_balance, unit_id FROM items WHERE is_active=1 ORDER BY name").fetchall()
    if items_full:
        item_names = [i['name'] for i in items_full]
        item = st.selectbox("الصنف", item_names)
        it = [i for i in items_full if i['name'] == item][0]
        st.info(f"الرصيد المسجل: {it['current_balance']}")
        actual = st.number_input("الكمية الفعلية", value=float(it['current_balance']), step=0.1, key="actual_qty")
        notes = st.text_input("ملاحظات")
        if st.button("حفظ الجرد"):
            diff = actual - it['current_balance']
            if diff != 0:
                conn.execute("INSERT INTO transactions (transaction_type,item_id,qty,unit_id,transaction_date,notes,created_by) VALUES (?,?,?,?,?,?,?)",
                             ('تسوية إضافة' if diff > 0 else 'تسوية عجز', it['id'], abs(diff), it['unit_id'], date.today().isoformat(), notes, st.session_state.user['full_name']))
                st.success(f"تم إضافة حركة بمقدار {abs(diff)}.")
            conn.execute("UPDATE items SET current_balance=?, last_updated=? WHERE id=?", (actual, date.today().isoformat(), it['id']))
            conn.execute("INSERT INTO inventory_counts (count_date,item_id,expected_qty,actual_qty,difference,notes,counted_by) VALUES (?,?,?,?,?,?,?)",
                         (date.today().isoformat(), it['id'], it['current_balance'], actual, diff, notes, st.session_state.user['full_name']))
            conn.commit()
            check_and_alert_item(it['id'])
            _clear_all_caches()
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
            FROM transactions t JOIN items i ON t.item_id = i.id
            LEFT JOIN hotels h ON t.hotel_id = h.id LEFT JOIN units u ON t.unit_id = u.id
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
                return "📎 موجود" if fid else ""
            if 'مرفق' in df.columns:
                df['مرفق'] = df['مرفق'].apply(attachment_status)
            ordered = [c for c in cols_order if c in df.columns]
            remaining = [c for c in df.columns if c not in ordered]
            df_display = df[ordered + remaining]
            show_rtl_table(df_display, use_container_width=True, hide_index=True)
            st.markdown(apply_table_styling(font_scale, bg_color), unsafe_allow_html=True)
            export_df = df.drop(columns=['مرفق'], errors='ignore')
            export_df = export_df[[c for c in ordered if c in export_df.columns]]
            export_buttons(export_df, "حركات", "تقرير الحركات")
            total_qty = df['الكمية'].sum()
            st.markdown(f"**📊 إجمالي الكمية:** `{total_qty}`")
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
            show_rtl_table(df_disp, use_container_width=True, hide_index=True)
            st.markdown(apply_table_styling(font_scale2, bg2), unsafe_allow_html=True)
            export_buttons(df_disp, "ارصدة", f"تقرير الأرصدة - {date.today()}")
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
        show_rtl_table(df, use_container_width=True, hide_index=True)
        trans_id = st.number_input("أدخل رقم الحركة للحذف", min_value=1, step=1)
        if st.button("حذف الحركة واسترجاع تأثيرها"):
            ok, msg = delete_transaction(trans_id)
            if ok:
                _clear_all_caches()
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
                _clear_all_caches()
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
            st.info(f"📎 معرّف الملف: `{st.session_state.telegram_file_id}`")
        else:
            st.error(msg)
    if st.button("⬇️ استعادة قاعدة البيانات من تيليجرام"):
        with st.spinner("جاري الاستعادة..."):
            success, msg = telegram_get_latest_db()
        if success:
            _clear_all_caches()
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
        show_rtl_table(df, use_container_width=True, hide_index=True)
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