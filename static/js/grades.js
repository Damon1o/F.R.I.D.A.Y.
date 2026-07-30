// Grades page: forced resync and the on-demand F.R.I.D.A.Y. readout.
(function () {
  const refresh = document.getElementById('grades-refresh');
  const status = document.getElementById('sync-status');
  const analyze = document.getElementById('analysis-run');
  const out = document.getElementById('analysis-text');

  refresh?.addEventListener('click', async () => {
    refresh.disabled = true;
    if (status) status.textContent = 'Syncing…';
    try {
      const r = await fetch('/api/grades/sync', { method: 'POST' });
      const d = await r.json();
      if (!r.ok || d.error) {
        if (status) status.textContent = 'Sync failed';
        refresh.disabled = false;
        return;
      }
      // The page is server-rendered; a reload is the whole update.
      location.reload();
    } catch {
      if (status) status.textContent = 'Sync failed';
      refresh.disabled = false;
    }
  });

  analyze?.addEventListener('click', async () => {
    analyze.disabled = true;
    if (out) out.textContent = 'Thinking…';
    try {
      const r = await fetch('/api/grades/analysis', { method: 'POST' });
      const d = await r.json();
      if (out) out.textContent = d.text || d.error || 'No response.';
    } catch {
      if (out) out.textContent = 'Analysis unavailable.';
    }
    analyze.disabled = false;
  });
})();
