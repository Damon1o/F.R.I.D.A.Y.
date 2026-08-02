// Calendar: month grid, week routing (#week=YYYY-MM-DD), event CRUD against /api/events.
(function () {
  var grid = document.getElementById('cal-grid');
  var label = document.getElementById('cal-label');
  var monthCard = document.getElementById('cal-month');
  var weekCard = document.getElementById('cal-week');
  var backBtn = document.getElementById('cal-back');
  var modal = document.getElementById('event-modal');
  var form = document.getElementById('event-form');
  var delBtn = document.getElementById('event-delete');
  var view = new Date();
  view.setDate(1);

  var pad = function (n) { return String(n).padStart(2, '0'); };
  var ymd = function (d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };
  var parseKey = function (key) { var p = key.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); };

  function weekKey() {
    var m = /^#week=(\d{4}-\d{2}-\d{2})$/.exec(location.hash);
    return m ? m[1] : null;
  }

  async function load() {
    var year = view.getFullYear(), month = view.getMonth();
    label.textContent = view.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });

    var first = new Date(year, month, 1);
    var start = new Date(first);
    start.setDate(1 - first.getDay());               // back to Sunday
    var from = ymd(start) + 'T00:00';
    var end = new Date(start);
    end.setDate(start.getDate() + 41);
    // Bounds are compared as text, so the upper bound must sort above stored seconds.
    var to = ymd(end) + 'T23:59:59.999999';

    var events = await fetch('/api/events?from=' + from + '&to=' + to).then(function (r) { return r.json(); });
    var byDay = {};
    events.forEach(function (e) { (byDay[e.start_at.slice(0, 10)] = byDay[e.start_at.slice(0, 10)] || []).push(e); });

    var today = ymd(new Date());
    grid.innerHTML = '';
    for (var i = 0; i < 42; i++) {
      var d = new Date(start);
      d.setDate(start.getDate() + i);
      var key = ymd(d);
      var cell = document.createElement('div');
      cell.className = 'cal-day' + (d.getMonth() !== month ? ' is-other' : '') + (key === today ? ' is-today' : '');
      cell.dataset.date = key;
      var num = document.createElement('span');
      num.className = 'cal-date';
      num.textContent = d.getDate();
      cell.appendChild(num);
      (byDay[key] || []).forEach(function (e) {
        var ev = document.createElement('div');
        ev.className = 'cal-event';
        ev.textContent = (e.all_day ? '' : e.start_at.slice(11, 16) + ' ') + e.title;
        ev.dataset.id = e.id;                    // optimistic delete finds the chip by this
        ev.dataset.event = JSON.stringify(e);
        cell.appendChild(ev);
      });
      grid.appendChild(cell);
    }
  }

  function openModal(ev, dateKey, allDay) {
    form.reset();
    var editing = !!ev;
    document.getElementById('modal-title').textContent = editing ? 'Edit event' : 'New event';
    delBtn.hidden = !editing;
    form.id.value = editing ? ev.id : '';
    if (editing) {
      form.title.value = ev.title;
      form.start_at.value = ev.start_at.slice(0, 16);
      form.end_at.value = ev.end_at ? ev.end_at.slice(0, 16) : '';
      form.location.value = ev.location || '';
      form.notes.value = ev.notes || '';
      form.all_day.checked = !!ev.all_day;
    } else if (dateKey) {
      form.start_at.value = dateKey.length > 10 ? dateKey : dateKey + 'T09:00';
      form.all_day.checked = !!allDay;
    }
    modal.hidden = false;
    form.title.focus();
  }
  function closeModal() { modal.hidden = true; }

  // ---- view routing -------------------------------------------------------
  function render() {
    var key = weekKey();
    if (key) {
      monthCard.hidden = true;
      weekCard.hidden = false;
      backBtn.hidden = false;
      window.CalWeek.render(key);
    } else {
      window.CalWeek.destroy();
      weekCard.hidden = true;
      monthCard.hidden = false;
      backBtn.hidden = true;
      load();
    }
  }

  // Optimistic write (Spec AC): show the intended state, then reconcile.
  // `render()` on success is deliberate and must not be dropped — it is one cheap
  // GET and it keeps the client from drifting from the server. Optimism buys the
  // perception; the reload keeps the truth.
  async function commit(apply, revert, request) {
    apply();
    try {
      var res = await request();
      if (!res.ok && res.status !== 204) throw new Error(res.status);
    } catch (e) {
      revert();
      window.toast('Could not save — reverted.', { error: true });
      return false;
    }
    render();
    return true;
  }

  // calendar-week.js talks back through this.
  window.CAL = {
    openModal: openModal,
    reload: render,
    commit: commit,
    setLabel: function (text) { label.textContent = text; },
  };

  grid.addEventListener('click', function (e) {
    var evEl = e.target.closest('.cal-event');
    if (evEl) { openModal(JSON.parse(evEl.dataset.event)); return; }
    var cell = e.target.closest('.cal-day');
    if (cell) location.hash = 'week=' + cell.dataset.date;
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var data = Object.fromEntries(new FormData(form).entries());
    var id = data.id; delete data.id;
    if (!data.end_at) delete data.end_at;
    data.all_day = !!data.all_day;             // checkbox is absent when unchecked

    // The modal closes and a provisional chip appears now; the trailing render()
    // inside commit() swaps it for the stored event once the write lands.
    var provisional = null;
    commit(function () {
      closeModal();
      provisional = provisionalChip(data);
    }, function () {
      if (provisional) provisional.remove();
      openModal(id ? Object.assign({ id: id }, data) : null, data.start_at, data.all_day);
    }, function () {
      return fetch(id ? '/api/events/' + id : '/api/events', {
        method: id ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    });
  });

  // A dimmed stand-in for an event the server has not confirmed yet. Month view
  // only — the week grid re-renders from calendar-week.js.
  function provisionalChip(data) {
    var cell = grid.querySelector('[data-date="' + String(data.start_at).slice(0, 10) + '"]');
    if (!cell) return null;
    var el = document.createElement('div');
    el.className = 'cal-event is-provisional';
    el.textContent = (data.all_day ? '' : String(data.start_at).slice(11, 16) + ' ') + data.title;
    cell.appendChild(el);
    return el;
  }

  delBtn.addEventListener('click', function () {
    var id = form.id.value;
    if (!id) return;
    var chip = grid.querySelector('.cal-event[data-id="' + id + '"]');
    commit(function () {
      closeModal();
      if (chip) chip.hidden = true;
    }, function () {
      if (chip) chip.hidden = false;
    }, function () {
      return fetch('/api/events/' + id, { method: 'DELETE' });
    });
  });

  document.getElementById('modal-close').addEventListener('click', closeModal);
  modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
  backBtn.addEventListener('click', function () { location.hash = ''; });

  function step(dir) {
    var key = weekKey();
    if (key) {
      var d = parseKey(key);
      d.setDate(d.getDate() + dir * 7);
      location.hash = 'week=' + ymd(d);
    } else {
      view.setMonth(view.getMonth() + dir);
      load();
    }
  }
  document.getElementById('cal-prev').addEventListener('click', function () { step(-1); });
  document.getElementById('cal-next').addEventListener('click', function () { step(1); });
  document.getElementById('cal-today').addEventListener('click', function () {
    if (weekKey()) { location.hash = 'week=' + ymd(new Date()); return; }
    view = new Date(); view.setDate(1); load();
  });

  window.addEventListener('hashchange', render);
  render();
})();
