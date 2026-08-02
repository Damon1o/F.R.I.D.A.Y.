// F.R.I.D.A.Y. assistant panel + UI prefs: vanilla fetch + SSE.
(function () {
  var list = document.getElementById('friday-messages');
  var form = document.getElementById('friday-form');
  var input = document.getElementById('friday-text');
  var newBtn = document.getElementById('friday-new');
  if (!list || !form) return;

  // The system prompt asks for plain sentences, but models slip markdown in anyway.
  // Strip it rather than render it: bubbles are plain text nodes, and voice-web.js speaks
  // that same textContent — so this keeps "asterisk asterisk" out of the speech too.
  function plain(text) {
    return String(text || '')
      .replace(/```[\s\S]*?```/g, '')                 // fenced code reads as noise either way
      .replace(/`([^`]+)`/g, '$1')
      .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')      // links and images keep their label
      .replace(/(\*\*|__)(.*?)\1/g, '$2')
      .replace(/(^|[\s(])[*_]([^*_\n]+)[*_]/g, '$1$2')
      .replace(/^\s{0,3}#{1,6}\s+/gm, '')
      .replace(/^\s*[-*+]\s+/gm, '')
      .replace(/^\s*>\s?/gm, '')
      .trim();
  }

  function bubble(role, text, id) {
    var el = document.createElement('div');
    el.className = 'friday-msg ' + role;
    if (id) el.dataset.id = id;
    el.textContent = role === 'assistant' ? plain(text) : (text || '');
    list.appendChild(el);
    list.scrollTop = list.scrollHeight;
    return el;
  }

  // Spec AE — which tools ran, collapsed. Names and argument echoes only; tool
  // results never reach the client, so nothing untrusted is rendered here.
  function toolNote(el, calls) {
    if (!calls || !calls.length) return;
    var d = document.createElement('details');
    d.className = 'friday-tools';
    var s = document.createElement('summary');
    s.textContent = 'Used ' + calls.length + (calls.length === 1 ? ' tool' : ' tools');
    d.appendChild(s);
    calls.forEach(function (c) {
      var p = document.createElement('p');
      p.textContent = c.summary ? c.name + ' — ' + c.summary : c.name;
      d.appendChild(p);
    });
    el.appendChild(d);
  }

  // History pages backwards: open on the last PAGE turns, fetch older on demand.
  var PAGE = 40;
  var oldestId = null;

  function olderButton() {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'friday-older label-mono';
    btn.textContent = 'Load earlier messages';
    btn.addEventListener('click', async function () {
      btn.disabled = true;
      try {
        var res = await fetch('/api/friday/history?limit=' + PAGE + '&before=' + oldestId);
        var rows = await res.json();
        btn.remove();
        var anchor = list.firstChild;
        rows.forEach(function (m) {
          var el = document.createElement('div');   // not bubble(): that appends and scrolls
          el.className = 'friday-msg ' + m.role;
          el.textContent = m.role === 'assistant' ? plain(m.content) : (m.content || '');
          list.insertBefore(el, anchor);
        });
        if (rows.length) {
          oldestId = rows[0].id;
          if (rows.length === PAGE) list.insertBefore(olderButton(), list.firstChild);
        }
      } catch (e) {
        btn.disabled = false;
      }
    });
    return btn;
  }

  function render(messages) {
    list.innerHTML = '';
    var lastUser = '';
    var lastUserId = null;
    messages.forEach(function (m) {
      var el = bubble(m.role, m.content, m.id);
      if (m.role === 'user') { lastUser = m.content; lastUserId = m.id; }
      else toolNote(el, m.tools);
    });
    if (messages.length) {
      oldestId = messages[0].id;
      if (messages.length === PAGE) list.insertBefore(olderButton(), list.firstChild);
    }
    var last = messages[messages.length - 1];
    if (last && last.role === 'assistant' && lastUser) {
      turnControls(list.lastElementChild, lastUser, lastUserId);
    }
  }

  async function loadHistory() {
    // Skeleton (Spec AF): the panel is otherwise a blank box until this resolves,
    // which on a cold serverless call reads as "empty conversation".
    window.skeletonRows(list, 3, 52);
    try {
      var res = await fetch('/api/friday/history?limit=' + PAGE);
      render(await res.json());
    } catch (e) {
      list.innerHTML = '';                     // never leave a skeleton shimmering
      window.toast('Could not load the conversation.', { error: true });
    }
  }

  function drain(buf, onFrame) {
    var parts = buf.split('\n\n');
    var rest = parts.pop();
    parts.forEach(function (block) {
      var event = 'message', data = '';
      block.split('\n').forEach(function (line) {
        if (line.indexOf('event:') === 0) event = line.slice(6).trim();
        else if (line.indexOf('data:') === 0) data = line.slice(5).trim();
      });
      if (data) onFrame(event, JSON.parse(data));
    });
    return rest;
  }

  // Interrupt: the send button turns into a stop button while a reply streams, Esc does
  // the same, and voice barge-in calls window.fridayStop(). Aborting the fetch closes the
  // SSE stream, which ends the server generator — it persists whatever was said already.
  var sendBtn = document.getElementById('friday-send');
  var inflight = null;

  // Always fires the event — speech outlives the stream, so a stop after the last token
  // still has something to cut. Returns whether a reply was actually being streamed.
  window.fridayStop = function () {
    var streaming = !!inflight;
    if (inflight) { inflight.abort(); inflight = null; }
    window.dispatchEvent(new Event('friday-interrupt'));   // voice-web.js cuts the speech
    return streaming;
  };

  function busy(on) {
    inflight = on || null;
    if (sendBtn) {
      sendBtn.classList.toggle('is-busy', !!on);
      sendBtn.setAttribute('aria-label', on ? 'Stop' : 'Send');
    }
  }

  // ---- Retry / edit the last turn (Spec AD) --------------------------------
  // The rewind is server-side: the rows have to be gone before the turn is replayed,
  // or the model sees its own discarded answer in the replayed context.
  async function truncate(id) {
    if (!id) return false;
    try {
      var res = await fetch('/api/friday/history/' + id, { method: 'DELETE' });
      if (!res.ok) throw new Error(res.status);
      return true;
    } catch (e) {
      window.toast('Could not rewind that turn.', { error: true });
      return false;
    }
  }

  function actionBtn(label, run) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'friday-turn-btn label-mono';
    b.textContent = label;
    b.addEventListener('click', run);
    return b;
  }

  // Attached to the final assistant bubble only, and cleared when a new turn starts.
  function turnControls(el, userText, userId) {
    if (!el || !el.dataset.id) return;
    var bar = document.createElement('div');
    bar.className = 'friday-turn-actions';
    bar.appendChild(actionBtn('Retry', async function () {
      if (inflight) return;                       // mid-stream retry is ambiguous
      if (await truncate(el.dataset.id)) { el.remove(); send(userText); }
    }));
    bar.appendChild(actionBtn('Edit', async function () {
      if (inflight) return;
      if (!userId || !await truncate(userId)) return;
      var prev = el.previousElementSibling;
      el.remove();
      if (prev && prev.classList.contains('user')) prev.remove();
      input.value = userText;
      input.focus();
    }));
    el.appendChild(bar);
  }

  function clearTurnControls() {
    list.querySelectorAll('.friday-turn-actions').forEach(function (el) { el.remove(); });
  }

  // Drafts are inert until this button is clicked. It posts the draft id and nothing
  // else, so the mail that goes out is the mail shown here.
  function confirmSend(draft) {
    var el = bubble('assistant', '');
    el.classList.add('friday-confirm');
    var text = document.createElement('p');
    text.textContent = 'Send to ' + draft.to + ' — "' + (draft.subject || '') + '"\n\n' + (draft.preview || '');
    var btn = document.createElement('button');
    btn.className = 'btn-primary';
    btn.textContent = 'Send it';
    btn.addEventListener('click', async function () {
      btn.disabled = true;
      var res = await fetch('/api/mail/send/' + encodeURIComponent(draft.draft_id), { method: 'POST' });
      btn.textContent = res.ok ? 'Sent' : 'Send failed';
    });
    el.appendChild(text);
    el.appendChild(btn);
    list.scrollTop = list.scrollHeight;
  }

  async function send(text) {
    input.disabled = true;
    clearTurnControls();                 // they belong to the last turn, not this one
    bubble('user', text);
    var pending = bubble('assistant', '');
    pending.classList.add('is-pending');
    var streamed = '';
    var calls = [];
    var ctrl = new AbortController();
    busy(ctrl);
    try {
      var res = await fetch('/api/friday/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text }),
        signal: ctrl.signal,
      });
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = '';
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        buf = drain(buf, function (event, payload) {
          if (event === 'status') {
            if (!streamed) pending.textContent = payload.text;
          } else if (event === 'token') {
            streamed += payload.text;
            pending.textContent = plain(streamed);   // half-written markers clear once closed
          } else if (event === 'tool') {
            calls.push(payload);
          } else if (event === 'action' && payload.type === 'confirm_send') {
            confirmSend(payload);
          } else if (event === 'error') {
            streamed = payload.text;
            pending.textContent = streamed;
            pending.classList.add('is-error');
          }
          list.scrollTop = list.scrollHeight;
        });
      }
    } catch (e) {
      // An abort is the user stopping on purpose: keep the partial reply as it stands.
      // is-stopped keeps voice-web.js from speaking a reply that was just cut off.
      if (e.name === 'AbortError') {
        pending.classList.add('is-stopped');
      } else {
        pending.textContent = 'F.R.I.D.A.Y. is unreachable.';
        pending.classList.add('is-error');
      }
    } finally {
      busy(null);
      // The stream can end with nothing rendered (a buffered/dropped connection, a
      // timed-out function) even though the turn ran and the reply is in the database.
      // Ask history for it rather than leaving the turn looking unanswered.
      if (!streamed && !pending.classList.contains('is-error')) await recoverReply(pending);
      pending.classList.remove('is-pending');
      if (!pending.textContent) pending.remove();
      else {
        toolNote(pending, calls);
        // The bubble was built client-side and has no stored id yet; ask history for
        // the one that was just persisted so Retry/Edit have something to rewind to.
        await tagLastTurn(pending, text);
      }
      input.disabled = false;
      input.focus();
    }
  }

  // Stamp the freshly streamed bubble with its stored id and attach Retry/Edit.
  async function tagLastTurn(el, userText) {
    try {
      var res = await fetch('/api/friday/history?limit=2');
      var rows = await res.json();
      var reply = rows[rows.length - 1];
      var question = rows[rows.length - 2];
      if (!reply || reply.role !== 'assistant') return;
      el.dataset.id = reply.id;
      turnControls(el, userText, question && question.role === 'user' ? question.id : null);
    } catch (e) { /* offline: the turn simply has no controls */ }
  }

  // Last stored assistant turn, if it is newer than the last one on screen.
  async function recoverReply(pending) {
    try {
      var res = await fetch('/api/friday/history?limit=2');
      var rows = await res.json();
      var last = rows[rows.length - 1];
      if (last && last.role === 'assistant' && last.content) pending.textContent = plain(last.content);
    } catch (e) { /* offline: the empty bubble is removed below */ }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (window.fridayStop()) return;      // the send button is a stop button mid-reply
    var text = input.value.trim();
    if (!text || input.disabled) return;
    input.value = '';
    send(text);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') window.fridayStop();
  });

  // Attachments: the server extracts text, the text goes out as a normal turn.
  var fileInput = document.getElementById('friday-file');
  var attachBtn = document.getElementById('friday-attach');
  if (fileInput && attachBtn) {
    attachBtn.addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', async function () {
      var file = fileInput.files[0];
      if (!file) return;
      fileInput.value = '';
      var note = bubble('user', 'Reading ' + file.name + '…');
      note.classList.add('is-pending');
      var body = new FormData();
      body.append('file', file);
      try {
        var res = await fetch('/api/friday/upload', { method: 'POST', body: body });
        var data = await res.json();
        note.remove();
        if (!res.ok) return bubble('assistant', data.error || 'Upload failed').classList.add('is-error');
        var question = input.value.trim() || 'Summarise this file.';
        input.value = '';
        // Say what was actually read, so a truncated summary can't sound complete.
        var marker = data.truncated
          ? '[Attachment: ' + data.name + ' — first ' + data.chars + ' of ' + data.total_chars + ' characters, truncated]'
          : '[Attachment: ' + data.name + ']';
        send(question + '\n\n' + marker + '\n' + data.text);
      } catch (e) {
        note.remove();
        bubble('assistant', 'Upload failed.').classList.add('is-error');
      }
    });
  }

  // New chat starts a fresh thread — the previous conversation stays readable
  // from the history drawer instead of being deleted.
  if (newBtn) newBtn.addEventListener('click', async function () {
    await fetch('/api/friday/thread', { method: 'POST' });
    list.innerHTML = '';
    oldestId = null;
    input.focus();
  });

  // ---- Past conversations: AnimatedList (React Bits) ported to vanilla ----
  // IntersectionObserver drives the scale/fade, the gradients track scroll
  // position, arrows + Enter navigate. Same behaviour, no React, no motion dep.
  function animatedList(container, items, onSelect, onRename, onDelete) {
    var view = container.querySelector('.scroll-list');
    var top = container.querySelector('.top-gradient');
    var bottom = container.querySelector('.bottom-gradient');
    var selected = -1;

    if (container._cleanup) container._cleanup();
    view.innerHTML = '';

    if (!items.length) {
      window.emptyState(view, {
        icon: 'message-square',
        title: 'No past conversations',
        hint: 'This is your first one.',
      });
      return;
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { e.target.classList.toggle('is-in', e.isIntersecting); });
    }, { root: view, threshold: 0.5 });

    function select(i, scroll) {
      selected = i;
      view.querySelectorAll('.item').forEach(function (el, n) {
        el.classList.toggle('selected', n === i);
      });
      var el = view.querySelector('[data-index="' + i + '"]');
      if (!el || !scroll) return;
      var margin = 50;
      var itemTop = el.offsetTop, itemBottom = itemTop + el.offsetHeight;
      if (itemTop < view.scrollTop + margin) {
        view.scrollTo({ top: itemTop - margin, behavior: 'smooth' });
      } else if (itemBottom > view.scrollTop + view.clientHeight - margin) {
        view.scrollTo({ top: itemBottom - view.clientHeight + margin, behavior: 'smooth' });
      }
    }

    // Rename in place: the title swaps for an input, Enter/blur saves, Escape cancels.
    // Keydown stops here or the list's own arrow/Enter handler would hijack typing.
    function rename(text, item) {
      var input = document.createElement('input');
      input.className = 'item-rename';
      input.value = item.title;
      text.replaceWith(input);
      input.focus();
      input.select();
      var closed = false;
      function finish(save) {
        if (closed) return;
        closed = true;
        var value = input.value.trim();
        input.replaceWith(text);
        if (!save || !value || value === item.title) return;
        item.title = value;
        text.textContent = value;
        onRename(item, value);
      }
      input.addEventListener('click', function (e) { e.stopPropagation(); });
      input.addEventListener('blur', function () { finish(true); });
      input.addEventListener('keydown', function (e) {
        e.stopPropagation();
        if (e.key === 'Enter') finish(true);
        else if (e.key === 'Escape') finish(false);
      });
    }

    var tpl = document.getElementById('thread-actions');

    items.forEach(function (item, i) {
      var el = document.createElement('div');
      el.className = 'item' + (item.current ? ' is-current' : '');
      el.dataset.index = i;
      el.style.transitionDelay = Math.min(i, 8) * 30 + 'ms';
      var text = document.createElement('p');
      text.className = 'item-text';
      text.textContent = item.title;
      var meta = document.createElement('span');
      meta.className = 'item-meta label-mono';
      meta.textContent = item.meta || '';
      el.appendChild(text);
      el.appendChild(meta);
      if (tpl && onRename && onDelete) {
        var acts = tpl.content.firstElementChild.cloneNode(true);
        acts.addEventListener('click', function (e) { e.stopPropagation(); });
        acts.querySelector('[data-rename]').addEventListener('click', function () {
          rename(text, item);
        });
        acts.querySelector('[data-delete]').addEventListener('click', function (e) {
          onDelete(item, e.currentTarget);
        });
        el.appendChild(acts);
      }
      el.addEventListener('mouseenter', function () { select(i, false); });
      el.addEventListener('click', function () { select(i, false); onSelect(item, i); });
      view.appendChild(el);
      io.observe(el);
    });

    function onScroll() {
      var d = view.scrollHeight - (view.scrollTop + view.clientHeight);
      top.style.opacity = Math.min(view.scrollTop / 50, 1);
      bottom.style.opacity = view.scrollHeight <= view.clientHeight ? 0 : Math.min(d / 50, 1);
    }

    function onKey(e) {
      if (container.closest('[hidden]')) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        select(Math.min(selected + 1, items.length - 1), true);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        select(Math.max(selected - 1, 0), true);
      } else if (e.key === 'Enter' && selected >= 0) {
        e.preventDefault();
        onSelect(items[selected], selected);
      }
    }

    view.addEventListener('scroll', onScroll);
    document.addEventListener('keydown', onKey);
    container._cleanup = function () {
      io.disconnect();
      view.removeEventListener('scroll', onScroll);
      document.removeEventListener('keydown', onKey);
    };
    onScroll();
  }

  var drawer = document.getElementById('chat-history');
  var histBtn = document.getElementById('friday-history');

  if (drawer && histBtn) {
    var box = drawer.querySelector('.scroll-list-container');

    async function loadThreads() {
      window.skeletonRows(box.querySelector('.scroll-list'), 4, 36);
      var res;
      try {
        res = await fetch('/api/friday/threads');
        if (!res.ok) throw new Error(res.status);
      } catch (e) {
        box.querySelector('.scroll-list').innerHTML = '';
        window.toast('Could not load past conversations.', { error: true });
        return;
      }
      var data = await res.json();
      animatedList(box, data.threads.map(function (t) {
        return {
          id: t.id,
          title: t.title,
          meta: (t.created_at || '').slice(0, 10),
          current: t.id === data.current,
        };
      }), async function (item) {
        await fetch('/api/friday/thread', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: item.id }),
        });
        drawer.hidden = true;
        histBtn.setAttribute('aria-expanded', 'false');
        oldestId = null;
        loadHistory();
      }, function (item, title) {
        fetch('/api/friday/thread/' + item.id, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: title }),
        });
      }, deleteThread);
    }

    // Two-click confirm instead of window.confirm — a modal dialog blocks the page,
    // and deleting a conversation on a stray click is not recoverable.
    async function deleteThread(item, btn) {
      if (!btn.classList.contains('is-confirm')) {
        btn.classList.add('is-confirm');
        btn.setAttribute('aria-label', 'Confirm delete');
        setTimeout(function () {
          btn.classList.remove('is-confirm');
          btn.setAttribute('aria-label', 'Delete chat');
        }, 3000);
        return;
      }
      await fetch('/api/friday/thread/' + item.id, { method: 'DELETE' });
      await loadThreads();
      oldestId = null;
      loadHistory();
    }

    histBtn.addEventListener('click', async function () {
      drawer.hidden = !drawer.hidden;
      histBtn.setAttribute('aria-expanded', String(!drawer.hidden));
      if (!drawer.hidden) {
        try { await loadThreads(); } catch (e) { /* offline: leave drawer empty */ }
      }
    });
  }

  loadHistory();
})();

// Nav rail: collapse + hover expand + keyboard shortcut (Ctrl/Cmd+B)
(function () {
  var rail = document.getElementById('nav-rail');
  var btn = document.getElementById('nav-toggle');
  if (!rail || !btn) return;

  var prefersCollapsed = false;
  // Below 860px the rail is an overlay drawer — start it closed whatever the
  // saved desktop preference says, or it covers the phone screen on every load.
  var isNarrow = window.matchMedia('(max-width: 860px)');

  if (isNarrow.matches) {
    prefersCollapsed = true;
    applyNavState(true); // sync, before the prefs fetch — no open-drawer flash
  }

  async function loadPrefs() {
    if (isNarrow.matches) return;
    try {
      var res = await fetch('/api/settings/ui');
      var data = await res.json();
      prefersCollapsed = data.nav_collapsed === 'true';
      applyNavState(prefersCollapsed);
    } catch (e) {
      // fallback to localStorage for backward compat
      prefersCollapsed = localStorage.getItem('navCollapsed') === 'true';
      applyNavState(prefersCollapsed);
    }
  }

  function applyNavState(collapsed) {
    rail.classList.toggle('is-collapsed', collapsed);
    document.querySelector('.app-shell')?.classList.toggle('rail-collapsed', collapsed);
    btn.setAttribute('aria-expanded', String(!collapsed));
    localStorage.setItem('navCollapsed', String(collapsed));
  }

  function toggleNav() {
    prefersCollapsed = !prefersCollapsed;
    applyNavState(prefersCollapsed);
    if (isNarrow.matches) return; // drawer state on a phone is not a saved preference
    fetch('/api/settings/ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nav_collapsed: prefersCollapsed }),
    }).catch(console.error);
  }

  btn.addEventListener('click', toggleNav);

  // Mobile drawer: tap the scrim to close.
  document.getElementById('rail-scrim')?.addEventListener('click', function () {
    if (!prefersCollapsed) toggleNav();
  });

  // Keyboard shortcut: Ctrl/Cmd + B
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      toggleNav();
    }
  });

  // Listen for settings page changes
  window.addEventListener('nav-pref-changed', function (e) {
    if (e.detail && typeof e.detail.collapsed === 'boolean') {
      prefersCollapsed = e.detail.collapsed;
      applyNavState(prefersCollapsed);
    }
  });

  loadPrefs();
})();

// Nav rail hover-to-peek when collapsed. Drives the expand via explicit classes so it
// never depends on :hover/:has() firing. Bind to #nav-rail (always present) — the
// is-collapsed class is applied async after prefs load, so querying .rail.is-collapsed
// here would return null and the listeners would never attach.
(function () {
  var rail = document.getElementById('nav-rail');
  var shell = document.querySelector('.app-shell');
  if (!rail || !shell) return;
  rail.addEventListener('mouseenter', function () {
    if (!rail.classList.contains('is-collapsed')) return;
    rail.classList.add('is-hovering');
    shell.classList.add('rail-hovered');
  });
  rail.addEventListener('mouseleave', function () {
    rail.classList.remove('is-hovering');
    shell.classList.remove('rail-hovered');
  });
})();

// F.R.I.D.A.Y. panel: visibility toggle + slide animation + keyboard shortcut (Ctrl/Cmd+Shift+F)
(function () {
  var panel = document.querySelector('.friday');
  var toggleBtn = document.getElementById('friday-toggle'); // button in topbar
  if (!panel) return;

  // Read initial state from server-rendered DOM — no fetch, no flash.
  var visible = !panel.classList.contains('is-hidden');
  // Same as the nav rail: on a phone the panel is a full-height sheet, so it
  // starts closed regardless of the saved desktop preference.
  var isNarrow = window.matchMedia('(max-width: 860px)');

  function applyFridayVisibility(show) {
    visible = show;
    panel.classList.toggle('is-hidden', !visible);
    document.querySelector('.app-shell')?.classList.toggle('friday-hidden', !visible);
    if (toggleBtn) {
      toggleBtn.setAttribute('aria-expanded', String(visible));
      toggleBtn.setAttribute('aria-label', visible ? 'Hide F.R.I.D.A.Y. panel' : 'Show F.R.I.D.A.Y. panel');
    }
    localStorage.setItem('fridayVisible', String(visible));
  }

  if (isNarrow.matches && visible) applyFridayVisibility(false);

  function toggleFriday() {
    var nextState = !visible;
    applyFridayVisibility(nextState);
    if (isNarrow.matches) return; // sheet state on a phone is not a saved preference
    fetch('/api/settings/ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ friday_visible: nextState }),
    }).catch(console.error);
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', toggleFriday);
  }

  // Keyboard shortcut: Ctrl/Cmd + Shift + F
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
      e.preventDefault();
      toggleFriday();
    }
  });

  // Listen for settings page changes
  window.addEventListener('friday-pref-changed', function (e) {
    if (e.detail && typeof e.detail.visible === 'boolean') {
      applyFridayVisibility(e.detail.visible);
    }
  });
})();