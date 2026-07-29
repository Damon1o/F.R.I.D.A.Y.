// Spec U — web button-to-talk. Browser-side STT (Web Speech API) feeds the existing
// chat form; browser-side TTS speaks F.R.I.D.A.Y.'s replies. No server audio path,
// no binaries, no bearer token — this is the laptop-testable voice loop.
(function () {
  var btn = document.getElementById('friday-voice');
  var input = document.getElementById('friday-text');
  var form = document.getElementById('friday-form');
  if (!btn || !input || !form) return;

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;              // unsupported browser: leave the mic button hidden
  btn.hidden = false;

  var rec = new SR();
  rec.lang = 'en-US';
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  var listening = false;

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

  function speak(text) {
    if (!text || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    var utt = new SpeechSynthesisUtterance(text);
    if (voice) utt.voice = voice;
    utt.rate = 0.95;
    utt.pitch = 0.9;
    window.speechSynthesis.speak(utt);
  }

  // Speak each assistant reply once it finishes streaming (bubble stops being pending).
  var list = document.getElementById('friday-messages');
  if (list && window.MutationObserver) {
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        if (m.type === 'attributes' && m.target.classList &&
          m.target.classList.contains('assistant') &&
          !m.target.classList.contains('is-pending')) {
          speak(m.target.textContent);
        }
      });
    }).observe(list, { subtree: true, attributes: true, attributeFilter: ['class'] });
  }

  rec.onresult = function (e) {
    var transcript = e.results[0][0].transcript;
    input.value = transcript;
    form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit', { cancelable: true }));
  };
  rec.onend = function () { listening = false; btn.classList.remove('is-live'); };
  rec.onerror = function () { listening = false; btn.classList.remove('is-live'); };

  btn.addEventListener('click', function () {
    if (listening) { rec.stop(); return; }
    try { rec.start(); listening = true; btn.classList.add('is-live'); }
    catch (err) { /* already started */ }
  });
})();
