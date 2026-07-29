// TargetCursor (React Bits) ported to vanilla: spinning bracket cursor that snaps
// its four corners onto whatever interactive element is hovered. GSAP is replaced
// by one rAF lerp loop + CSS (no new dependency, no external request).
(function () {
  var TARGETS = '.cursor-target, button, a[href], .item, .rail-link';
  var CORNER = 12;   // corner box size, matches .target-cursor-corner
  var BORDER = 3;    // corner border width
  var EASE = 0.22;   // per-frame lerp toward the pointer

  var coarse = matchMedia('(pointer: coarse)').matches || innerWidth <= 768;
  if (coarse || matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var wrap = document.createElement('div');
  wrap.className = 'target-cursor';
  wrap.setAttribute('aria-hidden', 'true');
  var spin = document.createElement('div');
  spin.className = 'target-cursor-spin';
  spin.innerHTML =
    '<i class="target-cursor-dot"></i>' +
    '<i class="target-cursor-corner corner-tl"></i>' +
    '<i class="target-cursor-corner corner-tr"></i>' +
    '<i class="target-cursor-corner corner-br"></i>' +
    '<i class="target-cursor-corner corner-bl"></i>';
  wrap.appendChild(spin);
  document.body.appendChild(wrap);
  document.documentElement.classList.add('has-target-cursor');

  var corners = spin.querySelectorAll('.target-cursor-corner');
  var mouse = { x: innerWidth / 2, y: innerHeight / 2 };
  var pos = { x: mouse.x, y: mouse.y };
  var locked = null;   // element the corners are wrapped around

  function cornerPoints(rect) {
    return [
      { x: rect.left - BORDER, y: rect.top - BORDER },
      { x: rect.right + BORDER - CORNER, y: rect.top - BORDER },
      { x: rect.right + BORDER - CORNER, y: rect.bottom + BORDER - CORNER },
      { x: rect.left - BORDER, y: rect.bottom + BORDER - CORNER },
    ];
  }

  function frame() {
    pos.x += (mouse.x - pos.x) * EASE;
    pos.y += (mouse.y - pos.y) * EASE;
    wrap.style.transform = 'translate(' + pos.x + 'px, ' + pos.y + 'px)';
    if (locked) {
      // Corners live inside the cursor, so they chase absolute page coordinates
      // minus wherever the cursor currently is.
      cornerPoints(locked.getBoundingClientRect()).forEach(function (p, i) {
        corners[i].style.transform =
          'translate(' + (p.x - pos.x) + 'px, ' + (p.y - pos.y) + 'px)';
      });
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  addEventListener('mousemove', function (e) { mouse.x = e.clientX; mouse.y = e.clientY; });

  function release() {
    locked = null;
    wrap.classList.remove('is-locked');
    corners.forEach(function (c) { c.style.transform = ''; });
  }

  addEventListener('mouseover', function (e) {
    var target = e.target.closest ? e.target.closest(TARGETS) : null;
    if (target === locked) return;
    if (!target) return release();
    locked = target;
    wrap.classList.add('is-locked');
  }, { passive: true });

  // A scroll or a removed node can strand the corners on nothing.
  addEventListener('scroll', function () {
    if (locked && !locked.isConnected) release();
  }, { passive: true });

  addEventListener('mousedown', function () { wrap.classList.add('is-down'); });
  addEventListener('mouseup', function () { wrap.classList.remove('is-down'); });
  addEventListener('blur', release);
})();
