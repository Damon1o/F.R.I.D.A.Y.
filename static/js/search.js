// Top-nav search. There is no results page: /api/search answers straight into a
// dropdown under the field. ponytail: one debounce, one fetch, innerHTML.
(function () {
  var input = document.getElementById('search-input');
  var pop = document.getElementById('search-results');
  var form = document.getElementById('search-form');
  if (!input || !pop) return;

  var GROUPS = [
    { key: 'events', label: 'Events', href: '/calendar', field: 'title' },
    { key: 'todos', label: 'Tasks', href: '/todos', field: 'title' },
    { key: 'notes', label: 'Notes', href: '/notes', field: 'text' },
  ];
  var timer = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function close() {
    pop.hidden = true;
    input.setAttribute('aria-expanded', 'false');
  }

  function render(data) {
    var html = GROUPS.map(function (g) {
      var items = (data[g.key] || []).slice(0, 5);
      if (!items.length) return '';
      return '<div class="search-group">' +
        '<a class="label-mono search-group-head" href="' + g.href + '">' + g.label + ' · ' + items.length + '</a>' +
        items.map(function (it) {
          return '<a class="search-hit" href="' + g.href + '">' + esc(it[g.field] || it.title || it.text) + '</a>';
        }).join('') +
        '</div>';
    }).join('');

    pop.innerHTML = html || '<p class="search-empty">No matches.</p>';
    pop.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  }

  function run() {
    var q = input.value.trim();
    if (q.length < 2) return close();
    fetch('/api/search?q=' + encodeURIComponent(q))
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(close);
  }

  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(run, 200);
  });

  form.addEventListener('submit', function (e) { e.preventDefault(); run(); });
  input.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
  document.addEventListener('click', function (e) {
    if (!pop.contains(e.target) && e.target !== input) close();
  });
})();
