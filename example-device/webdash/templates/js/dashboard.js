var NL = String.fromCharCode(10);
function barColor(pct, invert) {
  if (invert) return pct > 60 ? '#3fb950' : pct > 30 ? '#d29922' : '#f85149';
  return pct > 80 ? '#f85149' : pct > 60 ? '#d29922' : '#3fb950';
}
function setBar(id, pct, invert) {
  var el = document.getElementById(id);
  el.style.width = Math.min(100, Math.max(0, pct)) + '%';
  el.style.background = barColor(pct, invert);
}
function setText(id, val) { document.getElementById(id).textContent = val; }

/* ---- animated number transitions ---- */
var _animTargets = {};
var _animFrames = {};
function animateValue(id, newVal) {
  var el = document.getElementById(id);
  if (!el) return;
  var current = parseFloat(el.textContent) || 0;
  var target = parseFloat(newVal);
  if (isNaN(target)) { el.textContent = newVal; return; }
  if (current === target) return;
  if (_animFrames[id]) cancelAnimationFrame(_animFrames[id]);
  var start = performance.now();
  var duration = 400;
  function step(ts) {
    var progress = Math.min((ts - start) / duration, 1);
    progress = 1 - Math.pow(1 - progress, 3); /* ease-out cubic */
    var val = current + (target - current) * progress;
    el.textContent = Number.isInteger(target) ? Math.round(val) : val.toFixed(1);
    if (progress < 1) _animFrames[id] = requestAnimationFrame(step);
  }
  _animFrames[id] = requestAnimationFrame(step);
}

/* ---- toast notifications ---- */
function toast(msg, type) {
  var container = document.getElementById('toast-container');
  var el = document.createElement('div');
  el.className = 'toast';
  var icon = type === 'ok' ? '\u2713' : type === 'err' ? '\u2717' : '\u2139';
  var iconColor = type === 'ok' ? 'var(--green)' : type === 'err' ? 'var(--red)' : 'var(--accent)';
  var now = new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  el.innerHTML = '<span class="toast-icon" style="color:' + iconColor + '">' + icon + '</span><span class="toast-msg">' + esc(msg) + '</span><span class="toast-time">' + now + '</span>';
  container.appendChild(el);
  setTimeout(function() { el.classList.add('out'); setTimeout(function() { el.remove(); }, 300); }, 3500);
}

/* ---- custom modal ---- */
function showModal(title, msg, scriptName, btnClass) {
  var root = document.getElementById('modal-root');
  root.innerHTML = '<div class="modal-overlay" onclick="if(event.target===this)closeModal()">' +
    '<div class="modal"><h3>' + esc(title) + '</h3><p>' + esc(msg) + '</p>' +
    '<div class="modal-btns"><button onclick="closeModal()">Cancel</button>' +
    '<button class="' + (btnClass || '') + '" onclick="closeModal();run(\'' + scriptName + '\')">' + title + '</button></div></div></div>';
}
function closeModal() { document.getElementById('modal-root').innerHTML = ''; }

/* ---- panel state persistence ---- */
function savePanelState() {
  var panels = document.querySelectorAll('.panel');
  var state = [];
  panels.forEach(function(p, i) { if (p.classList.contains('open')) state.push(i); });
  try { localStorage.setItem('uc_panels', JSON.stringify(state)); } catch(e) {}
}
function restorePanelState() {
  try {
    var state = JSON.parse(localStorage.getItem('uc_panels') || '[]');
    var panels = document.querySelectorAll('.panel');
    state.forEach(function(i) { if (panels[i]) panels[i].classList.add('open'); });
  } catch(e) {}
}

/* ---- connection state ---- */
var _connected = false;
function setConnected(state) {
  _connected = state;
  var dot = document.getElementById('conn-dot');
  if (dot) { dot.className = state ? 'conn-dot' : 'conn-dot lost'; }
}

async function refresh() {
  try {
    var r = await fetch('/api/stats');
    var s = await r.json();
    setConnected(true);
    var now = new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
    setText('subtitle', now + '  up ' + s.uptime);

    animateValue('bat-pct', s.battery.capacity);
    setBar('bat-bar', s.battery.capacity, true);
    setText('bat-status', s.battery.status);
    setText('bat-source', s.battery.ac_online ? 'AC' : 'Battery');
    setText('bat-voltage', s.battery.voltage);
    setText('bat-current', s.battery.current_ma);
    setText('bat-power', s.battery.power_mw);
    setText('bat-rate', s.battery.charge_rate_ma);
    setText('bat-max', s.battery.charge_max_ma);
    setText('bat-health', s.battery.health);

    animateValue('cpu-usage', s.cpu.usage);
    setBar('cpu-bar', s.cpu.usage, false);
    setText('cpu-temp', s.cpu.temp);
    setText('cpu-freq', s.cpu.freq_mhz);
    setText('cpu-gov', s.cpu.governor);

    animateValue('mem-pct', s.memory.pct);
    setBar('mem-bar', s.memory.pct, false);
    setText('mem-used', s.memory.used_mb);
    setText('mem-total', s.memory.total_mb);

    animateValue('disk-pct', s.disk.pct);
    setBar('disk-bar', s.disk.pct, false);
    setText('disk-used', s.disk.used_gb);
    setText('disk-total', s.disk.total_gb);
    setText('disk-free', s.disk.free_gb);

    var wq = s.wifi.quality_max > 0 ? Math.round(s.wifi.quality * 100 / s.wifi.quality_max) : 0;
    setText('wifi-signal', s.wifi.signal_dbm);
    setBar('wifi-bar', wq, true);
    setText('wifi-ssid', s.wifi.ssid || '(none)');
    setText('wifi-rate', s.wifi.bitrate || '--');
    setText('wifi-quality', s.wifi.quality + '/' + s.wifi.quality_max);
    setText('wifi-ip', s.wifi.ip || '--');

    setText('uptime', s.uptime);
  } catch (e) {
    setConnected(false);
    setText('subtitle', 'connection lost');
  }
}

function manualRefresh() {
  var btn = document.getElementById('refresh-btn');
  btn.classList.remove('spinning');
  void btn.offsetWidth;
  btn.classList.add('spinning');
  refresh();
}

/* ---- timers ---- */

var _timerState = {};

async function loadTimers() {
  try {
    var r = await fetch('/api/timers');
    var timers = await r.json();
    timers.forEach(function(t) {
      var key = t.name.replace('uconsole-', '');
      _timerState[key] = t.active;

      var btn = document.getElementById('timer-' + key + '-btn');
      var next = document.getElementById('timer-' + key + '-next');
      var sel = document.getElementById('timer-' + key + '-select');

      if (btn) {
        btn.textContent = t.active ? 'On' : 'Off';
        btn.className = 'timer-toggle ' + (t.active ? 'on' : 'off');
      }
      if (next && t.active && t.next) {
        next.textContent = 'next: ' + t.next.replace(/^[A-Z]+ /, '').replace(/:[0-9]+ [A-Z]+$/, '');
      } else if (next) {
        next.textContent = '';
      }
      if (sel && t.presets) {
        var currentVal = sel.value || t.current_preset;
        sel.innerHTML = '';
        Object.keys(t.presets).forEach(function(k) {
          var opt = document.createElement('option');
          opt.value = k;
          opt.textContent = t.presets[k];
          if (k === t.current_preset) opt.selected = true;
          sel.appendChild(opt);
        });
        if (currentVal && !t.current_preset) sel.value = currentVal;
      }
    });
  } catch(e) {}
}

async function toggleTimer(name) {
  var isOn = _timerState[name];
  var action = isOn ? 'timer-disable-' + name : 'timer-enable-' + name;
  try {
    await fetch('/api/run/' + action, { method: 'POST' });
    await loadTimers();
    toast((isOn ? 'Disabled' : 'Enabled') + ' ' + name + ' timer', 'ok');
  } catch(e) {
    toast('Failed to toggle ' + name + ' timer', 'err');
  }
}

async function loadConfig() {
  try {
    var r = await fetch('/api/config');
    var c = await r.json();
    var slider = document.getElementById('brightness-slider');
    if (slider) {
      slider.max = c.brightness_max;
      slider.value = c.brightness;
      setText('brightness-val', c.brightness);
    }
    var gitInput = document.getElementById('git-remote-input');
    if (gitInput && !gitInput.matches(':focus')) gitInput.value = c.git_remote || '';
    var tzInput = document.getElementById('timezone-input');
    if (tzInput && !tzInput.matches(':focus')) tzInput.value = c.timezone || '';
    var portInput = document.getElementById('port-input');
    if (portInput && !portInput.matches(':focus')) portInput.value = c.port || 8080;
  } catch(e) {}
}

async function setBrightness(val) {
  setText('brightness-val', val);
  try {
    await fetch('/api/config/brightness', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({value: parseInt(val)})
    });
  } catch(e) {}
}

async function saveGitRemote() {
  var url = document.getElementById('git-remote-input').value.trim();
  if (!url) return;
  try {
    var r = await fetch('/api/config/git-remote', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: url})
    });
    var d = await r.json();
    toast(d.ok ? 'Git remote updated' : d.error, d.ok ? 'ok' : 'err');
  } catch(e) { toast('Failed', 'err'); }
}

async function saveTimezone() {
  var tz = document.getElementById('timezone-input').value.trim();
  if (!tz) return;
  try {
    var r = await fetch('/api/config/timezone', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({timezone: tz})
    });
    var d = await r.json();
    toast(d.ok ? 'Timezone set to ' + tz : d.error, d.ok ? 'ok' : 'err');
  } catch(e) { toast('Failed', 'err'); }
}

async function savePort() {
  var port = document.getElementById('port-input').value;
  if (!port) return;
  try {
    var r = await fetch('/api/config/port', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({port: parseInt(port)})
    });
    var d = await r.json();
    toast(d.ok ? 'Port set to ' + port + ' — restart to apply' : d.error, d.ok ? 'ok' : 'err');
  } catch(e) { toast('Failed', 'err'); }
}

async function setTimerSchedule(name, preset) {
  try {
    var r = await fetch('/api/timer-schedule/' + name, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({preset: preset})
    });
    var d = await r.json();
    if (d.ok) {
      await loadTimers();
      toast(name + ' schedule: ' + d.schedule, 'ok');
    } else {
      toast('Failed: ' + (d.error || 'unknown'), 'err');
    }
  } catch(e) {
    toast('Failed to update schedule', 'err');
  }
}

/* ---- output formatting engine ---- */
var _rawOutput = '';
var _rawError = '';
var _rawRc = 0;
var _showRaw = false;

function esc(s) {
  var d = document.createElement('div'); d.textContent = s; return d.innerHTML;
}

/* ---- SVG visualization helpers ---- */

function svgGauge(pct, size, label, color) {
  var r = (size - 8) / 2;
  var circ = 2 * Math.PI * r;
  var dashPct = Math.min(100, Math.max(0, pct));
  var arc = circ * 0.75; /* 270 deg arc */
  var filled = arc * dashPct / 100;
  var gap = arc - filled;
  if (!color) color = barColor(pct, true);
  return '<div class="viz-gauge">' +
    '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' +
    '<circle cx="' + size/2 + '" cy="' + size/2 + '" r="' + r + '" fill="none" stroke="#21262d" stroke-width="6" ' +
    'stroke-dasharray="' + arc + ' ' + (circ - arc) + '" stroke-dashoffset="' + (-circ * 0.375) + '" stroke-linecap="round"/>' +
    '<circle cx="' + size/2 + '" cy="' + size/2 + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="6" ' +
    'stroke-dasharray="' + filled + ' ' + (circ - filled) + '" stroke-dashoffset="' + (-circ * 0.375) + '" stroke-linecap="round" style="transition:stroke-dasharray 0.5s"/>' +
    '<text x="' + size/2 + '" y="' + (size/2 + 2) + '" text-anchor="middle" fill="' + color + '" font-size="' + (size * 0.22) + '" font-weight="700">' + pct + '%</text>' +
    '</svg>' +
    (label ? '<div class="viz-gauge-label">' + esc(label) + '</div>' : '') +
    '</div>';
}

function svgDonut(pct, size, label, used, total, color) {
  var r = (size - 8) / 2;
  var circ = 2 * Math.PI * r;
  var dashPct = Math.min(100, Math.max(0, pct));
  var filled = circ * dashPct / 100;
  if (!color) color = barColor(pct, false);
  return '<div class="viz-donut">' +
    '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' +
    '<circle cx="' + size/2 + '" cy="' + size/2 + '" r="' + r + '" fill="none" stroke="#21262d" stroke-width="5"/>' +
    '<circle cx="' + size/2 + '" cy="' + size/2 + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="5" ' +
    'stroke-dasharray="' + filled + ' ' + (circ - filled) + '" stroke-dashoffset="' + (-circ * 0.25) + '" stroke-linecap="round" style="transition:stroke-dasharray 0.5s"/>' +
    '<text x="' + size/2 + '" y="' + (size/2 - 2) + '" text-anchor="middle" fill="var(--bright)" font-size="' + (size * 0.18) + '" font-weight="700">' + pct + '%</text>' +
    '<text x="' + size/2 + '" y="' + (size/2 + size*0.12) + '" text-anchor="middle" fill="var(--dim)" font-size="' + (size * 0.11) + '">' + esc(used) + '/' + esc(total) + '</text>' +
    '</svg>' +
    (label ? '<div class="viz-donut-label">' + esc(label) + '</div>' : '') +
    '</div>';
}

function svgSignalArc(dbm) {
  /* map dBm to quality: -30=perfect, -90=terrible */
  var quality = Math.max(0, Math.min(100, (dbm + 90) * 100 / 60));
  var color = barColor(quality, true);
  var bars = 5;
  var html = '<div class="viz-signal"><svg width="100" height="60" viewBox="0 0 100 60">';
  for (var i = 0; i < bars; i++) {
    var bh = 12 + i * 10;
    var bx = 10 + i * 18;
    var active = quality > (i * 20);
    html += '<rect x="' + bx + '" y="' + (55 - bh) + '" width="12" height="' + bh + '" rx="2" fill="' + (active ? color : '#21262d') + '"/>';
  }
  html += '<text x="50" y="58" text-anchor="middle" fill="var(--dim)" font-size="9">' + dbm + ' dBm</text>';
  html += '</svg></div>';
  return html;
}

function vizHBar(items, maxVal) {
  /* items: [{name, value, label}] */
  if (!maxVal) {
    maxVal = 0;
    for (var i = 0; i < items.length; i++) if (items[i].value > maxVal) maxVal = items[i].value;
  }
  if (maxVal === 0) maxVal = 1;
  var html = '<div class="viz-hbar">';
  var colors = ['#58a6ff','#3fb950','#d29922','#f85149','#bc8cff','#79c0ff','#56d364','#e3b341','#ff7b72','#d2a8ff'];
  for (var i = 0; i < items.length; i++) {
    var pct = Math.round(items[i].value * 100 / maxVal);
    var c = colors[i % colors.length];
    html += '<div class="viz-hbar-row">' +
      '<span class="viz-hbar-name">' + esc(items[i].name) + '</span>' +
      '<div class="viz-hbar-track"><div class="viz-hbar-fill" style="width:' + pct + '%;background:' + c + '"></div></div>' +
      '<span class="viz-hbar-val">' + esc(items[i].label || String(items[i].value)) + '</span>' +
      '</div>';
  }
  html += '</div>';
  return html;
}

function vizCards(items) {
  /* items: [{value, label, color?}] */
  var html = '<div class="viz-cards">';
  for (var i = 0; i < items.length; i++) {
    var style = items[i].color ? ' style="color:' + items[i].color + '"' : '';
    html += '<div class="viz-card"><div class="viz-card-val"' + style + '>' + esc(items[i].value) + '</div>' +
      '<div class="viz-card-label">' + esc(items[i].label) + '</div></div>';
  }
  html += '</div>';
  return html;
}

function vizStatusGrid(items) {
  /* items: [{name, status, detail, color}] */
  var html = '<div class="viz-status-grid">';
  for (var i = 0; i < items.length; i++) {
    html += '<div class="viz-status-item">' +
      '<span class="viz-status-dot" style="background:' + (items[i].color || 'var(--dim)') + '"></span>' +
      '<span class="viz-status-name">' + esc(items[i].name) + '</span>' +
      (items[i].detail ? '<span class="viz-status-detail">' + esc(items[i].detail) + '</span>' : '') +
      '</div>';
  }
  html += '</div>';
  return html;
}

function svgSparkline(values, width, height, color) {
  if (!values.length) return '';
  var max = 0;
  for (var i = 0; i < values.length; i++) if (values[i] > max) max = values[i];
  if (max === 0) max = 1;
  var step = width / Math.max(1, values.length - 1);
  var pts = [];
  for (var i = 0; i < values.length; i++) {
    var x = Math.round(i * step);
    var y = Math.round(height - (values[i] / max) * (height - 4) - 2);
    pts.push(x + ',' + y);
  }
  return '<svg width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '" style="display:block">' +
    '<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + (color || 'var(--accent)') + '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' +
    '</svg>';
}

function svgMiniBar(pct, w, h, color) {
  return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
    '<rect x="0" y="0" width="' + w + '" height="' + h + '" rx="' + h/2 + '" fill="#21262d"/>' +
    '<rect x="0" y="0" width="' + Math.round(w * pct / 100) + '" height="' + h + '" rx="' + h/2 + '" fill="' + (color || 'var(--accent)') + '"/>' +
    '</svg>';
}

/* ---- parse helpers ---- */

function parseBoxLines(text) {
  var lines = text.split(NL);
  var sections = [];
  var current = { title: '', rows: [] };

  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var stripped = line.replace(/[\u2502\u250c\u2514\u251c\u2500\u2524\u2510\u2518\u2534\u252c\u2504\u2508\u2550\u2551\u2554\u2557\u255a\u255d\u2560\u2563]/g, '').trim();

    if (/^[\u250c\u2514\u2554\u255a]/.test(line.trim())) continue;
    if (/^[\u251c\u2500\u2524\u2560\u2550]+$/.test(line.replace(/\s/g, '')) || (!stripped && /[\u251c\u2500\u2550]/.test(line))) {
      if (current.rows.length > 0 || current.title) { sections.push(current); current = { title: '', rows: [] }; }
      continue;
    }
    if (!stripped) continue;
    /* title row */
    if (!stripped.includes(':') && !stripped.match(/^\d/) && stripped.length > 5 && /^\s{3,}/.test(line.replace(/[\u2502\u2551]/g, ''))) {
      current.title = stripped;
      continue;
    }
    current.rows.push(stripped);
  }
  if (current.rows.length > 0 || current.title) sections.push(current);
  return sections;
}

function parseSize(s) {
  var m = s.match(/([\d.]+)\s*([GMKT])/i);
  if (!m) return parseFloat(s) || 0;
  var v = parseFloat(m[1]);
  var u = m[2].toUpperCase();
  if (u === 'G') return v * 1024;
  if (u === 'T') return v * 1024 * 1024;
  if (u === 'K') return v / 1024;
  return v;
}

/* ---- main formatOutput ---- */

function formatOutput(text, rc) {
  var badge = '<span class="rc-badge ' + (rc === 0 ? 'rc-ok' : 'rc-fail') + '">exit ' + rc + '</span>';

  /* detect box-drawing */
  var isBox = /[\u2502\u250c\u2514\u251c\u2554\u255a\u2551]/.test(text);
  var html;
  if (isBox) {
    html = formatBoxOutput(text);
  } else {
    html = formatSectionOutput(text);
  }
  return badge + html;
}

function formatBoxOutput(text) {
  var sections = parseBoxLines(text);
  var html = [];
  var allKV = {};
  var fsData = [];
  var sizeData = [];

  /* first pass: extract structured data */
  for (var s = 0; s < sections.length; s++) {
    var sec = sections[s];
    for (var r = 0; r < sec.rows.length; r++) {
      var row = sec.rows[r];
      var kv = row.match(/^([A-Za-z][A-Za-z0-9 \/_.()-]+?):\s+(.+)$/);
      if (kv) allKV[kv[1].trim()] = kv[2].trim();

      /* filesystem lines: /path  25G / 30G  [bars]  88% */
      var fs = row.match(/^(\/\S*)\s+([\d.]+[GMK]?)\s*\/\s*([\d.]+[GMK]?)\s+.*?(\d+)%/);
      if (!fs) fs = row.match(/^(\/\S*)\s+([\d.]+[GMK]?)\s*\/\s*([\d.]+[GMK]?)\s+(\d+)%/);
      if (fs) { fsData.push({ mount: fs[1], used: fs[2], total: fs[3], pct: parseInt(fs[4]) }); continue; }

      /* size entries */
      var sz = row.match(/^([\d.]+[GMKT]?)\s+(.+)/);
      if (sz && !kv) { sizeData.push({ name: sz[2].trim(), size: sz[1], bytes: parseSize(sz[1]) }); }
    }
  }

  /* ---- battery report ---- */
  if (allKV['Charge'] || allKV['Status'] && (allKV['Voltage'] || allKV['Current'])) {
    var chargePct = 0;
    var chargeMatch = (allKV['Charge'] || '').match(/(\d+)\s*%/);
    if (chargeMatch) chargePct = parseInt(chargeMatch[1]);
    var isCharging = /charging/i.test(allKV['Status'] || '');

    html.push(svgGauge(chargePct, 140, allKV['Status'] || '', isCharging ? '#3fb950' : barColor(chargePct, true)));

    var cards = [];
    if (allKV['Voltage']) cards.push({ value: allKV['Voltage'], label: 'Voltage' });
    if (allKV['Current']) cards.push({ value: allKV['Current'], label: 'Current' });
    if (allKV['Power']) cards.push({ value: allKV['Power'], label: 'Power' });
    if (allKV['Charge rate']) cards.push({ value: allKV['Charge rate'], label: 'Charge Rate' });
    if (allKV['Time']) cards.push({ value: allKV['Time'], label: 'Time Remaining', color: 'var(--accent)' });
    if (allKV['Estimate']) cards.push({ value: allKV['Estimate'], label: 'Voltage Est.' });
    if (allKV['CPU temp']) cards.push({ value: allKV['CPU temp'], label: 'CPU Temp' });
    if (allKV['Health']) {
      var hc = /good/i.test(allKV['Health']) ? 'var(--green)' : 'var(--red)';
      cards.push({ value: allKV['Health'], label: 'Health', color: hc });
    }
    if (allKV['Source']) cards.push({ value: allKV['Source'], label: 'Source' });
    if (cards.length) html.push(vizCards(cards));
    return html.join('');
  }

  /* ---- network report ---- */
  if (allKV['Signal'] || allKV['SSID'] || allKV['Quality']) {
    var dbm = parseInt((allKV['Signal'] || '-80').match(/-?\d+/));
    html.push(svgSignalArc(dbm));

    var netCards = [];
    if (allKV['SSID']) netCards.push({ value: allKV['SSID'], label: 'Network' });
    if (allKV['Quality']) {
      var qc = /good/i.test(allKV['Quality']) ? 'var(--green)' : /fair/i.test(allKV['Quality']) ? 'var(--yellow)' : 'var(--text)';
      netCards.push({ value: allKV['Quality'], label: 'Quality', color: qc });
    }
    if (allKV['Bit rate']) netCards.push({ value: allKV['Bit rate'], label: 'Bit Rate' });
    if (allKV['IP']) netCards.push({ value: allKV['IP'], label: 'IP Address' });
    if (allKV['Band']) netCards.push({ value: allKV['Band'], label: 'Band' });
    if (allKV['Gateway']) netCards.push({ value: allKV['Gateway'], label: 'Gateway' });
    if (allKV['DNS']) netCards.push({ value: allKV['DNS'], label: 'DNS' });
    if (allKV['MAC']) netCards.push({ value: allKV['MAC'], label: 'MAC Address' });
    if (allKV['Tx power']) netCards.push({ value: allKV['Tx power'], label: 'Tx Power' });
    if (allKV['Antenna']) netCards.push({ value: allKV['Antenna'], label: 'Antenna' });
    if (allKV['Internet']) {
      var ic = /yes/i.test(allKV['Internet']) ? 'var(--green)' : 'var(--red)';
      netCards.push({ value: allKV['Internet'], label: 'Internet', color: ic });
    }
    if (netCards.length) html.push(vizCards(netCards));

    /* remaining KV */
    var netShown = ['Signal','SSID','Quality','Bit rate','IP','Band','Gateway','DNS','MAC','Tx power','Antenna','Internet','AP','Power mgmt'];
    for (var k in allKV) {
      if (netShown.indexOf(k) === -1) {
        html.push('<div class="out-row"><span class="out-key">' + esc(k) + '</span><span class="out-val">' + esc(allKV[k]) + '</span></div>');
      }
    }
    return html.join('');
  }

  /* ---- charge rate display ---- */
  if (allKV['Current charge rate'] || (Object.keys(allKV).length === 0 && text.match(/charge rate:\s*([\d]+)mA/i))) {
    var rateMatch = text.match(/(\d+)mA/);
    if (rateMatch) {
      var rate = parseInt(rateMatch[1]);
      var maxRate = 900;
      var ratePct = Math.round(rate * 100 / maxRate);
      html.push(svgGauge(ratePct, 120, rate + 'mA', rate >= 900 ? 'var(--red)' : rate >= 500 ? 'var(--yellow)' : 'var(--green)'));
      html.push(vizCards([
        { value: '300mA', label: 'Gentle', color: rate === 300 ? 'var(--green)' : 'var(--dim)' },
        { value: '500mA', label: 'Moderate', color: rate === 500 ? 'var(--yellow)' : 'var(--dim)' },
        { value: '900mA', label: 'Maximum', color: rate === 900 ? 'var(--red)' : 'var(--dim)' },
        { value: rate + 'mA', label: 'Current', color: 'var(--accent)' }
      ]));
      return '<span class="rc-badge rc-ok">exit 0</span>' + html.join('');
    }
  }

  /* ---- cleanup candidates ---- */
  var cleanupData = [];
  for (var s = 0; s < sections.length; s++) {
    if (/cleanup/i.test(sections[s].title)) {
      for (var r = 0; r < sections[s].rows.length; r++) {
        var row = sections[s].rows[r];
        var cm = row.match(/^([\d.]+[GMKT]?)\s+(.+)/);
        if (cm && parseSize(cm[1]) > 0) {
          cleanupData.push({ name: cm[2].trim(), size: cm[1], bytes: parseSize(cm[1]) });
        }
      }
    }
  }
  if (cleanupData.length > 0) {
    html.push('<div class="out-section-title">Cleanup Candidates</div>');
    var totalClean = 0;
    for (var i = 0; i < cleanupData.length; i++) totalClean += cleanupData[i].bytes;
    html.push('<div style="text-align:center;margin:8px 0"><span style="font-size:1.4em;font-weight:700;color:var(--bright)">' +
      (totalClean > 1024 ? (totalClean/1024).toFixed(1) + 'G' : totalClean.toFixed(0) + 'M') +
      '</span><span style="font-size:0.65em;color:var(--dim);margin-left:4px">reclaimable</span></div>');
    html.push(vizHBar(cleanupData.map(function(c) { return { name: c.name, value: c.bytes, label: c.size }; }), cleanupData[0].bytes));
    return '<span class="rc-badge rc-ok">exit 0</span>' + html.join('');
  }

  /* ---- storage / disk usage with filesystem donuts ---- */
  if (fsData.length > 0) {
    html.push('<div class="viz-donuts">');
    for (var f = 0; f < fsData.length; f++) {
      html.push(svgDonut(fsData[f].pct, 90, fsData[f].mount, fsData[f].used, fsData[f].total));
    }
    html.push('</div>');
  }

  /* size data as horizontal bars */
  if (sizeData.length > 0) {
    var maxBytes = 0;
    for (var i = 0; i < sizeData.length; i++) if (sizeData[i].bytes > maxBytes) maxBytes = sizeData[i].bytes;
    var barItems = [];
    for (var i = 0; i < sizeData.length; i++) {
      barItems.push({ name: sizeData[i].name, value: sizeData[i].bytes, label: sizeData[i].size });
    }
    html.push(vizHBar(barItems, maxBytes));
  }

  /* remaining key-value pairs not already visualized */
  var kvShown = ['Charge','Status','Voltage','Current','Power','Charge rate','Time','Estimate','CPU temp','Health','Source',
                 'Signal','SSID','Quality','Bit rate','IP','Band','Gateway','DNS','MAC','Tx power','Antenna','Internet','AP','Power mgmt'];
  for (var k in allKV) {
    if (kvShown.indexOf(k) === -1) {
      var val = allKV[k];
      var valClass = '';
      if (/good|active|yes|connected|charging|online/i.test(val)) valClass = ' ok';
      else if (/warning|fair|degraded/i.test(val)) valClass = ' warn';
      else if (/bad|failed|error|no|offline|critical/i.test(val)) valClass = ' err';
      html.push('<div class="out-row"><span class="out-key">' + esc(k) + '</span><span class="out-val' + valClass + '">' + esc(val) + '</span></div>');
    }
  }

  /* section titles without data */
  for (var s = 0; s < sections.length; s++) {
    if (sections[s].title && sections[s].rows.length === 0) {
      html.push('<div class="out-section-title">' + esc(sections[s].title) + '</div>');
    }
  }

  return html.join('');
}

function formatSectionOutput(text) {
  var lines = text.split(NL);
  var html = [];
  var inTable = false;
  var tableHeaders = [];
  var tableRows = [];
  var statusItems = [];

  function flushTable() {
    if (tableHeaders.length && tableRows.length) {
      /* render as status grid if it looks like backup status */
      var hasStatus = false;
      for (var r = 0; r < tableRows.length; r++) {
        if (/backed up|symlinked|not backed|empty/i.test(tableRows[r].join(' '))) { hasStatus = true; break; }
      }
      if (hasStatus) {
        var items = [];
        for (var r = 0; r < tableRows.length; r++) {
          var name = tableRows[r][0] || '';
          var status = tableRows[r][1] || '';
          var detail = tableRows[r][2] || '';
          var color = /backed up|symlinked/i.test(status) ? 'var(--green)' : /not backed|failed/i.test(status) ? 'var(--red)' : /empty/i.test(status) ? 'var(--yellow)' : 'var(--dim)';
          items.push({ name: name, status: status, detail: detail, color: color });
        }
        html.push(vizStatusGrid(items));
      } else {
        html.push('<table class="out-table"><thead><tr>');
        for (var h = 0; h < tableHeaders.length; h++) html.push('<th>' + esc(tableHeaders[h]) + '</th>');
        html.push('</tr></thead><tbody>');
        for (var r = 0; r < tableRows.length; r++) {
          html.push('<tr>');
          for (var c = 0; c < tableRows[r].length; c++) {
            var cell = tableRows[r][c];
            var cls = '';
            if (/backed up|symlinked|active|up to date/i.test(cell)) cls = ' style="color:var(--green)"';
            else if (/not backed|failed|empty/i.test(cell)) cls = ' style="color:var(--red)"';
            html.push('<td' + cls + '>' + esc(cell) + '</td>');
          }
          html.push('</tr>');
        }
        html.push('</tbody></table>');
      }
    }
    tableHeaders = [];
    tableRows = [];
    inTable = false;
  }

  /* ---- ping results visualization ---- */
  var pingTimes = [];
  var pingTarget = '';
  for (var i = 0; i < lines.length; i++) {
    var pt = lines[i].match(/time=([\d.]+)\s*ms/);
    if (pt) pingTimes.push(parseFloat(pt[1]));
    var ph = lines[i].match(/PING\s+(\S+)/);
    if (ph) pingTarget = ph[1];
  }
  if (pingTimes.length >= 3) {
    var pingMin = pingTimes[0], pingMax = pingTimes[0], pingSum = 0;
    for (var i = 0; i < pingTimes.length; i++) {
      if (pingTimes[i] < pingMin) pingMin = pingTimes[i];
      if (pingTimes[i] > pingMax) pingMax = pingTimes[i];
      pingSum += pingTimes[i];
    }
    var pingAvg = pingSum / pingTimes.length;
    var pingCol = pingAvg < 50 ? 'var(--green)' : pingAvg < 150 ? 'var(--yellow)' : 'var(--red)';
    html.push('<div class="out-section-title">Latency to ' + esc(pingTarget) + '</div>');
    html.push('<div style="text-align:center;margin:8px 0"><span style="font-size:1.6em;font-weight:700;color:' + pingCol + '">' +
      pingAvg.toFixed(0) + '</span><span style="font-size:0.65em;color:var(--dim);margin-left:4px">ms avg</span></div>');
    html.push('<div style="padding:4px 0">' + svgSparkline(pingTimes, 280, 40, pingCol) + '</div>');
    html.push(vizCards([
      { value: pingMin.toFixed(1) + 'ms', label: 'Min', color: 'var(--green)' },
      { value: pingMax.toFixed(1) + 'ms', label: 'Max', color: 'var(--red)' },
      { value: pingAvg.toFixed(1) + 'ms', label: 'Avg', color: pingCol },
      { value: String(pingTimes.length), label: 'Packets' }
    ]));
    /* packet loss */
    var lossMatch = text.match(/(\d+)% packet loss/);
    if (lossMatch) {
      var loss = parseInt(lossMatch[1]);
      var lossCol = loss === 0 ? 'var(--green)' : loss < 10 ? 'var(--yellow)' : 'var(--red)';
      html.push('<div class="out-row"><span class="out-key">Packet Loss</span><span class="out-val" style="color:' + lossCol + '">' + loss + '%</span></div>');
    }
    return '<span class="rc-badge rc-ok">exit 0</span>' + html.join('');
  }

  /* ---- power status ---- */
  var hasPowerData = false;
  var powerKV = {};
  for (var i = 0; i < lines.length; i++) {
    var pm = lines[i].trim().match(/^(Screen|Battery|AC|Uptime):\s+(.+)/);
    if (pm) { powerKV[pm[1]] = pm[2].trim(); hasPowerData = true; }
  }
  if (hasPowerData && powerKV['Battery']) {
    var batMatch = powerKV['Battery'].match(/(\d+)%/);
    var batPct = batMatch ? parseInt(batMatch[1]) : 0;
    html.push(svgGauge(batPct, 120, powerKV['Battery'], barColor(batPct, true)));
    var pCards = [];
    if (powerKV['AC']) {
      var acOn = /connected/i.test(powerKV['AC']);
      pCards.push({ value: acOn ? 'Connected' : 'Disconnected', label: 'AC Power', color: acOn ? 'var(--green)' : 'var(--dim)' });
    }
    if (powerKV['Screen']) pCards.push({ value: powerKV['Screen'], label: 'Screen' });
    if (powerKV['Uptime']) pCards.push({ value: powerKV['Uptime'], label: 'Uptime', color: 'var(--accent)' });
    if (pCards.length) html.push(vizCards(pCards));
    return '<span class="rc-badge rc-ok">exit 0</span>' + html.join('');
  }

  /* ---- update history timeline ---- */
  var historyEntries = [];
  var inHistory = false;
  for (var i = 0; i < lines.length; i++) {
    var hm = lines[i].trim().match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.+)$/);
    if (hm) { historyEntries.push({ time: hm[1], action: hm[2], detail: hm[3].trim() }); inHistory = true; }
    if (/entries in/.test(lines[i])) inHistory = true;
  }
  if (historyEntries.length >= 2 && inHistory) {
    html.push('<div class="out-section-title">Update History</div>');
    var actionColors = { all: 'var(--accent)', apt: 'var(--green)', flatpak: '#bc8cff', snapshot: 'var(--yellow)', repo: '#79c0ff', firmware: 'var(--dim)' };
    for (var i = 0; i < historyEntries.length; i++) {
      var e = historyEntries[i];
      var dot = actionColors[e.action] || 'var(--dim)';
      var isFail = /fail/i.test(e.detail);
      html.push('<div style="display:flex;align-items:flex-start;gap:10px;padding:4px 0;font-size:0.7em">' +
        '<span style="flex-shrink:0;width:8px;height:8px;border-radius:50%;background:' + (isFail ? 'var(--red)' : dot) + ';margin-top:4px"></span>' +
        '<div style="flex:1"><div style="color:var(--text)">' + esc(e.action) + '<span style="color:var(--dim);margin-left:6px">' + esc(e.detail) + '</span></div>' +
        '<div style="color:var(--dim);font-size:0.85em">' + esc(e.time) + '</div></div></div>');
    }
    return '<span class="rc-badge rc-ok">exit 0</span>' + html.join('');
  }

  /* big files: detect SIZE  FILE pattern */
  var bigFiles = [];
  var inBigFiles = false;

  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var trimmed = line.trim();

    if (!trimmed) { if (inTable) flushTable(); continue; }

    /* big files header */
    if (/files larger than/i.test(trimmed)) {
      inBigFiles = true;
      html.push('<div class="out-section-title">' + esc(trimmed) + '</div>');
      continue;
    }

    /* section header */
    var sec = trimmed.match(/^[\u2500\u2501\u2014-]+\s+(.+?)\s+[\u2500\u2501\u2014-]+$/);
    if (sec) {
      if (inTable) flushTable();
      if (inBigFiles && bigFiles.length > 0) {
        var maxB = 0;
        for (var b = 0; b < bigFiles.length; b++) if (bigFiles[b].bytes > maxB) maxB = bigFiles[b].bytes;
        html.push(vizHBar(bigFiles.slice(0, 15), maxB));
        bigFiles = [];
        inBigFiles = false;
      }
      html.push('<div class="out-section"><div class="out-section-title">' + esc(sec[1]) + '</div></div>');
      continue;
    }

    if (/^[\u2500\u2501\u2014-]+$/.test(trimmed)) continue;

    /* big file line */
    if (inBigFiles) {
      var bf = trimmed.match(/^([\d.]+[GMKT]?)\s+(.+)/);
      if (bf) {
        var fname = bf[2].replace(/.*\//, ''); /* basename */
        bigFiles.push({ name: fname, value: parseSize(bf[1]), label: bf[1] });
        continue;
      }
      if (/^SIZE|^-+/.test(trimmed)) continue;
    }

    /* status icon lines */
    var icon = trimmed.match(/^([\u2713\u2714\u2705\u2611])\s+(.+)/);
    if (icon) {
      html.push('<div class="out-status"><span class="out-icon ok">\u2713</span><span class="label">' + esc(icon[2]) + '</span></div>');
      continue;
    }
    icon = trimmed.match(/^([\u2717\u2718\u274C\u2612])\s+(.+)/);
    if (icon) {
      html.push('<div class="out-status"><span class="out-icon err">\u2717</span><span class="label">' + esc(icon[2]) + '</span></div>');
      continue;
    }
    icon = trimmed.match(/^(!)\s+(.+)/);
    if (icon) {
      html.push('<div class="out-status"><span class="out-icon warn">!</span><span class="label">' + esc(icon[2]) + '</span></div>');
      continue;
    }

    /* table header */
    if (/^[A-Z][A-Z ]+\s{2,}[A-Z]/.test(trimmed)) {
      if (inTable) flushTable();
      tableHeaders = trimmed.split(/\s{2,}/);
      inTable = true;
      continue;
    }

    /* table row */
    if (inTable && tableHeaders.length > 0) {
      var cells = trimmed.split(/\s{2,}/);
      if (cells.length >= 2) {
        tableRows.push(cells);
        continue;
      } else {
        flushTable();
      }
    }

    /* key: value */
    var kv = trimmed.match(/^([A-Za-z][A-Za-z0-9 _()-]+?):\s{2,}(.+)$/);
    if (!kv) kv = trimmed.match(/^([A-Za-z][A-Za-z0-9 _()-]+?)\s{3,}(.+)$/);
    if (kv) {
      var key = kv[1].trim();
      var val = kv[2].trim();
      var valClass = '';
      if (/good|active|up to date|backed up|symlinked/i.test(val)) valClass = ' ok';
      else if (/warning|partial|outdated|updatable/i.test(val)) valClass = ' warn';
      else if (/failed|error|not backed/i.test(val)) valClass = ' err';
      html.push('<div class="out-row"><span class="out-key">' + esc(key) + '</span><span class="out-val' + valClass + '">' + esc(val) + '</span></div>');
      continue;
    }

    /* note lines */
    if (/^(Intentionally|Note:|Tip:|Warning:|Checked:|Last )/i.test(trimmed)) {
      html.push('<div class="out-note">' + esc(trimmed) + '</div>');
      continue;
    }

    /* indented list */
    if (/^\s{4,}/.test(line) || /^[-*]/.test(trimmed)) {
      html.push('<div class="out-list-item">' + esc(trimmed) + '</div>');
      continue;
    }

    html.push('<div class="out-list-item">' + esc(trimmed) + '</div>');
  }

  if (inTable) flushTable();
  if (inBigFiles && bigFiles.length > 0) {
    var maxB = 0;
    for (var b = 0; b < bigFiles.length; b++) if (bigFiles[b].bytes > maxB) maxB = bigFiles[b].bytes;
    html.push(vizHBar(bigFiles.slice(0, 15), maxB));
  }

  return html.join('');
}

/* ---- output display ---- */

function showOutput(title, html) {
  var box = document.getElementById('output-box');
  var content = document.getElementById('output-content');
  setText('output-title', title);
  content.innerHTML = html;
  box.style.display = 'block';
  _showRaw = false;
  document.getElementById('raw-toggle').textContent = 'Raw';
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showRawOutput(title, text) {
  var box = document.getElementById('output-box');
  var content = document.getElementById('output-content');
  setText('output-title', title);
  var pre = document.createElement('pre');
  pre.className = 'raw';
  pre.textContent = text;
  content.innerHTML = '';
  content.appendChild(pre);
  box.style.display = 'block';
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function toggleRaw() {
  _showRaw = !_showRaw;
  document.getElementById('raw-toggle').textContent = _showRaw ? 'Styled' : 'Raw';
  var content = document.getElementById('output-content');
  if (_showRaw) {
    var pre = document.createElement('pre');
    pre.className = 'raw';
    pre.textContent = _rawOutput;
    if (_rawError) {
      var err = document.createElement('span');
      err.className = 'stderr';
      err.textContent = NL + '--- stderr ---' + NL + _rawError;
      pre.appendChild(err);
    }
    content.innerHTML = '';
    content.appendChild(pre);
  } else {
    content.innerHTML = formatOutput(_rawOutput, _rawRc);
    if (_rawError) {
      var errDiv = document.createElement('div');
      errDiv.className = 'out-section';
      errDiv.innerHTML = '<div class="out-section-title" style="color:var(--red)">stderr</div>';
      var errPre = document.createElement('pre');
      errPre.className = 'raw';
      errPre.style.color = 'var(--red)';
      errPre.textContent = _rawError;
      errDiv.appendChild(errPre);
      content.appendChild(errDiv);
    }
  }
}

var running = false;
async function run(name) {
  if (running) return;
  running = true;
  var startTime = performance.now();
  document.querySelectorAll('button').forEach(function(b) { b.disabled = true; });

  var box = document.getElementById('output-box');
  var content = document.getElementById('output-content');
  setText('output-title', name);
  box.style.display = 'block';
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  /* streaming output via SSE */
  var pre = document.createElement('pre');
  pre.className = 'raw';
  pre.style.maxHeight = '60vh';
  pre.style.overflow = 'auto';
  content.innerHTML = '';
  content.appendChild(pre);

  _rawOutput = '';
  _rawError = '';
  _rawRc = 0;
  _showRaw = false;

  try {
    var es = new EventSource('/api/stream/' + name);

    es.onmessage = function(e) {
      _rawOutput += e.data + '\n';
      pre.textContent += e.data + '\n';
      pre.scrollTop = pre.scrollHeight;
    };

    await new Promise(function(resolve, reject) {
      es.addEventListener('done', function(e) {
        es.close();
        try {
          var d = JSON.parse(e.data);
          _rawRc = d.returncode;
          _rawError = d.error || '';
        } catch(ex) {}
        resolve();
      });
      es.onerror = function() {
        es.close();
        reject(new Error('Stream connection lost'));
      };
    });

    var elapsed = ((performance.now() - startTime) / 1000).toFixed(1);

    /* re-render with styled output now that we have the full text */
    var html = formatOutput(_rawOutput || '(no output)', _rawRc);
    if (_rawError) {
      html += '<div class="out-section"><div class="out-section-title" style="color:var(--red)">stderr</div>';
      html += '<pre class="raw" style="color:var(--red)">' + esc(_rawError) + '</pre></div>';
    }
    content.innerHTML = html;

    if (_rawRc === 0) {
      toast(name + ' completed in ' + elapsed + 's', 'ok');
    } else {
      toast(name + ' failed (exit ' + _rawRc + ')', 'err');
    }
  } catch (e) {
    content.innerHTML = '<div class="out-list-item" style="color:var(--red)">Error: ' + esc(e.message) + '</div>';
    toast(name + ' error: ' + e.message, 'err');
  }

  running = false;
  document.querySelectorAll('button').forEach(function(b) { b.disabled = false; });
  refresh();
}

function togglePanel(panel, e) {
  if (e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT') return;
  panel.classList.toggle('open');
  savePanelState();
}
function closeOutput() {
  var box = document.getElementById('output-box');
  box.style.animation = 'none';
  box.style.display = 'none';
}

/* ---- debug tools (styled) ---- */

async function showProcs(sort) {
  showRawOutput('Top by ' + sort.toUpperCase(), 'loading...');
  try {
    var r = await fetch('/api/processes/' + sort);
    var procs = await r.json();
    if (procs[0] && procs[0].error) { showRawOutput('Error', procs[0].error); return; }
    _rawOutput = ''; _rawError = ''; _rawRc = 0;
    var html = '<table class="out-table"><thead><tr><th>PID</th><th>User</th><th>CPU%</th><th>Mem%</th><th>RSS</th><th>Command</th></tr></thead><tbody>';
    for (var i = 0; i < procs.length; i++) {
      var p = procs[i];
      var cpuCol = p.cpu > 50 ? 'var(--red)' : p.cpu > 20 ? 'var(--yellow)' : 'var(--text)';
      var memCol = p.mem > 30 ? 'var(--red)' : p.mem > 15 ? 'var(--yellow)' : 'var(--text)';
      html += '<tr><td>' + p.pid + '</td><td>' + esc(p.user) + '</td>';
      html += '<td style="color:' + cpuCol + '">' + p.cpu.toFixed(1) + '</td>';
      html += '<td style="color:' + memCol + '">' + p.mem.toFixed(1) + '</td>';
      html += '<td>' + (p.rss_kb/1024).toFixed(1) + 'M</td>';
      html += '<td>' + esc(p.command) + '</td></tr>';
    }
    html += '</tbody></table>';
    showOutput('Top by ' + sort.toUpperCase(), html);
    _rawOutput = procs.map(function(p) {
      return p.pid + ' ' + p.user + ' ' + p.cpu + '% ' + p.mem + '% ' + p.command;
    }).join(NL);
  } catch(e) { showRawOutput('Error', e.message); }
}

function segLog(btn, idx, source) {
  var slider = btn.parentElement.querySelector('.seg-slider');
  if (slider) slider.style.transform = 'translateX(' + (idx * 100) + '%)';
  showLogs(source);
}

async function showLogs(source) {
  showRawOutput(source, 'loading...');
  try {
    var r = await fetch('/api/logs/' + source);
    var d = await r.json();
    _rawOutput = d.output || d.error || '(empty)';
    _rawError = ''; _rawRc = 0;
    showRawOutput(source, _rawOutput);
  } catch(e) { showRawOutput('Error', e.message); }
}

async function showConns() {
  showRawOutput('Network Connections', 'loading...');
  try {
    var r = await fetch('/api/connections');
    var d = await r.json();
    _rawOutput = d.output || '(none)';
    _rawError = ''; _rawRc = 0;
    showRawOutput('Network Connections', _rawOutput);
  } catch(e) { showRawOutput('Error', e.message); }
}

async function showServices() {
  showRawOutput('Services', 'loading...');
  try {
    var r = await fetch('/api/services');
    var d = await r.json();
    var html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">';
    for (var i = 0; i < d.services.length; i++) {
      var s = d.services[i];
      var cls = s.state === 'active' ? 'active' : s.state === 'failed' ? 'failed' : 'inactive';
      html += '<span class="svc-pill ' + cls + '">' + esc(s.name) + ': ' + esc(s.state) + '</span>';
    }
    html += '</div>';
    if (d.failed) {
      html += '<div class="out-section"><div class="out-section-title" style="color:var(--red)">Failed Units</div>';
      html += '<pre class="raw">' + esc(d.failed) + '</pre></div>';
    }
    _rawOutput = d.services.map(function(s) { return s.name + ': ' + s.state; }).join(NL);
    if (d.failed) _rawOutput += NL + NL + '--- Failed ---' + NL + d.failed;
    _rawError = ''; _rawRc = 0;
    showOutput('Services', html);
    /* also update inline pills */
    var svcContainer = document.getElementById('svc-container');
    if (svcContainer) svcContainer.innerHTML = '';
  } catch(e) { showRawOutput('Error', e.message); }
}

async function showFailedUnits() {
  showRawOutput('Failed Units', 'loading...');
  try {
    var r = await fetch('/api/services');
    var d = await r.json();
    _rawOutput = d.failed || '(none - all clear)';
    _rawError = ''; _rawRc = 0;
    if (!d.failed) {
      showOutput('Failed Units', '<div class="out-status"><span class="out-icon ok">\u2713</span><span class="label">No failed units</span></div>');
    } else {
      showRawOutput('Failed Units', d.failed);
    }
  } catch(e) { showRawOutput('Error', e.message); }
}

/* ---- wiki ---- */
var _wikiSlug = '';

function wikiLoadList() {
  fetch('/api/wiki').then(function(r) { return r.json(); }).then(function(d) {
    var el = document.getElementById('wiki-list');
    var badge = document.getElementById('wiki-count');
    var docs = d.docs || [];
    badge.textContent = docs.length + ' docs';
    if (!docs.length) { el.innerHTML = '<div style="font-size:0.7em;color:var(--dim);padding:8px">No docs yet. Create one above.</div>'; return; }
    var html = '';
    for (var i = 0; i < docs.length; i++) {
      var doc = docs[i];
      var date = new Date(doc.modified * 1000);
      var ago = date.toLocaleDateString();
      html += '<div class="wiki-item" onclick="wikiOpen(\'' + esc(doc.slug) + '\')">' +
        '<span class="wi-icon">&#x1F4C4;</span>' +
        '<span class="wi-title">' + esc(doc.title) + '</span>' +
        '<span class="wi-meta">' + ago + '</span></div>';
    }
    el.innerHTML = html;
  }).catch(function() {});
}

function wikiOpen(slug) {
  _wikiSlug = slug;
  fetch('/api/wiki/' + slug).then(function(r) { return r.json(); }).then(function(d) {
    document.getElementById('wiki-view-title').textContent = slug;
    document.getElementById('wiki-view-content').innerHTML = renderMarkdown(d.content || '');
    document.getElementById('wiki-viewer').className = 'wiki-viewer open';
    document.getElementById('wiki-editor').className = 'wiki-editor';
    document.getElementById('wiki-list').style.display = 'none';
  });
}

function wikiEdit() {
  fetch('/api/wiki/' + _wikiSlug).then(function(r) { return r.json(); }).then(function(d) {
    document.getElementById('wiki-edit-title').textContent = _wikiSlug;
    document.getElementById('wiki-textarea').value = d.content || '';
    document.getElementById('wiki-editor').className = 'wiki-editor open';
    document.getElementById('wiki-viewer').className = 'wiki-viewer';
  });
}

function wikiNew() {
  var slug = document.getElementById('wiki-new-slug').value.trim().replace(/[^a-zA-Z0-9_-]/g, '-').replace(/-+/g, '-');
  if (!slug) return;
  _wikiSlug = slug;
  document.getElementById('wiki-edit-title').textContent = slug;
  document.getElementById('wiki-textarea').value = '# ' + slug.replace(/-/g, ' ') + NL + NL;
  document.getElementById('wiki-editor').className = 'wiki-editor open';
  document.getElementById('wiki-viewer').className = 'wiki-viewer';
  document.getElementById('wiki-list').style.display = 'none';
  document.getElementById('wiki-new-slug').value = '';
}

function wikiSave() {
  var content = document.getElementById('wiki-textarea').value;
  fetch('/api/wiki/' + _wikiSlug, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: content })
  }).then(function() {
    wikiClose();
    wikiLoadList();
  });
}

function wikiDelete() {
  if (!confirm('Delete "' + _wikiSlug + '"?')) return;
  fetch('/api/wiki/' + _wikiSlug, { method: 'DELETE' }).then(function() {
    wikiClose();
    wikiLoadList();
  });
}

function wikiClose() {
  document.getElementById('wiki-editor').className = 'wiki-editor';
  document.getElementById('wiki-viewer').className = 'wiki-viewer';
  document.getElementById('wiki-list').style.display = '';
  _wikiSlug = '';
}

function renderMarkdown(md) {
  /* lightweight markdown to HTML */
  var lines = md.split(NL);
  var html = '';
  var inCode = false;
  var inList = false;
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    /* fenced code blocks */
    if (/^```/.test(line.trim())) {
      if (inCode) { html += '</code></pre>'; inCode = false; }
      else { html += '<pre><code>'; inCode = true; }
      continue;
    }
    if (inCode) { html += esc(line) + NL; continue; }
    /* close list if needed */
    if (inList && !/^[-*]\s/.test(line.trim()) && line.trim()) { html += '</ul>'; inList = false; }
    /* headings */
    var h = line.match(/^(#{1,3})\s+(.+)/);
    if (h) { var lvl = h[1].length; html += '<h' + lvl + '>' + esc(h[2]) + '</h' + lvl + '>'; continue; }
    /* hr */
    if (/^---+$/.test(line.trim())) { html += '<hr>'; continue; }
    /* list items */
    var li = line.match(/^\s*[-*]\s+(.+)/);
    if (li) { if (!inList) { html += '<ul>'; inList = true; } html += '<li>' + inlineFormat(li[1]) + '</li>'; continue; }
    /* blockquote */
    if (/^>\s/.test(line)) { html += '<blockquote>' + inlineFormat(line.substring(2)) + '</blockquote>'; continue; }
    /* empty line */
    if (!line.trim()) { html += '<br>'; continue; }
    /* paragraph */
    html += '<p>' + inlineFormat(line) + '</p>';
  }
  if (inCode) html += '</code></pre>';
  if (inList) html += '</ul>';
  return html;
}

function inlineFormat(text) {
  var s = esc(text);
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/`(.+?)`/g, '<code>$1</code>');
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
  return s;
}

restorePanelState();
wikiLoadList();
refresh();
loadTimers();
loadConfig();
setInterval(refresh, 5000);
setInterval(loadTimers, 30000);
setInterval(loadConfig, 30000);

/* ── ESP32 sensor polling ── */
async function refreshESP32() {
  try {
    var r = await fetch('/api/esp32');
    var d = await r.json();
    var badge = document.getElementById('esp32-status');
    if (d.online) {
      badge.textContent = 'online';
      badge.style.color = 'var(--green)';
      badge.style.background = 'var(--green-glow)';
    } else {
      badge.textContent = 'offline';
      badge.style.color = 'var(--dim)';
      badge.style.background = 'var(--card2)';
    }
    if (d.temp_c !== undefined) setText('esp32-temp', d.temp_c);
    if (d.free_kb !== undefined) setText('esp32-free', d.free_kb);
    if (d.ip) setText('esp32-ip', d.ip);
    if (d.touches) {
      ['touch0','touch3','touch4','touch7'].forEach(function(k) {
        var el = document.getElementById('esp32-' + k.replace('ouch',''));
        if (el && d.touches[k] !== undefined) {
          el.textContent = d.touches[k] ? 'touched' : '--';
          el.style.color = d.touches[k] ? 'var(--green)' : '';
        }
      });
    }
    if (d.age >= 0) setText('esp32-age', d.age);
  } catch(e) {}
}
refreshESP32();
setInterval(refreshESP32, 3000);

/* ── GPS polling ── */
async function refreshGPS() {
  try {
    var r = await fetch('/api/gps');
    var d = await r.json();
    var badge = document.getElementById('gps-status');
    if (d.online) {
      var fix = d.fix || '3D';
      badge.textContent = fix;
      badge.style.color = 'var(--green)';
      badge.style.background = 'var(--green-glow)';
    } else {
      badge.textContent = 'no fix';
      badge.style.color = 'var(--dim)';
      badge.style.background = 'var(--card2)';
    }
    if (d.lat !== undefined) setText('gps-lat', d.lat.toFixed(6));
    if (d.lon !== undefined) setText('gps-lon', d.lon.toFixed(6));
    if (d.alt !== undefined) setText('gps-alt', d.alt.toFixed(0));
    if (d.speed !== undefined) setText('gps-speed', d.speed.toFixed(1));
    if (d.sats !== undefined) setText('gps-sats', d.sats);
    if (d.fix !== undefined) setText('gps-fix', d.fix);
    if (d.age >= 0) setText('gps-age', d.age);
  } catch(e) {}
}
refreshGPS();
setInterval(refreshGPS, 3000);

/* ── SDR polling ── */
async function refreshSDR() {
  try {
    var r = await fetch('/api/sdr');
    var d = await r.json();
    var badge = document.getElementById('sdr-status');
    if (d.online) {
      badge.textContent = 'active';
      badge.style.color = 'var(--green)';
      badge.style.background = 'var(--green-glow)';
    } else {
      badge.textContent = d.detected ? 'idle' : 'offline';
      badge.style.color = 'var(--dim)';
      badge.style.background = 'var(--card2)';
    }
    if (d.tuner) setText('sdr-tuner', d.tuner);
  } catch(e) {}
}
refreshSDR();
setInterval(refreshSDR, 5000);

/* ── LoRa polling ── */
async function refreshLoRa() {
  try {
    var r = await fetch('/api/lora');
    var d = await r.json();
    var badge = document.getElementById('lora-status');
    if (d.online) {
      badge.textContent = 'active';
      badge.style.color = 'var(--green)';
      badge.style.background = 'var(--green-glow)';
    } else {
      badge.textContent = 'idle';
      badge.style.color = 'var(--dim)';
      badge.style.background = 'var(--card2)';
    }
    if (d.freq) setText('lora-freq', d.freq);
    if (d.sf) setText('lora-sf', d.sf);
    if (d.bw) setText('lora-bw', d.bw);
    if (d.message) setText('lora-msg', d.message);
    if (d.rssi !== undefined) setText('lora-rssi', d.rssi);
    if (d.age >= 0) setText('lora-age', d.age);
  } catch(e) {}
}
refreshLoRa();
setInterval(refreshLoRa, 3000);

/* ── Battery Test chart ── */
var _batColors = ['#0a84ff','#30d158','#ff9f0a','#ff453a','#bf5af2','#64d2ff','#ff375f'];
function loadBatChart() {
  fetch('/api/battery-test/chart').then(function(r){return r.json()}).then(function(data) {
    var canvas = document.getElementById('battest-chart');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var W = canvas.width, H = canvas.height;
    var pad = {t:20,r:15,b:30,l:50};
    ctx.clearRect(0,0,W,H);
    ctx.fillStyle = 'var(--card2)';
    ctx.fillRect(0,0,W,H);

    var labels = Object.keys(data);
    var badge = document.getElementById('battest-badge');
    badge.textContent = labels.length ? labels.length + ' tests' : 'none';

    if (!labels.length) {
      ctx.fillStyle = '#8e8e93';
      ctx.font = '14px -apple-system, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('No test data yet', W/2, H/2);
      document.getElementById('battest-legend').innerHTML = '';
      return;
    }

    /* find global voltage range */
    var vmin = 5, vmax = 0;
    labels.forEach(function(k) {
      data[k].forEach(function(r) {
        if (r.v < vmin) vmin = r.v;
        if (r.v > vmax) vmax = r.v;
      });
    });
    vmin = Math.floor(vmin * 10) / 10 - 0.05;
    vmax = Math.ceil(vmax * 10) / 10 + 0.05;

    /* axes */
    ctx.strokeStyle = '#48484a';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.l, pad.t);
    ctx.lineTo(pad.l, H-pad.b);
    ctx.lineTo(W-pad.r, H-pad.b);
    ctx.stroke();

    /* Y axis labels */
    ctx.fillStyle = '#8e8e93';
    ctx.font = '11px -apple-system, system-ui, sans-serif';
    ctx.textAlign = 'right';
    for (var v = Math.ceil(vmin*10)/10; v <= vmax; v += 0.1) {
      var y = pad.t + (1 - (v-vmin)/(vmax-vmin)) * (H-pad.t-pad.b);
      ctx.fillText(v.toFixed(1)+'V', pad.l-5, y+4);
      ctx.strokeStyle = '#2c2c2e';
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W-pad.r, y); ctx.stroke();
    }

    /* plot each test by elapsed minutes */
    var maxMin = 0;
    labels.forEach(function(k) {
      var rows = data[k];
      if (rows.length < 2) return;
      var t0 = new Date(rows[0].t).getTime();
      var tN = (new Date(rows[rows.length-1].t).getTime() - t0) / 60000;
      if (tN > maxMin) maxMin = tN;
    });
    if (maxMin === 0) maxMin = 1;

    /* X axis labels */
    ctx.textAlign = 'center';
    ctx.fillStyle = '#8e8e93';
    var xStep = maxMin > 120 ? 30 : maxMin > 30 ? 10 : 5;
    for (var m = 0; m <= maxMin; m += xStep) {
      var x = pad.l + (m/maxMin) * (W-pad.l-pad.r);
      ctx.fillText(m+'m', x, H-pad.b+15);
    }

    var legend = [];
    labels.forEach(function(k, i) {
      var rows = data[k];
      if (rows.length < 2) return;
      var color = _batColors[i % _batColors.length];
      var t0 = new Date(rows[0].t).getTime();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      rows.forEach(function(r, j) {
        var elapsed = (new Date(r.t).getTime() - t0) / 60000;
        var x = pad.l + (elapsed/maxMin) * (W-pad.l-pad.r);
        var y = pad.t + (1 - (r.v-vmin)/(vmax-vmin)) * (H-pad.t-pad.b);
        if (j === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
      legend.push('<span style="color:'+color+'">&#9632;</span> '+esc(k)+' ('+rows.length+' samples)');
    });
    document.getElementById('battest-legend').innerHTML = legend.join(' &nbsp; ');
  }).catch(function(){});
}

async function startBatTest() {
  var label = document.getElementById('battest-label').value.trim();
  if (!label) { toast('Enter a label first', 'err'); return; }
  try {
    var r = await fetch('/api/battery-test/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({label: label})
    });
    var d = await r.json();
    if (d.ok) { toast('Started: ' + label, 'ok'); document.getElementById('battest-label').value = ''; }
    else toast(d.error || 'Failed', 'err');
  } catch(e) { toast('Error starting test', 'err'); }
}

loadBatChart();
setInterval(loadBatChart, 30000);

/* ── WiFi Picker ── */
function openWifiPicker() {
  var existing = document.getElementById('wifi-modal');
  if (existing) existing.remove();
  var modal = document.createElement('div');
  modal.id = 'wifi-modal';
  modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;padding:1rem;';
  modal.innerHTML = '<div style="background:var(--card);border:1px solid var(--border);border-radius:16px;width:100%;max-width:380px;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;">'
    + '<div style="padding:1rem 1.2rem;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">'
    + '<span style="font-weight:600;color:var(--bright);">WiFi Networks</span>'
    + '<button onclick="closeWifiPicker()" style="background:none;border:none;color:var(--dim);font-size:1.3rem;cursor:pointer;">&times;</button>'
    + '</div>'
    + '<div id="wifi-list" style="overflow-y:auto;padding:0.5rem;flex:1;"><div style="text-align:center;padding:2rem;color:var(--dim);">Scanning...</div></div>'
    + '</div>';
  document.body.appendChild(modal);
  modal.addEventListener('click', function(e) { if (e.target === modal) closeWifiPicker(); });
  fetch('/api/wifi/scan').then(function(r){return r.json()}).then(function(data) {
    if (data.error) { document.getElementById('wifi-list').innerHTML = '<div style="padding:1rem;color:var(--red);">' + esc(data.error) + '</div>'; return; }
    var html = '';
    data.networks.forEach(function(n) {
      var bars = n.signal > 75 ? 4 : n.signal > 50 ? 3 : n.signal > 25 ? 2 : 1;
      var barStr = '\u2582'.repeat(bars) + '<span style="color:var(--dim)">' + '\u2582'.repeat(4-bars) + '</span>';
      var lock = n.security !== 'Open' ? ' \uD83D\uDD12' : '';
      var active = n.active ? ' style="border:1px solid var(--green);background:var(--green-glow);"' : ' style="border:1px solid var(--border);"';
      var badge = n.active ? '<span style="color:var(--green);font-size:0.75rem;margin-left:0.5rem;">Connected</span>' : '';
      html += '<div class="wifi-item" onclick="selectWifi(this,\'' + n.ssid.replace(/'/g, "\\'") + '\',\'' + n.security + '\')"' + active
        + ' data-ssid="' + n.ssid.replace(/"/g, '&quot;') + '"'
        + ' style="padding:0.7rem 0.9rem;border-radius:10px;margin-bottom:0.4rem;cursor:pointer;' + (n.active ? 'border:1px solid var(--green);background:var(--green-glow);' : 'border:1px solid var(--border);') + '">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;">'
        + '<span style="color:var(--bright);">' + esc(n.ssid) + lock + badge + '</span>'
        + '<span style="font-size:0.9rem;">' + barStr + ' <span style="color:var(--dim);font-size:0.75rem;">' + n.signal + '%</span></span>'
        + '</div></div>';
    });
    if (!html) html = '<div style="padding:1rem;color:var(--dim);">No networks found</div>';
    document.getElementById('wifi-list').innerHTML = html;
  }).catch(function(e) {
    document.getElementById('wifi-list').innerHTML = '<div style="padding:1rem;color:var(--red);">Scan failed: ' + esc(String(e)) + '</div>';
  });
}

function selectWifi(el, ssid, security) {
  if (el.querySelector('.wifi-password-form')) return;
  document.querySelectorAll('.wifi-password-form').forEach(function(f){f.remove()});
  if (security === 'Open') { connectWifi(ssid, ''); return; }
  var form = document.createElement('div');
  form.className = 'wifi-password-form';
  form.style.cssText = 'margin-top:0.5rem;display:flex;gap:0.4rem;';
  form.innerHTML = '<input type="password" placeholder="Password" autocomplete="off" style="flex:1;padding:0.5rem 0.7rem;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--bright);font-size:0.9rem;outline:none;">'
    + '<button onclick="connectWifi(\'' + ssid.replace(/'/g, "\\'") + '\', this.parentNode.querySelector(\'input\').value)" style="padding:0.5rem 1rem;background:var(--accent);color:var(--bg);border:none;border-radius:8px;font-weight:600;cursor:pointer;">Join</button>';
  el.appendChild(form);
  form.querySelector('input').focus();
}

function connectWifi(ssid, password) {
  var list = document.getElementById('wifi-list');
  list.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--dim);">Connecting to ' + esc(ssid) + '...</div>';
  fetch('/api/wifi/connect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ssid: ssid, password: password})
  }).then(function(r){return r.json()}).then(function(data) {
    if (data.ok) {
      showToast(data.message, 'ok');
      closeWifiPicker();
    } else {
      list.innerHTML = '<div style="padding:1rem;color:var(--red);">' + esc(data.error || 'Connection failed') + '</div>';
      setTimeout(openWifiPicker, 2000);
    }
  }).catch(function(e) {
    list.innerHTML = '<div style="padding:1rem;color:var(--red);">Error: ' + esc(String(e)) + '</div>';
  });
}

function closeWifiPicker() {
  var m = document.getElementById('wifi-modal');
  if (m) m.remove();
}

/* PWA service worker */
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(function(e) { console.warn('SW:', e); });
}

/* ---- Terminal (xterm.js + SocketIO) — persists across show/hide ---- */
var _term = null, _termSocket = null, _termFit = null, _termReady = false;
var _termPendingCmd = null;

function termOpen(cmd) {
  _termPendingCmd = cmd || null;
  var overlay = document.getElementById('term-overlay');
  if (!overlay) return;

  /* already initialized — just show and refit */
  if (_termReady && _term) {
    overlay.classList.add('open');
    setTimeout(function() { _termFit.fit(); _term.focus(); }, 50);
    if (_termPendingCmd) { _termSendCmd(_termPendingCmd); _termPendingCmd = null; }
    return;
  }

  /* lazy-load xterm.js + socket.io */
  if (!window.Terminal) {
    overlay.classList.add('open');
    var s1 = document.createElement('script');
    s1.src = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.min.js';
    s1.onload = function() {
      var s2 = document.createElement('script');
      s2.src = 'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.min.js';
      s2.onload = function() {
        var s3 = document.createElement('script');
        s3.src = 'https://cdn.jsdelivr.net/npm/socket.io-client@4.8.1/dist/socket.io.min.js';
        s3.onload = function() { _termInit(); };
        document.head.appendChild(s3);
      };
      document.head.appendChild(s2);
    };
    document.head.appendChild(s1);
    return;
  }

  overlay.classList.add('open');
  _termInit();
}

function _termInit() {
  _term = new Terminal({
    cursorBlink: true, fontSize: 14,
    fontFamily: '"SF Mono","Menlo","Monaco","Courier New",monospace',
    theme: {
      background: '#000000', foreground: '#f5f5f7', cursor: '#0a84ff',
      selectionBackground: 'rgba(10,132,255,0.3)',
      black: '#000000', red: '#ff453a', green: '#30d158', yellow: '#ffd60a',
      blue: '#0a84ff', magenta: '#bf5af2', cyan: '#64d2ff', white: '#f5f5f7'
    },
    allowProposedApi: true
  });
  _termFit = new FitAddon.FitAddon();
  _term.loadAddon(_termFit);
  _term.open(document.getElementById('terminal-container'));
  setTimeout(function() { _termFit.fit(); }, 100);

  _termSocket = io({ transports: ['websocket'] });
  _termSocket.on('connect', function() {
    _termSocket.emit('pty-spawn', { rows: _term.rows, cols: _term.cols });
    _termReady = true;
    if (_termPendingCmd) {
      setTimeout(function() { _termSendCmd(_termPendingCmd); _termPendingCmd = null; }, 300);
    }
  });
  _termSocket.on('pty-output', function(d) { _term.write(d.output); });
  _termSocket.on('pty-exit', function() {
    _term.write('\r\n\x1b[90m[session ended — reopen to start a new one]\x1b[0m\r\n');
    _termReady = false;
  });
  _term.onData(function(d) { if (_termSocket) _termSocket.emit('pty-input', { input: d }); });
  _term.onResize(function(s) { if (_termSocket) _termSocket.emit('pty-resize', s); });

  var _fitTimer = null;
  window.addEventListener('resize', function() {
    clearTimeout(_fitTimer);
    _fitTimer = setTimeout(function() { if (_termFit) _termFit.fit(); }, 100);
  });
  window.addEventListener('orientationchange', function() {
    setTimeout(function() { if (_termFit) _termFit.fit(); }, 200);
  });

  _term.focus();
}

function _termSendCmd(cmd) {
  if (!_termSocket || !_termReady) return;
  var cmds = {
    'console': 'console\n',
    'htop': 'htop\n'
  };
  _termSocket.emit('pty-input', { input: cmds[cmd] || cmd + '\n' });
}

function termHide() {
  var overlay = document.getElementById('term-overlay');
  if (overlay) overlay.classList.remove('open');
}

function termDestroy() {
  termHide();
  if (_termSocket) { _termSocket.disconnect(); _termSocket = null; }
  if (_term) { _term.dispose(); _term = null; _termFit = null; }
  _termReady = false;
  var c = document.getElementById('terminal-container');
  if (c) c.innerHTML = '';
  toast('Terminal session killed', 'ok');
}

/* ASCII logo rotation */
(function() {
  var el = document.querySelector('.ascii-title');
  if (!el) return;
  el.style.cursor = 'pointer';
  el.title = 'Click to cycle logo';
  el.addEventListener('click', async function() {
    try {
      var r = await fetch('/api/logo');
      var d = await r.json();
      el.textContent = d.art;
    } catch(e) {}
  });
})();
