// Tasks page: add, toggle complete, delete. ponytail: reload on success.
(function () {
  async function send(url, method, body) {
    var res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok && res.status !== 204) {
      var msg = (await res.json().catch(function () { return {}; })).error || 'Request failed';
      alert(msg);
      return false;
    }
    return true;
  }

  var form = document.querySelector('.quick-add[data-quick="todo"]');
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    var data = Object.fromEntries(new FormData(form).entries());
    if (!data.due_at) delete data.due_at;
    if (await send('/api/todos', 'POST', data)) location.reload();
  });

  document.getElementById('todos-list').addEventListener('click', async function (e) {
    var li = e.target.closest('li[data-id]');
    if (!li) return;
    var id = li.dataset.id;
    if (e.target.closest('[data-check]')) {
      var done = !li.classList.contains('is-done');
      if (await send('/api/todos/' + id, 'PATCH', { done: done })) location.reload();
    } else if (e.target.closest('[data-delete]')) {
      if (await send('/api/todos/' + id, 'DELETE')) location.reload();
    }
  });
})();
