import sqlite3
from pathlib import Path
import secrets
import hashlib
import time

DB_PATH = Path(__file__).parent / "trailmark.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                distance_km REAL NOT NULL,
                date TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()

def create_user(email: str, password_hash: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)',
                           (email, password_hash, time.time()))
            user_id = cursor.lastrowid
            conn.commit()
            return user_id
        except sqlite3.IntegrityError:
            raise ValueError("Email already exists")

def get_user_by_email(email: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, email, password_hash, created_at FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        if user:
            return {'id': user[0], 'email': user[1], 'password_hash': user[2], 'created_at': user[3]}
        return None

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(16)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)',
                       (token_hash, user_id, time.time()))
        conn.commit()
        return token

def user_id_for_token(token: str) -> int | None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        cursor.execute('SELECT user_id FROM sessions WHERE token_hash = ?', (token_hash,))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None

def delete_session(token: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        cursor.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash,))
        conn.commit()

def add_trail(user_id: int, name: str, distance_km: float, date: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO trails (user_id, name, distance_km, date, created_at) VALUES (?, ?, ?, ?, ?)',
                       (user_id, name, distance_km, date, time.time()))
        trail_id = cursor.lastrowid
        conn.commit()
        return {'id': trail_id, 'name': name, 'distance_km': distance_km, 'date': date}

def list_trails(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, distance_km, date FROM trails WHERE user_id = ?', (user_id,))
        trails = cursor.fetchall()
        return [{'id': trail[0], 'name': trail[1], 'distance_km': trail[2], 'date': trail[3]} for trail in trails]

def delete_trail(trail_id: int, user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM trails WHERE id = ? AND user_id = ?', (trail_id, user_id))
        deleted_rows = cursor.rowcount
        conn.commit()
        return deleted_rows > 0