// SAT Prep: pull a generated set, play it one question at a time, grade server-side.
(function () {
  const start = document.getElementById('sat-start');
  const status = document.getElementById('sat-status');
  const quiz = document.getElementById('sat-quiz');
  if (!start) return;

  let set = [];        // questions from the last generate call
  let at = 0;          // index of the one on screen

  const esc = (s) => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };

  function render() {
    const q = set[at];
    quiz.hidden = false;
    quiz.innerHTML = `
      <div class="card-head">
        <h2>${esc(q.skill)}</h2>
        <span class="tag label-mono">${at + 1} / ${set.length} · ${esc(q.difficulty)}</span>
      </div>
      ${q.stimulus ? `<p class="sat-stimulus">${esc(q.stimulus)}</p>` : ''}
      <p class="sat-prompt">${esc(q.prompt)}</p>
      <div class="sat-choices">
        ${q.choices.map((c, i) => `
          <button class="sat-choice" type="button" data-letter="${'ABCD'[i]}">
            <span class="sat-letter label-mono">${'ABCD'[i]}</span>
            <span>${esc(c)}</span>
          </button>`).join('')}
      </div>
      <div class="sat-verdict" id="sat-verdict" hidden></div>`;
    quiz.querySelectorAll('.sat-choice').forEach((b) => {
      b.addEventListener('click', () => grade(b.dataset.letter));
    });
  }

  async function grade(letter) {
    const buttons = quiz.querySelectorAll('.sat-choice');
    buttons.forEach((b) => { b.disabled = true; });
    const r = await fetch('/api/sat/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: set[at].id, chosen: letter }),
    });
    const d = await r.json();
    if (d.error) { buttons.forEach((b) => { b.disabled = false; }); return; }

    buttons.forEach((b) => {
      if (b.dataset.letter === d.answer) b.classList.add('is-right');
      else if (b.dataset.letter === letter) b.classList.add('is-wrong');
    });
    const verdict = document.getElementById('sat-verdict');
    const last = at === set.length - 1;
    verdict.hidden = false;
    verdict.innerHTML = `
      <p class="sat-result">${d.correct ? 'Correct' : `Answer: ${d.answer}`}</p>
      ${d.explanation ? `<p class="subtle">${esc(d.explanation)}</p>` : ''}
      <button class="btn-primary" id="sat-next" type="button">
        ${last ? 'Finish' : 'Next question'}
      </button>`;
    document.getElementById('sat-next').addEventListener('click', () => {
      if (last) {
        // Server-rendered ranking: a reload is the whole progress update.
        location.reload();
        return;
      }
      at += 1;
      render();
    });
  }

  start.addEventListener('click', async () => {
    const [section, skill] = document.getElementById('sat-skill').value.split('|');
    start.disabled = true;
    quiz.hidden = true;
    status.textContent = 'F.R.I.D.A.Y. is writing your questions…';
    try {
      const r = await fetch('/api/sat/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section,
          skill: skill || null,
          difficulty: document.getElementById('sat-difficulty').value,
          count: Number(document.getElementById('sat-count').value),
        }),
      });
      const d = await r.json();
      if (!r.ok || d.error) { status.textContent = d.error || 'Could not write a set.'; return; }
      set = d.questions.map((q) => ({ ...q, difficulty: d.difficulty, skill: d.skill }));
      at = 0;
      status.textContent = `${d.skill} · ${d.domain}`;
      render();
    } catch {
      status.textContent = 'Could not reach F.R.I.D.A.Y.';
    } finally {
      start.disabled = false;
    }
  });

  // ---- Reset stats. Two clicks, no modal: the button arms, then fires. ----
  const reset = document.getElementById('sat-reset');
  reset?.addEventListener('click', async () => {
    const text = reset.querySelector('span');
    if (reset.dataset.armed === '0') {
      reset.dataset.armed = '1';
      text.textContent = 'Erase all stats?';
      setTimeout(() => {
        if (reset.dataset.armed === '1') { reset.dataset.armed = '0'; text.textContent = 'Reset stats'; }
      }, 4000);
      return;
    }
    reset.disabled = true;
    await fetch('/api/sat/reset', { method: 'POST' });
    location.reload();
  });

  // ---- Full-length test ----
  const testStart = document.getElementById('sat-test-start');
  const testStatus = document.getElementById('sat-test-status');
  const player = document.getElementById('sat-test-player');
  const modal = document.getElementById('sat-test-modal');

  // Leaving mid-module is safe: every answer is already on the server and the
  // page reopens on the question you stopped at.
  modal?.addEventListener('close', () => { clearInterval(tick); location.reload(); });
  document.getElementById('sat-test-exit')?.addEventListener('click', () => modal.close());

  let test = null;      // { test_id, module, label, minutes, questions }
  let cursor = 0;
  let deadline = 0;
  let tick = null;

  function clock() {
    const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
    const el = document.getElementById('sat-clock');
    if (el) el.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
    // Out of time ends the module exactly as the real one does: unanswered
    // questions stay unanswered and the next module starts.
    if (left <= 0) { clearInterval(tick); nextModule(); }
  }

  function renderTest() {
    const q = test.questions[cursor];
    if (!q) return;
    if (!modal.open) modal.showModal();
    player.innerHTML = `
      <div class="card-head">
        <h2>${esc(test.label)}</h2>
        <span class="tag label-mono"><span id="sat-clock">--:--</span> · ${cursor + 1} / ${test.questions.length}</span>
      </div>
      ${q.stimulus ? `<p class="sat-stimulus">${esc(q.stimulus)}</p>` : ''}
      <p class="sat-prompt">${esc(q.prompt)}</p>
      <div class="sat-choices">
        ${q.choices.map((c, i) => `
          <button class="sat-choice" type="button" data-letter="${'ABCD'[i]}">
            <span class="sat-letter label-mono">${'ABCD'[i]}</span>
            <span>${esc(c)}</span>
          </button>`).join('')}
      </div>
      <p class="faint">${esc(q.skill)} — answers are scored at the end of the test, not now.</p>`;
    player.querySelectorAll('.sat-choice').forEach((b) => {
      b.addEventListener('click', () => answerTest(b.dataset.letter));
    });
    clock();
    player.scrollTo({ top: 0 });
  }

  async function answerTest(letter) {
    player.querySelectorAll('.sat-choice').forEach((b) => { b.disabled = true; });
    const r = await fetch('/api/sat/test/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: test.questions[cursor].item_id, chosen: letter }),
    });
    const d = await r.json();
    if (d.error) { player.querySelectorAll('.sat-choice').forEach((b) => { b.disabled = false; }); return; }
    if (cursor < test.questions.length - 1) { cursor += 1; renderTest(); return; }
    clearInterval(tick);
    nextModule(d.next_module);
  }

  async function loadModule(testId, module) {
    testStatus.textContent = `Writing ${module}… about two minutes.`;
    const r = await fetch(`/api/sat/test/${testId}/module/${module}`, { method: 'POST' });
    const d = await r.json();
    if (!r.ok || d.error) { testStatus.textContent = d.error || 'Could not build the module.'; return false; }
    test = d;
    cursor = d.questions.findIndex((q) => !q.chosen);
    if (cursor < 0) cursor = 0;
    deadline = Date.now() + d.minutes * 60000;
    clearInterval(tick);
    tick = setInterval(clock, 1000);
    testStatus.textContent = '';
    renderTest();
    return true;
  }

  async function nextModule(known) {
    const order = ['rw1', 'rw2', 'math1', 'math2'];
    const next = known !== undefined ? known
      : (order[order.indexOf(test.module) + 1] || null);
    if (next) { await loadModule(test.test_id, next); return; }
    const r = await fetch(`/api/sat/test/${test.test_id}/finish`, { method: 'POST' });
    const s = await r.json();
    player.innerHTML = `
      <div class="card-head"><h2>Score</h2></div>
      <p class="sat-score">${s.total}</p>
      <ul class="rank-list">
        <li class="rank-row"><span class="rank-name">Reading and Writing</span>
          <span class="rank-val">${s.rw.score} <em class="faint">${s.rw.right_count}/${s.rw.asked}</em></span></li>
        <li class="rank-row"><span class="rank-name">Math</span>
          <span class="rank-val">${s.math.score} <em class="faint">${s.math.right_count}/${s.math.asked}</em></span></li>
      </ul>
      <div class="sat-target">
        <div class="sat-target-bar">
          <span class="sat-target-fill" style="width: ${Math.min(100, (s.total / s.target) * 100)}%"></span>
        </div>
        <p class="subtle">${s.gap ? `${s.gap} points to your ${s.target} target` : `Target ${s.target} cleared`}</p>
      </div>
      <button class="btn-primary" type="button" onclick="location.reload()">Done — see score history</button>`;
  }

  testStart?.addEventListener('click', async () => {
    testStart.disabled = true;
    document.getElementById('sat-quiz').hidden = true;
    if (testStart.dataset.resume) {
      await loadModule(Number(testStart.dataset.resume), testStart.dataset.module);
    } else {
      testStatus.textContent = 'Writing module 1… about two minutes.';
      const r = await fetch('/api/sat/test', { method: 'POST' });
      const d = await r.json();
      if (!r.ok || d.error) { testStatus.textContent = d.error || 'Could not start the test.'; }
      else {
        test = d;
        cursor = 0;
        deadline = Date.now() + d.minutes * 60000;
        clearInterval(tick);
        tick = setInterval(clock, 1000);
        testStatus.textContent = '';
        renderTest();
      }
    }
    testStart.disabled = false;
  });
})();
