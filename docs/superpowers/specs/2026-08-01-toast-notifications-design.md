# F.R.I.D.A.Y. — Toast / Error Surface Design (Spec AB)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** nothing. Spec AC (optimistic UI) depends on *this*.
**Estimate:** ~1 hour.

## 1. Context

Failures are currently silent. `calendar.js` does `await fetch('/api/events/' + id,
{method:'DELETE'})` and never checks `res.ok`; `todos.js`, `notes.js`, and
`music.js` do the same. If the network drops or the server 500s, the UI acts as
though the write succeeded and the truth only appears on the next reload. There is
no `toast` anywhere in the codebase — no shared place to say "that didn't work".

One tiny module fixes every one of those call sites and unblocks optimistic UI,
which *needs* a way to announce a rollback.

## 2. Goals / Non-goals

**Goals**
- `window.toast(message)` and `window.toast(message, { action, onAction })`.
- Errors persist until dismissed; successes auto-dismiss after 4 s.
- Screen-reader announced (`role="status"`, `aria-live="polite"`).
- One container, appended once, stacked bottom-right above the safe-area inset.

**Non-goals**
- A notification centre / history. Gone is gone.
- Queuing limits, priorities, positions, per-toast theming.
- Replacing the assistant's own error bubbles (`friday.js` `is-error`), which are
  in-conversation and should stay there.
- Push / OS notifications — that is Spec N territory.

## 3. Design

New file `static/js/toast.js`, loaded early in `base.html` (before the page modules,
so they can call it during init).

```js
// Shared failure surface. Errors stick until dismissed; the rest fade.
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

  window.toast = function (message, opts) {
    opts = opts || {};
    var el = document.createElement('div');
    el.className = 'toast' + (opts.error ? ' is-error' : '');

    var text = document.createElement('span');
    text.textContent = message;
    el.appendChild(text);

    if (opts.action) {
      var btn = document.createElement('button');
      btn.className = 'btn-ghost toast-action';
      btn.textContent = opts.action;
      btn.addEventListener('click', function () {
        el.remove();
        if (opts.onAction) opts.onAction();
      });
      el.appendChild(btn);
    }

    var close = document.createElement('button');
    close.className = 'icon-btn toast-close';
    close.setAttribute('aria-label', 'Dismiss');
    close.innerHTML = '<img src="/static/vendor/lucide/x.svg" alt="" width="14" height="14">';
    close.addEventListener('click', function () { el.remove(); });
    el.appendChild(close);

    container().appendChild(el);
    if (!opts.error) setTimeout(function () { el.remove(); }, 4000);
    return el;
  };
})();
```

`static/vendor/lucide/x.svg` must exist — add it to the pinned vendor set if it does
not.

**Call-site convention** — one helper, used by every module that writes:

```js
async function post(url, opts) {
  var res = await fetch(url, opts);
  if (!res.ok) window.toast('Could not save — try again.', { error: true });
  return res;
}
```

Rather than exporting a shared `post()` from a new "http" module (a layer for four
call sites), each page module keeps its own three-line version. Retry, where it
makes sense, is a `{ action: 'Retry', onAction: fn }` toast.

**Offline** — one listener in `toast.js`:

```js
window.addEventListener('offline', function () {
  offlineToast = window.toast('Offline — changes will not save.', { error: true });
});
window.addEventListener('online', function () {
  if (offlineToast) { offlineToast.remove(); offlineToast = null; }
  window.toast('Back online.');
});
```

**CSS** (`app.css`, tokens only): `.toast-host` is `position: fixed; right: var(--s-4);
bottom: calc(var(--s-4) + env(safe-area-inset-bottom)); z-index: 90;` — above the
Friday panel but below the palette scrim. Individual toasts use the existing glass
surface; `.is-error` uses the existing danger token already used by
`.friday-msg.is-error`. Entry is a `transform: translateY(8px)` + opacity transition,
`prefers-reduced-motion` respected.

**Z-index ledger** (existing values are already load-bearing — the context menu at 70
once blocked the calendar header): rail scrim 40, context menu 70, toast host 90,
palette scrim 100.

## 4. Testing

`tests/test_toast.py`:

1. `toast.js` is in `base.html`'s script list and precedes `calendar.js`/`todos.js`
   in load order.
2. `static/vendor/lucide/x.svg` exists on disk (vendor assets are pinned, not fetched).

Client behaviour is not unit-tested — there is no JS test runner in this project and
adding one for a 40-line module is not worth it. Manual: kill the dev server, click
delete on an event, confirm the error toast appears and sticks.

## 5. Risks

- **Toast spam** — a failing poll could stack dozens. Mitigation: the offline toast
  is deduped by holding its element; other toasts come from explicit user actions,
  which are inherently rate-limited by the user.
- **Covering content** — bottom-right overlaps the Friday panel's input on narrow
  screens. The z-index puts it above, and it auto-dismisses; errors are dismissible.

## 6. Skipped deliberately

Toast history, promise-wrapping sugar (`toast.promise(...)`), positions, a shared
HTTP client module. Add the HTTP client when a fifth module needs the same wrapper.
