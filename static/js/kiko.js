// Kiko assistant panel: streamed chat over /api/kiko/*. ponytail: vanilla fetch + SSE.
(function () {
  var list = document.getElementById('kiko-messages');
  var form = document.getElementById('kiko-form');
  var input = document.getElementById('kiko-text');
  var newBtn = document.getElementById('kiko-new');
  if (!list || !form) return;

  function bubble(role, text) {
    var el = document.createElement('div');
    el.className = 'kiko-msg ' + role;
    el.textContent = text || '';
    list.appendChild(el);
    list.scrollTop = list.scrollHeight;
    return el;
  }

  function render(messages) {
    list.innerHTML = '';
    messages.forEach(function (m) { bubble(m.role, m.content); });
  }

  async function loadHistory() {
    try {
      var res = await fetch('/api/kiko/history');
      render(await res.json());
    } catch (e) { /* offline: leave panel empty */ }
  }

  // Parse an SSE text buffer into complete {event, data} frames; return leftover.
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

  async function send(text) {
    input.disabled = true;
    bubble('user', text);
    var pending = bubble('assistant', '');
    pending.classList.add('is-pending');
    var streamed = '';
    try {
      var res = await fetch('/api/kiko/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text }),
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
            pending.textContent = streamed;
          } else if (event === 'error') {
            streamed = payload.text;
            pending.textContent = streamed;
            pending.classList.add('is-error');
          }
          list.scrollTop = list.scrollHeight;
        });
      }
    } catch (e) {
      pending.textContent = 'Kiko is unreachable.';
      pending.classList.add('is-error');
    } finally {
      pending.classList.remove('is-pending');
      if (!pending.textContent) pending.remove();
      input.disabled = false;
      input.focus();
    }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || input.disabled) return;
    input.value = '';
    send(text);
  });

  if (newBtn) newBtn.addEventListener('click', async function () {
    await fetch('/api/kiko/clear', { method: 'POST' });
    list.innerHTML = '';
    input.focus();
  });

  loadHistory();
})();
