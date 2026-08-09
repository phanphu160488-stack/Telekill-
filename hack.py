# hack.py - TeleKill V5 Dark Neon
# UI đẹp + API đơn giản GET/POST

from flask import Flask, render_template_string, request, jsonify
from flask_session import Session
import os
import random
import time
import threading
import base64
import secrets
from datetime import datetime
from collections import deque
import requests as _req_tg

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CẤU HÌNH
# ═══════════════════════════════════════════════════════════════════════════════

app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './flask_session'
Session(app)

SERVER_START_TIME = datetime.now()
SERVER_UUID = secrets.token_hex(6)

# ═══════════════════════════════════════════════════════════════════════════════
# TELEKILL CORE
# ═══════════════════════════════════════════════════════════════════════════════

class TeleKillCore:
    def __init__(self):
        self.enabled = False
        self.flush_running = False
        self.move_queue = deque(maxlen=10000)
        self.damage_queue = deque(maxlen=10000)
        self.packet_count = 0
        self.total_flushed = 0
        self.send_callback = None
        self.lock = threading.Lock()
        self.rng = random.Random()
        self.logs = deque(maxlen=200)
        
        # Delay config
        self.delay_min = 50
        self.delay_max = 200
        
        self._log("🔥 TeleKill V5 Dark Neon khởi tạo")

    def set_send_callback(self, cb):
        self.send_callback = cb
        return self

    def _log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        self.logs.append(log_msg)
        print(f"[TeleKill] {log_msg}")

    def start(self):
        with self.lock:
            if not self.enabled:
                self.enabled = True
                self._log("▶️ START - Bật TeleKill")
                return True
            return False

    def stop(self):
        with self.lock:
            if self.enabled:
                self.enabled = False
                total = len(self.move_queue) + len(self.damage_queue)
                self._log(f"⏹️ STOP - Flush {total} packets")
                if not self.flush_running and total > 0:
                    self._start_flush()
                return True
            return False

    def on_packet(self, raw: bytes, payload_len: int) -> bool:
        if raw is None or payload_len <= 0:
            return False

        self.packet_count += 1

        if not self.enabled:
            if self.flush_running:
                return True
            self._do_send(raw)
            return False

        # Buffer packet
        packet = Packet(raw, int(time.time() * 1000), payload_len, self.packet_count)
        
        if payload_len > 60:
            self.damage_queue.append(packet)
            self._log(f"💥 DAMAGE #{packet.id} [{payload_len}b] → {len(self.damage_queue)}")
        else:
            self.move_queue.append(packet)
            self._log(f"🚶 MOVE #{packet.id} [{payload_len}b] → {len(self.move_queue)}")

        return True

    def _do_send(self, raw: bytes):
        if self.send_callback:
            try:
                self.send_callback(raw)
            except Exception as e:
                self._log(f"❌ Lỗi gửi: {e}")

    def _start_flush(self):
        if self.flush_running:
            return
        self.flush_running = True
        threading.Thread(target=self._flush_worker, daemon=True).start()

    def _flush_worker(self):
        try:
            self._log("🚀 BẮT ĐẦU FLUSH...")
            start = time.time()
            
            all_packets = []
            while self.move_queue:
                all_packets.append(self.move_queue.popleft())
            while self.damage_queue:
                all_packets.append(self.damage_queue.popleft())
            
            total = len(all_packets)
            if total == 0:
                self.flush_running = False
                return

            all_packets.sort(key=lambda p: p.timestamp)
            
            total_delay = 0
            for i, p in enumerate(all_packets):
                self._do_send(p.raw)
                self.total_flushed += 1
                
                if i < total - 1:
                    delay = self.rng.randint(self.delay_min, self.delay_max)
                    total_delay += delay
                    time.sleep(delay / 1000.0)

            elapsed = (time.time() - start) * 1000
            self._log(f"✅ FLUSH: {total} packets, {elapsed:.0f}ms, avg {total_delay/total:.0f}ms")

        except Exception as e:
            self._log(f"❌ Lỗi flush: {e}")
        finally:
            self.flush_running = False

    def flush_now(self):
        if self.enabled:
            self.enabled = False
        if not self.flush_running:
            self._start_flush()
        return True

    def clear(self):
        with self.lock:
            self.enabled = False
            self.flush_running = False
            self.move_queue.clear()
            self.damage_queue.clear()
            self._log("🗑️ CLEAR - Đã xóa queue")

    def get_status(self):
        with self.lock:
            return {
                'enabled': self.enabled,
                'flush_running': self.flush_running,
                'move_queue': len(self.move_queue),
                'damage_queue': len(self.damage_queue),
                'total_queued': len(self.move_queue) + len(self.damage_queue),
                'packet_count': self.packet_count,
                'total_flushed': self.total_flushed,
                'uptime': str(datetime.now() - SERVER_START_TIME).split('.')[0],
                'uuid': SERVER_UUID
            }

    def get_logs(self, limit=30):
        return list(self.logs)[-limit:]


class Packet:
    __slots__ = ['raw', 'timestamp', 'payload_len', 'id']
    def __init__(self, raw, timestamp, payload_len, id):
        self.raw = raw
        self.timestamp = timestamp
        self.payload_len = payload_len
        self.id = id


# ═══════════════════════════════════════════════════════════════════════════════
# KHỞI TẠO
# ═══════════════════════════════════════════════════════════════════════════════

telekill = TeleKillCore()
packet_buffer = deque(maxlen=500)
packet_counter = 0

def send_callback(raw: bytes):
    global packet_counter
    packet_counter += 1
    packet_buffer.append({
        'id': packet_counter,
        'data': base64.b64encode(raw).decode('utf-8'),
        'size': len(raw),
        'timestamp': int(time.time() * 1000)
    })

telekill.set_send_callback(send_callback)


# ═══════════════════════════════════════════════════════════════════════════════
# HTML - DARK NEON UI ĐẸP
# ═══════════════════════════════════════════════════════════════════════════════

HTML = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔥 TeleKill V5</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0f;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            padding: 20px;
        }
        
        .container {
            max-width: 520px;
            width: 100%;
            background: linear-gradient(145deg, #111118, #0a0a0f);
            border-radius: 28px;
            padding: 32px 28px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.02);
            position: relative;
            overflow: hidden;
        }
        
        .container::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(ellipse at 30% 20%, rgba(139, 0, 0, 0.05), transparent 70%);
            pointer-events: none;
        }
        
        /* Header */
        .header {
            text-align: center;
            margin-bottom: 28px;
            position: relative;
        }
        .header .icon {
            font-size: 42px;
            margin-bottom: 4px;
            display: block;
        }
        .header h1 {
            color: #fff;
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        .header h1 span {
            color: #ff2244;
            text-shadow: 0 0 30px rgba(255, 34, 68, 0.2);
        }
        .header .sub {
            color: #444;
            font-size: 13px;
            margin-top: 2px;
            letter-spacing: 0.5px;
        }
        .header .uuid {
            color: #222;
            font-size: 11px;
            font-family: monospace;
            margin-top: 4px;
        }
        
        /* Status Card */
        .status-card {
            background: rgba(255, 255, 255, 0.02);
            border-radius: 16px;
            padding: 18px 20px;
            margin-bottom: 20px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
        }
        .status-item {
            text-align: center;
            padding: 4px 0;
        }
        .status-item .label {
            color: #555;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }
        .status-item .value {
            color: #fff;
            font-size: 22px;
            font-weight: 700;
            margin-top: 2px;
        }
        .status-item .value.on { color: #00ff88; text-shadow: 0 0 20px rgba(0, 255, 136, 0.2); }
        .status-item .value.off { color: #ff2244; text-shadow: 0 0 20px rgba(255, 34, 68, 0.15); }
        .status-item .value.running { color: #ffaa00; text-shadow: 0 0 20px rgba(255, 170, 0, 0.15); }
        .status-item .value.small { font-size: 16px; }
        
        /* Main Button */
        .btn-main {
            width: 100%;
            padding: 16px;
            border: none;
            border-radius: 14px;
            font-size: 18px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            letter-spacing: 0.5px;
            position: relative;
            overflow: hidden;
        }
        .btn-main:active { transform: scale(0.97); }
        .btn-main.start {
            background: linear-gradient(135deg, #00cc77, #00aa66);
            color: #fff;
            box-shadow: 0 4px 25px rgba(0, 204, 119, 0.25);
        }
        .btn-main.start:hover { box-shadow: 0 6px 35px rgba(0, 204, 119, 0.35); transform: translateY(-1px); }
        .btn-main.stop {
            background: linear-gradient(135deg, #ff2244, #cc0033);
            color: #fff;
            box-shadow: 0 4px 25px rgba(255, 34, 68, 0.25);
        }
        .btn-main.stop:hover { box-shadow: 0 6px 35px rgba(255, 34, 68, 0.35); transform: translateY(-1px); }
        .btn-main .sub-text {
            display: block;
            font-size: 12px;
            font-weight: 400;
            opacity: 0.7;
            margin-top: 2px;
        }
        
        /* Button Row */
        .btn-row {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 10px;
            margin-top: 14px;
        }
        .btn-sm {
            padding: 12px 8px;
            border: none;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: rgba(255, 255, 255, 0.04);
            color: #888;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }
        .btn-sm:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
        .btn-sm:active { transform: scale(0.95); }
        .btn-sm.flush { color: #ffaa00; }
        .btn-sm.flush:hover { background: rgba(255, 170, 0, 0.1); border-color: rgba(255, 170, 0, 0.15); }
        .btn-sm.clear { color: #ff4444; }
        .btn-sm.clear:hover { background: rgba(255, 68, 68, 0.1); border-color: rgba(255, 68, 68, 0.15); }
        .btn-sm.test { color: #4488ff; }
        .btn-sm.test:hover { background: rgba(68, 136, 255, 0.1); border-color: rgba(68, 136, 255, 0.15); }
        
        /* API Box */
        .api-box {
            margin-top: 18px;
            padding: 14px 16px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            font-size: 12px;
        }
        .api-box .title {
            color: #555;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 8px;
        }
        .api-box code {
            display: inline-block;
            color: #66aaff;
            background: rgba(255, 255, 255, 0.03);
            padding: 2px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-family: monospace;
            margin: 2px 4px 2px 0;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }
        .api-box .method {
            display: inline-block;
            font-size: 10px;
            font-weight: 700;
            padding: 1px 8px;
            border-radius: 3px;
            margin-right: 4px;
        }
        .api-box .method.get { color: #00ff88; background: rgba(0, 255, 136, 0.08); }
        .api-box .method.post { color: #ffaa00; background: rgba(255, 170, 0, 0.08); }
        
        /* Log */
        .log-box {
            margin-top: 14px;
            padding: 12px 14px;
            background: rgba(0, 0, 0, 0.4);
            border-radius: 12px;
            max-height: 140px;
            overflow-y: auto;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            color: #444;
            border: 1px solid rgba(255, 255, 255, 0.03);
        }
        .log-box::-webkit-scrollbar { width: 3px; }
        .log-box::-webkit-scrollbar-track { background: transparent; }
        .log-box::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
        .log-entry { padding: 2px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.02); }
        .log-entry .time { color: #333; }
        .log-entry .msg { color: #666; }
        .log-entry .highlight { color: #88ccff; }
        .log-entry .success { color: #00ff88; }
        .log-entry .error { color: #ff4444; }
        .log-entry .warn { color: #ffaa00; }
        
        .footer {
            text-align: center;
            margin-top: 18px;
            color: #1a1a1a;
            font-size: 10px;
            letter-spacing: 0.5px;
        }
        
        @media (max-width: 480px) {
            .container { padding: 20px 16px; }
            .status-card { grid-template-columns: 1fr 1fr; }
            .btn-row { grid-template-columns: 1fr; }
            .header h1 { font-size: 20px; }
        }
    </style>
</head>
<body>
<div class="container">
    
    <!-- HEADER -->
    <div class="header">
        <span class="icon">🔥</span>
        <h1>Tele<span>Kill</span> V5</h1>
        <div class="sub">Hầm Rượu Đen · Dark Neon</div>
        <div class="uuid">⚡ {{ uuid }} · {{ uptime }}</div>
    </div>
    
    <!-- STATUS -->
    <div class="status-card">
        <div class="status-item">
            <div class="label">📌 Trạng thái</div>
            <div class="value off" id="statusText">OFF</div>
        </div>
        <div class="status-item">
            <div class="label">📦 Queue</div>
            <div class="value small" id="queueText">0</div>
        </div>
        <div class="status-item">
            <div class="label">📤 Flushed</div>
            <div class="value small" id="flushedText">0</div>
        </div>
        <div class="status-item">
            <div class="label">🚶 Move</div>
            <div class="value small" id="moveText">0</div>
        </div>
        <div class="status-item">
            <div class="label">💥 Damage</div>
            <div class="value small" id="damageText">0</div>
        </div>
        <div class="status-item">
            <div class="label">🔄 Flush</div>
            <div class="value small" id="flushText">IDLE</div>
        </div>
    </div>
    
    <!-- MAIN BUTTON -->
    <button class="btn-main start" id="mainBtn" onclick="toggleMain()">
        ▶️ BẬT TELEKILL
        <span class="sub-text">Click để kích hoạt</span>
    </button>
    
    <!-- BUTTON ROW -->
    <div class="btn-row">
        <button class="btn-sm flush" onclick="flushNow()">⚡ Flush</button>
        <button class="btn-sm clear" onclick="clearAll()">🗑️ Clear</button>
        <button class="btn-sm test" onclick="testPackets()">🧪 Test 10</button>
    </div>
    
    <!-- API INFO -->
    <div class="api-box">
        <div class="title">📡 API — hỗ trợ GET / POST</div>
        <div>
            <span class="method post">POST</span><span class="method get">GET</span>
            <code>/api/start</code> <span style="color:#333;">— Bật TeleKill</span>
        </div>
        <div>
            <span class="method post">POST</span><span class="method get">GET</span>
            <code>/api/stop</code> <span style="color:#333;">— Dừng + Flush</span>
        </div>
        <div>
            <span class="method get">GET</span>
            <code>/api/status</code> <span style="color:#333;">— Trạng thái</span>
        </div>
        <div>
            <span class="method post">POST</span>
            <code>/api/packet</code> <span style="color:#333;">— Gửi packet (json)</span>
        </div>
    </div>
    
    <!-- LOG -->
    <div class="log-box" id="logBox">
        <div style="color:#222;text-align:center;padding:10px;">⏳ Đợi log...</div>
    </div>
    
    <div class="footer">DarkAi🇻🇳 · Vô Cực Đen</div>
</div>

<script>
    let isRunning = false;

    // ── Main Toggle ──
    async function toggleMain() {
        if (isRunning) {
            await stop();
        } else {
            await start();
        }
    }

    async function start() {
        try {
            const resp = await fetch('/api/start', { method: 'POST' });
            const data = await resp.json();
            isRunning = data.enabled;
            updateUI(data);
            loadLogs();
        } catch(e) { console.error(e); }
    }

    async function stop() {
        try {
            const resp = await fetch('/api/stop', { method: 'POST' });
            const data = await resp.json();
            isRunning = false;
            updateUI(data);
            loadLogs();
        } catch(e) { console.error(e); }
    }

    async function flushNow() {
        try {
            const resp = await fetch('/api/flush', { method: 'POST' });
            const data = await resp.json();
            updateUI(data);
            loadLogs();
        } catch(e) { console.error(e); }
    }

    async function clearAll() {
        try {
            const resp = await fetch('/api/clear', { method: 'POST' });
            const data = await resp.json();
            updateUI(data);
            loadLogs();
        } catch(e) { console.error(e); }
    }

    async function testPackets() {
        for (let i = 1; i <= 10; i++) {
            const size = 20 + (i * 15) % 180;
            const data = btoa(`TEST_${i}_${Date.now()}_${'x'.repeat(size)}`);
            await fetch('/api/packet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: data, size: data.length })
            });
            await new Promise(r => setTimeout(r, 30));
        }
        refreshStatus();
        loadLogs();
    }

    async function refreshStatus() {
        try {
            const resp = await fetch('/api/status');
            const data = await resp.json();
            updateUI(data);
        } catch(e) { console.error(e); }
    }

    async function loadLogs() {
        try {
            const resp = await fetch('/api/logs?limit=20');
            const data = await resp.json();
            const box = document.getElementById('logBox');
            if (!data.logs || data.logs.length === 0) {
                box.innerHTML = '<div style="color:#222;text-align:center;padding:10px;">📭 Không có log</div>';
                return;
            }
            let html = '';
            for (const log of data.logs) {
                let cls = 'msg';
                if (log.includes('✅')) cls = 'success';
                else if (log.includes('❌')) cls = 'error';
                else if (log.includes('⚠️')) cls = 'warn';
                else if (log.includes('START') || log.includes('BẬT')) cls = 'highlight';
                const time = log.substring(0, 12);
                const msg = log.substring(12);
                html += `<div class="log-entry"><span class="time">${time}</span> <span class="${cls}">${msg}</span></div>`;
            }
            box.innerHTML = html;
            box.scrollTop = box.scrollHeight;
        } catch(e) { console.error(e); }
    }

    function updateUI(data) {
        const status = document.getElementById('statusText');
        const mainBtn = document.getElementById('mainBtn');
        
        isRunning = data.enabled;
        
        if (data.enabled) {
            status.textContent = 'ON';
            status.className = 'value on';
            mainBtn.className = 'btn-main stop';
            mainBtn.innerHTML = '⏹️ TẮT TELEKILL<span class="sub-text">Click để dừng + flush</span>';
        } else {
            status.textContent = 'OFF';
            status.className = 'value off';
            mainBtn.className = 'btn-main start';
            mainBtn.innerHTML = '▶️ BẬT TELEKILL<span class="sub-text">Click để kích hoạt</span>';
        }
        
        document.getElementById('queueText').textContent = data.total_queued || 0;
        document.getElementById('flushedText').textContent = data.total_flushed || 0;
        document.getElementById('moveText').textContent = data.move_queue || 0;
        document.getElementById('damageText').textContent = data.damage_queue || 0;
        
        const flushText = document.getElementById('flushText');
        if (data.flush_running) {
            flushText.textContent = '⚡ RUNNING';
            flushText.className = 'value small running';
        } else {
            flushText.textContent = 'IDLE';
            flushText.className = 'value small';
        }
    }

    // ── Auto refresh ──
    setInterval(() => {
        refreshStatus();
        if (document.getElementById('logBox').innerHTML.includes('Đợi')) {
            loadLogs();
        }
    }, 2000);

    // ── Initial ──
    refreshStatus();
    loadLogs();
</script>
</body>
</html>
'''


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES - API ĐƠN GIẢN
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    status = telekill.get_status()
    return render_template_string(
        HTML,
        uuid=status.get('uuid', SERVER_UUID),
        uptime=status.get('uptime', '0s')
    )


# ── /api/start ── Bật TeleKill (GET + POST) ──
@app.route('/api/start', methods=['GET', 'POST'])
def api_start():
    telekill.start()
    return jsonify(telekill.get_status())


# ── /api/stop ── Dừng + Flush (GET + POST) ──
@app.route('/api/stop', methods=['GET', 'POST'])
def api_stop():
    telekill.stop()
    return jsonify(telekill.get_status())


# ── /api/status ── Trạng thái ──
@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify(telekill.get_status())


# ── /api/flush ── Flush thủ công ──
@app.route('/api/flush', methods=['POST', 'GET'])
def api_flush():
    telekill.flush_now()
    return jsonify(telekill.get_status())


# ── /api/clear ── Clear queue ──
@app.route('/api/clear', methods=['POST', 'GET'])
def api_clear():
    telekill.clear()
    return jsonify(telekill.get_status())


# ── /api/packet ── Gửi packet (POST) ──
@app.route('/api/packet', methods=['POST'])
def api_packet():
    data = request.json
    if not data or 'data' not in data:
        return jsonify({'error': 'Missing data'}), 400
    
    try:
        raw = base64.b64decode(data['data'])
        size = data.get('size', len(raw))
        buffered = telekill.on_packet(raw, size)
        return jsonify({
            'status': 'ok',
            'buffered': buffered,
            'size': len(raw),
            'enabled': telekill.enabled
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── /api/packet/raw ── Gửi packet raw (POST) ──
@app.route('/api/packet/raw', methods=['POST'])
def api_packet_raw():
    raw = request.data
    if not raw:
        return jsonify({'error': 'No data'}), 400
    
    buffered = telekill.on_packet(raw, len(raw))
    return jsonify({
        'status': 'ok',
        'buffered': buffered,
        'size': len(raw),
        'enabled': telekill.enabled
    })


# ── /api/logs ── Lấy logs ──
@app.route('/api/logs', methods=['GET'])
def api_logs():
    limit = request.args.get('limit', default=30, type=int)
    return jsonify({'logs': telekill.get_logs(limit)})


# ── /api/packets ── Lấy packets đã gửi ──
@app.route('/api/packets', methods=['GET'])
def api_packets():
    limit = request.args.get('limit', default=20, type=int)
    packets = list(packet_buffer)[-limit:]
    return jsonify({'packets': packets})


# ── /api/health ── Health check ──
@app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({
        'status': 'healthy',
        'uuid': SERVER_UUID,
        'uptime': str(datetime.now() - SERVER_START_TIME).split('.')[0]
    })


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    os.makedirs('./flask_session', exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    print(f"""
╔════════════════════════════════════════════════════╗
║  🔥 TeleKill V5 Dark Neon                         ║
║  http://0.0.0.0:{port}                            ║
║  UUID: {SERVER_UUID}                             ║
║  API: /api/start | /api/stop                     ║
╚════════════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)