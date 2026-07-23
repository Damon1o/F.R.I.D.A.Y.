// Theme toggle: persist to localStorage, fall back to OS preference.
(function () {
  var root = document.documentElement;
  var saved = localStorage.getItem('friday-theme');
  if (!saved) {
    saved = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  root.setAttribute('data-theme', saved);

  document.addEventListener('click', function (e) {
    if (!e.target.closest('#theme-toggle')) return;
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    localStorage.setItem('friday-theme', next);
  });
})();
