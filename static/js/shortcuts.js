// Global keyboard shortcuts (Spec AA). One listener, one table, no dependency.
// The table is exported so Settings renders the reference from the same source.
(function () {
  window.SHORTCUTS = [
    // The first three are bound elsewhere (palette.js, friday.js) and listed here so
    // the Settings reference stays complete.
    { keys: 'Ctrl K', label: 'Open command palette' },
    { keys: 'Ctrl B', label: 'Collapse or expand the nav rail' },
    { keys: 'Ctrl Shift F', label: 'Show or hide the assistant panel' },
    { keys: '/', label: 'Focus search' },
    { keys: 'f', label: 'Focus F.R.I.D.A.Y.' },
    { keys: 'c', label: 'New event (calendar only)' },
    { keys: 't', label: 'Toggle theme' },
    { keys: 'Esc', label: 'Stop the reply, close overlays' },
    { keys: 'g d', label: 'Go to Dashboard' },
    { keys: 'g c', label: 'Go to Calendar' },
    { keys: 'g t', label: 'Go to Tasks' },
    { keys: 'g n', label: 'Go to Notes' },
    { keys: 'g a', label: 'Go to Assistant' },
    { keys: 'g m', label: 'Go to Music' },
    { keys: 'g r', label: 'Go to Grades' },
    { keys: 'g p', label: 'Go to SAT Prep' },
    { keys: 'g s', label: 'Go to Settings' },
  ];

  var GO = {
    d: '/', c: '/calendar', t: '/todos', n: '/notes',
    a: '/friday', m: '/music', r: '/grades', p: '/sat', s: '/settings',
  };

  function click(id) {
    var el = document.getElementById(id);
    if (el) el.click();
  }
  function focus(id) {
    var el = document.getElementById(id);
    if (el) el.focus();
  }

  var SINGLE = {
    '/': function () { focus('search-input'); },
    f: function () { focus('friday-text'); },
    t: function () { click('theme-toggle'); },
    // Page-local: window.CAL only exists on the calendar page, so this no-ops elsewhere.
    c: function () {
      if (window.CAL) window.CAL.openModal(null, new Date().toISOString().slice(0, 10) + 'T09:00');
    },
  };

  // The guard that matters: a shortcut firing mid-sentence types into a form.
  function typing(e) {
    var t = e.target;
    return !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
  }

  var chord = null, chordTimer = null;

  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;   // palette.js owns Ctrl/Cmd+K
    if (typing(e)) return;

    if (chord === 'g') {
      clearTimeout(chordTimer);
      chord = null;
      var dest = GO[e.key];
      if (dest) { e.preventDefault(); location.href = dest; }
      return;
    }
    if (e.key === 'g') {
      chord = 'g';
      // Without the timeout a stale `g` swallows the next keystroke.
      chordTimer = setTimeout(function () { chord = null; }, 1200);
      return;
    }

    var run = SINGLE[e.key];
    if (run) { e.preventDefault(); run(); }
  });

  // Settings renders the reference from the table above (Spec AH).
  var host = document.getElementById('shortcut-list');
  if (host) {
    window.SHORTCUTS.forEach(function (s) {
      var row = document.createElement('div');
      row.className = 'shortcut-row';
      var keys = document.createElement('span');
      keys.className = 'shortcut-keys';
      s.keys.split(' ').forEach(function (k) {
        var kbd = document.createElement('kbd');
        kbd.textContent = k;
        keys.appendChild(kbd);
      });
      var label = document.createElement('span');
      label.textContent = s.label;
      row.appendChild(keys);
      row.appendChild(label);
      host.appendChild(row);
    });
  }
})();
