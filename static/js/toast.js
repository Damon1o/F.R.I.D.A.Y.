// Shared UI surfaces: toasts (Spec AB), empty states (Spec AG), skeletons (Spec AF).
// Loaded before the page modules so they can call these during init.
(function () {
  var host = null;

  function container() {
    if (!host) {
      host = document.createElement('div');
      host.className = 'toast-host';
      host.setAttribute('role', 'status');
      host.setAttribute('aria-live', 'polite');
      document.body.appendChild(host);
    }
    return host;
  }

  // Lucide only — the vendor set is pinned on disk, nothing is fetched from a CDN.
  function lucide(name, size) {
    var img = document.createElement('img');
    img.src = '/static/vendor/lucide/' + name + '.svg';
    img.alt = '';
    img.width = img.height = size;
    return img;
  }

  // Errors stick until dismissed; anything else fades. Returns the element so a
  // caller can drop it early (the offline toast does).
  window.toast = function (message, opts) {
    opts = opts || {};
    var el = document.createElement('div');
    el.className = 'toast' + (opts.error ? ' is-error' : '');

    var text = document.createElement('span');
    text.className = 'toast-text';
    text.textContent = message;
    el.appendChild(text);

    if (opts.action) {
      var act = document.createElement('button');
      act.type = 'button';
      act.className = 'btn-ghost toast-action';
      act.textContent = opts.action;
      act.addEventListener('click', function () {
        el.remove();
        if (opts.onAction) opts.onAction();
      });
      el.appendChild(act);
    }

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'icon-btn toast-close';
    close.setAttribute('aria-label', 'Dismiss');
    close.appendChild(lucide('x', 14));
    close.addEventListener('click', function () { el.remove(); });
    el.appendChild(close);

    container().appendChild(el);
    if (!opts.error) setTimeout(function () { el.remove(); }, 4000);
    return el;
  };

  // One held reference, so a flapping connection cannot stack offline toasts.
  var offline = null;
  window.addEventListener('offline', function () {
    if (!offline) offline = window.toast('Offline — changes will not save.', { error: true });
  });
  window.addEventListener('online', function () {
    if (offline) { offline.remove(); offline = null; }
    window.toast('Back online.');
  });

  // ---- Empty states (Spec AG) --------------------------------------------
  // Only ever called after a *successful* fetch that returned nothing. A failed
  // fetch clears the host and toasts instead — an empty state would lie about it.
  window.emptyState = function (host, opts) {
    host.innerHTML = '';
    var el = document.createElement('div');
    el.className = 'empty-state';
    el.appendChild(lucide(opts.icon, 24));

    var title = document.createElement('p');
    title.className = 'empty-title';
    title.textContent = opts.title;
    el.appendChild(title);

    if (opts.hint) {
      var hint = document.createElement('p');
      hint.className = 'empty-hint';
      hint.textContent = opts.hint;
      el.appendChild(hint);
    }
    if (opts.action) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-primary';
      btn.textContent = opts.action;
      btn.addEventListener('click', opts.onAction);
      el.appendChild(btn);
    }
    host.appendChild(el);
    return el;
  };

  // ---- Skeletons (Spec AF) -----------------------------------------------
  // Written by whichever function starts the fetch; every render path clears the
  // host first, so success, empty, and error all overwrite it.
  window.skeletonRows = function (host, n, height) {
    host.innerHTML = '';
    for (var i = 0; i < n; i++) {
      var el = document.createElement('div');
      el.className = 'skeleton';
      el.style.height = (height || 44) + 'px';
      host.appendChild(el);
    }
  };
})();
