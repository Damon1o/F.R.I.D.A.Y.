// Theme + density: persist to localStorage, fall back to OS preference.
// Not deferred on purpose — both attributes must land before first paint.
(function () {
  var root = document.documentElement;
  var saved = localStorage.getItem('friday-theme');
  if (!saved) {
    saved = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  root.setAttribute('data-theme', saved);

  // Spec AH — compact rescales the spacing tokens only; component CSS is unchanged.
  var density = localStorage.getItem('friday-density') || 'comfortable';
  root.setAttribute('data-density', density);
  document.querySelectorAll('[data-density-set]').forEach(function (b) {
    b.setAttribute('aria-pressed', String(b.dataset.densitySet === density));
  });

  document.addEventListener('click', function (e) {
    if (e.target.closest('#theme-toggle')) {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('friday-theme', next);
      return;
    }
    var densityBtn = e.target.closest('[data-density-set]');
    if (!densityBtn) return;
    var value = densityBtn.dataset.densitySet;
    root.setAttribute('data-density', value);
    localStorage.setItem('friday-density', value);
    document.querySelectorAll('[data-density-set]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.densitySet === value));
    });
  });
})();
