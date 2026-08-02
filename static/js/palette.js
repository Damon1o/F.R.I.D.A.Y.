// Command palette (Spec Z): Ctrl/Cmd+K. Nav destinations plus live /api/search hits.
// Substring match, not fuzzy — no scoring library for a ten-item command list.
(function () {
  var root = document.getElementById('palette');
  var input = document.getElementById('palette-input');
  var listEl = document.getElementById('palette-list');
  if (!root || !input || !listEl) return;

  var COMMANDS = [
    { label: 'Dashboard', icon: 'layout-dashboard', url: '/' },
    { label: 'Calendar', icon: 'calendar', url: '/calendar' },
    { label: 'Tasks', icon: 'circle-check-big', url: '/todos' },
    { label: 'Notes', icon: 'file-text', url: '/notes' },
    { label: 'Assistant', icon: 'message-square', url: '/friday' },
    { label: 'Music', icon: 'music', url: '/music' },
    { label: 'Grades', icon: 'graduation-cap', url: '/grades' },
    { label: 'SAT Prep', icon: 'book-open-check', url: '/sat' },
    { label: 'Settings', icon: 'settings', url: '/settings' },
    { label: 'New event', icon: 'plus', url: '/calendar' },
    {
      label: 'Toggle theme', icon: 'sun', run: function () {
        var t = document.getElementById('theme-toggle');
        if (t) t.click();
      },
    },
  ];

  // /api/search groups its answer; the palette flattens it into rows.
  var GROUPS = [
    { key: 'events', icon: 'calendar', url: '/calendar', field: 'title' },
    { key: 'todos', icon: 'circle-check-big', url: '/todos', field: 'title' },
    { key: 'notes', icon: 'file-text', url: '/notes', field: 'text' },
  ];

  var rows = [];        // flattened, in render order — the arrow keys walk this
  var active = 0;
  var timer = null;
  var lastFocus = null;

  function icon(name) {
    var img = document.createElement('img');
    img.src = '/static/vendor/lucide/' + name + '.svg';
    img.alt = '';
    img.width = img.height = 16;
    return img;
  }

  function heading(text) {
    var h = document.createElement('p');
    h.className = 'palette-group label-mono';
    h.textContent = text;
    listEl.appendChild(h);
  }

  function addRow(item) {
    var el = document.createElement('div');
    el.className = 'palette-row';
    el.setAttribute('role', 'option');
    el.dataset.index = rows.length;
    el.appendChild(icon(item.icon));
    var label = document.createElement('span');
    label.textContent = item.label;
    el.appendChild(label);
    el.addEventListener('mousemove', function () { setActive(+el.dataset.index); });
    el.addEventListener('click', function () { run(item); });
    listEl.appendChild(el);
    rows.push(item);
  }

  function setActive(i) {
    active = Math.max(0, Math.min(i, rows.length - 1));
    listEl.querySelectorAll('.palette-row').forEach(function (el, n) {
      el.classList.toggle('is-active', n === active);
      if (n === active) el.scrollIntoView({ block: 'nearest' });
    });
  }

  function run(item) {
    close();
    if (item.run) item.run();
    else location.href = item.url;
  }

  function matches(q) {
    if (!q) return COMMANDS;
    var starts = [], has = [];
    COMMANDS.forEach(function (c) {
      var i = c.label.toLowerCase().indexOf(q);
      if (i === 0) starts.push(c);
      else if (i > 0) has.push(c);
    });
    return starts.concat(has);
  }

  function draw(q, results) {
    listEl.innerHTML = '';
    rows = [];
    var cmds = matches(q);
    if (cmds.length) {
      heading('Go to');
      cmds.forEach(addRow);
    }
    var hits = [];
    GROUPS.forEach(function (g) {
      (results && results[g.key] ? results[g.key] : []).slice(0, 5).forEach(function (it) {
        hits.push({ label: it[g.field] || it.title || it.text || '', icon: g.icon, url: g.url });
      });
    });
    if (hits.length) {
      heading('Results');
      hits.forEach(addRow);
    }
    if (!rows.length) {
      var none = document.createElement('p');
      none.className = 'palette-none';
      none.textContent = 'No matches.';
      listEl.appendChild(none);
    }
    setActive(0);
  }

  function search(q) {
    if (q.length < 2) return draw(q, null);
    draw(q, null);                                  // commands render immediately
    fetch('/api/search?q=' + encodeURIComponent(q))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (input.value.trim().toLowerCase() === q) draw(q, data);
      })
      .catch(function () { /* commands are already on screen */ });
  }

  function open() {
    lastFocus = document.activeElement;
    root.hidden = false;
    input.value = '';
    draw('', null);
    input.focus();
  }

  function close() {
    if (root.hidden) return;
    root.hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    lastFocus = null;
  }

  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      root.hidden ? open() : close();
      return;
    }
    if (root.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setActive(active + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(active - 1); }
    else if (e.key === 'Enter' && rows[active]) { e.preventDefault(); run(rows[active]); }
  });

  input.addEventListener('input', function () {
    clearTimeout(timer);
    var q = input.value.trim().toLowerCase();
    timer = setTimeout(function () { search(q); }, 150);
  });

  root.addEventListener('click', function (e) { if (e.target === root) close(); });
})();
