import sqlite3
import secrets
import hashlib
import time
from passwords import hash_password, verify_password

def create_session(email):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        user_id = cursor.fetchone()
        if not user_id:
            raise ValueError("User does not exist")
        token = secrets.token_urlsafe()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        cursor.execute("INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)", (token_hash, user_id[0], time.time()))
        conn.commit()
    finally:
        conn.close()
    return token

def list_records(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, amount, date FROM records WHERE user_id = ?", (user_id,))
    records = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'title': r[1], 'amount': r[2], 'date': r[3]} for r in records]

def delete_record(user_id, record_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM records WHERE user_id = ? AND id = ?", (user_id, record_id))
    conn.commit()
    conn.close()

def create_user(email, password):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise ValueError("Email already exists")
        password_hash = hash_password(password)
        cursor.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)", (email, password_hash, time.time()))
        conn.commit()
    finally:
        conn.close()

def add_record(user_id, title, amount, date):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO records (user_id, title, amount, date, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, title, amount, date, time.time()))
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return {'id': record_id, 'title': title, 'amount': amount, 'date': date}