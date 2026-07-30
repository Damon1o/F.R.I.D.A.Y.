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

  // GPA: hand-entered years, and the official-number accuracy check.
  document.getElementById('gpa-add')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const r = await fetch('/api/gpa/courses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        year: f.get('year'), name: f.get('name'),
        final_pct: f.get('final_pct'), level: f.get('level'), credits: f.get('credits'),
      }),
    });
    if (r.ok) location.reload();
  });

  document.querySelectorAll('[data-gpa-delete]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const r = await fetch(`/api/gpa/courses/${btn.dataset.gpaDelete}`, { method: 'DELETE' });
      if (r.ok) location.reload();
    });
  });

  document.querySelectorAll('[data-gpa-level]').forEach((sel) => {
    sel.addEventListener('change', async () => {
      const r = await fetch('/api/gpa/level', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: sel.dataset.gpaLevel, level: sel.value }),
      });
      if (r.ok) location.reload();
    });
  });

  document.getElementById('official-save')?.addEventListener('click', async () => {
    const val = document.getElementById('official-gpa').value;
    const r = await fetch('/api/gpa/official', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ official: val }),
    });
    if (r.ok) location.reload();
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
