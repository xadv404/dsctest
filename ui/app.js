// ── TAB NAVIGATION ───────────────────────────────────────────────
var TAB_ORDER     = ['scan', 'history', 'settings'];
var _currentTab   = 'scan';
var _tabSwitching = false;

function showTab(name, btn) {
  if (name === _currentTab || _tabSwitching) return;
  _tabSwitching = true;

  var oldIdx     = TAB_ORDER.indexOf(_currentTab);
  var newIdx     = TAB_ORDER.indexOf(name);
  var goRight    = newIdx > oldIdx;
  var oldPanel   = document.getElementById('tab-' + _currentTab);
  var newPanel   = document.getElementById('tab-' + name);

  document.querySelectorAll('nav button').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');

  oldPanel.classList.add('panel-exiting', goRight ? 'slide-out-left' : 'slide-out-right');
  newPanel.classList.add('active', goRight ? 'slide-in-right' : 'slide-in-left');

  setTimeout(function() {
    oldPanel.classList.remove('active', 'panel-exiting', 'slide-out-left', 'slide-out-right');
    newPanel.classList.remove('slide-in-right', 'slide-in-left');
    _currentTab   = name;
    _tabSwitching = false;
    if (name === 'history')  loadHistory();
    if (name === 'settings') loadSettings();
  }, 220);
}

// ── EVENT BUS FROM PYTHON ─────────────────────────────────────────
function onPythonEvent(msg) {
  const { event, data } = msg;
  switch (event) {
    case 'log':            addLog(data.text, data.type);  break;
    case 'progress':       updateProgress(data);          break;
    case 'username_found': flashFound(data.username);     break;
    case 'proxy_status':   updateProxyBadge(data.alive);  break;
    case 'scan_ended':     onScanEnded();                 break;
  }
}

// ── LOG CONSOLE ───────────────────────────────────────────────────
function addLog(text, type) {
  const verbose = document.getElementById('chk-verbose').checked;
  if (type === 'taken' && !verbose) return;

  const con  = document.getElementById('console');
  const line = document.createElement('div');
  line.className    = 'log-line';
  line.dataset.type = type || 'info';
  line.textContent  = text;
  con.appendChild(line);

  while (con.children.length > 1000) con.removeChild(con.firstChild);
  con.scrollTop = con.scrollHeight;
}

function flashFound(username) {
  addLog('✅ TROUVÉ : ' + username, 'success');
}

function clearConsole() {
  document.getElementById('console').innerHTML = '';
}

// ── STATS ─────────────────────────────────────────────────────────
function updateProgress(d) {
  document.getElementById('s-checked').textContent       = Number(d.checked).toLocaleString('fr-FR');
  document.getElementById('s-total').textContent         = Number(d.total).toLocaleString('fr-FR');
  document.getElementById('s-found').textContent         = d.found;
  document.getElementById('s-speed').textContent         = d.speed === '—' ? '—' : d.speed + '/s';
  document.getElementById('s-eta').textContent           = d.eta;
  document.getElementById('s-pct').textContent           = d.pct + '%';
  document.getElementById('progress-fill').style.width   = d.pct + '%';
}

function updateProxyBadge(count) {
  document.getElementById('proxy-count').textContent = count;
}

// ── SCAN CONTROLS ─────────────────────────────────────────────────
async function startScan() {
  const mode = document.getElementById('mode-select').value;
  clearConsole();
  setScanState(true);
  addLog('Démarrage du scan mode "' + mode + '"…', 'info');
  const result = await window.pywebview.api.start_scan(mode);
  if (!result.ok) {
    addLog('[ERREUR] ' + result.error, 'error');
    setScanState(false);
  }
}

async function stopScan() {
  await window.pywebview.api.stop_scan();
  addLog('Arrêt demandé…', 'info');
}

async function resetProgress() {
  const mode = document.getElementById('mode-select').value;
  if (!confirm('Réinitialiser la progression du mode "' + mode + '" ?')) return;
  const result = await window.pywebview.api.reset_progress(mode);
  if (result.ok) addLog('Progression du mode ' + mode + ' réinitialisée.', 'info');
  else           addLog('[ERREUR] ' + result.error, 'error');
  onModeChange();
}

function onScanEnded() {
  setScanState(false);
}

function setScanState(scanning) {
  document.getElementById('btn-start').disabled   = scanning;
  document.getElementById('btn-stop').disabled    = !scanning;
  document.getElementById('btn-reset').disabled   = scanning;
  document.getElementById('mode-select').disabled = scanning;
}

async function onModeChange() {
  const mode  = document.getElementById('mode-select').value;
  const prog  = await window.pywebview.api.get_saved_progress(mode);
  const idx   = prog.last_index || 0;
  const found = prog.total_found || 0;
  if (idx > 0) {
    addLog(
      'Mode ' + mode + ' — reprise possible à l\'index ' +
      idx.toLocaleString('fr-FR') + ' (' + found + ' trouvés)',
      'info'
    );
  }
}

// ── HISTORY ───────────────────────────────────────────────────────
async function loadHistory() {
  const items = await window.pywebview.api.get_history();
  const cont  = document.getElementById('history-content');
  const badge = document.getElementById('history-count');

  badge.textContent = items.length
    ? items.length + ' résultat' + (items.length > 1 ? 's' : '')
    : '';

  if (items.length === 0) {
    cont.innerHTML = '<div class="empty-state">Aucun username trouvé pour l\'instant.</div>';
    return;
  }

  const rows = items.map(function(it) {
    return (
      '<tr>' +
        '<td class="username-cell">' + escHtml(it.username) + '</td>' +
        '<td><span class="mode-tag">'  + escHtml(it.mode)     + '</span></td>' +
        '<td class="date-cell">'       + escHtml(it.date)     + '</td>' +
        '<td>' +
          '<button class="copy-btn" onclick="copyUsername(this, \'' + escAttr(it.username) + '\')">' +
            'Copier' +
          '</button>' +
        '</td>' +
      '</tr>'
    );
  }).join('');

  cont.innerHTML =
    '<table>' +
      '<thead><tr>' +
        '<th>Username</th><th>Mode</th><th>Date</th><th></th>' +
      '</tr></thead>' +
      '<tbody>' + rows + '</tbody>' +
    '</table>';
}

async function clearHistory() {
  if (!confirm('Effacer tout l\'historique des usernames trouvés ?')) return;
  const result = await window.pywebview.api.clear_history();
  if (result.ok) loadHistory();
  else alert('Erreur : ' + result.error);
}

function copyUsername(btn, username) {
  navigator.clipboard.writeText(username).then(function() {
    btn.textContent = 'Copié !';
    btn.classList.add('copied');
    setTimeout(function() {
      btn.textContent = 'Copier';
      btn.classList.remove('copied');
    }, 1500);
  });
}

// ── SETTINGS ──────────────────────────────────────────────────────
var WH_KEYS = ['checker', '2', '3', '4a', '4b', '4c', '4d', '4e', '4f', '4g', '5a', '5b'];

async function loadSettings() {
  const cfg   = await window.pywebview.api.get_settings();
  const count = await window.pywebview.api.get_proxy_count();

  WH_KEYS.forEach(function(k) {
    const el = document.getElementById('wh-' + k);
    if (el && cfg[k] && !cfg[k].startsWith('REMPLACE')) el.value = cfg[k];
  });

  const proxyBox = document.getElementById('proxy-info-box');
  if (count === 0) {
    proxyBox.innerHTML =
      'Aucun proxy trouvé dans <code>proxies.txt</code>.<br>' +
      'Format accepté : <code>ip:port</code> ou <code>ip:port:user:pass</code>';
  } else {
    proxyBox.textContent = count + ' proxies chargés depuis proxies.txt.';
  }
}

async function saveSettings() {
  const settings = {};
  WH_KEYS.forEach(function(k) {
    const el = document.getElementById('wh-' + k);
    if (el && el.value.trim()) settings[k] = el.value.trim();
  });
  const result = await window.pywebview.api.save_settings(settings);
  const status = document.getElementById('save-status');
  if (result.ok) {
    status.textContent = '✓ Sauvegardé';
    status.style.color = '';
    status.classList.add('visible');
    setTimeout(function() { status.classList.remove('visible'); }, 2000);
  } else {
    status.textContent = '✗ Erreur';
    status.style.color = 'var(--red)';
    status.classList.add('visible');
  }
}

// ── FILE UPLOAD ───────────────────────────────────────────────────
function handleUpload(type, input) {
  var file = input.files[0];
  if (!file) return;
  var statusEl = document.getElementById('upload-status-' + type);
  statusEl.textContent = 'Envoi…';
  statusEl.className = 'upload-status';

  var reader = new FileReader();
  reader.onload = async function(e) {
    var result = await window.pywebview.api.upload_file(type, e.target.result);
    if (result.ok) {
      statusEl.textContent = '✓ ' + result.lines + ' lignes';
      statusEl.className = 'upload-status ok';
      if (type === 'proxies') loadSettings();
    } else {
      statusEl.textContent = '✗ Erreur';
      statusEl.className = 'upload-status err';
    }
    input.value = '';
    setTimeout(function() { statusEl.textContent = ''; statusEl.className = 'upload-status'; }, 3000);
  };
  reader.readAsText(file);
}

// ── UTILS ─────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(str) {
  return String(str).replace(/'/g, "\\'");
}

// ── INIT ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  var splash = document.getElementById('splash');
  setTimeout(function() {
    splash.classList.add('slide-out');
    setTimeout(function() { splash.remove(); }, 550);
  }, 2000);
});

window.addEventListener('pywebviewready', async function() {
  const count = await window.pywebview.api.get_proxy_count();
  updateProxyBadge(count);
  onModeChange();
});
