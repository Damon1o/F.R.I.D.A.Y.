// Magnet (React Bits) ported to vanilla: widget containers drift toward the
// pointer when it comes within PADDING of them. No wrapper element — the
// transform goes straight on the card, CSS owns the easing (see 20c in app.css).
(function () {
  var SELECTOR = '.card, .widget, .metric';
  var PADDING = 50;      // pull starts this far outside the card
  var STRENGTH = 24;     // higher = less movement (cards are big, so > React's 2)

  if (matchMedia('(pointer: coarse)').matches ||
    matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  // Chrome stays put: the nav rail, the topbar and the dashboard status strip
  // are navigation/reference surfaces — drifting text is harder to read and aim at.
  var EXCLUDE = '.rail, .topbar, .widget-bar';

  var cards = [].slice.call(document.querySelectorAll(SELECTOR))
    .filter(function (c) { return !c.closest(EXCLUDE); });
  if (!cards.length) return;
  cards.forEach(function (c) { c.classList.add('is-magnet'); });

  var queued = false, ev = null;

  function apply() {
    queued = false;
    cards.forEach(function (card) {
      var r = card.getBoundingClientRect();
      var dx = ev.clientX - (r.left + r.width / 2);
      var dy = ev.clientY - (r.top + r.height / 2);
      var pulled = Math.abs(dx) < r.width / 2 + PADDING &&
        Math.abs(dy) < r.height / 2 + PADDING;
      card.classList.toggle('is-pulled', pulled);
      card.style.setProperty('--mag-x', (pulled ? dx / STRENGTH : 0) + 'px');
      card.style.setProperty('--mag-y', (pulled ? dy / STRENGTH : 0) + 'px');
    });
  }

  // rAF-throttled: one layout read pass per frame, not per mousemove.
  addEventListener('mousemove', function (e) {
    ev = e;
    if (queued) return;
    queued = true;
    requestAnimationFrame(apply);
  }, { passive: true });
})();
