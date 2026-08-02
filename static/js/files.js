// Files page: browse the machine, edit text files, rename/move/delete.
// Every call carries X-FRIDAY-FS — the server rejects anything without it, which is what
// keeps a random page in another tab from driving the filesystem API (see routes.py).
(function () {
  var list = document.getElementById('fs-list');
  if (!list) return;
  var crumbs = document.getElementById('fs-crumbs');
  var editor = document.getElementById('fs-editor');
  var text = document.getElementById('fs-text');
  var name = document.getElementById('fs-editor-name');
  var cwd = '';
  var open = '';

  function api(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'X-FRIDAY-FS': '1', 'Content-Type': 'application/json' }, opts.headers);
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) throw new Error(body.error || 'That did not work.');
        return body;
      });
    });
  }

  function fail(e) { window.toast(e.message, { error: true }); }

  function row(entry) {
    var li = document.createElement('li');
    li.dataset.path = entry.path;
    li.dataset.dir = entry.is_dir ? '1' : '';
    var title = document.createElement('span');
    title.className = 'task-title';
    title.textContent = entry.name;
    var meta = document.createElement('span');
    meta.className = 'task-due';
    meta.textContent = entry.is_dir ? entry.mtime : size(entry.size) + '  ' + entry.mtime;
    li.append(title, meta);
    li.classList.add(entry.is_dir ? 'is-dir' : 'is-file');
    return li;
  }

  function size(n) {
    if (!n) return '';
    var u = ['B', 'KB', 'MB', 'GB'], i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return (i ? n.toFixed(1) : n) + ' ' + u[i];
  }

  function paint(entries, empty) {
    list.innerHTML = '';
    if (!entries.length) {
      var li = document.createElement('li');
      li.className = 'empty-state';
      li.innerHTML = '<p class="empty-title">' + empty + '</p>' +
        '<p class="empty-hint">Right-click for new file, new folder.</p>';
      list.appendChild(li);
      return;
    }
    entries.forEach(function (e) { list.appendChild(row(e)); });
  }

  function trail(path, parent) {
    crumbs.innerHTML = '';
    function link(label, target) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.addEventListener('click', function () { load(target); });
      crumbs.appendChild(b);
    }
    link('This machine', '');
    if (!path) return;
    var parts = path.split(/[\\/]/).filter(Boolean);
    var acc = '';
    parts.forEach(function (p, i) {
      acc = i === 0 ? p + '\\' : acc.replace(/\\$/, '') + '\\' + p;
      link(p, acc);
    });
    if (parent) crumbs.dataset.parent = parent; else delete crumbs.dataset.parent;
  }

  function load(path) {
    api('/api/files?path=' + encodeURIComponent(path)).then(function (data) {
      cwd = data.path;
      trail(data.path, data.parent);
      paint(data.entries, 'Empty folder');
    }).catch(fail);
  }

  function show(path) {
    api('/api/files/read?path=' + encodeURIComponent(path)).then(function (data) {
      open = data.path;
      name.textContent = data.path + (data.truncated ? '  (truncated)' : '');
      text.value = data.text;
      editor.hidden = false;
    }).catch(fail);
  }

  list.addEventListener('click', function (e) {
    var li = e.target.closest('li[data-path]');
    if (!li) return;
    if (li.dataset.dir) load(li.dataset.path); else show(li.dataset.path);
  });

  document.getElementById('fs-close').addEventListener('click', function () {
    editor.hidden = true;
    open = '';
  });

  document.getElementById('fs-save').addEventListener('click', function () {
    if (!open) return;
    api('/api/files/write', { method: 'POST', body: JSON.stringify({ path: open, text: text.value }) })
      .then(function () { window.toast('Saved.'); })
      .catch(fail);
  });

  document.getElementById('fs-find').addEventListener('submit', function (e) {
    e.preventDefault();
    var q = document.getElementById('fs-q').value.trim();
    if (!q) return load(cwd);
    api('/api/files/search?path=' + encodeURIComponent(cwd) + '&q=' + encodeURIComponent(q))
      .then(function (hits) { paint(hits, 'Nothing matched'); })
      .catch(fail);
  });

  function join(dir, leaf) { return dir.replace(/[\\/]+$/, '') + '\\' + leaf; }

  window.ctxMenu.bind(list, function (target) {
    var li = target.closest('li[data-path]');
    var here = [
      {
        label: 'New file', run: function () {
          var n = prompt('File name');
          if (n) api('/api/files/write', { method: 'POST', body: JSON.stringify({ path: join(cwd, n), text: '' }) })
            .then(function () { load(cwd); }).catch(fail);
        },
      },
      {
        label: 'New folder', run: function () {
          var n = prompt('Folder name');
          if (n) api('/api/files/mkdir', { method: 'POST', body: JSON.stringify({ path: join(cwd, n) }) })
            .then(function () { load(cwd); }).catch(fail);
        },
      },
      { label: 'Refresh', run: function () { load(cwd); } },
    ];
    if (!li) return cwd ? here : null;
    var path = li.dataset.path;
    return [
      {
        label: li.dataset.dir ? 'Open' : 'Edit',
        run: function () { li.dataset.dir ? load(path) : show(path); },
      },
      {
        label: 'Rename', run: function () {
          var n = prompt('New name', li.querySelector('.task-title').textContent);
          if (n) api('/api/files/rename', { method: 'POST', body: JSON.stringify({ path: path, name: n }) })
            .then(function () { load(cwd); }).catch(fail);
        },
      },
      {
        label: 'Move to…', run: function () {
          var d = prompt('Destination folder', cwd);
          if (d) api('/api/files/move', { method: 'POST', body: JSON.stringify({ path: path, to: d }) })
            .then(function () { load(cwd); }).catch(fail);
        },
      },
      {
        label: 'Delete', danger: true, run: function () {
          api('/api/files/delete', { method: 'POST', body: JSON.stringify({ path: path }) })
            .then(function () {
              load(cwd);
              window.toast('Moved to the Recycle Bin.');
            }).catch(fail);
        },
      },
    ].concat(here);
  });

  load(list.dataset.start || '');
})();
