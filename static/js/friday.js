// F.R.I.D.A.Y. assistant panel + UI prefs: vanilla fetch + SSE.
(function () {
  var list = document.getElementById('friday-messages');
  var form = document.getElementById('friday-form');
  var input = document.getElementById('friday-text');
  var newBtn = document.getElementById('friday-new');
  if (!list || !form) return;

  function bubble(role, text) {
    var el = document.createElement('div');
    el.className = 'friday-msg ' + role;
    el.textContent = text || '';
    list.appendChild(el);
    list.scrollTop = list.scrollHeight;
    return el;
  }

  // History pages backwards: open on the last PAGE turns, fetch older on demand.
  var PAGE = 40;
  var oldestId = null;

  function olderButton() {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'friday-older label-mono';
    btn.textContent = 'Load earlier messages';
    btn.addEventListener('click', async function () {
      btn.disabled = true;
      try {
        var res = await fetch('/api/friday/history?limit=' + PAGE + '&before=' + oldestId);
        var rows = await res.json();
        btn.remove();
        var anchor = list.firstChild;
        rows.forEach(function (m) {
          var el = document.createElement('div');
          el.className = 'friday-msg ' + m.role;
          el.textContent = m.content || '';
          list.insertBefore(el, anchor);
        });
        if (rows.length) {
          oldestId = rows[0].id;
          if (rows.length === PAGE) list.insertBefore(olderButton(), list.firstChild);
        }
      } catch (e) {
        btn.disabled = false;
      }
    });
    return btn;
  }

  function render(messages) {
    list.innerHTML = '';
    messages.forEach(function (m) { bubble(m.role, m.content); });
    if (messages.length) {
      oldestId = messages[0].id;
      if (messages.length === PAGE) list.insertBefore(olderButton(), list.firstChild);
    }
  }

  async function loadHistory() {
    try {
      var res = await fetch('/api/friday/history?limit=' + PAGE);
      render(await res.json());
    } catch (e) { /* offline: leave panel empty */ }
  }

  function drain(buf, onFrame) {
    var parts = buf.split('\n\n');
    var rest = parts.pop();
    parts.forEach(function (block) {
      var event = 'message', data = '';
      block.split('\n').forEach(function (line) {
        if (line.indexOf('event:') === 0) event = line.slice(6).trim();
        else if (line.indexOf('data:') === 0) data = line.slice(5).trim();
      });
      if (data) onFrame(event, JSON.parse(data));
    });
    return rest;
  }

  async function send(text) {
    input.disabled = true;
    bubble('user', text);
    var pending = bubble('assistant', '');
    pending.classList.add('is-pending');
    var streamed = '';
    try {
      var res = await fetch('/api/friday/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text }),
      });
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = '';
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        buf = drain(buf, function (event, payload) {
          if (event === 'status') {
            if (!streamed) pending.textContent = payload.text;
          } else if (event === 'token') {
            streamed += payload.text;
            pending.textContent = streamed;
          } else if (event === 'error') {
            streamed = payload.text;
            pending.textContent = streamed;
            pending.classList.add('is-error');
          }
          list.scrollTop = list.scrollHeight;
        });
      }
    } catch (e) {
      pending.textContent = 'F.R.I.D.A.Y. is unreachable.';
      pending.classList.add('is-error');
    } finally {
      pending.classList.remove('is-pending');
      if (!pending.textContent) pending.remove();
      input.disabled = false;
      input.focus();
    }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || input.disabled) return;
    input.value = '';
    send(text);
  });

  // Attachments: the server extracts text, the text goes out as a normal turn.
  var fileInput = document.getElementById('friday-file');
  var attachBtn = document.getElementById('friday-attach');
  if (fileInput && attachBtn) {
    attachBtn.addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', async function () {
      var file = fileInput.files[0];
      if (!file) return;
      fileInput.value = '';
      var note = bubble('user', 'Reading ' + file.name + '…');
      note.classList.add('is-pending');
      var body = new FormData();
      body.append('file', file);
      try {
        var res = await fetch('/api/friday/upload', { method: 'POST', body: body });
        var data = await res.json();
        note.remove();
        if (!res.ok) return bubble('assistant', data.error || 'Upload failed').classList.add('is-error');
        var question = input.value.trim() || 'Summarise this file.';
        input.value = '';
        send(question + '\n\n--- ' + data.name + ' ---\n' + data.text);
      } catch (e) {
        note.remove();
        bubble('assistant', 'Upload failed.').classList.add('is-error');
      }
    });
  }

  if (newBtn) newBtn.addEventListener('click', async function () {
    await fetch('/api/friday/clear', { method: 'POST' });
    list.innerHTML = '';
    input.focus();
  });

  loadHistory();
})();

// Nav rail: collapse + hover expand + keyboard shortcut (Ctrl/Cmd+B)
(function () {
  var rail = document.getElementById('nav-rail');
  var btn = document.getElementById('nav-toggle');
  if (!rail || !btn) return;

  var prefersCollapsed = false;

  async function loadPrefs() {
    try {
      var res = await fetch('/api/settings/ui');
      var data = await res.json();
      prefersCollapsed = data.nav_collapsed === 'true';
      applyNavState(prefersCollapsed);
    } catch (e) {
      // fallback to localStorage for backward compat
      prefersCollapsed = localStorage.getItem('navCollapsed') === 'true';
      applyNavState(prefersCollapsed);
    }
  }

  function applyNavState(collapsed) {
    rail.classList.toggle('is-collapsed', collapsed);
    document.querySelector('.app-shell')?.classList.toggle('rail-collapsed', collapsed);
    btn.setAttribute('aria-expanded', String(!collapsed));
    localStorage.setItem('navCollapsed', String(collapsed));
  }

  function toggleNav() {
    prefersCollapsed = !prefersCollapsed;
    applyNavState(prefersCollapsed);
    fetch('/api/settings/ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nav_collapsed: prefersCollapsed }),
    }).catch(console.error);
  }

  btn.addEventListener('click', toggleNav);

  // Keyboard shortcut: Ctrl/Cmd + B
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      toggleNav();
    }
  });

  // Listen for settings page changes
  window.addEventListener('nav-pref-changed', function (e) {
    if (e.detail && typeof e.detail.collapsed === 'boolean') {
      prefersCollapsed = e.detail.collapsed;
      applyNavState(prefersCollapsed);
    }
  });

  loadPrefs();
})();

// Nav rail hover-to-peek when collapsed. Drives the expand via explicit classes so it
// never depends on :hover/:has() firing. Bind to #nav-rail (always present) — the
// is-collapsed class is applied async after prefs load, so querying .rail.is-collapsed
// here would return null and the listeners would never attach.
(function () {
  var rail = document.getElementById('nav-rail');
  var shell = document.querySelector('.app-shell');
  if (!rail || !shell) return;
  rail.addEventListener('mouseenter', function () {
    if (!rail.classList.contains('is-collapsed')) return;
    rail.classList.add('is-hovering');
    shell.classList.add('rail-hovered');
  });
  rail.addEventListener('mouseleave', function () {
    rail.classList.remove('is-hovering');
    shell.classList.remove('rail-hovered');
  });
})();

// F.R.I.D.A.Y. panel: visibility toggle + slide animation + keyboard shortcut (Ctrl/Cmd+Shift+F)
(function () {
  var panel = document.querySelector('.friday');
  var toggleBtn = document.getElementById('friday-toggle'); // button in topbar
  if (!panel) return;

  // Read initial state from server-rendered DOM — no fetch, no flash.
  var visible = !panel.classList.contains('is-hidden');

  function applyFridayVisibility(show) {
    visible = show;
    panel.classList.toggle('is-hidden', !visible);
    document.querySelector('.app-shell')?.classList.toggle('friday-hidden', !visible);
    if (toggleBtn) {
      toggleBtn.setAttribute('aria-expanded', String(visible));
      toggleBtn.setAttribute('aria-label', visible ? 'Hide F.R.I.D.A.Y. panel' : 'Show F.R.I.D.A.Y. panel');
    }
    localStorage.setItem('fridayVisible', String(visible));
  }

  function toggleFriday() {
    applyFridayVisibility(!visible);
    fetch('/api/settings/ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ friday_visible: !visible }),
    }).catch(console.error);
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', toggleFriday);
  }

  // Keyboard shortcut: Ctrl/Cmd + Shift + F
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
      e.preventDefault();
      toggleFriday();
    }
  });

  // Listen for settings page changes
  window.addEventListener('friday-pref-changed', function (e) {
    if (e.detail && typeof e.detail.visible === 'boolean') {
      applyFridayVisibility(e.detail.visible);
    }
  });
})();