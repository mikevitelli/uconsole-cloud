#!/usr/bin/env python3
"""uConsole Web Dashboard — Flask app with Jinja2 templates."""

import fcntl
import gzip
import io
import os
import pty
import re
import secrets
import select
import struct
import subprocess
import sys
import termios
import threading
import time

from flask import Flask, jsonify, render_template, request, make_response, send_from_directory, redirect, url_for

# ascii_logos may be alongside this file (installed /opt/uconsole/webdash),
# or one level up in the source-tree lib/ dir (dev runs), or in ~/scripts
# on legacy installs.
_app_dir = os.path.dirname(os.path.abspath(__file__))
_lib_dir = os.path.normpath(os.path.join(_app_dir, '..', 'lib'))
for _p in [_app_dir, _lib_dir, os.path.expanduser('~/scripts')]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
from ascii_logos import get_random_logo, get_logo, list_logos

try:
    from flask_socketio import SocketIO
    _HAS_SOCKETIO = True
except ImportError:
    _HAS_SOCKETIO = False

app = Flask(__name__)
app.secret_key = os.environ.get('WEBDASH_SECRET', secrets.token_hex(32))

# --- Terminal PTY via SocketIO ---
socketio = SocketIO(app, cors_allowed_origins=[
    'https://uconsole.local',
    'https://uconsole.cloud',
], async_mode='threading') if _HAS_SOCKETIO else None
_pty_sessions = {}  # sid -> {pid, fd}


def _set_winsize(fd, row, col):
    winsize = struct.pack('HHHH', row, col, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def _pty_reader(sid, fd):
    """Background thread: read PTY output and emit to browser."""
    while True:
        try:
            ready, _, _ = select.select([fd], [], [], 0.05)
            if ready:
                data = os.read(fd, 1024 * 20)
                if not data:
                    break
                if socketio:
                    socketio.emit('pty-output', {'output': data.decode(errors='replace')}, to=sid)
        except OSError:
            break
    if socketio:
        socketio.emit('pty-exit', {}, to=sid)


if _HAS_SOCKETIO:
    @socketio.on('pty-spawn')
    def _on_pty_spawn(data):
        sid = request.sid
        if sid in _pty_sessions:
            return
        if not _is_authenticated():
            socketio.emit('pty-exit', {'error': 'Not authenticated'}, to=sid)
            return
        pid, fd = pty.fork()
        if pid == 0:
            # Child: exec shell
            shell = os.environ.get('SHELL', '/bin/bash')
            os.execvp(shell, [shell])
        else:
            _set_winsize(fd, data.get('rows', 24), data.get('cols', 80))
            _pty_sessions[sid] = {'pid': pid, 'fd': fd}
            t = threading.Thread(target=_pty_reader, args=(sid, fd), daemon=True)
            t.start()

    @socketio.on('pty-input')
    def _on_pty_input(data):
        sess = _pty_sessions.get(request.sid)
        if sess:
            try:
                os.write(sess['fd'], data['input'].encode())
            except OSError:
                pass

    @socketio.on('pty-resize')
    def _on_pty_resize(data):
        sess = _pty_sessions.get(request.sid)
        if sess:
            _set_winsize(sess['fd'], data.get('rows', 24), data.get('cols', 80))

    @socketio.on('disconnect')
    def _on_disconnect():
        sess = _pty_sessions.pop(request.sid, None)
        if sess:
            try:
                os.kill(sess['pid'], 9)
            except OSError:
                pass
            try:
                os.waitpid(sess['pid'], 0)
            except (OSError, ChildProcessError):
                pass
            try:
                os.close(sess['fd'])
            except OSError:
                pass

# --- Auth config ---
import json as _json_mod

try:
    import bcrypt as _bcrypt
except ImportError:
    _bcrypt = None

_USER_CONF_PATH = os.path.join(os.path.expanduser('~'),
                               '.config', 'uconsole', 'config.json')
_USER_CONF_DEFAULT = os.path.join(os.path.expanduser('~'),
                                  '.config', 'uconsole', 'config.json.default')

def _load_user_conf():
    for path in (_USER_CONF_PATH, _USER_CONF_DEFAULT):
        try:
            with open(path) as f:
                return _json_mod.load(f)
        except (FileNotFoundError, _json_mod.JSONDecodeError):
            continue
    return {}

def _save_user_conf(data):
    os.makedirs(os.path.dirname(_USER_CONF_PATH), exist_ok=True)
    with open(_USER_CONF_PATH, 'w') as f:
        _json_mod.dump(data, f, indent=2)
        f.write('\n')

def _get_password_hash():
    return _load_user_conf().get('webdash_password_hash')

def _password_is_set():
    h = _get_password_hash()
    return h is not None and h != ''

def _check_password(password):
    h = _get_password_hash()
    if not h or not _bcrypt:
        return False
    if isinstance(h, str):
        h = h.encode('utf-8')
    return _bcrypt.checkpw(password.encode('utf-8'), h)

def _hash_password(password):
    if not _bcrypt:
        raise RuntimeError('bcrypt not installed — run: pip3 install bcrypt')
    return _bcrypt.hashpw(password.encode('utf-8'), _bcrypt.gensalt()).decode('utf-8')

SESSION_DAYS = 30
SESSION_COOKIE = 'webdash_session'

# Server-side session store: token -> expiry timestamp
_active_sessions = {}

def _make_token():
    """Create a random session token and register it server-side."""
    token = secrets.token_hex(32)
    _active_sessions[token] = time.time() + SESSION_DAYS * 86400
    return token

def _is_authenticated():
    token = request.cookies.get(SESSION_COOKIE)
    if not token or token not in _active_sessions:
        return False
    if time.time() > _active_sessions[token]:
        _active_sessions.pop(token, None)
        return False
    return True

def _invalidate_session(token):
    _active_sessions.pop(token, None)


# LOGIN_HTML — extracted to templates/login.html

# SET_PASSWORD_HTML — extracted to templates/set_password.html



@app.route('/login', methods=['GET', 'POST'])
def login():
    if not _password_is_set():
        return redirect('/setup-password')
    if request.method == 'POST':
        if _bcrypt is None:
            return render_template('login.html',
                error='Server error: bcrypt not installed (pip3 install bcrypt)'), 500
        p = request.form.get('password', '')
        if _check_password(p):
            token = _make_token()
            resp = redirect('/')
            resp.set_cookie(SESSION_COOKIE, token,
                            max_age=SESSION_DAYS * 86400, httponly=True,
                            secure=True, samesite='Lax')
            return resp
        return render_template('login.html', error='Wrong password'), 401
    return render_template('login.html', error=None)


@app.route('/setup-password', methods=['GET'])
def setup_password_page():
    if _password_is_set():
        return redirect('/login')
    return render_template('set_password.html', error=None)


@app.route('/api/set-password', methods=['POST'])
def api_set_password():
    if _password_is_set():
        return redirect('/login')
    pw = request.form.get('password', '')
    confirm = request.form.get('confirm', '')
    if len(pw) < 4:
        return render_template('set_password.html', error='Password must be at least 4 characters'), 400
    if pw != confirm:
        return render_template('set_password.html', error='Passwords do not match'), 400
    h = _hash_password(pw)
    conf = _load_user_conf()
    conf['webdash_password_hash'] = h
    _save_user_conf(conf)
    token = _make_token()
    resp = redirect('/')
    resp.set_cookie(SESSION_COOKIE, token,
                    max_age=SESSION_DAYS * 86400, httponly=True,
                    secure=True, samesite='Lax')
    return resp


@app.route('/api/change-password', methods=['POST'])
def api_change_password():
    if not _is_authenticated():
        return jsonify({'error': 'Not authenticated'}), 401
    pw = request.form.get('password', '')
    confirm = request.form.get('confirm', '')
    if len(pw) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    if pw != confirm:
        return jsonify({'error': 'Passwords do not match'}), 400
    h = _hash_password(pw)
    conf = _load_user_conf()
    conf['webdash_password_hash'] = h
    _save_user_conf(conf)
    return jsonify({'ok': True})


@app.route('/logout')
def logout():
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _invalidate_session(token)
    resp = redirect('/login')
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# --- Rate limiting for public endpoints ---
_rate_buckets = {}  # ip -> (count, window_start)
_RATE_LIMIT = 30
_RATE_WINDOW = 60


def _is_local_ip(ip):
    """Check if IP is in a private range (RFC 1918)."""
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return (a == 10 or
            (a == 172 and 16 <= b <= 31) or
            (a == 192 and b == 168) or
            ip == '127.0.0.1')


def _check_rate_limit(ip):
    """Returns True if request is allowed, False if rate limited."""
    now = time.time()
    count, start = _rate_buckets.get(ip, (0, now))
    if now - start > _RATE_WINDOW:
        _rate_buckets[ip] = (1, now)
        return True
    if count >= _RATE_LIMIT:
        return False
    _rate_buckets[ip] = (count + 1, start)
    return True


_PUBLIC_PATHS = frozenset((
    '/login', '/setup-password', '/api/set-password',
    '/favicon.png', '/apple-touch-icon.png',
    '/apple-touch-icon-precomposed.png', '/uconsole.crt',
    '/uConsole.gif', '/manifest.json', '/sw.js',
))
_LOCAL_ONLY_PATHS = frozenset((
    '/api/public/stats',
    '/api/esp32/push', '/api/esp32',
    '/api/gps/push', '/api/gps',
    '/api/sdr/push', '/api/sdr',
    '/api/lora/push', '/api/lora',
    '/api/battery-test/chart', '/api/battery-test/start',
))


@app.before_request
def require_auth():
    if request.path in _PUBLIC_PATHS:
        return
    if request.path in _LOCAL_ONLY_PATHS:
        client_ip = request.headers.get('X-Real-IP', request.remote_addr)
        if not _is_local_ip(client_ip):
            return jsonify({'error': 'Forbidden'}), 403
        if not _check_rate_limit(client_ip):
            return jsonify({'error': 'Rate limit exceeded'}), 429
        return
    if not _is_authenticated():
        return redirect('/login')


@app.route('/favicon.png')
@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def favicon():
    return send_from_directory(APP_DIR, 'favicon.png', mimetype='image/png')


@app.route('/uConsole.gif')
def login_gif():
    return send_from_directory(APP_DIR, 'uConsole.gif', mimetype='image/gif')


@app.route('/uconsole.crt')
def cert_download():
    return send_from_directory(APP_DIR, 'uconsole.crt',
                               mimetype='application/x-x509-ca-cert',
                               as_attachment=True)


@app.route('/manifest.json')
def manifest():
    import json as _json
    m = {
        "name": "uConsole Dashboard",
        "short_name": "uConsole",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#000000",
        "icons": [
            {"src": "/favicon.png", "sizes": "180x180", "type": "image/png"}
        ]
    }
    r = app.response_class(_json.dumps(m), mimetype='application/manifest+json'); r.headers['Cache-Control'] = 'no-cache, no-store'; return r


@app.route('/sw.js')
def service_worker():
    # Invalidate cache when app code OR any template changes.
    mtime = int(os.path.getmtime(__file__))
    try:
        tpl_dir = os.path.join(os.path.dirname(__file__), 'templates')
        for entry in os.scandir(tpl_dir):
            if entry.is_file():
                mtime = max(mtime, int(entry.stat().st_mtime))
    except OSError:
        pass
    sw = "var CACHE='webdash-%d';\n" % mtime + r'''
var PRECACHE=['/favicon.png','/manifest.json'];
self.addEventListener('install',function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(PRECACHE)}));
  self.skipWaiting();
});
self.addEventListener('activate',function(e){
  e.waitUntil(caches.keys().then(function(n){
    return Promise.all(n.filter(function(k){return k!==CACHE}).map(function(k){return caches.delete(k)}));
  }));
  self.clients.claim();
});
self.addEventListener('fetch',function(e){
  var u=new URL(e.request.url);
  /* never cache auth, API, socket.io, or live-data pages */
  if(u.pathname==='/'||u.pathname==='/login'||u.pathname==='/logout'){e.respondWith(fetch(e.request));return;}
  if(u.pathname==='/wardrive'){e.respondWith(fetch(e.request));return;}
  if(u.pathname.indexOf('/api/')===0||u.pathname.indexOf('/socket.io/')===0){e.respondWith(fetch(e.request));return;}
  e.respondWith(caches.match(e.request).then(function(r){
    return r||fetch(e.request).then(function(resp){
      /* only cache 200 OK responses */
      if(resp.status===200){var cl=resp.clone();caches.open(CACHE).then(function(c){c.put(e.request,cl)});}
      return resp;
    });
  }));
});'''
    return app.response_class(sw, mimetype='application/javascript',
                              headers={'Service-Worker-Allowed': '/'})


_WARDRIVE_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
    "https://unpkg.com https://cdn.tailwindcss.com "
    "https://cdn.jsdelivr.net; "
    "script-src-elem 'self' 'unsafe-inline' "
    "https://unpkg.com https://cdn.tailwindcss.com "
    "https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com "
    "https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "style-src-elem 'self' 'unsafe-inline' https://unpkg.com "
    "https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "worker-src 'self' blob:; "
    "child-src blob:; "
    "connect-src 'self' wss://uconsole.local "
    "https://*.tile.openstreetmap.org "
    "https://*.basemaps.cartocdn.com "
    "https://basemaps.cartocdn.com; "
    "img-src 'self' data: blob: "
    "https://*.tile.openstreetmap.org "
    "https://*.basemaps.cartocdn.com "
    "https://basemaps.cartocdn.com "
    "https://unpkg.com "
    "https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com"
)

_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self' wss://uconsole.local; "
    "img-src 'self' data:; "
    "font-src 'self'"
)


@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    # Relax CSP for the wardrive map page to allow Leaflet + OSM tiles.
    if request.path == '/wardrive':
        response.headers['Content-Security-Policy'] = _WARDRIVE_CSP
    else:
        response.headers['Content-Security-Policy'] = _DEFAULT_CSP
    return response


@app.after_request
def compress_response(response):
    """Gzip responses when client supports it."""
    if (response.status_code < 200 or response.status_code >= 300
            or 'Content-Encoding' in response.headers
            or 'gzip' not in request.headers.get('Accept-Encoding', '')
            or response.direct_passthrough
            or len(response.get_data()) < 500):
        return response
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as gz:
        gz.write(response.get_data())
    response.set_data(buf.getvalue())
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(response.get_data())
    return response
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Scripts directory: env override, else sibling ../scripts/ relative to webdash
SCRIPTS_DIR = os.environ.get('UCONSOLE_SCRIPTS_DIR',
    os.path.join(os.path.dirname(APP_DIR), 'scripts'))

# Package mode: system-level services, sudo for systemctl
PACKAGE_MODE = os.path.isdir('/opt/uconsole/scripts')

# previous CPU sample for delta calculation
_prev_cpu = None
_prev_cpu_time = 0


def read_sysfs(path, default=''):
    try:
        with open(path) as f:
            return f.read().strip()
    except (IOError, OSError):
        return default


def get_cpu_usage():
    global _prev_cpu, _prev_cpu_time
    with open('/proc/stat') as f:
        parts = f.readline().split()
    user, nice, system, idle, iowait, irq, softirq = (int(x) for x in parts[1:8])
    total = user + nice + system + idle + iowait + irq + softirq
    busy = user + nice + system + irq + softirq

    if _prev_cpu is None:
        _prev_cpu = (busy, total)
        _prev_cpu_time = time.time()
        return 0

    prev_busy, prev_total = _prev_cpu
    _prev_cpu = (busy, total)

    d_total = total - prev_total
    d_busy = busy - prev_busy
    if d_total == 0:
        return 0
    return round(d_busy * 100 / d_total)


def get_stats():
    stats = {}

    # battery
    bat = '/sys/class/power_supply/axp20x-battery'
    ac = '/sys/class/power_supply/axp22x-ac'
    capacity = int(read_sysfs(f'{bat}/capacity', '0'))
    voltage_ua = int(read_sysfs(f'{bat}/voltage_now', '0'))
    current_ua = int(read_sysfs(f'{bat}/current_now', '0'))
    charge_rate_ua = int(read_sysfs(f'{bat}/constant_charge_current', '0'))
    charge_max_ua = int(read_sysfs(f'{bat}/constant_charge_current_max', '0'))
    stats['battery'] = {
        'status': read_sysfs(f'{bat}/status'),
        'capacity': capacity,
        'voltage': round(voltage_ua / 1_000_000, 3),
        'current_ma': current_ua // 1000,
        'power_mw': (voltage_ua // 1000) * (current_ua // 1000) // 1000,
        'charge_rate_ma': charge_rate_ua // 1000,
        'charge_max_ma': charge_max_ua // 1000,
        'health': read_sysfs(f'{bat}/health'),
        'ac_online': read_sysfs(f'{ac}/online') == '1',
    }

    # cpu
    temp_raw = int(read_sysfs('/sys/class/thermal/thermal_zone0/temp', '0'))
    freq_raw = int(read_sysfs('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq', '0'))
    stats['cpu'] = {
        'usage': get_cpu_usage(),
        'temp': round(temp_raw / 1000, 1),
        'freq_mhz': freq_raw // 1000,
        'governor': read_sysfs('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'),
    }

    # memory
    meminfo = {}
    with open('/proc/meminfo') as f:
        for line in f:
            parts = line.split()
            meminfo[parts[0].rstrip(':')] = int(parts[1])
    mem_total = meminfo.get('MemTotal', 0) // 1024
    mem_avail = meminfo.get('MemAvailable', 0) // 1024
    mem_used = mem_total - mem_avail
    stats['memory'] = {
        'total_mb': mem_total,
        'used_mb': mem_used,
        'pct': round(mem_used * 100 / mem_total) if mem_total else 0,
    }

    # disk
    st = os.statvfs('/')
    disk_total = st.f_blocks * st.f_frsize
    disk_free = st.f_bavail * st.f_frsize
    disk_used = disk_total - disk_free
    stats['disk'] = {
        'total_gb': round(disk_total / 1_073_741_824, 1),
        'used_gb': round(disk_used / 1_073_741_824, 1),
        'free_gb': round(disk_free / 1_073_741_824, 1),
        'pct': round(disk_used * 100 / disk_total) if disk_total else 0,
    }

    # wifi
    wifi = {'ssid': '', 'signal_dbm': 0, 'quality': 0, 'quality_max': 70,
            'bitrate': '', 'ip': ''}
    try:
        iw = subprocess.run(['iwconfig', 'wlan0'], capture_output=True, text=True, timeout=5)
        out = iw.stdout
        m = re.search(r'ESSID:"([^"]+)"', out)
        if m:
            wifi['ssid'] = m.group(1)
        m = re.search(r'Signal level=(-?\d+)', out)
        if m:
            wifi['signal_dbm'] = int(m.group(1))
        m = re.search(r'Link Quality=(\d+)/(\d+)', out)
        if m:
            wifi['quality'] = int(m.group(1))
            wifi['quality_max'] = int(m.group(2))
        m = re.search(r'Bit Rate=([\d.]+)', out)
        if m:
            wifi['bitrate'] = m.group(1)
    except Exception:
        pass
    try:
        ip_out = subprocess.run(['ip', '-4', '-o', 'addr', 'show', 'wlan0'],
                                capture_output=True, text=True, timeout=5)
        m = re.search(r'inet ([\d.]+)', ip_out.stdout)
        if m:
            wifi['ip'] = m.group(1)
    except Exception:
        pass
    stats['wifi'] = wifi

    # uptime
    with open('/proc/uptime') as f:
        up_secs = int(float(f.read().split()[0]))
    days = up_secs // 86400
    hours = (up_secs % 86400) // 3600
    mins = (up_secs % 3600) // 60
    if days > 0:
        stats['uptime'] = f'{days}d {hours}h {mins}m'
    else:
        stats['uptime'] = f'{hours}h {mins}m'

    return stats


def get_top_processes(sort_by='cpu', count=15):
    """Return top processes sorted by cpu or memory."""
    try:
        fmt = 'pid,user,%cpu,%mem,rss,etime,comm'
        sort_flag = '-%cpu' if sort_by == 'cpu' else '-%mem'
        result = subprocess.run(
            ['ps', '-eo', fmt, '--sort', sort_flag, '--no-headers'],
            capture_output=True, text=True, timeout=5
        )
        procs = []
        for line in result.stdout.strip().splitlines()[:count]:
            parts = line.split(None, 6)
            if len(parts) == 7:
                procs.append({
                    'pid': int(parts[0]),
                    'user': parts[1],
                    'cpu': float(parts[2]),
                    'mem': float(parts[3]),
                    'rss_kb': int(parts[4]),
                    'elapsed': parts[5],
                    'command': parts[6],
                })
        return procs
    except Exception as e:
        return [{'error': str(e)}]


def get_system_logs(source='journal', lines=80):
    """Fetch recent system log entries."""
    cmds = {
        'journal': ['journalctl', '--no-pager', '-n', str(lines), '--output=short-iso'],
        'journal-errors': ['journalctl', '--no-pager', '-n', str(lines), '-p', 'err', '--output=short-iso'],
        'dmesg': ['dmesg', '--time-format=iso', '-T'],
        'syslog': ['tail', '-n', str(lines), '/var/log/syslog'],
    }
    cmd = cmds.get(source, cmds['journal'])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = result.stdout.strip()
        if source == 'dmesg':
            output = '\n'.join(output.splitlines()[-lines:])
        return output
    except Exception as e:
        return f'Error reading {source}: {e}'


def get_active_connections():
    """Return active network connections via ss."""
    try:
        result = subprocess.run(
            ['ss', '-tunap'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception as e:
        return f'Error: {e}'


def get_service_status(services=None):
    """Check status of key systemd services."""
    if services is None:
        services = [
            'ssh', 'NetworkManager', 'bluetooth', 'cron',
            'systemd-journald', 'systemd-resolved', 'systemd-timesyncd',
        ]
    statuses = []
    for svc in services:
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', svc],
                capture_output=True, text=True, timeout=5
            )
            state = result.stdout.strip()
        except Exception:
            state = 'unknown'
        statuses.append({'name': svc, 'state': state})
    return statuses


def get_failed_units():
    """Return list of failed systemd units."""
    try:
        result = subprocess.run(
            ['systemctl', '--failed', '--no-pager', '--no-legend'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception as e:
        return f'Error: {e}'


def _script(subdir, name, *args):
    """Build a script command list: ['bash', SCRIPTS_DIR/subdir/name, ...args]."""
    return ['bash', os.path.join(SCRIPTS_DIR, subdir, name)] + list(args)


def _systemctl(*args):
    """Build a systemctl command, using sudo (no --user) in package mode."""
    if PACKAGE_MODE:
        return ['sudo', 'systemctl'] + list(args)
    return ['systemctl', '--user'] + list(args)


ALLOWED_SCRIPTS = {
    # battery (power/)
    'battery':          _script('power', 'battery.sh'),
    'battery-log':      _script('power', 'battery.sh', 'log'),
    # charge (power/)
    'charge-status':    _script('power', 'charge.sh'),
    'charge-300':       _script('power', 'charge.sh', '300'),
    'charge-500':       _script('power', 'charge.sh', '500'),
    'charge-900':       _script('power', 'charge.sh', '900'),
    # network (network/)
    'network-overview': _script('network', 'network.sh'),
    'network-speed':    _script('network', 'network.sh', 'speed'),
    'network-scan':     _script('network', 'network.sh', 'scan'),
    'network-ping':     _script('network', 'network.sh', 'ping'),
    'network-trace':    _script('network', 'network.sh', 'trace'),
    'network-log':      _script('network', 'network.sh', 'log'),
    'hotspot-status':   _script('network', 'hotspot.sh', 'status'),
    'hotspot-start':    _script('network', 'hotspot.sh', 'on'),
    'hotspot-stop':     _script('network', 'hotspot.sh', 'off'),
    # storage (util/)
    'storage':          _script('util', 'storage.sh'),
    'storage-devices':  _script('util', 'storage.sh', 'devices'),
    'storage-smart':    _script('util', 'storage.sh', 'smart'),
    'storage-usb':      _script('util', 'storage.sh', 'usb'),
    'storage-mount':    _script('util', 'storage.sh', 'mount'),
    'storage-temp':     _script('util', 'storage.sh', 'temp'),
    # disk usage (util/)
    'disk-usage':       _script('util', 'diskusage.sh'),
    'disk-big':         _script('util', 'diskusage.sh', 'big'),
    'disk-dirs':        _script('util', 'diskusage.sh', 'dirs'),
    'disk-clean':       _script('util', 'diskusage.sh', 'clean'),
    # audit (util/)
    'audit-overview':   _script('util', 'audit.sh'),
    'audit-junk':       _script('util', 'audit.sh', 'junk'),
    'audit-untracked':  _script('util', 'audit.sh', 'untracked'),
    'audit-categories': _script('util', 'audit.sh', 'categories'),
    # backup (system/)
    'backup-all':       _script('system', 'backup.sh', 'all'),
    'backup-git':       _script('system', 'backup.sh', 'git'),
    'backup-gh':        _script('system', 'backup.sh', 'gh'),
    'backup-system':    _script('system', 'backup.sh', 'system'),
    'backup-pkgs':      _script('system', 'backup.sh', 'packages'),
    'backup-desktop':   _script('system', 'backup.sh', 'desktop'),
    'backup-browser':   _script('system', 'backup.sh', 'browser'),
    'backup-scripts':   _script('system', 'backup.sh', 'scripts'),
    'backup-status':    _script('system', 'backup.sh', 'status'),
    # backup (gather-only + explicit sync)
    'backup-gather-all':     _script('system', 'backup.sh', 'gather', 'all'),
    'backup-gather-git':     _script('system', 'backup.sh', 'gather', 'git'),
    'backup-gather-gh':      _script('system', 'backup.sh', 'gather', 'gh'),
    'backup-gather-system':  _script('system', 'backup.sh', 'gather', 'system'),
    'backup-gather-pkgs':    _script('system', 'backup.sh', 'gather', 'packages'),
    'backup-gather-desktop': _script('system', 'backup.sh', 'gather', 'desktop'),
    'backup-gather-browser': _script('system', 'backup.sh', 'gather', 'browser'),
    'backup-gather-scripts': _script('system', 'backup.sh', 'gather', 'scripts'),
    'backup-sync':           _script('system', 'backup.sh', 'sync'),
    # update (system/)
    'update-all':       _script('system', 'update.sh', 'all'),
    'update-apt':       _script('system', 'update.sh', 'apt'),
    'update-flatpak':   _script('system', 'update.sh', 'flatpak'),
    'update-firmware':  _script('system', 'update.sh', 'firmware'),
    'update-repo':      _script('system', 'update.sh', 'repo'),
    'update-status':    _script('system', 'update.sh', 'status'),
    'update-log':       _script('system', 'update.sh', 'log'),
    'update-snapshot':  _script('system', 'update.sh', 'snapshot'),
    # power (power/)
    'power-status':     _script('power', 'power.sh', 'status'),
    'power-reboot':     _script('power', 'power.sh', 'reboot'),
    'power-shutdown':   _script('power', 'power.sh', 'shutdown'),
    # dashboard (util/)
    'dashboard-status': _script('util', 'dashboard.sh', 'status'),
    # esp32 (radio/)
    'esp32-status':     _script('radio', 'esp32.sh', 'status'),
    'esp32-log':        _script('radio', 'esp32.sh', 'log'),
    'esp32-flash':      _script('radio', 'esp32.sh', 'flash'),
    'esp32-reset':      _script('radio', 'esp32.sh', 'reset'),
    'esp32-info':       _script('radio', 'esp32.sh', 'info'),
    # gps (radio/)
    'gps-status':       _script('radio', 'gps.sh', 'status'),
    'gps-log':          _script('radio', 'gps.sh', 'log'),
    'gps-fix':          _script('radio', 'gps.sh', 'fix'),
    'gps-time':         _script('radio', 'gps.sh', 'time'),
    'gps-track':        _script('radio', 'gps.sh', 'track'),
    'gps-stop':         _script('radio', 'gps.sh', 'stop'),
    # sdr (radio/)
    'sdr-status':       _script('radio', 'sdr.sh', 'status'),
    'sdr-test':         _script('radio', 'sdr.sh', 'test'),
    'sdr-info':         _script('radio', 'sdr.sh', 'info'),
    'sdr-scan':         _script('radio', 'sdr.sh', 'scan'),
    # lora (radio/)
    'lora-status':      _script('radio', 'lora.sh', 'status'),
    'lora-config':      _script('radio', 'lora.sh', 'config'),
    'lora-listen':      _script('radio', 'lora.sh', 'listen'),
    'lora-send':        _script('radio', 'lora.sh', 'send', 'test'),
    # battery test (power/)
    'battest-status':   _script('power', 'battery-test.sh', 'status'),
    'battest-stop':     _script('power', 'battery-test.sh', 'stop'),
    'battest-list':     _script('power', 'battery-test.sh', 'list'),
    'battest-compare':  _script('power', 'battery-test.sh', 'compare'),
    # config / timers
    'timer-enable-backup':  _systemctl('enable', '--now', 'uconsole-backup.timer'),
    'timer-disable-backup': _systemctl('disable', '--now', 'uconsole-backup.timer'),
    'timer-enable-update':  _systemctl('enable', '--now', 'uconsole-update.timer'),
    'timer-disable-update': _systemctl('disable', '--now', 'uconsole-update.timer'),
}

ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
DOCS_DIR = os.path.join(os.path.dirname(APP_DIR), 'docs')


@app.route('/')
def index():
    return render_template('dashboard.html', ascii_title=get_random_logo())


@app.route('/api/logo')
def api_logo():
    name = request.args.get('name')
    return jsonify({'art': get_logo(name) if name else get_random_logo(),
                    'logos': list_logos()})

@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())


@app.route('/api/public/stats')
def api_public_stats():
    """Public system stats endpoint — no auth, rate limited, local IPs only."""
    client_ip = request.headers.get('X-Real-IP', request.remote_addr)
    if not _is_local_ip(client_ip):
        return jsonify({'error': 'Forbidden'}), 403
    if not _check_rate_limit(client_ip):
        return jsonify({'error': 'Rate limit exceeded'}), 429

    import socket
    s = get_stats()

    # uptime seconds
    with open('/proc/uptime') as f:
        up_secs = int(float(f.read().split()[0]))

    # load average
    with open('/proc/loadavg') as f:
        parts = f.read().split()
        load_avg = [float(parts[0]), float(parts[1]), float(parts[2])]

    # screen brightness
    bl_brightness, bl_max = 0, 255
    try:
        import glob as _glob
        bl_paths = _glob.glob('/sys/class/backlight/*/brightness')
        if bl_paths:
            bl_dir = os.path.dirname(bl_paths[0])
            with open(bl_paths[0]) as f:
                bl_brightness = int(f.read().strip())
            with open(os.path.join(bl_dir, 'max_brightness')) as f:
                bl_max = int(f.read().strip())
    except Exception:
        pass

    # AIO board detection
    aio = {
        'sdr': {'detected': False, 'chip': ''},
        'lora': {'detected': False, 'chip': ''},
        'gps': {'detected': False, 'hasFix': False},
        'rtc': {'detected': False, 'synced': False, 'time': ''},
    }
    try:
        lsusb = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
        if '0bda:2838' in lsusb.stdout:
            aio['sdr'] = {'detected': True, 'chip': 'RTL2838'}
    except Exception:
        pass
    if os.path.exists('/dev/spidev4.0'):
        aio['lora'] = {'detected': True, 'chip': 'SX1262'}
    if os.path.exists('/sys/class/rtc/rtc0'):
        aio['rtc']['detected'] = True
        try:
            hw = subprocess.run(['sudo', 'hwclock', '-r'], capture_output=True, text=True, timeout=5)
            if hw.stdout.strip():
                aio['rtc']['synced'] = True
                aio['rtc']['time'] = hw.stdout.strip().split('\n')[0]
        except Exception:
            pass

    # webdash status
    wd_running = False
    wd_port = int(os.environ.get('WEBDASH_PORT', 8080))
    try:
        result = subprocess.run(['systemctl', '--user', 'is-active', 'webdash.service'],
                                capture_output=True, text=True, timeout=5)
        wd_running = result.stdout.strip() == 'active'
    except Exception:
        pass

    # wifi fallback
    wf_enabled = False
    wf_ap = 'uConsole'
    fb_conf = os.path.join(os.path.expanduser('~'), '.config', 'uconsole', 'wifi-fallback.conf')
    try:
        with open(fb_conf) as f:
            for line in f:
                line = line.strip()
                if line == 'enabled=1':
                    wf_enabled = True
                elif line.startswith('ap_name='):
                    wf_ap = line[8:]
    except FileNotFoundError:
        pass

    # wifi quality percentage
    wifi_quality = 0
    if s['wifi'].get('quality_max', 0) > 0:
        wifi_quality = s['wifi']['quality'] * 100 // s['wifi']['quality_max']

    return jsonify({
        'hostname': socket.gethostname(),
        'uptime': s['uptime'],
        'uptimeSeconds': up_secs,
        'battery': {
            'capacity': s['battery']['capacity'],
            'voltage': int(s['battery']['voltage'] * 1000),
            'current': s['battery']['current_ma'],
            'status': s['battery']['status'],
            'health': s['battery']['health'],
        },
        'cpu': {
            'tempC': s['cpu']['temp'],
            'loadAvg': load_avg,
            'cores': os.cpu_count() or 4,
        },
        'memory': {
            'totalMB': s['memory']['total_mb'],
            'usedMB': s['memory']['used_mb'],
            'availableMB': s['memory']['total_mb'] - s['memory']['used_mb'],
        },
        'disk': {
            'totalGB': s['disk']['total_gb'],
            'usedGB': s['disk']['used_gb'],
            'availableGB': s['disk']['free_gb'],
            'usedPercent': s['disk']['pct'],
        },
        'wifi': {
            'ssid': s['wifi']['ssid'],
            'signalDBm': s['wifi']['signal_dbm'],
            'quality': wifi_quality,
            'bitrateMbps': float(s['wifi']['bitrate']) if s['wifi']['bitrate'] else 0,
            'ip': s['wifi']['ip'],
        },
        'aio': aio,
        'screen': {
            'brightness': bl_brightness,
            'maxBrightness': bl_max,
        },
        'webdash': {
            'running': wd_running,
            'port': wd_port,
        },
        'wifiFallback': {
            'enabled': wf_enabled,
            'apName': wf_ap,
        },
        'collectedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    })


@app.route('/api/timers')
def api_timers():
    """Return status of backup/update systemd timers."""
    timers = []
    for name in ['uconsole-backup', 'uconsole-update']:
        t = {'name': name, 'active': False, 'next': '', 'last': '', 'schedule': ''}
        try:
            active = subprocess.run(
                ['systemctl', '--user', 'is-active', f'{name}.timer'],
                capture_output=True, text=True, timeout=5
            )
            t['active'] = active.stdout.strip() == 'active'
            if t['active']:
                show = subprocess.run(
                    ['systemctl', '--user', 'show', f'{name}.timer',
                     '--property=NextElapseUSecRealtime,LastTriggerUSec'],
                    capture_output=True, text=True, timeout=5
                )
                for line in show.stdout.strip().splitlines():
                    if line.startswith('NextElapseUSecRealtime='):
                        t['next'] = line.split('=', 1)[1]
                    elif line.startswith('LastTriggerUSec='):
                        val = line.split('=', 1)[1]
                        t['last'] = val if val != 'n/a' else 'never'
        except Exception:
            pass
        # read current schedule from timer file
        key = name.replace('uconsole-', '')
        timer_file = TIMER_FILES.get(key, '')
        calendar = ''
        try:
            with open(timer_file, 'r') as f:
                for line in f:
                    if line.strip().startswith('OnCalendar='):
                        calendar = line.strip().split('=', 1)[1]
                        break
        except Exception:
            pass
        # find matching preset label
        preset_key = CALENDAR_TO_PRESET.get((key, calendar), '')
        presets = TIMER_PRESETS.get(key, {})
        if preset_key and preset_key in presets:
            t['schedule'] = presets[preset_key][0]
        else:
            t['schedule'] = calendar or 'unknown'
        t['calendar'] = calendar
        t['current_preset'] = preset_key
        t['presets'] = {k: v[0] for k, v in presets.items()}
        timers.append(t)
    return jsonify(timers)


TIMER_PRESETS = {
    'backup': {
        'every-2h':  ('Every 2 hours',        '*-*-* 0/2:00:00'),
        'every-6h':  ('Every 6 hours',         '*-*-* 0/6:00:00'),
        'daily-3am': ('Daily at 3:00 AM',      '*-*-* 03:00:00'),
        'daily-noon':('Daily at 12:00 PM',     '*-*-* 12:00:00'),
        'daily-9pm': ('Daily at 9:00 PM',      '*-*-* 21:00:00'),
    },
    'update': {
        'daily-4am': ('Daily at 4:00 AM',      '*-*-* 04:00:00'),
        'weekly-sun':('Weekly, Sunday 4:00 AM', 'Sun *-*-* 04:00:00'),
        'weekly-sat':('Weekly, Saturday 4:00 AM','Sat *-*-* 04:00:00'),
        'monthly':   ('Monthly, 1st at 4:00 AM','*-*-01 04:00:00'),
    },
}

# map OnCalendar values back to preset keys for display
CALENDAR_TO_PRESET = {}
for _timer, _presets in TIMER_PRESETS.items():
    for _key, (_label, _cal) in _presets.items():
        CALENDAR_TO_PRESET[(_timer, _cal)] = _key

TIMER_FILES = {
    'backup': os.path.join(os.path.dirname(APP_DIR), 'config', 'systemd-user', 'uconsole-backup.timer'),
    'update': os.path.join(os.path.dirname(APP_DIR), 'config', 'systemd-user', 'uconsole-update.timer'),
}


@app.route('/api/timer-schedule/<timer_name>', methods=['POST'])
def api_timer_schedule(timer_name):
    """Update the schedule of a backup or update timer."""
    if timer_name not in ('backup', 'update'):
        return jsonify({'error': 'Unknown timer'}), 404

    data = request.get_json(silent=True) or {}
    preset = data.get('preset', '')

    if preset not in TIMER_PRESETS[timer_name]:
        return jsonify({'error': 'Unknown preset', 'valid': list(TIMER_PRESETS[timer_name].keys())}), 400

    label, calendar = TIMER_PRESETS[timer_name][preset]
    timer_file = TIMER_FILES[timer_name]
    service_name = f'uconsole-{timer_name}'

    try:
        with open(timer_file, 'r') as f:
            content = f.read()

        # update OnCalendar and Description
        import re as _re
        content = _re.sub(r'OnCalendar=.*', f'OnCalendar={calendar}', content)
        content = _re.sub(r'Description=.*', f'Description=Run uConsole {timer_name} — {label}', content)

        with open(timer_file, 'w') as f:
            f.write(content)

        # reload systemd and restart timer
        subprocess.run(_systemctl('daemon-reload'), timeout=10)
        subprocess.run(_systemctl('restart', f'{service_name}.timer'), timeout=10)

        return jsonify({'ok': True, 'schedule': label, 'calendar': calendar})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


BACKLIGHT_DIR = '/sys/class/backlight/backlight@0'


@app.route('/api/config')
def api_config():
    """Return current config values for all configurable items."""
    config = {}

    # brightness
    try:
        with open(os.path.join(BACKLIGHT_DIR, 'brightness')) as f:
            config['brightness'] = int(f.read().strip())
        with open(os.path.join(BACKLIGHT_DIR, 'max_brightness')) as f:
            config['brightness_max'] = int(f.read().strip())
    except Exception:
        config['brightness'] = 0
        config['brightness_max'] = 9

    # webdash port
    config['port'] = int(os.environ.get('WEBDASH_PORT', 8080))

    # git remote
    try:
        result = subprocess.run(
            ['git', '-C', os.path.dirname(APP_DIR), 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, timeout=5
        )
        config['git_remote'] = result.stdout.strip()
    except Exception:
        config['git_remote'] = ''

    # timezone
    try:
        result = subprocess.run(['timedatectl', 'show', '--property=Timezone', '--value'],
                                capture_output=True, text=True, timeout=5)
        config['timezone'] = result.stdout.strip()
    except Exception:
        config['timezone'] = 'Unknown'

    return jsonify(config)


@app.route('/api/config/brightness', methods=['POST'])
def api_set_brightness():
    data = request.get_json(silent=True) or {}
    val = data.get('value')
    if val is None:
        return jsonify({'error': 'Missing value'}), 400
    try:
        val = int(val)
        with open(os.path.join(BACKLIGHT_DIR, 'max_brightness')) as f:
            max_b = int(f.read().strip())
        val = max(0, min(val, max_b))
        with open(os.path.join(BACKLIGHT_DIR, 'brightness'), 'w') as f:
            f.write(str(val))
        return jsonify({'ok': True, 'brightness': val})
    except PermissionError:
        # try via sudo tee
        try:
            subprocess.run(['sudo', 'tee', os.path.join(BACKLIGHT_DIR, 'brightness')],
                           input=str(val), text=True, timeout=5, check=True,
                           stdout=subprocess.DEVNULL)
            return jsonify({'ok': True, 'brightness': val})
        except Exception as e:
            return jsonify({'error': f'Permission denied: {e}'}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/git-remote', methods=['POST'])
def api_set_git_remote():
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    try:
        subprocess.run(
            ['git', '-C', os.path.dirname(APP_DIR), 'remote', 'set-url', 'origin', url],
            check=True, timeout=10
        )
        return jsonify({'ok': True, 'git_remote': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/timezone', methods=['POST'])
def api_set_timezone():
    data = request.get_json(silent=True) or {}
    tz = data.get('timezone', '').strip()
    if not tz or '/' not in tz:
        return jsonify({'error': 'Invalid timezone (e.g. America/New_York)'}), 400
    try:
        subprocess.run(['sudo', 'timedatectl', 'set-timezone', tz],
                       check=True, timeout=10)
        return jsonify({'ok': True, 'timezone': tz})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/port', methods=['POST'])
def api_set_port():
    data = request.get_json(silent=True) or {}
    port = data.get('port')
    if not port:
        return jsonify({'error': 'Missing port'}), 400
    try:
        port = int(port)
        if port < 1024 or port > 65535:
            return jsonify({'error': 'Port must be 1024-65535'}), 400
        # update the webdash service file
        svc_file = os.path.expanduser('~/.config/systemd/user/webdash.service')
        if os.path.exists(svc_file):
            with open(svc_file, 'r') as f:
                content = f.read()
            import re as _re
            # look for --port or port= in ExecStart
            if 'WEBDASH_PORT' in content:
                content = _re.sub(r'WEBDASH_PORT=\d+', f'WEBDASH_PORT={port}', content)
            else:
                content = _re.sub(
                    r'(ExecStart=.*)',
                    f'Environment=WEBDASH_PORT={port}\n\\1',
                    content, count=1
                )
            with open(svc_file, 'w') as f:
                f.write(content)
            subprocess.run(_systemctl('daemon-reload'), timeout=10)
            return jsonify({'ok': True, 'port': port,
                            'message': 'Restart webdash service to apply'})
        return jsonify({'ok': True, 'port': port,
                        'message': 'Set WEBDASH_PORT env var and restart'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/processes')
@app.route('/api/processes/<sort_by>')
def api_processes(sort_by='cpu'):
    return jsonify(get_top_processes(sort_by))


@app.route('/api/logs/<source>')
def api_logs(source):
    if source not in ('journal', 'journal-errors', 'dmesg', 'syslog'):
        return jsonify({'error': 'Unknown log source'}), 404
    return jsonify({'source': source, 'output': get_system_logs(source)})


@app.route('/api/connections')
def api_connections():
    return jsonify({'output': get_active_connections()})


@app.route('/api/services')
def api_services():
    return jsonify({'services': get_service_status(), 'failed': get_failed_units()})


@app.route('/api/wiki')
def api_wiki_list():
    """List all docs."""
    if not os.path.isdir(DOCS_DIR):
        return jsonify({'docs': []})
    docs = []
    for f in sorted(os.listdir(DOCS_DIR)):
        if f.endswith('.md'):
            fpath = os.path.join(DOCS_DIR, f)
            stat = os.stat(fpath)
            with open(fpath) as fh:
                first_line = fh.readline().strip().lstrip('#').strip()
            docs.append({
                'slug': f[:-3],
                'title': first_line or f[:-3],
                'size': stat.st_size,
                'modified': int(stat.st_mtime),
            })
    return jsonify({'docs': docs})


@app.route('/api/wiki/<slug>')
def api_wiki_read(slug):
    """Read a doc."""
    safe = re.sub(r'[^a-zA-Z0-9_-]', '', slug)
    fpath = os.path.join(DOCS_DIR, safe + '.md')
    if not os.path.isfile(fpath):
        return jsonify({'error': 'Not found'}), 404
    with open(fpath) as f:
        content = f.read()
    stat = os.stat(fpath)
    return jsonify({'slug': safe, 'content': content, 'modified': int(stat.st_mtime)})


@app.route('/api/wiki/<slug>', methods=['POST'])
def api_wiki_write(slug):
    """Create or update a doc."""
    safe = re.sub(r'[^a-zA-Z0-9_-]', '', slug)
    if not safe:
        return jsonify({'error': 'Invalid slug'}), 400
    os.makedirs(DOCS_DIR, exist_ok=True)
    fpath = os.path.join(DOCS_DIR, safe + '.md')
    data = request.get_json(force=True)
    content = data.get('content', '')
    with open(fpath, 'w') as f:
        f.write(content)
    return jsonify({'slug': safe, 'saved': True})


@app.route('/api/wiki/<slug>', methods=['DELETE'])
def api_wiki_delete(slug):
    """Delete a doc."""
    safe = re.sub(r'[^a-zA-Z0-9_-]', '', slug)
    fpath = os.path.join(DOCS_DIR, safe + '.md')
    if os.path.isfile(fpath):
        os.remove(fpath)
    return jsonify({'slug': safe, 'deleted': True})


@app.route('/api/wifi/scan')
def api_wifi_scan():
    """Scan for available WiFi networks."""
    try:
        # Trigger a fresh scan
        subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'],
                       capture_output=True, timeout=10)
        import time; time.sleep(2)
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,IN-USE', 'device', 'wifi', 'list'],
            capture_output=True, text=True, timeout=10
        )
        networks = []
        seen = set()
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split(':')
            if len(parts) >= 4:
                ssid = parts[0]
                if not ssid or ssid in seen:
                    continue
                seen.add(ssid)
                networks.append({
                    'ssid': ssid,
                    'signal': int(parts[1]) if parts[1].isdigit() else 0,
                    'security': parts[2] if parts[2] else 'Open',
                    'active': parts[3] == '*'
                })
        networks.sort(key=lambda n: (-n['active'], -n['signal']))
        return jsonify({'networks': networks})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/wifi/connect', methods=['POST'])
def api_wifi_connect():
    """Connect to a WiFi network."""
    data = request.get_json() or {}
    ssid = data.get('ssid', '').strip()
    password = data.get('password', '').strip()
    if not ssid:
        return jsonify({'error': 'Missing SSID'}), 400
    try:
        cmd = ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid]
        if password:
            cmd += ['password', password]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return jsonify({'ok': True, 'message': f'Connected to {ssid}'})
        else:
            error = result.stderr.strip() or result.stdout.strip()
            return jsonify({'ok': False, 'error': error}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/wifi/disconnect', methods=['POST'])
def api_wifi_disconnect():
    """Disconnect from current WiFi network."""
    try:
        result = subprocess.run(['nmcli', 'device', 'disconnect', 'wlan0'],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return jsonify({'ok': True, 'message': 'Disconnected'})
        return jsonify({'ok': False, 'error': result.stderr.strip()}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/run/<script>', methods=['POST'])
def api_run(script):
    if script not in ALLOWED_SCRIPTS:
        return jsonify({'error': 'Unknown script'}), 404
    try:
        result = subprocess.run(
            ALLOWED_SCRIPTS[script],
            capture_output=True, text=True, timeout=300
        )
        output = ANSI_RE.sub('', result.stdout)
        error = ANSI_RE.sub('', result.stderr)
        return jsonify({'output': output, 'error': error, 'returncode': result.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Script timed out', 'output': '', 'returncode': -1})


@app.route('/api/stream/<script>', methods=['GET'])
def api_stream(script):
    """Stream script output line-by-line via Server-Sent Events."""
    if script not in ALLOWED_SCRIPTS:
        return jsonify({'error': 'Unknown script'}), 404

    def generate():
        import json as _json
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        proc = subprocess.Popen(
            ALLOWED_SCRIPTS[script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env
        )
        try:
            for line in proc.stdout:
                clean = ANSI_RE.sub('', line.rstrip('\n'))
                yield f"data: {clean}\n\n"
            proc.wait(timeout=300)
            stderr = ANSI_RE.sub('', proc.stderr.read())
            done = _json.dumps({"returncode": proc.returncode, "error": stderr})
            yield f"event: done\ndata: {done}\n\n"
        except subprocess.TimeoutExpired:
            proc.kill()
            done = _json.dumps({"returncode": -1, "error": "Script timed out"})
            yield f"event: done\ndata: {done}\n\n"
        finally:
            proc.stdout.close()
            proc.stderr.close()

    return app.response_class(generate(), mimetype='text/event-stream',
                              headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# --- ESP32 sensor data ---
_esp32_data = {}
_esp32_last_seen = 0

# --- GPS live data ---
_gps_data = {}
_gps_last_seen = 0

# --- SDR status data ---
_sdr_data = {}
_sdr_last_seen = 0

# --- LoRa message data ---
_lora_data = {}
_lora_last_seen = 0


@app.route('/api/battery-test/chart')
def api_battest_chart():
    """Return discharge curve data for all tests as JSON for charting."""
    import csv as _csv
    test_dir = os.path.join(os.path.expanduser('~'), 'battery-tests')
    result = {}
    if os.path.isdir(test_dir):
        for fname in sorted(os.listdir(test_dir)):
            if not fname.endswith('.csv'):
                continue
            label = fname[:-4]
            rows = []
            with open(os.path.join(test_dir, fname)) as f:
                for row in _csv.DictReader(f):
                    rows.append({
                        't': row['timestamp'],
                        'v': float(row['voltage_v']),
                        'ma': int(row['current_ma']),
                        'cap': int(row['capacity_pct']),
                    })
            result[label] = rows
    return jsonify(result)


@app.route('/api/battery-test/start', methods=['POST'])
def api_battest_start():
    """Start a battery test with a given label."""
    data = request.get_json(silent=True) or {}
    label = data.get('label', '').strip()
    if not label or not re.match(r'^[a-zA-Z0-9_\-]+$', label):
        return jsonify({'error': 'Invalid label (alphanumeric, hyphens, underscores only)'}), 400
    interval = str(data.get('interval', 5))
    subprocess.Popen(
        ['bash', os.path.join(SCRIPTS_DIR, 'power', 'battery-test.sh'), 'start', label, interval],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        start_new_session=True
    )
    return jsonify({'ok': True, 'label': label})


@app.route('/api/esp32/push', methods=['POST'])
def api_esp32_push():
    """Receive sensor data from ESP32."""
    global _esp32_data, _esp32_last_seen
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data'}), 400
    _esp32_data = data
    _esp32_last_seen = time.time()
    return jsonify({'ok': True})


@app.route('/api/esp32')
def api_esp32():
    """Return latest ESP32 sensor reading."""
    age = round(time.time() - _esp32_last_seen) if _esp32_last_seen else -1
    return jsonify({**_esp32_data, 'age': age, 'online': 0 < age < 60})


@app.route('/api/gps/push', methods=['POST'])
def api_gps_push():
    """Receive GPS fix data (from gps-push.sh or external)."""
    global _gps_data, _gps_last_seen
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data'}), 400
    _gps_data = data
    _gps_last_seen = time.time()
    return jsonify({'ok': True})


@app.route('/api/gps')
def api_gps():
    """Return latest GPS fix."""
    age = round(time.time() - _gps_last_seen) if _gps_last_seen else -1
    return jsonify({**_gps_data, 'age': age, 'online': 0 < age < 30})


@app.route('/api/sdr/push', methods=['POST'])
def api_sdr_push():
    """Receive SDR status data."""
    global _sdr_data, _sdr_last_seen
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data'}), 400
    _sdr_data = data
    _sdr_last_seen = time.time()
    return jsonify({'ok': True})


@app.route('/api/sdr')
def api_sdr():
    """Return latest SDR status."""
    age = round(time.time() - _sdr_last_seen) if _sdr_last_seen else -1
    return jsonify({**_sdr_data, 'age': age, 'online': 0 < age < 60})


@app.route('/api/lora/push', methods=['POST'])
def api_lora_push():
    """Receive LoRa message/status data."""
    global _lora_data, _lora_last_seen
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data'}), 400
    _lora_data = data
    _lora_last_seen = time.time()
    return jsonify({'ok': True})


@app.route('/api/lora')
def api_lora():
    """Return latest LoRa data."""
    age = round(time.time() - _lora_last_seen) if _lora_last_seen else -1
    return jsonify({**_lora_data, 'age': age, 'online': 0 < age < 60})


# ── War Drive (WIP / opt-in) ─────────────────────────────────────────
# Disabled by default — the UX is still in flux. Enable with either:
#   sudo touch /etc/uconsole/wardrive-enabled
# or set UCONSOLE_WARDRIVE_ENABLED=1 in the webdash service env.
# When disabled, both /wardrive and /api/wardrive/* return 404 so the
# feature is invisible to users who haven't opted in.

_WARDRIVE_DIR = os.path.expanduser('~/esp32/marauder-logs')
_WARDRIVE_NAME_RE = re.compile(r'^wardrive-(?:DEMO-)?\d{8}T\d{6}\.csv$')
_WARDRIVE_FLAG_FILE = '/etc/uconsole/wardrive-enabled'


def _wardrive_enabled():
    if os.environ.get('UCONSOLE_WARDRIVE_ENABLED') in ('1', 'true', 'yes'):
        return True
    try:
        return os.path.exists(_WARDRIVE_FLAG_FILE)
    except OSError:
        return False


def _wardrive_gate():
    """Return a 404 response if the feature is disabled; else None."""
    if _wardrive_enabled():
        return None
    return ('War Drive is disabled. To enable:\n'
            '  sudo touch /etc/uconsole/wardrive-enabled\n'
            '  sudo systemctl restart uconsole-webdash'), 404


def _wardrive_list_files():
    """Return list of {name, size, mtime} for wardrive CSVs, newest first."""
    out = []
    try:
        for n in os.listdir(_WARDRIVE_DIR):
            if not _WARDRIVE_NAME_RE.match(n):
                continue
            p = os.path.join(_WARDRIVE_DIR, n)
            try:
                st = os.stat(p)
                out.append({
                    'name': n,
                    'size': st.st_size,
                    'mtime': st.st_mtime,
                })
            except OSError:
                continue
    except FileNotFoundError:
        pass
    out.sort(key=lambda f: f['mtime'], reverse=True)
    return out


def _wardrive_parse(path, since_row=0):
    """Parse CSV rows past `since_row` index. Returns (rows, total_rows)."""
    import csv as _csv
    rows = []
    total = 0
    try:
        with open(path, 'r') as f:
            reader = _csv.DictReader(f)
            for i, r in enumerate(reader):
                total = i + 1
                if i < since_row:
                    continue
                try:
                    lat = float(r['lat']) if r.get('lat') else None
                    lon = float(r['lon']) if r.get('lon') else None
                except ValueError:
                    lat = lon = None
                try:
                    rssi = int(r['rssi'])
                except (ValueError, KeyError):
                    rssi = -100
                try:
                    ch = int(r['channel'])
                except (ValueError, KeyError):
                    ch = 0
                rows.append({
                    'idx': i,
                    'ts': r.get('timestamp_iso', ''),
                    'bssid': r.get('bssid', ''),
                    'essid': r.get('essid', ''),
                    'channel': ch,
                    'rssi': rssi,
                    'lat': lat,
                    'lon': lon,
                    'first_seen': r.get('first_seen', '0') == '1',
                })
    except FileNotFoundError:
        pass
    return rows, total


@app.route('/wardrive')
def wardrive_page():
    g = _wardrive_gate()
    if g: return g
    """Live map of war-drive sessions.

    Default view uses MapLibre GL + deck.gl for a 3D cyberpunk
    visualization. ?basic=1 falls back to the Leaflet version for
    browsers without WebGL2.
    """
    now = time.time()
    sessions = []
    for f in _wardrive_list_files():
        sessions.append({
            'name': f['name'],
            'size': f['size'],
            'mtime': f['mtime'],
            'live': (now - f['mtime']) < 300,
            'label': f['name'].replace('wardrive-', '').replace('.csv', ''),
        })
    template = ('wardrive_basic.html' if request.args.get('basic') == '1'
                else 'wardrive.html')
    return render_template(template, initial_sessions=sessions,
                           log_dir=_WARDRIVE_DIR)


@app.route('/api/wardrive/sessions')
def api_wardrive_sessions():
    """List available war-drive CSV sessions, newest first."""
    g = _wardrive_gate()
    if g: return g
    files = _wardrive_list_files()
    # Also report whether this is the live/in-progress session (newest,
    # modified in last 5 minutes)
    now = time.time()
    for f in files:
        f['live'] = (now - f['mtime']) < 300
    return jsonify({'sessions': files})


@app.route('/api/wardrive/data/<name>')
def api_wardrive_data(name):
    """Return parsed rows from a war-drive CSV. Supports ?since=<idx>."""
    g = _wardrive_gate()
    if g: return g
    if not _WARDRIVE_NAME_RE.match(name):
        return jsonify({'error': 'invalid name'}), 400
    path = os.path.join(_WARDRIVE_DIR, name)
    if not os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    try:
        since = int(request.args.get('since', 0))
    except ValueError:
        since = 0
    rows, total = _wardrive_parse(path, since)
    try:
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
    except OSError:
        mtime = 0
        size = 0
    return jsonify({
        'name': name,
        'total_rows': total,
        'returned': len(rows),
        'since': since,
        'size': size,
        'mtime': mtime,
        'rows': rows,
    })


def _watch_and_reload():
    """Restart process when this file changes."""
    path = os.path.abspath(__file__)
    mtime = os.path.getmtime(path)
    while True:
        time.sleep(2)
        try:
            new_mtime = os.path.getmtime(path)
            if new_mtime != mtime:
                print('[webdash] File changed, reloading...', flush=True)
                os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception:
            pass


if __name__ == '__main__':
    t = threading.Thread(target=_watch_and_reload, daemon=True)
    t.start()
    _port = int(os.environ.get('WEBDASH_PORT', 8080))
    if socketio:
        socketio.run(app, host='127.0.0.1', port=_port,
                     debug=False, allow_unsafe_werkzeug=True)
    else:
        app.run(host='127.0.0.1', port=_port,
                debug=False, threaded=True)
