// Skills page: toggle and delete move into the right-click menu. The forms stay
// in the DOM and only hide once this runs, so the page still works without JS.
(function () {
  var list = document.getElementById('skills-list');
  var add = document.getElementById('skill-add');
  if (!list) return;

  list.querySelectorAll('form[data-toggle], form[data-delete]').forEach(function (f) {
    f.hidden = true;
  });

  // The card, not the list: a full <ul> leaves no empty pixel to right-click, so
  // "New skill" would only ever appear on an empty list.
  window.ctxMenu.bind(list.closest('.card'), function (target) {
    var li = target.closest('li[data-enabled]');
    if (!li) {
      return [{ label: 'New skill', run: function () { add.querySelector('[name=name]').focus(); } }];
    }
    return [
      {
        label: li.dataset.enabled === '1' ? 'Disable' : 'Enable',
        run: function () { li.querySelector('form[data-toggle]').requestSubmit(); },
      },
      {
        label: 'Delete', danger: true,
        run: function () { li.querySelector('form[data-delete]').requestSubmit(); },
      },
    ];
  });
})();
