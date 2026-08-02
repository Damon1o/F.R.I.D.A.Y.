// Window buttons for the native (frameless) build. pywebview exposes the host methods as
// window.pywebview.api; it appears a moment after load, so calls go through a small wait.
(function () {
  var maximized = false;

  function api() {
    return new Promise(function (resolve) {
      (function poll() {
        if (window.pywebview && window.pywebview.api) resolve(window.pywebview.api);
        else setTimeout(poll, 50);
      })();
    });
  }

  function on(id, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('click', function () { api().then(fn); });
  }

  on('win-min', function (a) { a.minimize(); });
  on('win-close', function (a) { a.close(); });
  on('win-max', function (a) {
    // pywebview reports no window state, so track which way we last went.
    maximized = !maximized;
    maximized ? a.maximize() : a.restore();
  });

  // Double-clicking the bar is the same as the maximize button, as on any Windows app.
  var bar = document.querySelector('.titlebar');
  if (bar) bar.addEventListener('dblclick', function (e) {
    if (e.target.closest('.titlebar-btn')) return;
    api().then(function (a) { maximized = !maximized; maximized ? a.maximize() : a.restore(); });
  });
})();
