# server.py - Flask + Gunicorn server với TeleKillV5 logic
# Chạy: gunicorn server:app --bind 0.0.0.0:5000 --workers 1 --timeout 120 --preload

from flask import Flask, request, jsonify, render_template_string, send_from_directory
import threading
import time
import random
import json
from collections import deque
from dataclasses import dataclass
from typing import Optional, List
import hashlib
import base64

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════
# TeleKillV5 Core - Python implementation
# ═══════════════════════════════════════════════════════════

@dataclass
class TimedPacket:
    raw: bytes
    timestamp: int
    payload_len: int

class TeleKillV5:
    def __init__(self):
        # Constants (bitwise obfuscated)
        self.BUF_MAX = (0x13 << 8) + 0x88  # 5000
        self.DMG_BUF_MAX = (0x0B << 8) + 0xB8  # 3000
        self.SIZE_THRESHOLD_1 = (0x20 + 0x08)  # 40
        self.SIZE_THRESHOLD_2 = (0x01 << 8) + 0x2C  # 300
        self.FLUSH_THRESHOLD = (0x01 << 8) + 0x90  # 400
        self.FLUSH_KEEP_COUNT = (0x80 + 0x02)  # 130
        self.DELAY_MIN_DMG = (0x10 + 0x09)  # 25
        self.DELAY_MAX_DMG = (0x20 + 0x1E)  # 50
        self.DELAY_MAX_MOVE = (0x08 + 0x02)  # 10

        self.enabled = False
        self.flush_running = False
        self.movement_queue = deque()
        self.damage_queue = deque()
        self.send_callback = None
        self.antiban = None
        self.lock = threading.Lock()
        self.rng = random.Random()
        self.last_move_packet = None

    def set_send_callback(self, cb):
        self.send_callback = cb
        return self

    def toggle(self):
        with self.lock:
            if not self.enabled:
                self.enabled = True
                self.movement_queue.clear()
                self.damage_queue.clear()
                self.flush_running = False
            else:
                self.enabled = False
                if not self.flush_running:
                    self._start_flush()
        return self.enabled

    def on_packet(self, raw: bytes, payload_len: int) -> bool:
        if raw is None or payload_len <= 0:
            return False

        if self.enabled:
            # Ctrl packet (< 40 bytes): send immediately
            if payload_len <= (self.SIZE_THRESHOLD_1 - 1):
                self._do_send(raw)
                return False

            # Move or Damage packet: buffer
            packet = TimedPacket(raw, int(time.time() * 1000), payload_len)
            if payload_len > self.SIZE_THRESHOLD_2:
                self.damage_queue.append(packet)
            else:
                self.movement_queue.append(packet)
                self.last_move_packet = packet
            return True

        if self.flush_running:
            if (payload_len & 0xFFFF) >= self.SIZE_THRESHOLD_1:
                return True

        return False

    def _do_send(self, raw: bytes):
        if self.send_callback:
            try:
                if self.antiban:
                    # Simple header modification simulation
                    raw = self._modify_packet_header(raw)
                self.send_callback(raw)
            except Exception:
                pass

    def _modify_packet_header(self, raw: bytes) -> bytes:
        # Simulate AntiBan header modification
        if len(raw) > 0:
            ihl = (raw[0] & 0x0F) * 4
            # Just return as-is for simulation
            pass
        return raw

    def _start_flush(self):
        self.flush_running = True
        threading.Thread(target=self._flush_worker, daemon=True).start()

    def _flush_worker(self):
        try:
            # Trim movement queue
            self._trim_queue()

            # Lock final position
            if self.last_move_packet:
                self._do_send(self.last_move_packet.raw)

            # Collect all packets
            all_packets = []
            while self.movement_queue:
                all_packets.append(self.movement_queue.popleft())
            while self.damage_queue:
                all_packets.append(self.damage_queue.popleft())

            if not all_packets:
                self.flush_running = False
                return

            # Sort by timestamp
            all_packets.sort(key=lambda p: p.timestamp)

            # Send with delays
            for i, packet in enumerate(all_packets):
                self._do_send(packet.raw)

                if i < len(all_packets) - 1:
                    original_delay = all_packets[i + 1].timestamp - packet.timestamp
                    if packet.payload_len > self.SIZE_THRESHOLD_2:
                        jitter = self.rng.randint(0, 10)
                        delay = (original_delay * 35 // 100) + jitter
                        delay = max(delay, self.DELAY_MIN_DMG)
                        delay = min(delay, self.DELAY_MAX_DMG)
                    else:
                        jitter = self.rng.randint(0, 4)
                        delay = (original_delay * 10 // 100) + jitter
                        delay = max(delay, 1)
                        delay = min(delay, self.DELAY_MAX_MOVE)

                    time.sleep(delay / 1000.0)

        except Exception:
            pass
        finally:
            time.sleep(0.2)
            self.movement_queue.clear()
            self.damage_queue.clear()
            self.flush_running = False

    def _trim_queue(self):
        # Keep only latest FLUSH_KEEP_COUNT items in movement queue
        while len(self.movement_queue) > self.FLUSH_KEEP_COUNT:
            self.movement_queue.popleft()

    def clear(self):
        with self.lock:
            self.enabled = False
            self.flush_running = False
            self.movement_queue.clear()
            self.damage_queue.clear()

    def get_status(self):
        return {
            'enabled': self.enabled,
            'flush_running': self.flush_running,
            'movement_queue_size': len(self.movement_queue),
            'damage_queue_size': len(self.damage_queue)
        }

# ═══════════════════════════════════════════════════════════
# Flask Server
# ═══════════════════════════════════════════════════════════

telekill = TeleKillV5()

# Packet storage for iPhone to retrieve
packet_buffer = deque(maxlen=1000)
packet_counter = 0

def send_callback(raw: bytes):
    global packet_counter
    packet_counter += 1
    # Store packet for iPhone to fetch (base64 encoded)
    packet_buffer.append({
        'id': packet_counter,
        'data': base64.b64encode(raw).decode('utf-8'),
        'timestamp': int(time.time() * 1000),
        'size': len(raw)
    })

telekill.set_send_callback(send_callback)

# ═══════════════════════════════════════════════════════════
# HTML Menu (gộp vào server)
# ═══════════════════════════════════════════════════════════

HTML_MENU = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DarkAi TeleKill V5 - Hầm Rượu Đen</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0a;
            color: #c8c8c8;
            font-family: 'Courier New', monospace;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: #121212;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            padding: 40px;
            max-width: 800px;
            width: 100%;
            box-shadow: 0 0 40px rgba(0,0,0,0.8);
        }
        h1 {
            color: #8B0000;
            font-size: 28px;
            text-align: center;
            margin-bottom: 10px;
            text-shadow: 0 0 20px rgba(139,0,0,0.3);
        }
        .subtitle {
            text-align: center;
            color: #555;
            font-size: 14px;
            margin-bottom: 30px;
            border-bottom: 1px solid #1a1a1a;
            padding-bottom: 20px;
        }
        .status-bar {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .status-item {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid #0a0a0a;
        }
        .status-item .label { color: #666; }
        .status-item .value { color: #00ff88; font-weight: bold; }
        .status-item .value.off { color: #ff4444; }
        .status-item .value.running { color: #ffaa00; }

        .btn-group {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin: 20px 0;
        }
        .btn {
            padding: 14px 20px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: inherit;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .btn-toggle {
            background: #2a2a2a;
            color: #888;
        }
        .btn-toggle.active {
            background: #8B0000;
            color: #fff;
            box-shadow: 0 0 30px rgba(139,0,0,0.3);
        }
        .btn-toggle:hover { transform: scale(1.02); }

        .btn-clear {
            background: #1a1a1a;
            color: #666;
        }
        .btn-clear:hover {
            background: #2a2a2a;
            color: #fff;
        }

        .btn-flush {
            background: #1a1a1a;
            color: #666;
        }
        .btn-flush:hover {
            background: #2a2a2a;
            color: #ffaa00;
        }

        .btn-refresh {
            background: #0a1a0a;
            color: #00ff88;
        }
        .btn-refresh:hover {
            background: #1a2a1a;
            box-shadow: 0 0 20px rgba(0,255,136,0.1);
        }

        .packet-log {
            background: #0a0a0a;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            max-height: 200px;
            overflow-y: auto;
            border: 1px solid #1a1a1a;
        }
        .packet-log::-webkit-scrollbar {
            width: 4px;
        }
        .packet-log::-webkit-scrollbar-track {
            background: #0a0a0a;
        }
        .packet-log::-webkit-scrollbar-thumb {
            background: #2a2a2a;
            border-radius: 2px;
        }
        .packet-entry {
            padding: 4px 8px;
            font-size: 12px;
            color: #555;
            border-bottom: 1px solid #0a0a0a;
        }
        .packet-entry .pid { color: #666; }
        .packet-entry .psize { color: #444; }
        .packet-entry .ptime { color: #333; }
        .packet-entry .pdata { color: #2a5a2a; font-size: 10px; }

        .footer {
            text-align: center;
            margin-top: 30px;
            color: #222;
            font-size: 12px;
            border-top: 1px solid #0a0a0a;
            padding-top: 20px;
        }

        .api-info {
            background: #0a0a0a;
            border-radius: 6px;
            padding: 10px 15px;
            margin-top: 15px;
            font-size: 12px;
            color: #333;
            border: 1px solid #1a1a1a;
        }
        .api-info code { color: #666; background: #0a0a0a; padding: 2px 6px; border-radius: 3px; }

        @media (max-width: 600px) {
            .container { padding: 20px; }
            .btn-group { grid-template-columns: 1fr; }
            .status-bar { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🍷 DarkAi TeleKill V5</h1>
        <div class="subtitle">Lãnh Chúa Tối Cao — Hầm Rượu Đen Vô Tận</div>

        <div class="status-bar" id="statusBar">
            <div class="status-item">
                <span class="label">Trạng thái</span>
                <span class="value" id="statusEnabled">OFF</span>
            </div>
            <div class="status-item">
                <span class="label">Flush</span>
                <span class="value" id="statusFlush">IDLE</span>
            </div>
            <div class="status-item">
                <span class="label">Movement Queue</span>
                <span class="value" id="statusMoveQ">0</span>
            </div>
            <div class="status-item">
                <span class="label">Damage Queue</span>
                <span class="value" id="statusDmgQ">0</span>
            </div>
        </div>

        <div class="btn-group">
            <button class="btn btn-toggle" id="btnToggle" onclick="toggleTeleKill()">
                🔴 BẬT
            </button>
            <button class="btn btn-clear" onclick="clearTeleKill()">
                🗑️ CLEAR
            </button>
            <button class="btn btn-flush" onclick="flushTeleKill()">
                ⚡ FLUSH NOW
            </button>
            <button class="btn btn-refresh" onclick="refreshStatus()">
                🔄 REFRESH
            </button>
        </div>

        <div class="api-info">
            <strong>📱 iPhone API:</strong><br>
            <code>GET /api/status</code> — Lấy trạng thái hiện tại<br>
            <code>POST /api/toggle</code> — Bật/Tắt<br>
            <code>POST /api/flush</code> — Xả hàng đợi<br>
            <code>GET /api/packets?limit=10</code> — Lấy packet gần đây<br>
            <code>POST /api/packet</code> — Gửi packet (json: {"data": "base64", "size": 123})
        </div>

        <div class="packet-log" id="packetLog">
            <div style="color:#222;text-align:center;padding:20px;">⏳ Đợi packet...</div>
        </div>

        <div class="footer">
            DarkAi🇻🇳 — Rót tri thức, không giới hạn
        </div>
    </div>

    <script>
        let autoRefresh = null;

        async function toggleTeleKill() {
            try {
                const resp = await fetch('/api/toggle', { method: 'POST' });
                const data = await resp.json();
                updateStatus(data);
            } catch(e) {
                console.error('Toggle error:', e);
            }
        }

        async function clearTeleKill() {
            try {
                const resp = await fetch('/api/clear', { method: 'POST' });
                const data = await resp.json();
                updateStatus(data);
            } catch(e) {
                console.error('Clear error:', e);
            }
        }

        async function flushTeleKill() {
            try {
                const resp = await fetch('/api/flush', { method: 'POST' });
                const data = await resp.json();
                updateStatus(data);
            } catch(e) {
                console.error('Flush error:', e);
            }
        }

        async function refreshStatus() {
            try {
                const resp = await fetch('/api/status');
                const data = await resp.json();
                updateStatus(data);
            } catch(e) {
                console.error('Status error:', e);
            }
        }

        async function loadPackets() {
            try {
                const resp = await fetch('/api/packets?limit=20');
                const data = await resp.json();
                renderPackets(data.packets || []);
            } catch(e) {
                console.error('Packets error:', e);
            }
        }

        function updateStatus(data) {
            const enabled = document.getElementById('statusEnabled');
            const flush = document.getElementById('statusFlush');
            const moveQ = document.getElementById('statusMoveQ');
            const dmgQ = document.getElementById('statusDmgQ');
            const btn = document.getElementById('btnToggle');

            enabled.textContent = data.enabled ? '🟢 ON' : '🔴 OFF';
            enabled.className = 'value' + (data.enabled ? '' : ' off');

            flush.textContent = data.flush_running ? '⚡ RUNNING' : 'IDLE';
            flush.className = 'value' + (data.flush_running ? ' running' : '');

            moveQ.textContent = data.movement_queue_size || 0;
            dmgQ.textContent = data.damage_queue_size || 0;

            btn.textContent = data.enabled ? '⏹️ TẮT' : '🔴 BẬT';
            btn.className = 'btn btn-toggle' + (data.enabled ? ' active' : '');
        }

        function renderPackets(packets) {
            const log = document.getElementById('packetLog');
            if (!packets || packets.length === 0) {
                log.innerHTML = '<div style="color:#222;text-align:center;padding:20px;">📭 Không có packet</div>';
                return;
            }

            let html = '';
            for (const p of packets) {
                const time = new Date(p.timestamp).toLocaleTimeString();
                const preview = p.data ? p.data.substring(0, 20) + '...' : '';
                html += `<div class="packet-entry">
                    <span class="pid">#${p.id}</span>
                    <span class="ptime">${time}</span>
                    <span class="psize">[${p.size} bytes]</span>
                    <span class="pdata">${preview}</span>
                </div>`;
            }
            log.innerHTML = html;
        }

        // Auto refresh every 2 seconds
        setInterval(() => {
            refreshStatus();
            loadPackets();
        }, 2000);

        // Initial load
        refreshStatus();
        loadPackets();
    </script>
</body>
</html>
'''

# ═══════════════════════════════════════════════════════════
# API Routes
# ═══════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template_string(HTML_MENU)

@app.route('/api/status')
def api_status():
    status = telekill.get_status()
    status['packet_count'] = packet_counter
    return jsonify(status)

@app.route('/api/toggle', methods=['POST'])
def api_toggle():
    telekill.toggle()
    return jsonify(telekill.get_status())

@app.route('/api/clear', methods=['POST'])
def api_clear():
    telekill.clear()
    return jsonify(telekill.get_status())

@app.route('/api/flush', methods=['POST'])
def api_flush():
    if telekill.enabled:
        # Disable to trigger flush
        telekill.enabled = False
        if not telekill.flush_running:
            telekill._start_flush()
    return jsonify(telekill.get_status())

@app.route('/api/packets')
def api_packets():
    limit = request.args.get('limit', default=20, type=int)
    packets = list(packet_buffer)[-limit:]
    return jsonify({
        'packets': packets,
        'total': packet_counter,
        'buffer_size': len(packet_buffer)
    })

@app.route('/api/packet', methods=['POST'])
def api_packet():
    """iPhone gửi packet lên server"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400

    raw_b64 = data.get('data')
    size = data.get('size', 0)

    if not raw_b64:
        return jsonify({'error': 'Missing data field'}), 400

    try:
        raw = base64.b64decode(raw_b64)
        payload_len = size if size > 0 else len(raw)

        # Process through TeleKill
        buffered = telekill.on_packet(raw, payload_len)

        return jsonify({
            'status': 'processed',
            'buffered': buffered,
            'size': len(raw),
            'enabled': telekill.enabled
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/packet/raw', methods=['POST'])
def api_packet_raw():
    """iPhone gửi packet raw (binary)"""
    raw = request.data
    if not raw:
        return jsonify({'error': 'No data'}), 400

    buffered = telekill.on_packet(raw, len(raw))
    return jsonify({
        'status': 'processed',
        'buffered': buffered,
        'size': len(raw),
        'enabled': telekill.enabled
    })

@app.route('/api/stats')
def api_stats():
    return jsonify({
        'total_packets': packet_counter,
        'buffer_size': len(packet_buffer),
        'status': telekill.get_status(),
        'uptime': time.time() - app.config.get('start_time', time.time())
    })

# ═══════════════════════════════════════════════════════════
# Gunicorn entry point
# ═══════════════════════════════════════════════════════════

app.config['start_time'] = time.time()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)