// Desktop build only: /api/update exists when the app was launched by desktop/main.py.
// On the web the route is absent (404) and this quietly does nothing.
fetch('/api/update').then(function (r) { return r.ok ? r.json() : null; }).then(function (u) {
  if (!u || !u.version) return;
  window.toast('Version ' + u.version + ' is available.', {
    action: 'Download',
    onAction: function () { window.open(u.url, '_blank'); },
  });
}).catch(function () { });
