// "Hey F.R.I.D.A.Y." wake word, in-browser. openWakeWord pipeline, three ONNX models
// run through self-hosted onnxruntime-web (no CDN, no server audio path):
//
//   mic @16kHz -> 1280-sample chunk (+480 samples of context)
//     -> melspectrogram.onnx  -> 8 mel frames x 32
//     -> embedding_model.onnx -> 96-float embedding (needs the last 76 mel frames)
//     -> hey_friday.onnx      -> score (needs the last 16 embeddings)
//
// On/off is the `wake_word` setting (Settings > F.R.I.D.A.Y. Panel), so it persists
// across devices. Sensitivity is a local knob in localStorage.
(function () {
  var ORT = '/static/vendor/ort/';
  var MODELS = '/static/vendor/wakeword/';
  var COOLDOWN_MS = 3000;      // ignore detections right after one fires
  // Barge-in: talking over F.R.I.D.A.Y. cuts her off and opens the mic. The stream below
  // is captured with echo cancellation on, so her own voice is subtracted out and what's
  // left above this threshold is the room — i.e. you. Sustained, so a cough can't do it.
  var BARGE_RMS = 1500;        // int16 scale, same units as the wake-word pipeline
  var BARGE_MS = 350;

  var mic = document.getElementById('friday-voice');
  if (!mic || !navigator.mediaDevices) return;

  var threshold = parseFloat(localStorage.getItem('friday_wake_threshold')) || 0.5;
  var running = false, starting = false, ctx = null, stream = null, lastFire = 0;

  // onnxruntime is ~1 MB of JS. Load it the first time the wake word actually
  // turns on instead of on every page view.
  function loadOrt() {
    if (window.ort) return Promise.resolve();
    if (loadOrt.pending) return loadOrt.pending;
    loadOrt.pending = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = ORT + 'ort.wasm.min.js';
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return loadOrt.pending;
  }

  async function build() {
    await loadOrt();
    // Single-threaded so the page needs no COOP/COEP cross-origin isolation headers.
    ort.env.wasm.wasmPaths = ORT;
    ort.env.wasm.numThreads = 1;
    var opts = { executionProviders: ['wasm'] };
    return {
      mel: await ort.InferenceSession.create(MODELS + 'melspectrogram.onnx', opts),
      emb: await ort.InferenceSession.create(MODELS + 'embedding_model.onnx', opts),
      ww: await ort.InferenceSession.create(MODELS + 'hey_friday.onnx', opts)
    };
  }

  async function start() {
    if (running || starting) return;
    starting = true;
    try {
      var m = await build();
      // Ask for raw-ish audio: the models were trained on unprocessed mic input, and
      // noise suppression / AGC chew up the quiet leading "hey" badly enough to miss it.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: false }
      });
      ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      var src = ctx.createMediaStreamSource(stream);
      var node = ctx.createScriptProcessor(1024, 1, 1);

      var pending = [];                       // raw samples not yet formed into a 1280 chunk
      var ctxTail = new Float32Array(480);    // 3 mel frames of lookback the mel model consumes
      var melBuf = [];                        // last >=76 mel frames, 32 floats each
      var featBuf = [];                       // last 16 embeddings, 96 floats each
      var busy = false;

      var bargeMs = 0;

      function speaking() {
        return !!window.fridaySpeaking ||
          !!(window.speechSynthesis && window.speechSynthesis.speaking);
      }

      // Called on every audio frame; only does anything while she's talking.
      function bargeIn(rms, samples) {
        if (!speaking() || mic.classList.contains('is-live')) { bargeMs = 0; return; }
        bargeMs = rms >= BARGE_RMS ? bargeMs + samples / 16 : 0;   // 16 samples per ms @ 16 kHz
        if (bargeMs < BARGE_MS) return;
        bargeMs = 0;
        featBuf = [];                       // the interruption isn't a wake word
        if (window.fridayStop) window.fridayStop();
        setTimeout(function () { mic.click(); }, 150);   // then listen for the rest of it
      }

      node.onaudioprocess = function (e) {
        var input = e.inputBuffer.getChannelData(0);
        var sum = 0;
        for (var i = 0; i < input.length; i++) {
          var s = input[i] * 32767;         // models want int16 scale
          pending.push(s);
          sum += s * s;
        }
        bargeIn(Math.sqrt(sum / input.length), input.length);
        while (pending.length >= 1280 && !busy) {
          busy = true;
          step(pending.splice(0, 1280))
            .catch(function () { /* drop the frame, keep listening */ })
            .then(function () { busy = false; });
        }
      };

      async function step(chunk) {
        var audio = new Float32Array(1760);   // 480 context + 1280 new
        audio.set(ctxTail, 0);
        audio.set(chunk, 480);
        ctxTail = audio.slice(-480);

        var mel = await m.mel.run({ input: new ort.Tensor('float32', audio, [1, 1760]) });
        var md = mel.output.data;             // 8 frames x 32, flattened
        for (var f = 0; f < md.length / 32; f++) {
          var frame = new Float32Array(32);
          for (var b = 0; b < 32; b++) frame[b] = md[f * 32 + b] / 10 + 2; // openWakeWord's scaling
          melBuf.push(frame);
        }
        if (melBuf.length > 76) melBuf = melBuf.slice(-76);
        if (melBuf.length < 76) return;

        var flat = new Float32Array(76 * 32);
        melBuf.forEach(function (fr, i) { flat.set(fr, i * 32); });
        var emb = await m.emb.run({ input_1: new ort.Tensor('float32', flat, [1, 76, 32, 1]) });
        featBuf.push(emb.conv2d_19.data);
        if (featBuf.length > 16) featBuf = featBuf.slice(-16);
        if (featBuf.length < 16) return;

        var feats = new Float32Array(16 * 96);
        featBuf.forEach(function (v, i) { feats.set(v, i * 96); });
        var out = await m.ww.run({ embeddings: new ort.Tensor('float32', feats, [1, 16, 96]) });
        var score = out.score.data[0];
        window.dispatchEvent(new CustomEvent('wake-score', { detail: { score: score } }));
        if (score >= threshold) fire();
      }

      function fire() {
        var now = Date.now();
        // Don't retrigger mid-utterance, and don't wake on F.R.I.D.A.Y.'s own reply.
        if (now - lastFire < COOLDOWN_MS) return;
        if (window.fridaySpeaking) return;   // offline TTS: speechSynthesis.speaking stays false
        if (window.speechSynthesis && window.speechSynthesis.speaking) return;
        if (mic.classList.contains('is-live')) return;
        lastFire = now;
        featBuf = [];   // clear so the same utterance can't score twice
        // voice-web.js answers "Yes sir" then opens the mic itself. It bails early on
        // browsers with no SpeechRecognition, so fall back to the plain mic click.
        window.fridayAck ? window.fridayAck() : mic.click();
      }

      // A ScriptProcessorNode is only pulled by the graph once it reaches a destination,
      // so route it through a muted gain node. Without this, onaudioprocess never fires.
      var mute = ctx.createGain();
      mute.gain.value = 0;
      src.connect(node);
      node.connect(mute);
      mute.connect(ctx.destination);
      running = true;
      ctx.resume().then(function () { console.info('wake word: ' + ctx.state); });
    } catch (err) {
      console.error('wake word: start failed', err);
      stop();
    } finally {
      starting = false;
    }
  }

  function stop() {
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    if (ctx) ctx.close();
    stream = ctx = null;
    running = false;
  }

  var wakeWordEnabled = false;

  window.addEventListener('wake-pref-changed', function (e) {
    wakeWordEnabled = !!e.detail.enabled;
    wakeWordEnabled ? start() : stop();
  });
  window.addEventListener('wake-threshold-changed', function (e) { threshold = e.detail.value; });

  // A page loaded without a user gesture gets a suspended AudioContext, and a suspended
  // context never pumps onaudioprocess — so nothing is ever scored. Retry the resume on
  // every gesture until it actually takes; the settings page only appeared to work
  // because flipping the toggle *is* the gesture.
  ['click', 'keydown', 'touchstart'].forEach(function (evt) {
    document.addEventListener(evt, function () {
      if (!wakeWordEnabled) return;
      if (!running) start();
      else if (ctx && ctx.state !== 'running') ctx.resume();
    }, { capture: true });
  });

  fetch('/api/settings/ui')
    .then(function (r) { return r.json(); })
    .then(function (prefs) {
      wakeWordEnabled = prefs.wake_word === 'true';
      if (wakeWordEnabled) start();
    })
    .catch(function () { /* settings unreachable: stay off */ });
})();
