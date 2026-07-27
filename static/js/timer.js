// Timer widget: presets, custom minutes, countdown with beep, localStorage persistence
(function () {
  var STORAGE_KEY = 'friday_timer_state';

  var displayEl = document.querySelector('[data-timer-display]');
  var presetBtns = document.querySelectorAll('.btn-preset');
  var customInput = document.getElementById('timer-custom-min');
  var setCustomBtn = document.getElementById('timer-set-custom');
  var startBtn = document.getElementById('timer-start');
  var pauseBtn = document.getElementById('timer-pause');
  var resetBtn = document.getElementById('timer-reset');

  var totalSeconds = 0;
  var remaining = 0;
  var intervalId = null;
  var isRunning = false;
  var audioCtx = null;

  function fmt(sec) {
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function render() {
    if (displayEl) displayEl.textContent = fmt(remaining);
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        total: totalSeconds,
        remaining: remaining,
        running: isRunning,
        ts: Date.now()
      }));
    } catch (e) {}
  }

  function load() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      var s = JSON.parse(raw);
      // If timer was running, adjust remaining for elapsed time
      var elapsed = Math.floor((Date.now() - s.ts) / 1000);
      if (s.running && s.remaining > 0) {
        s.remaining = Math.max(0, s.remaining - elapsed);
        s.running = s.remaining > 0;
      }
      totalSeconds = s.total || 0;
      remaining = s.remaining || 0;
      isRunning = s.running || false;
      return true;
    } catch (e) { return false; }
  }

  function beep() {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      var osc = audioCtx.createOscillator();
      var gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.value = 880;
      gain.gain.value = 0.1;
      osc.connect(gain).connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.6);
    } catch (e) {}
  }

  function start() {
    if (remaining <= 0) return;
    isRunning = true;
    startBtn.hidden = true;
    pauseBtn.hidden = false;
    intervalId = setInterval(function () {
      remaining--;
      render();
      save();
      if (remaining <= 0) {
        stop();
        beep();
      }
    }, 1000);
    save();
  }

  function pause() {
    isRunning = false;
    clearInterval(intervalId);
    intervalId = null;
    startBtn.hidden = false;
    pauseBtn.hidden = true;
    save();
  }

  function stop() {
    isRunning = false;
    clearInterval(intervalId);
    intervalId = null;
    startBtn.hidden = false;
    pauseBtn.hidden = true;
  }

  function reset() {
    stop();
    remaining = totalSeconds;
    render();
    save();
  }

  function setPreset(min) {
    totalSeconds = min * 60;
    remaining = totalSeconds;
    render();
    presetBtns.forEach(function (b) {
      b.classList.toggle('is-active', Number(b.dataset.min) === min);
    });
    customInput.value = '';
    save();
  }

  function setCustom() {
    var m = parseInt(customInput.value, 10);
    if (!m || m < 1 || m > 1440) return;
    setPreset(m);
  }

  // Init
  load();
  render();

  if (isRunning && remaining > 0) start();

  presetBtns.forEach(function (b) {
    b.addEventListener('click', function () { setPreset(Number(b.dataset.min)); });
  });

  setCustomBtn.addEventListener('click', setCustom);
  customInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') setCustom(); });

  startBtn.addEventListener('click', start);
  pauseBtn.addEventListener('click', pause);
  resetBtn.addEventListener('click', reset);

  // Sync across tabs
  window.addEventListener('storage', function (e) {
    if (e.key === STORAGE_KEY) {
      load();
      render();
      if (isRunning && remaining > 0) start();
      else stop();
    }
  });
})();