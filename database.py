import sqlite3
import os
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shadowtrace.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_tables():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            ip_address TEXT,
            details TEXT
        )
    """)
    conn.commit()
    conn.close()

def init_db(default_admin_user="admin", default_admin_pass=None):
    """Initializes the database schema and creates default admin if not existing."""
    ensure_tables()
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if admin user exists
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (default_admin_user,))
    user = cursor.fetchone()
    
    created_password = None
    if not user:
        if not default_admin_pass:
            default_admin_pass = secrets.token_urlsafe(12)
            created_password = default_admin_pass
        
        password_hash = generate_password_hash(default_admin_pass, method='scrypt')
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (default_admin_user, password_hash)
        )
        conn.commit()
        log_security_event("SYSTEM_INIT", "127.0.0.1", f"Admin user '{default_admin_user}' initialized.")
    elif default_admin_pass:
        # Update admin password if explicitly specified in environment
        password_hash = generate_password_hash(default_admin_pass, method='scrypt')
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (password_hash, default_admin_user)
        )
        conn.commit()
        log_security_event("SYSTEM_UPDATE", "127.0.0.1", f"Admin password updated from environment.")
        
    conn.close()
    return created_password

def verify_credentials(username, password):
    """Verifies username and password securely."""
    ensure_tables()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user and check_password_hash(user["password_hash"], password):
        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"]
        }
    return None

def log_security_event(event_type, ip_address, details):
    """Logs security relevant actions (logins, buffer resets, unauthorized access)."""
    try:
        ensure_tables()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (event_type, ip_address, details) VALUES (?, ?, ?)",
            (event_type, ip_address, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SECURITY LOG ERROR] {e}")
