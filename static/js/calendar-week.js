// Week view for /calendar: 7 day columns x 24 hours, 1px per minute.
// Driven by calendar.js via window.CalWeek.render(dateKey) / .destroy().
(function () {
  var DAY_MIN = 1440;      // grid height in px, 1px == 1 minute
  var SNAP = 15;           // drag snap, minutes
  var MIN_H = 20;          // shortest tappable block

  var headEl = document.getElementById('cal-week-head');
  var alldayEl = document.getElementById('cal-allday');
  var scrollEl = document.getElementById('cal-hours');
  var innerEl = document.getElementById('cal-hours-inner');

  var weekStart = null, cols = [], nowTimer = null, draft = null;

  var pad = function (n) { return String(n).padStart(2, '0'); };
  var ymd = function (d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };
  var isoLocal = function (d) { return ymd(d) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()); };
  var parseKey = function (k) { var p = k.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); };
  // The API returns tz-naive local wall time; slicing beats Date parsing for that.
  var minsOf = function (s) { return +s.slice(11, 13) * 60 + +s.slice(14, 16); };
  var hourLabel = function (h) {
    return new Date(2000, 0, 1, h).toLocaleTimeString(undefined, { hour: 'numeric' });
  };
  var timeLabel = function (s) {
    return new Date(2000, 0, 1, +s.slice(11, 13), +s.slice(14, 16))
      .toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  };

  // ---- overlap: split a column between events whose times touch ------------
  function layout(list) {
    list.sort(function (a, b) { return a._top - b._top || a._bot - b._bot; });
    var group = [], maxBot = -1;
    var flush = function () {
      group.forEach(function (e, i) { e._left = (i / group.length) * 100; e._width = 100 / group.length; });
      group = [];
    };
    list.forEach(function (e) {
      if (group.length && e._top >= maxBot) { flush(); maxBot = -1; }
      group.push(e);
      maxBot = Math.max(maxBot, e._bot);
    });
    if (group.length) flush();
    return list;
  }

  // ---- rendering ----------------------------------------------------------
  function block(ev) {
    var el = document.createElement('div');
    el.className = 'cal-wev' + (ev.occurrence_of ? ' is-occurrence' : '');
    el.style.top = ev._top + 'px';
    el.style.height = Math.max(ev._bot - ev._top, MIN_H) + 'px';
    el.style.left = ev._left + '%';
    el.style.width = 'calc(' + ev._width + '% - 2px)';
    el.dataset.event = JSON.stringify(ev);
    var t = document.createElement('span');
    t.className = 'cal-wev-title';
    t.textContent = ev.title;
    var when = document.createElement('span');
    when.className = 'cal-wev-time';
    when.textContent = timeLabel(ev.start_at);
    el.appendChild(t);
    el.appendChild(when);
    if (!ev.occurrence_of) {
      var grip = document.createElement('span');
      grip.className = 'cal-wev-grip';
      el.appendChild(grip);
    }
    return el;
  }

  async function render(key) {
    var d = parseKey(key);
    weekStart = new Date(d);
    weekStart.setDate(d.getDate() - d.getDay());        // back to Sunday
    var weekEnd = new Date(weekStart);
    weekEnd.setDate(weekStart.getDate() + 6);

    var opts = { month: 'short', day: 'numeric' };
    var sameYear = weekStart.getFullYear() === weekEnd.getFullYear();
    window.CAL.setLabel(
      weekStart.toLocaleDateString(undefined, sameYear ? opts : Object.assign({ year: 'numeric' }, opts)) +
      ' – ' + weekEnd.toLocaleDateString(undefined, Object.assign({ year: 'numeric' }, opts))
    );

    // Bounds are compared as text, so the upper bound must sort above stored seconds.
    var events = await fetch('/api/events?from=' + ymd(weekStart) + 'T00:00&to=' + ymd(weekEnd) + 'T23:59:59.999999')
      .then(function (r) { return r.json(); });

    var today = ymd(new Date());
    var days = [];
    for (var i = 0; i < 7; i++) {
      var dd = new Date(weekStart);
      dd.setDate(weekStart.getDate() + i);
      days.push(ymd(dd));
    }

    // header
    headEl.innerHTML = '';
    headEl.appendChild(document.createElement('span'));      // gutter spacer
    days.forEach(function (k) {
      var dd = parseKey(k);
      var c = document.createElement('div');
      c.className = 'cal-wday' + (k === today ? ' is-today' : '');
      var n = document.createElement('span');
      n.className = 'cal-wday-name';
      n.textContent = dd.toLocaleDateString(undefined, { weekday: 'short' });
      var num = document.createElement('span');
      num.className = 'cal-wday-num';
      num.textContent = dd.getDate();
      c.appendChild(n);
      c.appendChild(num);
      headEl.appendChild(c);
    });

    // all-day strip
    alldayEl.innerHTML = '';
    var alldayLabel = document.createElement('span');
    alldayLabel.className = 'cal-gutter-label';
    alldayLabel.textContent = 'all day';
    alldayEl.appendChild(alldayLabel);
    var alldayCells = {};
    days.forEach(function (k) {
      var cell = document.createElement('div');
      cell.className = 'cal-allday-cell';
      cell.dataset.date = k;
      alldayCells[k] = cell;
      alldayEl.appendChild(cell);
    });

    // hour grid
    innerEl.innerHTML = '';
    var gutter = document.createElement('div');
    gutter.className = 'cal-gutter';
    for (var h = 1; h < 24; h++) {
      var lab = document.createElement('span');
      lab.style.top = (h * 60) + 'px';
      lab.textContent = hourLabel(h);
      gutter.appendChild(lab);
    }
    innerEl.appendChild(gutter);
    cols = [];
    days.forEach(function (k) {
      var col = document.createElement('div');
      col.className = 'cal-col' + (k === today ? ' is-today' : '');
      col.dataset.date = k;
      cols.push(col);
      innerEl.appendChild(col);
    });

    // place events
    var timed = {};
    events.forEach(function (e) {
      var k = e.start_at.slice(0, 10);
      if (e.all_day) {
        if (!alldayCells[k]) return;
        var chip = document.createElement('div');
        chip.className = 'cal-wev is-allday';
        chip.textContent = e.title;
        chip.dataset.event = JSON.stringify(e);
        alldayCells[k].appendChild(chip);
        return;
      }
      var top = minsOf(e.start_at);
      // no end_at: show 30 minutes. Layout only — the stored value stays null.
      var bot = e.end_at && e.end_at.slice(0, 10) === k ? minsOf(e.end_at) : top + 30;
      if (e.end_at && e.end_at.slice(0, 10) !== k) bot = DAY_MIN;
      e._top = top; e._bot = Math.max(bot, top + MIN_H);
      (timed[k] = timed[k] || []).push(e);
    });
    days.forEach(function (k, i) {
      layout(timed[k] || []).forEach(function (e) { cols[i].appendChild(block(e)); });
    });

    drawNow();
    if (nowTimer) clearInterval(nowTimer);
    nowTimer = setInterval(drawNow, 60000);

    var nowCol = days.indexOf(today);
    scrollEl.scrollTop = nowCol >= 0 ? Math.max(0, nowMinutes() - 120) : 7 * 60;
  }

  function nowMinutes() { var n = new Date(); return n.getHours() * 60 + n.getMinutes(); }

  function drawNow() {
    var old = innerEl.querySelector('.cal-now');
    if (old) old.remove();
    var today = ymd(new Date());
    var col = cols.filter(function (c) { return c.dataset.date === today; })[0];
    if (!col) return;
    var line = document.createElement('div');
    line.className = 'cal-now';
    line.style.top = nowMinutes() + 'px';
    col.appendChild(line);
  }

  function destroy() {
    if (nowTimer) { clearInterval(nowTimer); nowTimer = null; }
    hideMenu();
    clearDraft();
  }

  // ---- inline draft (left-click an empty slot) ----------------------------
  function clearDraft() { if (draft) { draft.remove(); draft = null; } }

  function startDraft(col, minutes) {
    clearDraft();
    var done = false;                    // Enter removes the input, which then fires blur

    draft = document.createElement('div');
    draft.className = 'cal-wev is-draft';
    draft.style.top = minutes + 'px';
    draft.style.height = '60px';
    draft.style.left = '0';
    draft.style.width = 'calc(100% - 2px)';
    var input = document.createElement('input');
    input.placeholder = 'New event';
    draft.appendChild(input);
    col.appendChild(draft);
    input.focus();

    var save = async function () {
      if (done) return;
      done = true;
      var title = input.value.trim();
      if (!title) { clearDraft(); return; }
      var start = parseKey(col.dataset.date);
      start.setMinutes(minutes);
      var end = new Date(start.getTime() + 3600000);
      clearDraft();
      var res = await fetch('/api/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title, start_at: isoLocal(start), end_at: isoLocal(end) }),
      });
      if (!res.ok) { window.toast('Could not save that event.', { error: true }); return; }
      window.CAL.reload();
    };
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); save(); }
      if (e.key === 'Escape') { done = true; clearDraft(); }
    });
    input.addEventListener('blur', save);
  }

  // ---- context menu (shared, see menu.js) ---------------------------------
  var hideMenu = window.ctxMenu.hide;
  var showMenu = window.ctxMenu.show;

  async function del(url, opts) {
    var res = await fetch(url, opts);
    if (!res.ok && res.status !== 204) {
      window.toast('That did not go through.', { error: true });
      return;
    }
    window.CAL.reload();
  }

  function eventMenu(x, y, ev) {
    var items = [
      { label: 'Edit', run: function () { window.CAL.openModal(ev); } },
      {
        label: 'Duplicate', run: function () {
          // ponytail: copies the occurrence, not the rrule — duplicating a series is not a thing you asked for.
          del('/api/events', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              title: ev.title, start_at: ev.start_at, end_at: ev.end_at,
              all_day: ev.all_day, location: ev.location, notes: ev.notes,
            }),
          });
        },
      },
    ];
    if (ev.occurrence_of) {
      items.push({
        label: 'Skip this occurrence', run: function () {
          del('/api/events/' + ev.occurrence_of + '/skip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ occurrence: ev.start_at }),
          });
        },
      });
      items.push({
        label: 'Delete series', danger: true, run: function () {
          if (confirm('Delete the whole repeating series?')) del('/api/events/' + ev.occurrence_of, { method: 'DELETE' });
        },
      });
    } else {
      items.push({ label: 'Delete', danger: true, run: function () { del('/api/events/' + ev.id, { method: 'DELETE' }); } });
    }
    showMenu(x, y, items);
  }

  function slotMenu(x, y, dateKey, minutes) {
    var start = parseKey(dateKey);
    start.setMinutes(minutes);
    showMenu(x, y, [
      { label: 'New event', run: function () { window.CAL.openModal(null, isoLocal(start)); } },
      { label: 'New all-day event', run: function () { window.CAL.openModal(null, dateKey + 'T00:00', true); } },
    ]);
  }

  // ---- drag to move / resize ---------------------------------------------
  var drag = null;

  function onDown(e) {
    if (e.button !== 0) return;
    var el = e.target.closest('.cal-wev');
    if (!el || el.classList.contains('is-draft') || el.classList.contains('is-allday')) return;
    var ev = JSON.parse(el.dataset.event);
    if (ev.occurrence_of) return;                  // moving one would move the series
    drag = {
      el: el, ev: ev, x: e.clientX, y: e.clientY, moved: false,
      resize: !!e.target.closest('.cal-wev-grip'),
      h: el.offsetHeight,
      colW: el.parentElement.getBoundingClientRect().width,
    };
    el.setPointerCapture(e.pointerId);
  }

  function snap(px) { return Math.round(px / SNAP) * SNAP; }

  function onMove(e) {
    if (!drag) return;
    var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
    drag.moved = true;
    drag.el.classList.add('is-dragging');
    drag.dMin = snap(dy);
    if (drag.resize) {
      drag.el.style.height = Math.max(MIN_H, drag.h + drag.dMin) + 'px';
    } else {
      drag.dDays = Math.round(dx / drag.colW);
      drag.el.style.transform = 'translate(' + (drag.dDays * drag.colW) + 'px,' + drag.dMin + 'px)';
    }
  }

  function onUp() {
    if (!drag) return;
    var d = drag; drag = null;
    d.el.classList.remove('is-dragging');
    if (!d.moved) { window.CAL.openModal(d.ev); return; }

    var body;
    if (d.resize) {
      var start = new Date(d.ev.start_at);
      var mins = Math.max(SNAP, d.h + d.dMin);
      body = { end_at: isoLocal(new Date(start.getTime() + mins * 60000)) };
    } else {
      var shift = (d.dDays * 1440 + d.dMin) * 60000;
      body = { start_at: isoLocal(new Date(new Date(d.ev.start_at).getTime() + shift)) };
      if (d.ev.end_at) body.end_at = isoLocal(new Date(new Date(d.ev.end_at).getTime() + shift));
    }

    // Spec AC: the chip already sits where it was dropped (the drag left a transform
    // on it), so "apply" is keeping it there. A rejected write drops the transform and
    // the chip snaps back to the slot the server still believes it occupies.
    window.CAL.commit(function () { }, function () {
      d.el.style.transform = '';
      d.el.style.height = d.h + 'px';
    }, function () {
      return fetch('/api/events/' + d.ev.id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    });
  }

  // ---- wiring -------------------------------------------------------------
  innerEl.addEventListener('pointerdown', onDown);
  innerEl.addEventListener('pointermove', onMove);
  innerEl.addEventListener('pointerup', onUp);
  innerEl.addEventListener('pointercancel', function () { drag = null; window.CAL.reload(); });

  innerEl.addEventListener('click', function (e) {
    if (e.target.closest('.cal-wev')) return;       // events are handled by the drag path
    var col = e.target.closest('.cal-col');
    if (col) startDraft(col, Math.floor(e.offsetY / 30) * 30);
  });

  alldayEl.addEventListener('click', function (e) {
    var chip = e.target.closest('.cal-wev');
    if (chip) { window.CAL.openModal(JSON.parse(chip.dataset.event)); return; }
    var cell = e.target.closest('.cal-allday-cell');
    if (cell) window.CAL.openModal(null, cell.dataset.date + 'T00:00', true);
  });

  // The slot menu needs where in the column the press landed, which ctxMenu.bind
  // does not carry, so the week grid keeps its own listener and calls show().
  document.getElementById('cal-week').addEventListener('contextmenu', function (e) {
    var el = e.target.closest('.cal-wev');
    if (el && !el.classList.contains('is-draft')) {
      e.preventDefault();
      eventMenu(e.clientX, e.clientY, JSON.parse(el.dataset.event));
      return;
    }
    var col = e.target.closest('.cal-col');
    if (col) {
      e.preventDefault();
      slotMenu(e.clientX, e.clientY, col.dataset.date, Math.floor(e.offsetY / 30) * 30);
    }
  });

  scrollEl.addEventListener('scroll', hideMenu);

  window.CalWeek = { render: render, destroy: destroy };
})();
