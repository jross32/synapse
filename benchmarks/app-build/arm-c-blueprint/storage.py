import sqlite3
import secrets
import hashlib
import time
from passwords import hash_password, verify_password

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password_hash TEXT,
            created_at INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            distance_km REAL,
            date TEXT,
            created_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def create_session(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    token = secrets.token_urlsafe()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
        
    cursor.execute("INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)", 
                   (token_hash, user_id, int(time.time())))
    conn.commit()
    conn.close()
    return token

def list_records(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name, distance_km, date FROM trails WHERE user_id = ?", (user_id,))
    records = cursor.fetchall()
    
    conn.close()
    return [{'id': r[0], 'name': r[1], 'distance_km': r[2], 'date': r[3]} for r in records]

def delete_record(record_id, user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM trails WHERE user_id = ? AND id = ?", (user_id, record_id))
    conn.commit()
    conn.close()

def create_user(email, password_hash):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise ValueError("Email already exists")
        
        created_at = int(time.time())
        
        cursor.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)", 
                       (email, password_hash, created_at))
        conn.commit()
    finally:
        conn.close()

def add_record(user_id, name, distance_km, date):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    created_at = int(time.time())
    
    cursor.execute("INSERT INTO trails (user_id, name, distance_km, date, created_at) VALUES (?, ?, ?, ?, ?)", 
                   (user_id, name, distance_km, date, created_at))
    conn.commit()

    record_id = cursor.lastrowid
    conn.close()
    return {'id': record_id, 'name': name, 'distance_km': distance_km, 'date': date}

def get_user_by_email(email):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    user_id = cursor.fetchone()
    
    if not user_id:
        raise ValueError("User does not exist")
    
    conn.close()
    return {'id': user_id[0], 'email': email}

def user_id_for_token(token):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cursor.execute("SELECT user_id FROM sessions WHERE token_hash = ?", (token_hash,))
    user_id = cursor.fetchone()
    
    if not user_id:
        raise ValueError("Invalid token")
    
    conn.close()
    return {'id': user_id[0]}

def delete_session(token):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cursor.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    conn.commit()
    conn.close()