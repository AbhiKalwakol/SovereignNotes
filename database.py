import sqlite3
import os

from cryptography.fernet import Fernet, InvalidToken
import base64
import hashlib
import hmac
from typing import Any, Optional
import time
from pathlib import Path

APP_NAME = "SovereignNotes"

def _data_dir() -> Path:
    """
    Store user data OUTSIDE the repo so nothing private is accidentally committed.
    Windows: %APPDATA%\\SovereignNotes
    Fallback: ~/.sovereignnotes
    """
    appdata = os.getenv("APPDATA")
    if appdata:
        d = Path(appdata) / APP_NAME
    else:
        d = Path.home() / ".sovereignnotes"
    d.mkdir(parents=True, exist_ok=True)
    return d

DB_FILENAME = str(_data_dir() / "notes.db")
ENCRYPTED_DB_FILENAME = str(_data_dir() / "notes_encrypted.db")
KEY_DERIVATION_SALT = b"notetaking_salt"  # Use a constant or (better) persist a random one on first run

def derive_key(password: str, salt: bytes = KEY_DERIVATION_SALT) -> bytes:
    # Derive a secret key from the password
    kdf = hashlib.pbkdf2_hmac(
        "sha256", 
        password.encode(), 
        salt, 
        100_000, 
        dklen=32
    )
    return base64.urlsafe_b64encode(kdf)

def init_db():
    conn = sqlite3.connect(DB_FILENAME)
    cur = conn.cursor()
    # Create table for notes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Table for user (1 user: password hash)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY,
            password_hash TEXT NOT NULL
        );
    """)

    # App settings (e.g., chosen AI model/provider)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    # Mood check-ins
    cur.execute("""
        CREATE TABLE IF NOT EXISTS moods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            mood_score INTEGER NOT NULL,
            mood TEXT
        );
    """)

    # Feelings/thoughts logs + optional AI insights
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            text TEXT NOT NULL,
            ai_source TEXT,
            ai_json TEXT
        );
    """)

    # Upload metadata + optional extracted text + AI insights
    cur.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename TEXT NOT NULL,
            mime_type TEXT,
            size_bytes INTEGER,
            extracted_text TEXT,
            ai_source TEXT,
            ai_json TEXT
        );
    """)

    # Calendar events / reminders extracted from logs/uploads (single-user)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_date TEXT,                -- ISO date or datetime string
            title TEXT NOT NULL,
            details TEXT,
            source_type TEXT,               -- "log" | "upload" | "manual"
            source_id INTEGER
        );
    """)
    conn.commit()
    conn.close()

def set_password(password: str):
    password_hash = hash_password(password)
    conn = sqlite3.connect(DB_FILENAME)
    cur = conn.cursor()
    # Insert or replace the single user row
    cur.execute("""
        INSERT OR REPLACE INTO user (id, password_hash) VALUES (?, ?)
    """, (1, password_hash))
    conn.commit()
    conn.close()

def authenticate(password: str) -> bool:
    conn = sqlite3.connect(DB_FILENAME)
    cur = conn.cursor()
    try:
        cur.execute("SELECT password_hash FROM user WHERE id=1")
        row = cur.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    if row:
        return verify_password(password, row[0])
    return False

def has_password() -> bool:
    conn = sqlite3.connect(DB_FILENAME)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM user WHERE id=1")
        row = cur.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    return row is not None

def encrypted_db_exists() -> bool:
    return os.path.exists(ENCRYPTED_DB_FILENAME)

def decrypted_db_exists() -> bool:
    return os.path.exists(DB_FILENAME)

def delete_decrypted_db(retries: int = 8, delay_s: float = 0.15) -> bool:
    """
    Windows can keep SQLite files locked briefly (or by other processes).
    Return True if deleted (or didn't exist), False if still locked after retries.
    """
    if not os.path.exists(DB_FILENAME):
        return True

    for i in range(max(1, int(retries))):
        try:
            os.remove(DB_FILENAME)
            return True
        except PermissionError as e:
            time.sleep(delay_s * (i + 1))
        except OSError as e:
            time.sleep(delay_s * (i + 1))

    return False

def delete_all_user_data(retries: int = 8, delay_s: float = 0.15) -> bool:
    """
    Deletes BOTH decrypted and encrypted DB files. Returns True if both are gone.
    """
    ok_plain = delete_decrypted_db(retries=retries, delay_s=delay_s)
    ok_enc = True
    if os.path.exists(ENCRYPTED_DB_FILENAME):
        for i in range(max(1, int(retries))):
            try:
                os.remove(ENCRYPTED_DB_FILENAME)
                ok_enc = True
                break
            except PermissionError:
                ok_enc = False
                time.sleep(delay_s * (i + 1))
            except OSError:
                ok_enc = False
                time.sleep(delay_s * (i + 1))
    return ok_plain and ok_enc and (not os.path.exists(DB_FILENAME)) and (not os.path.exists(ENCRYPTED_DB_FILENAME))

def hash_password(password: str) -> str:
    # Simple salted hash
    salt = KEY_DERIVATION_SALT
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, 200_000
    )
    return base64.b64encode(pw_hash).decode()

def verify_password(password: str, stored_hash: str) -> bool:
    calc_hash = hash_password(password)
    # Secure compare
    return hmac.compare_digest(calc_hash, stored_hash)

def encrypt_database(password: str):
    key = derive_key(password)
    f = Fernet(key)
    if os.path.exists(DB_FILENAME):
        with open(DB_FILENAME, "rb") as file:
            data = file.read()
        encrypted = f.encrypt(data)
        with open(ENCRYPTED_DB_FILENAME, "wb") as file:
            file.write(encrypted)
        os.remove(DB_FILENAME)

def decrypt_database(password: str) -> bool:
    key = derive_key(password)
    f = Fernet(key)
    if os.path.exists(ENCRYPTED_DB_FILENAME):
        with open(ENCRYPTED_DB_FILENAME, "rb") as file:
            encrypted = file.read()
        try:
            data = f.decrypt(encrypted)
        except InvalidToken:
            return False
        with open(DB_FILENAME, "wb") as file:
            file.write(data)
        # Optionally, remove the encrypted file after decryption
        # os.remove(ENCRYPTED_DB_FILENAME)
        return True
    return False

def _get_conn():
    return sqlite3.connect(DB_FILENAME)

def set_setting(key: str, value: str):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key: str) -> Optional[str]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def add_mood(mood_score: int, mood: Optional[str] = None):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO moods (mood_score, mood) VALUES (?, ?)",
        (int(mood_score), mood),
    )
    conn.commit()
    conn.close()

def add_mood_at(iso_datetime: str, mood_score: int, mood: Optional[str] = None):
    """
    Insert a mood entry attributed to a specific date/time.
    iso_datetime: e.g. "2026-03-16" or "2026-03-16T10:30:00"
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO moods (created_at, mood_score, mood) VALUES (?, ?, ?)",
        (iso_datetime, int(mood_score), mood),
    )
    conn.commit()
    conn.close()

def list_moods(limit: int = 50):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, created_at, mood_score, mood FROM moods ORDER BY datetime(created_at) DESC LIMIT ?",
        (int(limit),),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def add_log(text: str, ai_source: Optional[str] = None, ai_json: Optional[str] = None):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (text, ai_source, ai_json) VALUES (?, ?, ?)",
        (text, ai_source, ai_json),
    )
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return log_id

def list_logs(limit: int = 50):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, created_at, text, ai_source, ai_json FROM logs ORDER BY datetime(created_at) DESC LIMIT ?",
        (int(limit),),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def add_upload(
    filename: str,
    mime_type: Optional[str],
    size_bytes: Optional[int],
    extracted_text: Optional[str] = None,
    ai_source: Optional[str] = None,
    ai_json: Optional[str] = None,
):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO uploads (filename, mime_type, size_bytes, extracted_text, ai_source, ai_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (filename, mime_type, size_bytes, extracted_text, ai_source, ai_json),
    )
    upload_id = cur.lastrowid
    conn.commit()
    conn.close()
    return upload_id

def list_uploads(limit: int = 50):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, filename, mime_type, size_bytes, extracted_text, ai_source, ai_json
        FROM uploads
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def add_event(event_date: Optional[str], title: str, details: Optional[str], source_type: str, source_id: Optional[int]):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events (event_date, title, details, source_type, source_id) VALUES (?, ?, ?, ?, ?)",
        (event_date, title, details, source_type, source_id),
    )
    conn.commit()
    conn.close()

def list_events(limit: int = 50, upcoming_only: bool = False):
    conn = _get_conn()
    cur = conn.cursor()
    if upcoming_only:
        cur.execute(
            """
            SELECT id, created_at, event_date, title, details, source_type, source_id
            FROM events
            WHERE event_date IS NOT NULL
            ORDER BY event_date ASC
            LIMIT ?
            """,
            (int(limit),),
        )
    else:
        cur.execute(
            """
            SELECT id, created_at, event_date, title, details, source_type, source_id
            FROM events
            ORDER BY COALESCE(event_date, created_at) DESC
            LIMIT ?
            """,
            (int(limit),),
        )
    rows = cur.fetchall()
    conn.close()
    return rows
