import sqlite3
import os

from cryptography.fernet import Fernet, InvalidToken
import base64
import hashlib

DB_FILENAME = "notes.db"
ENCRYPTED_DB_FILENAME = "notes_encrypted.db"
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
    cur.execute("SELECT password_hash FROM user WHERE id=1")
    row = cur.fetchone()
    conn.close()
    if row:
        return verify_password(password, row[0])
    return False

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
    return hashlib.compare_digest(calc_hash, stored_hash)

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
