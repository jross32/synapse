"""A correct storage module, used as the positive control for the storage scenario.

Named `storage.db` on purpose: that is the filename the local model actually chose, and
the one the scenario's original three-guess cleanup missed - which made every repair attempt
after the first fail on a duplicate email that no fix to the module could clear.
"""
import hashlib
import secrets
import sqlite3

DB = "storage.db"


def _conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL, amount REAL NOT NULL, date TEXT NOT NULL);""")
    conn.commit()
    conn.close()


def create_user(email, password_hash):
    conn = _conn()
    try:
        cur = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                           (email, password_hash))
        conn.commit()
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        raise ValueError("that email is already registered")
    finally:
        conn.close()


def get_user_by_email(email):
    conn = _conn()
    row = conn.execute("SELECT id, email, password_hash FROM users WHERE email = ?",
                       (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    conn = _conn()
    conn.execute("INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)",
                 (hashlib.sha256(token.encode()).hexdigest(), int(user_id)))
    conn.commit()
    conn.close()
    return token


def user_id_for_token(token):
    conn = _conn()
    row = conn.execute("SELECT user_id FROM sessions WHERE token_hash = ?",
                       (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    conn.close()
    return int(row["user_id"]) if row else None


def delete_session(token):
    conn = _conn()
    conn.execute("DELETE FROM sessions WHERE token_hash = ?",
                 (hashlib.sha256(token.encode()).hexdigest(),))
    conn.commit()
    conn.close()


def add_record(user_id, title, amount, date):
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO records (user_id, title, amount, date) VALUES (?, ?, ?, ?)",
        (int(user_id), title, float(amount), date))
    conn.commit()
    rid = int(cur.lastrowid)
    conn.close()
    return {"id": rid, "title": title, "amount": float(amount), "date": date}


def list_records(user_id):
    conn = _conn()
    rows = conn.execute(
        "SELECT id, title, amount, date FROM records WHERE user_id = ? ORDER BY id DESC",
        (int(user_id),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_record(record_id, user_id):
    conn = _conn()
    cur = conn.execute("DELETE FROM records WHERE id = ? AND user_id = ?",
                       (int(record_id), int(user_id)))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted

