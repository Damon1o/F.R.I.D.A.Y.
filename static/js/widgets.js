// Dashboard widgets: live clock + weather fetch
(function () {
  // ---- Live clock ----
  var clockEl = document.querySelector('[data-clock]');
  var clock24 = true;
  try { clock24 = localStorage.getItem('friday_clock24') !== 'false'; } catch (e) { /* default 24h */ }

  function tick() {
    var now = new Date();
    var h = now.getHours();
    var suffix = '';
    if (!clock24) {
      suffix = h < 12 ? ' AM' : ' PM';
      h = h % 12 || 12;
    }
    var m = String(now.getMinutes()).padStart(2, '0');
    var s = String(now.getSeconds()).padStart(2, '0');
    if (clockEl) clockEl.textContent = String(h).padStart(2, '0') + ':' + m + ':' + s + suffix;
  }
  tick();
  setInterval(tick, 1000);

  // First visit has no localStorage copy yet — take the server's answer.
  fetch('/api/settings/ui', { credentials: 'same-origin' })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      clock24 = d.clock_24h !== 'false';
      try { localStorage.setItem('friday_clock24', String(clock24)); } catch (e) { /* ignore */ }
      tick();
    })
    .catch(function () { /* keep default */ });

  window.addEventListener('storage', function (e) {
    if (e.key === 'friday_clock24') { clock24 = e.newValue !== 'false'; tick(); }
  });

  // ---- Weather ----
  var tempEl = document.querySelector('[data-weather-temp]');
  var condEl = document.querySelector('[data-weather-cond]');
  var locEl = document.querySelector('[data-weather-loc]');
  var rangeEl = document.querySelector('[data-weather-range]');

  function unitLabel() {
    try {
      return localStorage.getItem('friday_units') === 'imperial' ? '°F' : '°C';
    } catch (e) { return '°C'; }
  }

  function loadWeather() {
    fetch('/api/weather', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) {
          if (tempEl) tempEl.textContent = '—';
          if (condEl) condEl.textContent = d.error;
          if (locEl) locEl.textContent = '';
          if (rangeEl) rangeEl.style.display = 'none';
          return;
        }
        var u = unitLabel();
        if (tempEl && d.current && d.current.temp != null) {
          tempEl.textContent = Math.round(d.current.temp) + u;
        }
        if (condEl && d.current) {
          condEl.textContent = d.current.conditions || '—';
        }
        if (locEl) {
          locEl.textContent = d.location || '';
        }
        if (rangeEl && d.forecast && d.forecast[0]) {
          var today = d.forecast[0];
          if (today.hi != null && today.lo != null) {
            rangeEl.textContent = 'Today: ' + Math.round(today.hi) + u + ' / ' + Math.round(today.lo) + u;
            rangeEl.style.display = 'flex';
          } else {
            rangeEl.style.display = 'none';
          }
        }
      })
      .catch(function () {
        if (tempEl) tempEl.textContent = '—';
        if (condEl) condEl.textContent = 'Unavailable';
      });
  }

  loadWeather();
  // Refresh every 10 minutes
  setInterval(loadWeather, 10 * 60 * 1000);

  // Listen for unit changes from settings
  window.addEventListener('storage', function (e) {
    if (e.key === 'friday_units') loadWeather();
  });
})();