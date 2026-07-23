// Dashboard quick-add (event + todo) and inline task completion.
// ponytail: reload on success instead of DOM patching — simplest correct refresh for Phase 1.
(function () {
  async function send(url, method, body) {
    var res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      var msg = (await res.json().catch(function () { return {}; })).error || 'Request failed';
      alert(msg);
      return false;
    }
    return true;
  }

  document.querySelectorAll('.quick-add').forEach(function (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var kind = form.dataset.quick;
      var data = Object.fromEntries(new FormData(form).entries());
      var url = kind === 'event' ? '/api/events' : '/api/todos';
      if (await send(url, 'POST', data)) location.reload();
    });
  });

  var todos = document.getElementById('todos-list');
  if (todos) {
    todos.addEventListener('click', async function (e) {
      var btn = e.target.closest('[data-check]');
      if (!btn) return;
      var id = btn.closest('li').dataset.id;
      if (await send('/api/todos/' + id, 'PATCH', { done: true })) location.reload();
    });
  }
})();
