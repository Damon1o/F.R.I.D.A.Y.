// Spec U — web button-to-talk. Two interchangeable engines behind one mic button:
//
//   default            Web Speech API. Zero setup, but Chrome routes mic audio through
//                      Google's servers, so it needs the network.
//   `voice_offline` on whisper.cpp + piper via /api/voice/stt and /api/voice/tts. Nothing
//                      leaves the origin. Needs the vendor/voice/ binaries; local dev only.
//
// Either way STT fills #friday-text and submits the normal chat form, and TTS speaks the
// finished reply — the chat path (friday.js -> POST /api/friday/message) is untouched.
(function () {
  var btn = document.getElementById('friday-voice');
  var input = document.getElementById('friday-text');
  var form = document.getElementById('friday-form');
  if (!btn || !input || !form) return;

  var RATE = 16000;
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  // The native desktop window runs on WebView2. It exposes webkitSpeechRecognition but the
  // service behind it is Chrome-only, so dictation there goes to the bundled whisper/piper
  // engine instead — which is local anyway, and needs no network.
  var native = document.body.classList.contains('native-app');
  var offline = native || !SR;
  var listening = false;
  var rec = null;

  if (SR) {
    rec = new SR();
    rec.lang = 'en-US';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = function (e) { submitTranscript(e.results[0][0].transcript); };
    rec.onend = rec.onerror = function () { listening = false; btn.classList.remove('is-live'); };
    btn.hidden = false;
  }

  // Offline mode failing mid-flow must not kill voice outright: drop back to Web Speech and
  // say so once, instead of one console line per utterance.
  var warned = false;

  function offlineFailed(err) {
    offline = false;
    if (warned) return;
    warned = true;
    console.warn('offline voice unavailable, falling back to Web Speech:', err);
  }

  function submitTranscript(text) {
    text = (text || '').trim();
    if (!text) return;
    input.value = text;
    form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit', { cancelable: true }));
  }

  // ---- speaking ----------------------------------------------------------------

  // SpeechSynthesis can only use voices the OS ships — it cannot load piper's
  // en_GB-alan-medium.onnx. Closest stand-in: an en-GB male voice, slowed and
  // pitched down to sit near alan. Names differ per platform, so try in order.
  var VOICE_PREFS = [/Ryan/i, /Google UK English Male/i, /Daniel/i, /Arthur/i, /George/i];
  var voice = null;

  function pickVoice() {
    var gb = window.speechSynthesis.getVoices().filter(function (v) {
      return /^en[-_]GB/i.test(v.lang);
    });
    var best = null;
    VOICE_PREFS.forEach(function (re) {
      if (!best) best = gb.filter(function (v) { return re.test(v.name); })[0];
    });
    voice = best || gb[0] || null;   // any en-GB beats the default en-US
  }

  if (window.speechSynthesis) {
    pickVoice();                                        // populated already in Firefox/Safari
    window.speechSynthesis.onvoiceschanged = pickVoice; // Chrome loads the list async
  }

  // Mobile (iOS Safari, Android Chrome) refuses speak() unless synthesis was first started
  // inside a user gesture. Replies are spoken from a MutationObserver, which never is — so
  // prime the engine with a silent utterance on the first touch/click and it stays unlocked.
  if (window.speechSynthesis) {
    var unlock = function () {
      document.removeEventListener('touchend', unlock, true);
      document.removeEventListener('click', unlock, true);
      var u = new SpeechSynthesisUtterance(' ');
      u.volume = 0;
      window.speechSynthesis.speak(u);
    };
    document.addEventListener('touchend', unlock, true);
    document.addEventListener('click', unlock, true);
  }

  // Both engines spell dotted acronyms out letter by letter ("F. R. I. D. A. Y."). Strip the
  // dots so they're read as a word, with a map for the ones that still come out wrong.
  var SAY_AS = { FRIDAY: 'Friday', EG: 'for example', IE: 'that is', ETC: 'etcetera' };

  function sayable(text) {
    return String(text || '').replace(/\b(?:[A-Za-z]\.){2,}[A-Za-z]?\b/g, function (m) {
      var word = m.replace(/\./g, '');
      return SAY_AS[word.toUpperCase()] || word;
    });
  }

  function speak(text, done) {
    text = sayable(text);
    if (!text) { if (done) done(); return; }
    offline ? speakOffline(text, done) : speakWeb(text, done);
  }

  function speakWeb(text, done) {
    if (!window.speechSynthesis) { if (done) done(); return; }
    window.speechSynthesis.cancel();
    window.speechSynthesis.resume();   // iOS parks the queue paused after a background/cancel
    var utt = new SpeechSynthesisUtterance(text);
    if (voice) utt.voice = voice;
    utt.rate = 0.95;
    utt.pitch = 0.9;
    // onerror too: a failed utterance must not strand the wake-word flow mid-chain.
    if (done) utt.onend = utt.onerror = function () { done(); };
    window.speechSynthesis.speak(utt);
  }

  // Interrupt — stop button, Esc, or voice barge-in. Cuts the reply mid-sentence on
  // either engine. Silent when nothing is speaking, so callers needn't check first.
  function stopSpeaking() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (player) { player.pause(); player = null; }
    window.fridaySpeaking = false;
  }

  window.addEventListener('friday-interrupt', stopSpeaking);

  var player = null;

  function speakOffline(text, done) {
    if (player) { player.pause(); player = null; }
    fetch('/api/voice/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text })
    })
      .then(function (r) {
        if (!r.ok) throw new Error('tts ' + r.status);
        return r.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        player = new Audio(url);
        player.onended = player.onerror = function () {
          window.fridaySpeaking = false;
          URL.revokeObjectURL(url);
          if (done) done();
        };
        // wakeword.js checks this to avoid waking on F.R.I.D.A.Y.'s own reply;
        // speechSynthesis.speaking is always false on this path.
        window.fridaySpeaking = true;
        player.play();
      })
      .catch(function (err) {
        offlineFailed(err);
        speakWeb(text, done);
      });
  }

  // Speak each assistant reply once it finishes streaming (bubble stops being pending).
  var list = document.getElementById('friday-messages');
  if (list && window.MutationObserver) {
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        if (m.type === 'attributes' && m.target.classList &&
          m.target.classList.contains('assistant') &&
          !m.target.classList.contains('is-pending') &&
          !m.target.classList.contains('is-stopped')) {   // interrupted: don't read it back
          speak(m.target.textContent);
        }
      });
    }).observe(list, { subtree: true, attributes: true, attributeFilter: ['class'] });
  }

  // ---- listening ---------------------------------------------------------------

  function startListening() {
    if (listening) return;
    if (offline) { recordOffline(); return; }
    if (!rec) return;
    try { rec.start(); listening = true; btn.classList.add('is-live'); }
    catch (err) { /* already started */ }
  }

  function stopListening() {
    if (!listening) return;
    if (offline) { if (stopRecord) stopRecord(); return; }
    if (rec) rec.stop();
  }

  // Mirrors scripts/wakeword.py _record/_wav_bytes: 16 kHz mono int16, stop after ~1.2 s of
  // silence, 10 s hard cap. MediaRecorder is deliberately unused — it emits webm/opus, which
  // whisper.cpp cannot read without pulling in ffmpeg.
  var SILENCE_RMS = 500;       // int16 scale, same threshold as the headless listener
  var SILENCE_MS = 1200;
  var MAX_MS = 10000;
  var stopRecord = null;

  function recordOffline() {
    if (!navigator.mediaDevices) { offlineFailed('no mediaDevices'); startListening(); return; }
    navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } }).then(function (stream) {
      var ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: RATE });
      var node = ctx.createScriptProcessor(1024, 1, 1);
      var mute = ctx.createGain();
      var chunks = [], total = 0, quiet = 0, heard = false, cap = null;

      function finish() {
        if (!stopRecord) return;                // already finished
        stopRecord = null;
        clearTimeout(cap);
        node.onaudioprocess = null;
        stream.getTracks().forEach(function (t) { t.stop(); });
        ctx.close();
        listening = false;
        btn.classList.remove('is-live');
        if (!heard) return;                     // silence only: don't bother the server
        upload(wavBytes(chunks, total));
      }

      node.onaudioprocess = function (e) {
        var buf = e.inputBuffer.getChannelData(0);
        var frame = new Int16Array(buf.length);
        var sum = 0;
        for (var i = 0; i < buf.length; i++) {
          var s = Math.max(-1, Math.min(1, buf[i])) * 32767;
          frame[i] = s;
          sum += s * s;
        }
        chunks.push(frame);
        total += frame.length;
        if (Math.sqrt(sum / frame.length) >= SILENCE_RMS) { heard = true; quiet = 0; }
        else quiet += frame.length;
        if (heard && quiet / RATE * 1000 >= SILENCE_MS) finish();
      };

      // A ScriptProcessorNode is only pulled by the graph once it reaches a destination,
      // so route it through a muted gain node (same trick as wakeword.js).
      mute.gain.value = 0;
      ctx.createMediaStreamSource(stream).connect(node);
      node.connect(mute);
      mute.connect(ctx.destination);

      stopRecord = finish;
      listening = true;
      btn.classList.add('is-live');
      cap = setTimeout(finish, MAX_MS);
      ctx.resume();
    }).catch(function (err) {
      offlineFailed(err);
      startListening();                          // retry the same utterance on Web Speech
    });
  }

  function upload(wav) {
    var body = new FormData();
    body.append('audio', new Blob([wav], { type: 'audio/wav' }), 'in.wav');
    fetch('/api/voice/stt', { method: 'POST', body: body })
      .then(function (r) {
        if (!r.ok) throw new Error('stt ' + r.status);
        return r.json();
      })
      .then(function (d) { submitTranscript(d.transcript); })
      .catch(function (err) { offlineFailed(err); startListening(); });
  }

  function wavBytes(chunks, samples) {
    var bytes = samples * 2;
    var buf = new ArrayBuffer(44 + bytes);
    var v = new DataView(buf);
    function str(off, s) { for (var i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i)); }
    str(0, 'RIFF'); v.setUint32(4, 36 + bytes, true); str(8, 'WAVEfmt ');
    v.setUint32(16, 16, true);          // fmt chunk size
    v.setUint16(20, 1, true);           // PCM
    v.setUint16(22, 1, true);           // mono
    v.setUint32(24, RATE, true);
    v.setUint32(28, RATE * 2, true);    // byte rate
    v.setUint16(32, 2, true);           // block align
    v.setUint16(34, 16, true);          // bits per sample
    str(36, 'data'); v.setUint32(40, bytes, true);
    var out = new Int16Array(buf, 44);
    var at = 0;
    chunks.forEach(function (c) { out.set(c, at); at += c.length; });
    return buf;
  }

  // ---- wiring ------------------------------------------------------------------

  btn.addEventListener('click', function () {
    listening ? stopListening() : startListening();
  });

  // Wake-word acknowledgment. wakeword.js calls this instead of clicking the mic, so
  // "Hey F.R.I.D.A.Y." is answered audibly before the mic opens. The 150 ms gap keeps the
  // tail of the spoken ack from bleeding into the transcript.
  window.fridayAck = function () {
    if (listening) return;
    speak('Yes sir.', function () { setTimeout(startListening, 150); });
  };

  function setOffline(on) {
    offline = !!on;
    warned = false;
    if (offline) btn.hidden = false;   // the offline path needs no SpeechRecognition
    else if (!SR) btn.hidden = true;
  }

  window.addEventListener('voice-mode-changed', function (e) { setOffline(e.detail.offline); });

  fetch('/api/settings/ui')
    .then(function (r) { return r.json(); })
    .then(function (prefs) { setOffline(native || !SR || prefs.voice_offline === 'true'); })
    .catch(function () { /* settings unreachable: stay on Web Speech */ });
})();
