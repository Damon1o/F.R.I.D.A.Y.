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

  // New chat starts a fresh thread — the previous conversation stays readable
  // from the history drawer instead of being deleted.
  if (newBtn) newBtn.addEventListener('click', async function () {
    await fetch('/api/friday/thread', { method: 'POST' });
    list.innerHTML = '';
    oldestId = null;
    input.focus();
  });

  // ---- Past conversations: AnimatedList (React Bits) ported to vanilla ----
  // IntersectionObserver drives the scale/fade, the gradients track scroll
  // position, arrows + Enter navigate. Same behaviour, no React, no motion dep.
  function animatedList(container, items, onSelect) {
    var view = container.querySelector('.scroll-list');
    var top = container.querySelector('.top-gradient');
    var bottom = container.querySelector('.bottom-gradient');
    var selected = -1;

    if (container._cleanup) container._cleanup();
    view.innerHTML = '';

    if (!items.length) {
      var empty = document.createElement('p');
      empty.className = 'empty label-mono';
      empty.textContent = 'No earlier conversations';
      view.appendChild(empty);
      return;
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { e.target.classList.toggle('is-in', e.isIntersecting); });
    }, { root: view, threshold: 0.5 });

    function select(i, scroll) {
      selected = i;
      view.querySelectorAll('.item').forEach(function (el, n) {
        el.classList.toggle('selected', n === i);
      });
      var el = view.querySelector('[data-index="' + i + '"]');
      if (!el || !scroll) return;
      var margin = 50;
      var itemTop = el.offsetTop, itemBottom = itemTop + el.offsetHeight;
      if (itemTop < view.scrollTop + margin) {
        view.scrollTo({ top: itemTop - margin, behavior: 'smooth' });
      } else if (itemBottom > view.scrollTop + view.clientHeight - margin) {
        view.scrollTo({ top: itemBottom - view.clientHeight + margin, behavior: 'smooth' });
      }
    }

    items.forEach(function (item, i) {
      var el = document.createElement('div');
      el.className = 'item' + (item.current ? ' is-current' : '');
      el.dataset.index = i;
      el.style.transitionDelay = Math.min(i, 8) * 30 + 'ms';
      var text = document.createElement('p');
      text.className = 'item-text';
      text.textContent = item.title;
      var meta = document.createElement('span');
      meta.className = 'item-meta label-mono';
      meta.textContent = item.meta || '';
      el.appendChild(text);
      el.appendChild(meta);
      el.addEventListener('mouseenter', function () { select(i, false); });
      el.addEventListener('click', function () { select(i, false); onSelect(item, i); });
      view.appendChild(el);
      io.observe(el);
    });

    function onScroll() {
      var d = view.scrollHeight - (view.scrollTop + view.clientHeight);
      top.style.opacity = Math.min(view.scrollTop / 50, 1);
      bottom.style.opacity = view.scrollHeight <= view.clientHeight ? 0 : Math.min(d / 50, 1);
    }

    function onKey(e) {
      if (container.closest('[hidden]')) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        select(Math.min(selected + 1, items.length - 1), true);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        select(Math.max(selected - 1, 0), true);
      } else if (e.key === 'Enter' && selected >= 0) {
        e.preventDefault();
        onSelect(items[selected], selected);
      }
    }

    view.addEventListener('scroll', onScroll);
    document.addEventListener('keydown', onKey);
    container._cleanup = function () {
      io.disconnect();
      view.removeEventListener('scroll', onScroll);
      document.removeEventListener('keydown', onKey);
    };
    onScroll();
  }

  var drawer = document.getElementById('chat-history');
  var histBtn = document.getElementById('friday-history');

  if (drawer && histBtn) {
    var box = drawer.querySelector('.scroll-list-container');

    async function loadThreads() {
      var res = await fetch('/api/friday/threads');
      var data = await res.json();
      animatedList(box, data.threads.map(function (t) {
        return {
          id: t.id,
          title: t.title,
          meta: (t.created_at || '').slice(0, 10),
          current: t.id === data.current,
        };
      }), async function (item) {
        await fetch('/api/friday/thread', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: item.id }),
        });
        drawer.hidden = true;
        histBtn.setAttribute('aria-expanded', 'false');
        oldestId = null;
        loadHistory();
      });
    }

    histBtn.addEventListener('click', async function () {
      drawer.hidden = !drawer.hidden;
      histBtn.setAttribute('aria-expanded', String(!drawer.hidden));
      if (!drawer.hidden) {
        try { await loadThreads(); } catch (e) { /* offline: leave drawer empty */ }
      }
    });
  }

  loadHistory();
})();

// Nav rail: collapse + hover expand + keyboard shortcut (Ctrl/Cmd+B)
(function () {
  var rail = document.getElementById('nav-rail');
  var btn = document.getElementById('nav-toggle');
  if (!rail || !btn) return;

  var prefersCollapsed = false;
  // Below 860px the rail is an overlay drawer — start it closed whatever the
  // saved desktop preference says, or it covers the phone screen on every load.
  var isNarrow = window.matchMedia('(max-width: 860px)');

  if (isNarrow.matches) {
    prefersCollapsed = true;
    applyNavState(true); // sync, before the prefs fetch — no open-drawer flash
  }

  async function loadPrefs() {
    if (isNarrow.matches) return;
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
    if (isNarrow.matches) return; // drawer state on a phone is not a saved preference
    fetch('/api/settings/ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nav_collapsed: prefersCollapsed }),
    }).catch(console.error);
  }

  btn.addEventListener('click', toggleNav);

  // Mobile drawer: tap the scrim to close.
  document.getElementById('rail-scrim')?.addEventListener('click', function () {
    if (!prefersCollapsed) toggleNav();
  });

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
  // Same as the nav rail: on a phone the panel is a full-height sheet, so it
  // starts closed regardless of the saved desktop preference.
  var isNarrow = window.matchMedia('(max-width: 860px)');

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

  if (isNarrow.matches && visible) applyFridayVisibility(false);

  function toggleFriday() {
    var nextState = !visible;
    applyFridayVisibility(nextState);
    if (isNarrow.matches) return; // sheet state on a phone is not a saved preference
    fetch('/api/settings/ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ friday_visible: nextState }),
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