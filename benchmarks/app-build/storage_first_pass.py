import sqlite3
import secrets
import hashlib
import time

def init_db():
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE,
                  password_hash TEXT,
                  created_at REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (token_hash TEXT PRIMARY KEY,
                  user_id INTEGER,
                  created_at REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  title TEXT,
                  amount REAL,
                  date TEXT,
                  created_at REAL)''')
    conn.commit()
    conn.close()

def create_user(email, password_hash):
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                  (email, password_hash, time.time()))
        user_id = c.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("Email already exists")
    finally:
        conn.close()
    return user_id

def get_user_by_email(email):
    conn = sqlite3.connect('storage.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, email, password_hash FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    else:
        return None

def create_session(user_id):
    token = secrets.token_urlsafe()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)",
              (token_hash, user_id, time.time()))
    conn.commit()
    conn.close()
    return token

def user_id_for_token(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM sessions WHERE token_hash = ?", (token_hash,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def delete_session(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def add_record(user_id, title, amount, date):
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("INSERT INTO records (user_id, title, amount, date, created_at) VALUES (?, ?, ?, ?, ?)",
              (user_id, title, amount, date, time.time()))
    record_id = c.lastrowid
    conn.commit()
    conn.close()
    return {'id': record_id, 'title': title, 'amount': amount, 'date': date}

def list_records(user_id):
    conn = sqlite3.connect('storage.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, title, amount, date FROM records WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{'id': r['id'], 'title': r['title'], 'amount': r['amount'], 'date': r['date']} for r in rows]

def delete_record(record_id, user_id):
    conn = sqlite3.connect('storage.db')
    c = conn.cursor()
    c.execute("DELETE FROM records WHERE id = ? AND user_id = ?", (record_id, user_id))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted