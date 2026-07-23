// Calendar: month grid + event CRUD against /api/events.
(function () {
  var grid = document.getElementById('cal-grid');
  var label = document.getElementById('cal-label');
  var modal = document.getElementById('event-modal');
  var form = document.getElementById('event-form');
  var delBtn = document.getElementById('event-delete');
  var view = new Date();
  view.setDate(1);

  var pad = function (n) { return String(n).padStart(2, '0'); };
  var ymd = function (d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };

  async function load() {
    var year = view.getFullYear(), month = view.getMonth();
    label.textContent = view.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });

    var first = new Date(year, month, 1);
    var start = new Date(first);
    start.setDate(1 - first.getDay());               // back to Sunday
    var from = ymd(start) + 'T00:00';
    var end = new Date(start);
    end.setDate(start.getDate() + 41);
    var to = ymd(end) + 'T23:59';

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
        ev.dataset.event = JSON.stringify(e);
        cell.appendChild(ev);
      });
      grid.appendChild(cell);
    }
  }

  function openModal(ev, dateKey) {
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
    } else if (dateKey) {
      form.start_at.value = dateKey + 'T09:00';
    }
    modal.hidden = false;
  }
  function closeModal() { modal.hidden = true; }

  grid.addEventListener('click', function (e) {
    var evEl = e.target.closest('.cal-event');
    if (evEl) { openModal(JSON.parse(evEl.dataset.event)); return; }
    var cell = e.target.closest('.cal-day');
    if (cell) openModal(null, cell.dataset.date);
  });

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    var data = Object.fromEntries(new FormData(form).entries());
    var id = data.id; delete data.id;
    if (!data.end_at) delete data.end_at;
    var res = await fetch(id ? '/api/events/' + id : '/api/events', {
      method: id ? 'PATCH' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) { alert((await res.json().catch(function () { return {}; })).error || 'Save failed'); return; }
    closeModal(); load();
  });

  delBtn.addEventListener('click', async function () {
    var id = form.id.value;
    if (!id) return;
    await fetch('/api/events/' + id, { method: 'DELETE' });
    closeModal(); load();
  });

  document.getElementById('modal-close').addEventListener('click', closeModal);
  modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
  document.getElementById('cal-prev').addEventListener('click', function () { view.setMonth(view.getMonth() - 1); load(); });
  document.getElementById('cal-next').addEventListener('click', function () { view.setMonth(view.getMonth() + 1); load(); });
  document.getElementById('cal-today').addEventListener('click', function () { view = new Date(); view.setDate(1); load(); });

  load();
})();
