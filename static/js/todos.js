// Tasks page: add, reorder, and a right-click menu for everything else.
// Complete/rename/delete apply to the DOM first and revert on failure (Spec AC) —
// a round trip plus a full page reload for one checkbox was the worst lag in the app.
(function () {
  async function send(url, method, body) {
    var res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok && res.status !== 204) {
      var msg = (await res.json().catch(function () { return {}; })).error || 'Request failed';
      window.toast(msg, { error: true });
      return false;
    }
    return true;
  }

  var form = document.querySelector('.quick-add[data-quick="todo"]');
  var list = document.getElementById('todos-list');

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    var data = Object.fromEntries(new FormData(form).entries());
    if (!data.due_at) delete data.due_at;
    // Adding still reloads: the new row's id and its open/done placement come from
    // the server, and the page head recounts. One reload on an explicit add is fine.
    if (await send('/api/todos', 'POST', data)) location.reload();
  });

  // Drag to reorder. Only open tasks: the server sorts done ones to the bottom,
  // so dragging one up would just snap back on the next load.
  window.dragSort(list, 'li[data-id]:not(.is-done)', function (ids) {
    send('/api/todos/reorder', 'POST', { ids: ids });
  });

  async function toggle(li, done) {
    li.classList.toggle('is-done', done);
    if (!await send('/api/todos/' + li.dataset.id, 'PATCH', { done: done })) {
      li.classList.toggle('is-done', !done);
    }
  }

  async function remove(li) {
    li.hidden = true;
    if (await send('/api/todos/' + li.dataset.id, 'DELETE')) li.remove();
    else li.hidden = false;
  }

  // Rename in place: the title swaps for an input, Enter/blur saves, Escape cancels.
  function rename(li) {
    var text = li.querySelector('.task-title');
    var was = text.textContent;
    var input = document.createElement('input');
    input.className = 'item-rename';
    input.value = was;
    text.replaceWith(input);
    input.focus();
    input.select();
    var closed = false;
    function finish(save) {
      if (closed) return;
      closed = true;
      var value = input.value.trim();
      input.replaceWith(text);
      if (!save || !value || value === was) return;
      text.textContent = value;
      send('/api/todos/' + li.dataset.id, 'PATCH', { title: value }).then(function (ok) {
        if (!ok) text.textContent = was;
      });
    }
    input.addEventListener('blur', function () { finish(true); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') finish(true);
      else if (e.key === 'Escape') finish(false);
    });
  }

  // Bound to the card, not the list: the <ul> shrink-wraps its rows, so with any
  // task on screen there is no empty pixel inside it left to right-click and
  // "New task" would be unreachable. The card's padding is that empty space.
  window.ctxMenu.bind(list.closest('.card'), function (target) {
    // Inputs keep the browser's own menu — cut/paste beats "New task" there.
    if (target.closest('input, textarea')) return null;
    var li = target.closest('li[data-id]');
    if (!li) {
      return [{ label: 'New task', run: function () { form.querySelector('[name=title]').focus(); } }];
    }
    var done = li.classList.contains('is-done');
    return [
      { label: done ? 'Mark incomplete' : 'Mark complete', run: function () { toggle(li, !done); } },
      { label: 'Rename', run: function () { rename(li); } },
      { label: 'Delete', danger: true, run: function () { remove(li); } },
    ];
  });
})();
