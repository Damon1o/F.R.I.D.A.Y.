// Shared drag-to-reorder. Native HTML5 drag and drop — no library, no pointer
// math. The dragged node moves in the DOM as you go, so the list you see while
// dragging is already the list that gets saved.
//
//   window.dragSort(container, 'li[data-id]', function (ids) { ... })
//
// onDrop gets the ids (data-id or data-card) in their new order, and only fires
// when the order actually changed. An item containing a [data-grip] element is
// only draggable from that grip — cards hold inputs and buttons that still need
// to take a plain mousedown.
(function () {
  function ids(container, selector) {
    return Array.prototype.map.call(
      container.querySelectorAll(selector),
      function (el) { return el.dataset.id || el.dataset.card; }
    );
  }

  window.dragSort = function (container, selector, onDrop) {
    if (!container) return;
    var dragging = null;
    var before = null;

    Array.prototype.forEach.call(container.querySelectorAll(selector), function (el) {
      var grip = el.querySelector('[data-grip]');
      if (!grip) { el.draggable = true; return; }
      grip.addEventListener('mousedown', function () { el.draggable = true; });
      grip.addEventListener('touchstart', function () { el.draggable = true; }, { passive: true });
      el.addEventListener('mouseup', function () { el.draggable = false; });
    });

    container.addEventListener('dragstart', function (e) {
      var el = e.target.closest(selector);
      if (!el || !container.contains(el)) return;
      dragging = el;
      before = ids(container, selector).join();
      el.classList.add('is-dragging');
      e.dataTransfer.effectAllowed = 'move';
      // Firefox refuses to start a drag without payload; the id is unused.
      e.dataTransfer.setData('text/plain', el.dataset.id || '');
    });

    container.addEventListener('dragover', function (e) {
      if (!dragging) return;
      e.preventDefault();
      var over = e.target.closest(selector);
      if (!over || over === dragging) return;
      // Past the midpoint means the pointer wants the slot after this row.
      var box = over.getBoundingClientRect();
      var vertical = box.height >= box.width;
      var past = vertical
        ? e.clientY > box.top + box.height / 2
        : e.clientX > box.left + box.width / 2;
      over.parentNode.insertBefore(dragging, past ? over.nextSibling : over);
    });

    container.addEventListener('dragend', function () {
      if (!dragging) return;
      dragging.classList.remove('is-dragging');
      if (dragging.querySelector('[data-grip]')) dragging.draggable = false;
      dragging = null;
      var after = ids(container, selector);
      if (after.join() !== before) onDrop(after);
    });
  };
})();
