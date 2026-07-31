(function () {
  function build(select) {
    const wrap = document.createElement('div');
    wrap.className = 'select';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'select-btn';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    if (select.getAttribute('aria-label')) button.setAttribute('aria-label', select.getAttribute('aria-label'));
    const label = document.createElement('span');
    label.className = 'select-label';
    button.append(label);
    const caret = document.createElement('span');
    caret.className = 'select-caret';
    caret.setAttribute('aria-hidden', 'true');
    button.append(caret);

    const list = document.createElement('div');
    list.className = 'select-menu';
    list.setAttribute('role', 'listbox');
    list.hidden = true;

    const rows = [];
    Array.from(select.children).forEach((node) => {
      const options = node.tagName === 'OPTGROUP' ? Array.from(node.children) : [node];
      if (node.tagName === 'OPTGROUP') {
        const head = document.createElement('p');
        head.className = 'select-group label-mono';
        head.textContent = node.label;
        list.append(head);
      }
      options.forEach((option) => {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'select-option';
        row.setAttribute('role', 'option');
        row.dataset.value = option.value;
        row.textContent = option.textContent;
        row.addEventListener('click', () => pick(option.value));
        list.append(row);
        rows.push(row);
      });
    });

    function sync() {
      const option = select.selectedOptions[0];
      label.textContent = option ? option.textContent : '';
      rows.forEach((r) => {
        const on = r.dataset.value === select.value;
        r.classList.toggle('is-on', on);
        r.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    }

    function open(state) {
      list.hidden = !state;
      wrap.classList.toggle('is-open', state);
      button.setAttribute('aria-expanded', state ? 'true' : 'false');
      if (state) (rows.find((r) => r.classList.contains('is-on')) || rows[0])?.focus();
    }

    function pick(value) {
      select.value = value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      sync();
      open(false);
      button.focus();
    }

    button.addEventListener('click', () => open(list.hidden));
    // Arrow keys move between rows; Escape closes without changing anything.
    list.addEventListener('keydown', (e) => {
      const i = rows.indexOf(document.activeElement);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        rows[(i + (e.key === 'ArrowDown' ? 1 : rows.length - 1)) % rows.length].focus();
      } else if (e.key === 'Escape') {
        open(false);
        button.focus();
      }
    });
    document.addEventListener('click', (e) => {
      if (!wrap.contains(e.target)) open(false);
    });
    select.addEventListener('change', sync);

    select.parentNode.insertBefore(wrap, select);
    wrap.append(button, list, select);
    select.classList.add('select-native');
    sync();
  }

  document.querySelectorAll('select[data-select]').forEach(build);
  // Anything rendered after load (the quiz player) opts in the same way.
  window.enhanceSelects = (root) =>
    (root || document).querySelectorAll('select[data-select]:not(.select-native)').forEach(build);
})();
