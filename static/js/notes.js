// Notes page: delete + lazy paging. The server renders the first page; an
// IntersectionObserver on the sentinel pulls the next one as it scrolls in.
(function () {
  var list = document.getElementById('notes-list');
  var sentinel = document.getElementById('notes-more');
  if (!list) return;

  window.ctxMenu.bind(list, function (target) {
    var li = target.closest('li[data-id]');
    if (!li) return null;
    return [{
      label: 'Delete', danger: true, run: async function () {
        li.hidden = true;                               // optimistic (Spec AC)
        var res = await fetch('/api/notes/' + li.dataset.id, { method: 'DELETE' });
        if (res.ok || res.status === 204) li.remove();
        else { li.hidden = false; window.toast('Could not delete that note.', { error: true }); }
      },
    }];
  });

  if (!sentinel) return;
  var size = parseInt(sentinel.dataset.pageSize, 10) || 30;
  var total = parseInt(sentinel.dataset.total, 10) || 0;
  var loaded = list.querySelectorAll('li[data-id]').length;
  var busy = false;

  function row(n) {
    var li = document.createElement('li');
    li.dataset.id = n.id;
    var text = document.createElement('span');
    text.className = 'task-title';
    text.textContent = n.text;
    var when = document.createElement('span');
    when.className = 'task-due';
    when.textContent = (n.created_at || '').slice(0, 16).replace('T', ' ');
    li.append(text, when);
    return li;
  }

  async function more() {
    if (busy || loaded >= total) return;
    busy = true;
    try {
      var res = await fetch('/api/notes?limit=' + size + '&offset=' + loaded);
      var rows = await res.json();
      rows.forEach(function (n) { list.insertBefore(row(n), sentinel); });
      loaded += rows.length;
      if (loaded >= total || !rows.length) sentinel.remove();
    } finally {
      busy = false;
    }
  }

  if (loaded >= total) { sentinel.remove(); return; }
  new IntersectionObserver(function (entries) {
    if (entries[0].isIntersecting) more();
  }, { root: list }).observe(sentinel);
})();
