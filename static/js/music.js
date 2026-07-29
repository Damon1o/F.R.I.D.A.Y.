/* Music widget — polls /api/music/now-playing and handles controls */
(function () {
  const API_NOW_PLAYING = '/api/music/now-playing';
  const API_CONTROL = '/api/music/control';
  const POLL_INTERVAL = 2000;

  const widget = document.getElementById('music-widget');
  if (!widget) return;

  const content = document.getElementById('music-content');
  const providerTag = document.getElementById('music-provider-tag');

  let pollTimer = null;

  function renderLoading() {
    content.innerHTML = `<div class="music-loading">${icon('loader', 20)} Connecting…</div>`;
  }

  function renderDisconnected(provider = 'Spotify') {
    content.innerHTML = `
      <div class="music-disconnected">
        <div>${icon('music', 32)}</div>
        <div class="music-title">No ${provider} connection</div>
        <div class="music-artist">Connect in Settings to control playback</div>
        <a class="btn-primary" href="/settings">Open Settings</a>
      </div>
    `;
  }

  function renderPlaying(data) {
    providerTag.textContent = data.provider || 'Spotify';
    const progress = data.duration_ms > 0 ? (data.progress_ms / data.duration_ms) * 100 : 0;
    content.innerHTML = `
      <div class="music-info">
        <img class="music-art" id="music-art" src="${data.album_art || ''}" alt="">
        <div class="music-meta">
          <div class="music-title" id="music-title">${escapeHtml(data.title || 'Unknown')}</div>
          <div class="music-artist" id="music-artist">${escapeHtml(data.artist || 'Unknown')}</div>
        </div>
      </div>
      <div class="music-progress" role="slider" aria-label="Playback progress" tabindex="0">
        <span class="music-time" id="music-current">${formatTime(data.progress_ms)}</span>
        <div class="music-bar" id="music-bar"><div class="music-fill" id="music-fill" style="width: ${progress}%"></div></div>
        <span class="music-time" id="music-total">${formatTime(data.duration_ms)}</span>
      </div>
      <div class="music-controls">
        <button class="icon-btn" data-action="prev" aria-label="Previous">${icon('skip-back', 18)}</button>
        <button class="icon-btn music-play" data-action="${data.is_playing ? 'pause' : 'play'}" aria-label="${data.is_playing ? 'Pause' : 'Play'}">${icon(data.is_playing ? 'pause' : 'play', 20)}</button>
        <button class="icon-btn" data-action="next" aria-label="Next">${icon('skip-forward', 18)}</button>
      </div>
    `;
    bindControls();
    bindProgressBar(data.duration_ms);
  }

  function bindControls() {
    content.querySelectorAll('[data-action]').forEach(btn => {
      btn.onclick = () => control(btn.dataset.action);
    });
  }

  function bindProgressBar(duration) {
    const bar = document.getElementById('music-bar');
    if (!bar) return;
    bar.onclick = (e) => {
      const rect = bar.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      control('seek', Math.round(pct * duration));
    };
  }

  function control(action, positionMs) {
    const payload = { action };
    if (action === 'seek' && typeof positionMs === 'number') {
      payload.position_ms = positionMs;
    }
    fetch(API_CONTROL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => r.json()).then(() => {
      if (action !== 'seek') pollNow();
    }).catch(console.error);
  }

  function pollNow() {
    fetch(API_NOW_PLAYING)
      .then(r => r.json())
      .then(data => {
        if (data.error) {
          renderDisconnected(data.provider);
        } else if (data.is_playing !== undefined) {
          renderPlaying(data);
        } else {
          renderDisconnected(data.provider);
        }
      })
      .catch(() => renderDisconnected());
  }

  function startPolling() {
    pollNow();
    pollTimer = setInterval(pollNow, POLL_INTERVAL);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
  }

  function formatTime(ms) {
    if (!ms) return '0:00';
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${r.toString().padStart(2, '0')}`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function icon(name, size = 18) {
    const icons = {
      loader: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"/><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round" opacity="0.8"/></svg>`,
      music: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`,
      'skip-back': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>`,
      'skip-forward': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>`,
      play: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
      pause: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`,
    };
    return icons[name] || '';
  }

  // Start polling when page loads
  document.addEventListener('DOMContentLoaded', startPolling);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopPolling();
    else startPolling();
  });
})();