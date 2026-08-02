// Shared right-click menu. One element for the whole app: every page that wants
// a menu calls ctxMenu.bind() and returns items for whatever was clicked.
//
//   ctxMenu.bind(list, function (target) {
//     var row = target.closest('li[data-id]');
//     return row ? [{ label: 'Delete', danger: true, run: fn }] : [{ label: 'New', run: fn }];
//   });
//
// Returning null or an empty array lets the browser's own menu through, which is
// what you want over a link or a text selection.
(function () {
  var menu = document.createElement('div');
  menu.className = 'ctx-menu';
  menu.setAttribute('role', 'menu');
  menu.hidden = true;
  document.body.appendChild(menu);

  function hide() { menu.hidden = true; }

  function show(x, y, items) {
    menu.innerHTML = '';
    items.forEach(function (it) {
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('role', 'menuitem');
      b.textContent = it.label;
      if (it.danger) b.className = 'danger';
      b.addEventListener('click', function () { hide(); it.run(); });
      menu.appendChild(b);
    });
    menu.hidden = false;
    // Measure after it is visible, then pull it back on screen if it overflows.
    var r = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(x, window.innerWidth - r.width - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(y, window.innerHeight - r.height - 8)) + 'px';
    menu.querySelector('button').focus();
  }

  function bind(container, build) {
    if (!container) return;

    function open(x, y, target) {
      var items = build(target);
      if (!items || !items.length) return false;
      show(x, y, items);
      return true;
    }

    container.addEventListener('contextmenu', function (e) {
      if (open(e.clientX, e.clientY, e.target)) e.preventDefault();
    });

    // Touch has no right-click, so a half-second press stands in. Any movement
    // means the finger is scrolling, not pressing.
    var timer = null;
    container.addEventListener('touchstart', function (e) {
      var t = e.touches[0];
      var target = e.target;
      timer = setTimeout(function () {
        timer = null;
        open(t.clientX, t.clientY, target);
      }, 500);
    }, { passive: true });

    function cancel() { clearTimeout(timer); timer = null; }
    container.addEventListener('touchmove', cancel, { passive: true });
    container.addEventListener('touchend', cancel);
    container.addEventListener('touchcancel', cancel);
  }

  document.addEventListener('click', function (e) { if (!menu.contains(e.target)) hide(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') hide(); });
  window.addEventListener('scroll', hide, true);
  window.addEventListener('resize', hide);

  window.ctxMenu = { bind: bind, show: show, hide: hide };
})();
