// The motif workbench: every motif page's work in one window. The motifs as a tree (left), one or two open motifs
// (middle), an inbox of decisions (right), and drag-and-drop between all of them: hover a drop target and its choices
// pop up beside it; let go on one. Talks to /workbench.json, /workbench-queue.json, POST /workbench (scripts/validate.py).
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem('wb-' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('wb-' + k, JSON.stringify(v)); } catch (e) { /* private window */ } },
  };
  const SOURCE = {narrative: 'online', 'focus-group': 'focus group'};

  const S = {
    data: null, by: {}, kids: {}, open: store.get('open', []), view: store.get('view', 'all'), sort: store.get('sort', 'size'),
    q: '', sel: [], last: [], active: 0, tab: store.get('tab', 'check'), queues: {}, folded: new Set(store.get('folded', [])),
    checkAt: 0, extra: {}, claimHits: [],
  };

  // ---------- talking to the server ----------
  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    return r.json();
  }
  function setData(d) {
    S.data = d;
    S.by = Object.fromEntries(d.entries.map((e) => [e.id, e]));
    S.kids = {};
    for (const e of d.entries) for (const p of e.parents) (S.kids[p] = S.kids[p] || []).push(e.id);
    S.open = S.open.filter((id) => S.by[id]);
    resetSelection();
  }
  async function act(body, done) {
    const r = await fetch('/workbench', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const out = await r.json().catch(() => ({error: r.statusText}));
    if (!r.ok) { toast('😬 ' + (out.error || 'that didn’t work'), true); await reload(); return false; }
    setData(out);
    S.queues.pairs = S.queues.singles = null;  // suggestions change after most moves
    render();
    await refreshUndo();
    if (done) toast(done, false, true);
    return true;
  }
  const MAX_OPEN = 8;  // open motifs side by side; the middle scrolls sideways when they don't fit
  const COLORS = 6;  // panel colors cycle (pink, teal, yellow, blue, orange, purple)
  function resetSelection() { S.sel = S.open.map(() => new Set()); S.last = S.open.map(() => null); }
  async function reload() { setData(await getJSON('/workbench.json')); render(); refreshUndo(); }

  // Undo: the same server-side stack as every motif page (one step per action; a multi-claim drag is one step)
  const undoBtn = $('#undo-btn'), undoWhat = $('#undo-what');
  async function refreshUndo() {
    if (!undoBtn) return;
    const u = await getJSON('/undo.json').catch(() => ({what: null}));
    undoBtn.disabled = !u.what;
    undoWhat.textContent = u.what ? 'last: ' + u.what : '';
  }
  async function undo() {
    if (!undoBtn || undoBtn.disabled) return;
    const r = await fetch('/undo', {method: 'POST'});
    if (!r.ok) { toast('Can’t undo: ' + (await r.text()).slice(0, 200), true); return; }
    const u = await r.json();
    S.queues = {};
    await reload();
    toast('↶ undid: ' + u.undid);
  }
  if (undoBtn) undoBtn.addEventListener('click', undo);

  // ---------- small helpers ----------
  const motifs = () => S.data.entries;
  const isSingle = (e) => e.claims.length === 1 && !e.stands_alone && !e.parents.length && !(S.kids[e.id] || []).length;
  const isEmpty = (e) => !e.claims.length && !(S.kids[e.id] || []).length;
  const noteState = (e) => (!e.note ? 'none' : ['model', 'claude'].includes(e.note_by) ? 'draft' : 'yours');
  const newCount = (e) => e.claims.filter((c) => c.new).length;
  const VIEWS = [
    ['all', '🗂️ all', () => true],
    ['singles', '1️⃣ singles', isSingle],
    ['nonote', '📝 no note', (e) => noteState(e) === 'none'],
    ['drafts', '🤖 draft notes', (e) => noteState(e) === 'draft'],
    ['todo', '⏳ not done', (e) => e.done !== 'done'],
    ['new', '🆕 new claims', (e) => e.done === 'new'],
    ['unchecked', '❔ unchecked', (e) => e.claims.some((c) => !c.checked)],
    ['empty', '🫙 empty', isEmpty],
  ];
  const SORTS = {
    size: (a, b) => b.claims.length - a.claims.length || a.name.localeCompare(b.name),
    az: (a, b) => a.name.localeCompare(b.name),
    new: (a, b) => (b.first_seen || '').localeCompare(a.first_seen || '') || b.id.localeCompare(a.id),
    old: (a, b) => (a.first_seen || '').localeCompare(b.first_seen || '') || a.id.localeCompare(b.id),
  };
  function matches(e, words) {
    if (!words.length) return true;
    const hay = (e.id + ' ' + e.name + ' ' + (e.note || '') + ' ' + e.claims.map((c) => c.claim + ' #' + c.id).join(' ')).toLowerCase();
    return words.every((w) => hay.includes(w.replace(/^m(\d+)$/, 'm$1')));
  }
  const qWords = () => S.q.toLowerCase().split(/\s+/).filter(Boolean);
  const chip = (id, extra = '') => {
    const e = S.by[id];
    return e ? `<span class="wb-chip" data-drag="motif" data-id="${id}" data-drop="motif" data-open="${id}" title="${esc(e.note || e.name)} · ${id}">${esc(e.name)}<i>${e.claims.length}</i>${extra}</span>` : '';
  };
  const claimData = (c, source) => `data-drag="claim" data-claim="${esc(c.claim)}" data-source="${esc(source || '')}" data-src="${esc(c.source || '')}" data-ref="${esc(c.ref || '')}"`;

  // ---------- render: stats and views ----------
  function render() {
    if (!S.data) return;
    const es = motifs();
    const filings = es.reduce((n, e) => n + e.claims.length, 0);
    $('#stats').innerHTML = `<b>${es.length}</b> motifs · <b>${filings}</b> filings · <b>${es.filter((e) => e.claims.length > 1).length}</b> with 2+ · <b>${es.filter((e) => e.done !== 'done').length}</b> not done`;
    $('#views').innerHTML = VIEWS.map(([k, label, test]) => `<button class="wb-view${S.view === k ? ' on' : ''}" data-view="${k}">${label} <i>${es.filter(test).length}</i></button>`).join('');
    $('#sort').value = S.sort;
    renderTree();
    renderPanels();
    renderTabs();
    renderInbox();
  }

  // ---------- the tree ----------
  function renderTree() {
    const words = qWords();
    const test = (VIEWS.find((v) => v[0] === S.view) || VIEWS[0])[2];
    const shown = motifs().filter((e) => test(e) && matches(e, words)).sort(SORTS[S.sort]);
    const flat = S.view !== 'all' || words.length;
    const groups = [...S.data.groups, {id: '', name: 'Ungrouped'}];
    let html = '';
    if (words.length) html += claimHitsHTML(words);
    if (flat) {
      html += `<div class="wb-group"><div class="wb-ghead">${shown.length} motif${shown.length === 1 ? '' : 's'}</div>${shown.map((e) => row(e, 0, false)).join('')}</div>`;
    } else {
      const ids = new Set(shown.map((e) => e.id));
      for (const g of groups) {
        const inG = shown.filter((e) => (e.group || '') === g.id);
        if (!inG.length && !g.id) continue;
        // Roots: no parent in this group. Kinds nest under their parents (a motif with two parents shows under both)
        const roots = inG.filter((e) => !e.parents.some((p) => ids.has(p) && (S.by[p].group || '') === g.id));
        const folded = S.folded.has('g:' + g.id);
        html += `<div class="wb-group" data-drop="group" data-g="${g.id}">
          <div class="wb-ghead"><button class="wb-fold" data-fold="g:${g.id}">${folded ? '▸' : '▾'}</button>
            <span class="wb-gname">${g.id ? '📁 ' : '🗃️ '}${esc(g.name)}</span> <i>${inG.length}</i>
            ${g.id ? `<span class="wb-gtools"><button class="wb-mini" data-grename="${g.id}" title="rename">✎</button><button class="wb-mini" data-gdelete="${g.id}" title="delete the group (its motifs stay)">🗑️</button></span>` : ''}</div>
          ${folded ? '' : roots.map((e) => branch(e, 0, g.id, new Set())).join('')}</div>`;
      }
    }
    $('#tree').innerHTML = html || '<p class="wb-empty">🦗 nothing here</p>';
  }
  function branch(e, depth, gid, seen) {
    if (seen.has(e.id)) return '';
    seen = new Set(seen).add(e.id);
    const kids = (S.kids[e.id] || []).map((k) => S.by[k]).filter((k) => k && (k.group || '') === gid).sort(SORTS[S.sort]);
    const folded = S.folded.has('m:' + e.id);
    return row(e, depth, kids.length ? (folded ? '▸' : '▾') : '') + (folded ? '' : kids.map((k) => branch(k, depth + 1, gid, seen)).join(''));
  }
  function row(e, depth, fold) {
    const n = newCount(e), ns = noteState(e);
    const badges = [e.done === 'done' ? '<b title="done">✓</b>' : '', n ? `<b class="b-new" title="new since done">🆕${n}</b>` : '',
      ns === 'none' ? '<b title="no note yet" class="b-faint">📝</b>' : ns === 'draft' ? '<b title="the note is a draft">🤖</b>' : '',
      e.stands_alone ? '<b title="stands alone">🧍</b>' : ''].join('');
    const open = S.open.indexOf(e.id);
    return `<div class="wb-row${open >= 0 ? ' open o' + (open % COLORS) : ''}" style="--depth:${depth}" data-drag="motif" data-drop="motif" data-id="${e.id}" data-open="${e.id}">
      ${fold ? `<button class="wb-fold" data-fold="m:${e.id}">${fold}</button>` : '<span class="wb-fold-sp"></span>'}
      <span class="wb-rname">${esc(e.name)}</span><span class="wb-badges">${badges}</span><i class="wb-n">${e.claims.length}</i>
      <button class="wb-mini wb-side" data-open2="${e.id}" title="open beside (compare)">⧉</button></div>`;
  }
  function claimHitsHTML(words) {
    const local = [];
    for (const e of motifs()) for (const c of e.claims) {
      const hay = (c.claim + ' #' + c.id).toLowerCase();
      if (words.every((w) => hay.includes(w))) local.push([c, e]);
    }
    const unfiled = S.claimHits.filter((c) => !c.motifs.length);
    if (!local.length && !unfiled.length) return '';
    const items = local.slice(0, 30).map(([c, e]) => `<li class="wb-claim mini" ${claimData(c, e.id)}><span class="wb-ctext">${esc(c.claim)}</span> <span class="wb-meta">#${c.id} · in ${chip(e.id)}</span></li>`).join('')
      + unfiled.slice(0, 20).map((c) => `<li class="wb-claim mini unfiled" ${claimData(c, '')}><span class="wb-ctext">${esc(c.claim)}</span> <span class="wb-meta">📥 not filed · ${esc(SOURCE[c.source] || c.source)}</span></li>`).join('');
    return `<div class="wb-group hits"><div class="wb-ghead">💬 claims that match <i>${local.length + unfiled.length}</i></div><ul class="wb-claims">${items}</ul></div>`;
  }

  // ---------- the open motifs ----------
  function renderPanels() {
    const box = $('#panels');
    if (!S.open.length) {
      $('#work-head').innerHTML = '';
      box.innerHTML = `<div class="wb-welcome"><div class="wb-big">👈 pick a motif</div>
        <p>Click one on the left to open it here; <b>Shift-click</b> or ⧉ opens a second beside it.</p>
        <p>Then drag: claims onto motifs, motifs onto motifs, motifs onto groups. Hover a target to see your choices. 🫳</p>
        <p class="wb-faint">The inbox on the right has decisions waiting: ✅ checks, 🔗 pairs, 1️⃣ singles, 📥 unfiled claims.</p></div>`;
      return;
    }
    box.dataset.count = S.open.length;
    $('#work-head').innerHTML = S.open.length > 1 ? `<b>${S.open.length}</b> open side by side · a click opens in the outlined one; <b>Shift-click</b> or ⧉ adds another <button class="wb-mini" id="close-all">✕ close all</button>`
      : 'Shift-click a motif (or ⧉) to open it beside this one, as many as you like';
    box.innerHTML = S.open.map((id, i) => panel(S.by[id], i)).join('');
    S.open.forEach((id, i) => { if (S.extra[id]) fillExtra(id, i); });
  }
  function panel(e, i) {
    const kids = S.kids[e.id] || [];
    const groups = S.data.groups.map((g) => `<option value="${g.id}"${e.group === g.id ? ' selected' : ''}>📁 ${esc(g.name)}</option>`).join('');
    const ns = noteState(e);
    const shared = {};
    for (const c of e.claims) for (const o of motifs()) if (o.id !== e.id && o.claims.some((x) => x.claim === c.claim)) shared[o.id] = (shared[o.id] || 0) + 1;
    const sharedIds = Object.keys(shared).sort((a, b) => shared[b] - shared[a]);
    const order = [...e.claims].sort((a, b) => (b.new - a.new));
    const sel = S.sel[i] || (S.sel[i] = new Set());
    return `<article data-scroll class="wb-panel p${i % COLORS}${i === S.active && S.open.length > 1 ? ' active' : ''}" data-drop="motif" data-id="${e.id}" data-panel="${i}">
      <header class="wb-phead">
        <h2 class="wb-pname" data-drag="motif" data-id="${e.id}" title="drag me onto another motif or a group">${esc(e.name)}</h2>
        <span class="wb-pid">${e.id} · ${e.claims.length} claim${e.claims.length === 1 ? '' : 's'}${e.curated ? ' · ✋ by hand' : ''}${e.first_seen ? ' · since ' + esc(e.first_seen.slice(0, 10)) : ''}</span>
        <span class="wb-ptools">
          <button class="wb-btn" data-rename="${e.id}" title="rename">✎ rename</button>
          <button class="wb-btn${e.done === 'done' ? ' on' : ''}" data-done="${e.id}" title="mark it done: you've looked at every claim">${e.done === 'done' ? '✓ done' : e.done === 'new' ? '🆕 new claims' : '✓ mark done'}</button>
          <select data-group="${e.id}" title="its group"><option value="">🗃️ no group</option>${groups}</select>
          ${isSingle(e) || e.stands_alone ? `<button class="wb-btn${e.stands_alone ? ' on' : ''}" data-alone="${e.id}" title="a single motif that needs no partner">🧍 ${e.stands_alone ? 'stands alone' : 'stands alone?'}</button>` : ''}
          <button class="wb-btn" data-delete="${e.id}" title="delete this motif (its claims aren't filed again)">🗑️</button>
          <button class="wb-btn" data-close="${i}" title="close">✕</button>
        </span>
      </header>
      <div class="wb-rels">
        <div><span class="wb-rlabel">↳ a kind of</span> ${e.parents.map((p) => chip(p, `<button class="wb-x" data-unparent="${e.id}|${p}" title="not a kind of it">✕</button>`)).join(' ') || '<span class="wb-faint">—</span>'}</div>
        <div><span class="wb-rlabel">⤷ its kinds</span> ${kids.map((k) => chip(k, `<button class="wb-x" data-unparent="${k}|${e.id}" title="not a kind of this">✕</button>`)).join(' ') || '<span class="wb-faint">—</span>'}</div>
        <div><span class="wb-rlabel">↔ related</span> ${e.related.map((r) => chip(r, `<button class="wb-x" data-unrelate="${e.id}|${r}" title="not related">✕</button>`)).join(' ') || '<span class="wb-faint">—</span>'}</div>
        ${sharedIds.length ? `<div><span class="wb-rlabel">🤝 shares claims with</span> ${sharedIds.slice(0, 8).map((o) => chip(o, `<b class="wb-shared">${shared[o]}</b>`)).join(' ')}</div>` : ''}
      </div>
      <div class="wb-note ${ns}">
        <label>📝 note <span class="wb-ntag">${ns === 'none' ? 'none yet' : ns === 'draft' ? '🤖 draft by the ' + esc(e.note_by) : 'yours'}</span></label>
        <textarea data-note="${e.id}" rows="2" placeholder="what this motif is, in a sentence (Enter saves, Shift+Enter for a new line)">${esc(e.note || '')}</textarea>
        <div class="wb-nbtns"><button class="wb-btn" data-savenote="${e.id}" disabled>💾 save</button>${ns === 'draft' ? `<button class="wb-btn" data-keepnote="${e.id}">✓ keep the draft</button>` : ''}</div>
      </div>
      ${sel.size ? `<div class="wb-selbar">☑️ <b>${sel.size}</b> selected: drag them anywhere, or
        <button class="wb-btn" data-bulk="unfile|${i}">🗑️ take out</button><button class="wb-btn" data-bulk="no_motif|${i}">∅ no motif</button>
        <button class="wb-btn" data-bulk="check|${i}">✓ check all</button><button class="wb-btn" data-bulk="clear|${i}">clear</button></div>` : ''}
      <ul class="wb-claims">${order.map((c) => claimRow(c, e, sel.has(c.claim))).join('') || '<li class="wb-empty">🫙 no claims: drag some here, or delete it</li>'}</ul>
      <div class="wb-more">
        <button class="wb-btn" data-similar="${e.id}|${i}">🧲 more like this</button>
        <label class="wb-addsearch">📥 add claims <input type="search" data-claimsearch="${e.id}|${i}" placeholder="search every claim…"></label>
      </div>
      <div class="wb-extra" id="extra-${i}"></div>
    </article>`;
  }
  function claimRow(c, e, selected) {
    const tags = [c.new ? '<b class="b-new">NEW</b>' : '', c.checked === 'yes' ? '<b title="checked: belongs here">✓</b>' : c.checked === 'unsure' ? '<b title="checked: not sure">🤷</b>' : ''].join('');
    return `<li class="wb-claim${selected ? ' sel' : ''}" ${claimData(c, e.id)}>
      <span class="wb-ctext" data-select="1">${tags}${esc(c.claim)}</span>
      <span class="wb-meta"><a class="wb-cid" data-inspect="1" title="open it on the right">#${c.id}</a> · ${esc(SOURCE[c.source] || c.source || '')}</span>
      <span class="wb-cbtns">
        <button class="wb-mini" data-inspect="1" title="open it on the right: its source and every motif it's in, to reassign">🔍</button>
        ${c.checked !== 'yes' ? `<button class="wb-mini" data-check="yes" title="yes, it belongs here">✓</button>` : ''}
        <button class="wb-mini" data-unfile="1" title="take it out of this motif">✕</button>
        <button class="wb-mini" data-nomotif="1" title="no motif: tells no recurring story">∅</button>
        <button class="wb-mini" data-correct="1" title="correct the wording">✎</button>
        <button class="wb-mini" data-detail="1" title="where it came from">ⓘ</button>
      </span><div class="wb-detail" hidden></div></li>`;
  }
  async function fillExtra(id, i) {
    const box = $('#extra-' + i);
    const x = S.extra[id];
    if (!box || !x) return;
    if (x.kind === 'similar') {
      box.innerHTML = `<h3>🧲 more like this <button class="wb-mini" data-closeextra="${id}">✕</button></h3>` + (x.items.length ? `<ul class="wb-claims">${x.items.map((c) => {
        const src = c.motifs[0] ? c.motifs[0].id : '';
        return `<li class="wb-claim mini" ${claimData(c, src)}><span class="wb-ctext">${esc(c.claim)}</span>
          <span class="wb-meta">${c.motifs.length ? 'in ' + c.motifs.map((m) => chip(m.id)).join(' ') : '📥 not filed'} · ${c.score}</span>
          <span class="wb-cbtns"><button class="wb-mini" data-addhere="${id}" title="add it here">＋</button><button class="wb-mini" data-reject="${id}" title="not this motif: don't suggest it again">✕</button></span></li>`;
      }).join('')}</ul>` : '<p class="wb-faint">🦗 nothing close</p>');
    } else if (x.kind === 'search') {
      box.innerHTML = `<h3>📥 claims matching “${esc(x.q)}” <button class="wb-mini" data-closeextra="${id}">✕</button></h3><ul class="wb-claims">${x.items.map((c) => {
        const here = c.motifs.some((m) => m.id === id);
        return `<li class="wb-claim mini${c.motifs.length ? '' : ' unfiled'}" ${claimData(c, c.motifs[0] ? c.motifs[0].id : '')}><span class="wb-ctext">${esc(c.claim)}</span>
          <span class="wb-meta">${c.motifs.length ? 'in ' + c.motifs.map((m) => chip(m.id)).join(' ') : '📥 not filed · ' + esc(SOURCE[c.source] || c.source)}</span>
          <span class="wb-cbtns">${here ? '✓ here' : `<button class="wb-mini" data-addhere="${id}" title="add it here">＋</button>`}</span></li>`;
      }).join('') || '<li class="wb-faint">🦗 none</li>'}</ul>`;
    }
  }

  // ---------- the inbox ----------
  const TABS = [['claim', '🔍 claim'], ['check', '✅ check'], ['pairs', '🔗 pairs'], ['singles', '1️⃣ singles'], ['claims', '📥 unfiled'], ['empty', '🫙 empty']];
  function renderTabs() {
    const counts = {check: S.data.to_check, singles: motifs().filter(isSingle).length, empty: motifs().filter(isEmpty).length};
    $('#tabs').innerHTML = TABS.map(([k, label]) => `<button role="tab" class="wb-tab${S.tab === k ? ' on' : ''}" data-tab="${k}">${label}${counts[k] !== undefined ? ` <i>${counts[k]}</i>` : ''}</button>`).join('');
  }
  async function queue(kind) {
    if (!S.queues[kind]) {
      $('#inbox').innerHTML = '<p class="wb-faint">⏳ thinking…</p>';
      S.queues[kind] = await getJSON('/workbench-queue.json?kind=' + kind).catch((e) => ({error: e.message}));
    }
    return S.queues[kind];
  }
  async function renderInbox() {
    const box = $('#inbox');
    const tab = S.tab;
    delete box.dataset.check;
    if (tab === 'claim') return renderClaim(box);
    if (tab === 'check') {
      const q = await queue('check');
      if (S.tab !== tab) return;
      const items = (q.error ? [] : q).filter((x) => S.by[x.id] && S.by[x.id].claims.some((c) => c.claim === x.claim && !c.checked));
      const x = items[S.checkAt % Math.max(items.length, 1)];
      if (!x) { box.innerHTML = '<div class="wb-welcome"><div class="wb-big">🎉</div><p>Nothing to check right now.</p></div>'; S.queues.check = null; return; }
      const e = S.by[x.id];
      box.innerHTML = `<div class="wb-checkcard">
        <p class="wb-faint">${items.length} filing${items.length === 1 ? '' : 's'} to check here (${S.data.to_check} in all) · the biggest motifs first</p>
        <p class="wb-checkq">Does this claim belong in</p><p>${chip(x.id)}</p>
        <blockquote class="wb-claim big" ${claimData({claim: x.claim, source: x.source}, x.id)}>${esc(x.claim)}<span class="wb-meta">${esc(SOURCE[x.source] || x.source || '')}</span></blockquote>
        ${e.note ? `<p class="wb-faint">📝 ${esc(e.note)}</p>` : ''}
        ${x.others.length ? `<p class="wb-faint">also there: ${x.others.map((o) => '“' + esc(o.slice(0, 140)) + '”').join(' · ')}</p>` : ''}
        <div class="wb-checkbtns">
          <button class="wb-btn yes" data-verdict="yes">✓ yes <kbd>Y</kbd></button>
          <button class="wb-btn no" data-verdict="no">✗ no, take it out <kbd>N</kbd></button>
          <button class="wb-btn" data-verdict="unsure">🤷 not sure <kbd>U</kbd></button>
          <button class="wb-btn" data-verdict="skip">⏭ skip <kbd>S</kbd></button>
        </div>
        <p class="wb-faint">Or drag the claim onto the motif it does belong in. <button class="wb-mini" data-open="${x.id}">open the motif</button></p></div>`;
      box.dataset.check = JSON.stringify(x);
    } else if (tab === 'pairs') {
      const q = await queue('pairs');
      if (S.tab !== tab) return;
      if (q.error) { box.innerHTML = `<p class="wb-faint">😬 ${esc(q.error)}</p>`; return; }
      const seen = new Set(S.data.not_same.map((p) => p.join('|')));
      const ok = (a, b) => S.by[a] && S.by[b] && a !== b && !seen.has([a, b].sort().join('|'))
        && !S.by[a].parents.includes(b) && !S.by[b].parents.includes(a) && !S.by[a].related.includes(b);
      const shared = q.shared.filter((p) => ok(p.a, p.b));
      const similar = q.similar.filter((p) => ok(p.a, p.b));
      box.innerHTML = `${q.note ? `<p class="wb-faint">${esc(q.note)}</p>` : ''}
        <h3>🤝 filed together <i>${shared.length}</i></h3>${shared.map((p) => pairCard(p.a, p.b, `${p.shared.length} shared claim${p.shared.length === 1 ? '' : 's'}`, p.shared[0])).join('') || '<p class="wb-faint">🦗 none</p>'}
        <h3>👯 similar names <i>${similar.length}</i></h3>${similar.map((p) => pairCard(p.a, p.b, 'alike ' + p.score)).join('') || '<p class="wb-faint">🦗 none</p>'}`;
    } else if (tab === 'singles') {
      const q = await queue('singles');
      if (S.tab !== tab) return;
      if (q.error) { box.innerHTML = `<p class="wb-faint">😬 ${esc(q.error)}</p>`; return; }
      const items = q.filter((s) => S.by[s.id] && isSingle(S.by[s.id]));
      box.innerHTML = items.map((s) => `<div class="wb-card">
        <div>${chip(s.id)} <button class="wb-mini" data-alone1="${s.id}" title="it stands alone: stop suggesting">🧍</button></div>
        <p class="wb-claim mini" ${claimData({claim: s.claim, source: s.source}, s.id)}><span class="wb-ctext">${esc(s.claim)}</span></p>
        ${s.suggest.filter((m) => S.by[m.id]).map((m) => `<div class="wb-sug">${chip(m.id)} <span class="wb-faint">${m.same_claim ? '🎯 same claim' : 'alike ' + (m.score ?? '')}</span>
          <span class="wb-sbtns"><button class="wb-mini" data-pair="merge|${s.id}|${m.id}" title="merge the single into it">⤵</button><button class="wb-mini" data-pair="under|${s.id}|${m.id}" title="the single is a kind of it">⊂</button><button class="wb-mini" data-pair="related|${s.id}|${m.id}" title="related">↔</button><button class="wb-mini" data-compare="${s.id}|${m.id}" title="open both">⧉</button></span></div>`).join('')}
      </div>`).join('') || '<div class="wb-welcome"><div class="wb-big">🎉</div><p>No singles waiting.</p></div>';
    } else if (tab === 'claims') {
      box.innerHTML = `<label class="wb-addsearch">🔎 <input type="search" id="unfiled-q" placeholder="search claims not filed yet" value="${esc(S.unfiledQ || '')}"></label><ul class="wb-claims" id="unfiled-list"><li class="wb-faint">⏳</li></ul>`;
      loadUnfiled();
    } else if (tab === 'empty') {
      const empty = motifs().filter(isEmpty);
      box.innerHTML = empty.length ? `<p><button class="wb-btn" id="delete-empty">🗑️ delete all ${empty.length}</button></p>` + empty.map((e) => `<div class="wb-sug">${chip(e.id)} <span class="wb-faint">${e.curated ? '✋ made by hand' : ''} ${esc((e.first_seen || '').slice(0, 10))}</span><span class="wb-sbtns"><button class="wb-mini" data-delete="${e.id}">🗑️</button></span></div>`).join('')
        : '<div class="wb-welcome"><div class="wb-big">✨</div><p>No empty motifs.</p></div>';
    }
  }
  // ---------- one claim, inspected: where it came from, every motif it's in, and moving it ----------
  function motifsOf(text) { return motifs().filter((e) => e.claims.some((c) => c.claim === text)); }
  function inspect(li) {
    S.claim = {claim: li.dataset.claim, src: li.dataset.src, ref: li.dataset.ref};
    S.tab = 'claim';
    S.claimQ = '';
    renderTabs();
    renderInbox();
  }
  function renderClaim(box) {
    const c = S.claim;
    if (!c) {
      box.innerHTML = '<div class="wb-welcome"><div class="wb-big">🔍</div><p>Click a claim’s 🔍 or its #id (or a claim in the search results) to open it here: where it came from, every motif it’s in, and where to move it.</p></div>';
      return;
    }
    const ins = motifsOf(c.claim);
    const first = ins[0], rec = first && first.claims.find((x) => x.claim === c.claim);
    const src = (rec && rec.source) || c.src || '';
    box.innerHTML = `<div class="wb-inspect" data-drop="claim">
      <blockquote class="wb-claim big" ${claimData({claim: c.claim, source: src, ref: (rec && rec.ref) || c.ref}, first ? first.id : '')}>${esc(c.claim)}
        <span class="wb-meta">${rec ? '#' + rec.id + ' · ' : ''}${esc(SOURCE[src] || src)} · drag me onto a motif</span></blockquote>
      <h3>🧩 filed under <i>${ins.length}</i></h3>
      ${ins.map((e) => { const r = e.claims.find((x) => x.claim === c.claim); return `<div class="wb-sug">${chip(e.id)}
        <span class="wb-faint">${r.checked === 'yes' ? '✓ checked' : r.checked === 'unsure' ? '🤷 unsure' : ''}</span>
        <span class="wb-sbtns">${r.checked !== 'yes' ? `<button class="wb-mini" data-cl="check|${e.id}" title="yes, it belongs here">✓</button>` : ''}
        <button class="wb-mini" data-cl="unfile|${e.id}" title="take it out of this motif">✕ take out</button></span></div>`; }).join('')
        || '<p class="wb-faint">📥 not in any motif</p>'}
      <h3>➕ file it under…</h3>
      <label class="wb-addsearch">🔎 <input type="search" id="cl-q" placeholder="find a motif" value="${esc(S.claimQ || '')}" autocomplete="off"></label>
      <div id="cl-results"></div>
      <div class="wb-sbtns wb-clacts">
        <button class="wb-btn" data-cl="new|">✨ new motif with it</button>
        <button class="wb-btn" data-cl="correct|">✎ correct wording</button>
        ${ins.length ? '<button class="wb-btn" data-cl="nomotif|">∅ no motif</button>' : ''}
      </div>
      <h3>📜 where it came from</h3><div class="wb-detail" id="cl-detail">⏳</div>
    </div>`;
    claimResults();
    getJSON('/claim-detail.json?claim=' + encodeURIComponent(c.claim)).then((x) => {
      const d = $('#cl-detail');
      if (d) d.innerHTML = detailHTML(x, c.claim);
    }).catch(() => { const d = $('#cl-detail'); if (d) d.textContent = '😬 couldn’t load it'; });
  }
  function claimResults() {
    const box = $('#cl-results');
    if (!box || !S.claim) return;
    const words = (S.claimQ || '').toLowerCase().split(/\s+/).filter(Boolean);
    const ins = motifsOf(S.claim.claim), inIds = new Set(ins.map((e) => e.id));
    if (!words.length) { box.innerHTML = '<p class="wb-faint">type to find a motif, or drag the claim onto one</p>'; return; }
    const found = motifs().filter((e) => !inIds.has(e.id) && words.every((w) => (e.id + ' ' + e.name + ' ' + (e.note || '')).toLowerCase().includes(w)))
      .sort(SORTS.size).slice(0, 12);
    box.innerHTML = found.map((e) => `<div class="wb-sug">${chip(e.id)}<span class="wb-sbtns">
        <button class="wb-mini" data-cl="add|${e.id}" title="file it here too">＋ add</button>
        ${ins.length ? `<button class="wb-mini" data-cl="move|${e.id}" title="file it here and take it out of ${ins.length === 1 ? '“' + esc(ins[0].name) + '”' : 'the ' + ins.length + ' motifs it’s in'}">⇢ move here</button>` : ''}</span></div>`).join('')
      || '<p class="wb-faint">🦗 no motif matches</p>';
  }
  function claimAction(kind, id) {
    const c = S.claim, ins = motifsOf(c.claim), first = ins[0];
    const rec = first && first.claims.find((x) => x.claim === c.claim);
    const src = (rec && rec.source) || c.src || '', ref = (rec && rec.ref) || c.ref || '';
    const fileHere = (to) => first ? {action: 'also', claim: c.claim, source: first.id, target: to} : {action: 'file', claim: c.claim, id: to, source: src, ref};
    const name = (to) => (S.by[to] || {}).name;
    if (kind === 'check') return act({action: 'check', claim: c.claim, id, answer: 'yes'}, '✓ checked');
    if (kind === 'unfile') return act({action: 'unfile', claim: c.claim, id}, `✕ out of “${name(id)}”`);
    if (kind === 'add') return act(fileHere(id), `＋ filed in “${name(id)}”`);
    if (kind === 'move') {
      const steps = [{action: 'move', claim: c.claim, source: first.id, target: id}].concat(ins.slice(1).map((e) => ({action: 'unfile', claim: c.claim, id: e.id})));
      return batch(steps, `⇢ moved to “${name(id)}”`);
    }
    if (kind === 'new') {
      const n = prompt('Name the new motif:', c.claim.slice(0, 80));
      if (n && n.trim()) act({action: 'new_with', name: n.trim(), claims: [{claim: c.claim, source: first ? first.id : '', src, ref, mode: 'also'}]}, `✨ made “${n.trim()}”`);
      return;
    }
    if (kind === 'correct') {
      const text = prompt('Correct the wording (the summary, not the source):', c.claim);
      if (text && text.trim() && text.trim() !== c.claim) act({action: 'correct', claim: c.claim, text: text.trim()}, '✎ corrected').then((ok) => { if (ok) { S.claim.claim = text.trim(); renderInbox(); } });
      return;
    }
    if (kind === 'nomotif' && confirm('No motif: take it out of every motif, for good?')) return act({action: 'no_motif', claim: c.claim}, '∅ no motif');
  }

  function pairCard(a, b, why, example) {
    return `<div class="wb-card"><div class="wb-pair">${chip(a)} <span class="wb-faint">&amp;</span> ${chip(b)}</div>
      <p class="wb-faint">${esc(why)}${example ? ': “' + esc(example.slice(0, 120)) + '”' : ''}</p>
      <div class="wb-sbtns"><button class="wb-mini" data-compare="${a}|${b}" title="open both side by side">⧉ compare</button>
        <button class="wb-mini" data-pair="merge|${a}|${b}" title="merge the first into the second">⤵ merge →</button>
        <button class="wb-mini" data-pair="merge|${b}|${a}" title="merge the second into the first">← merge ⤵</button>
        <button class="wb-mini" data-pair="under|${a}|${b}" title="the first is a kind of the second">⊂ kind of →</button>
        <button class="wb-mini" data-pair="under|${b}|${a}" title="the second is a kind of the first">← kind of ⊃</button>
        <button class="wb-mini" data-pair="related|${a}|${b}">↔ related</button>
        <button class="wb-mini" data-pair="notsame|${a}|${b}" title="different motifs: stop suggesting">≠ not the same</button></div></div>`;
  }
  let unfiledTimer = null;
  async function loadUnfiled() {
    const list = $('#unfiled-list');
    if (!list) return;
    const items = await getJSON('/claims.json?q=' + encodeURIComponent(S.unfiledQ || '')).catch(() => []);
    const rows = items.filter((c) => !c.motifs.length);
    list.innerHTML = rows.map((c) => `<li class="wb-claim mini unfiled" ${claimData(c, '')}><span class="wb-ctext">${esc(c.claim)}</span><span class="wb-meta">📥 ${esc(SOURCE[c.source] || c.source)}</span></li>`).join('')
      || '<li class="wb-faint">🦗 none: every claim matching has a motif</li>';
  }

  // ---------- opening motifs ----------
  // A click opens a motif in the active panel (the last one you worked in); Shift-click or ⧉ adds a panel beside the
  // others. A motif already open is just brought into view.
  function openMotif(id, beside) {
    if (!S.by[id]) return;
    const at = S.open.indexOf(id);
    if (at >= 0) S.active = at;
    else if (beside || !S.open.length) {
      S.open.push(id);
      if (S.open.length > MAX_OPEN) S.open.shift();
      S.active = S.open.length - 1;
    } else {
      S.active = Math.min(S.active, S.open.length - 1);
      S.open[S.active] = id;
    }
    resetSelection();
    store.set('open', S.open);
    render();
    const p = $(`.wb-panel[data-panel="${S.active}"]`);
    if (p) p.scrollIntoView({behavior: 'smooth', block: 'nearest', inline: 'nearest'});
  }
  function closePanel(i) {
    S.open.splice(i, 1);
    if (S.active >= i && S.active > 0) S.active -= 1;
    resetSelection();
    store.set('open', S.open);
    render();
  }

  // ---------- what a drop does ----------
  // A dragged thing is {kind: 'claim', claims: [{claim, source, src, ref}]} or {kind: 'motif', id}
  function claimsName(item) { return item.claims.length === 1 ? '“' + item.claims[0].claim.slice(0, 60) + '…”' : item.claims.length + ' claims'; }
  function zones(item, t) {
    const drop = t.dataset.drop;
    if (item.kind === 'claim') {
      const cs = item.claims;
      if (drop === 'motif') {
        const to = t.dataset.id, e = S.by[to];
        if (!e) return [];
        const has = new Set(e.claims.map((c) => c.claim));
        const todo = cs.filter((c) => !has.has(c.claim) || (c.source && c.source !== to));
        if (!todo.length || cs.every((c) => c.source === to)) return [];
        const filed = cs.filter((c) => c.source && c.source !== to);
        const out = [];
        if (filed.length) {
          out.push({label: '⇢ move here', say: `move ${claimsName(item)} into “${e.name}”`, run: () => batch(cs.map((c) =>
            c.source === to ? null : has.has(c.claim) ? {action: 'unfile', claim: c.claim, id: c.source}
              : c.source ? {action: 'move', claim: c.claim, source: c.source, target: to}
                : {action: 'file', claim: c.claim, id: to, source: c.src, ref: c.ref}), `⇢ moved ${claimsName(item)} into “${e.name}”`)});
          out.push({label: '＋ also here', say: `file ${claimsName(item)} here too, keeping where it is`, run: () => batch(cs.map((c) =>
            has.has(c.claim) ? null : c.source ? {action: 'also', claim: c.claim, source: c.source, target: to}
              : {action: 'file', claim: c.claim, id: to, source: c.src, ref: c.ref}), `＋ filed ${claimsName(item)} in “${e.name}” too`)});
        } else {
          out.push({label: '＋ file here', say: `file ${claimsName(item)} in “${e.name}”`, run: () => batch(cs.map((c) =>
            has.has(c.claim) ? null : {action: 'file', claim: c.claim, id: to, source: c.src, ref: c.ref}), `＋ filed ${claimsName(item)} in “${e.name}”`)});
        }
        return out;
      }
      if (drop === 'newmotif') {
        const named = (mode) => () => {
          const name = prompt('Name the new motif:', cs.length === 1 ? cs[0].claim.slice(0, 80) : '');
          if (name && name.trim()) act({action: 'new_with', name: name.trim(), claims: cs.map((c) => ({...c, mode}))}, `✨ made “${name.trim()}”`);
        };
        return cs.some((c) => c.source)
          ? [{label: '⇢ move into a new motif', say: 'move them out into a motif of their own', run: named('move')},
            {label: '＋ copy into a new motif', say: 'start a new motif with them, keeping where they are', run: named('also')}]
          : [{label: '✨ new motif', say: 'start a new motif with them', run: named('file')}];
      }
      if (drop === 'nomotif') {
        return [{label: '∅ no motif', say: 'they tell no recurring story: out of every motif, never filed again', run: () =>
          confirm(`Take ${claimsName(item)} out of every motif, for good?`) && batch(cs.map((c) => ({action: 'no_motif', claim: c.claim})), `∅ ${claimsName(item)}: no motif`)}];
      }
      if (drop === 'trash') {
        const filed = cs.filter((c) => c.source);
        return filed.length ? [{label: '🗑️ take out', say: 'out of the motif you dragged them from', run: () =>
          batch(filed.map((c) => ({action: 'unfile', claim: c.claim, id: c.source})), `🗑️ took ${claimsName(item)} out`)}] : [];
      }
      return [];
    }
    // a motif
    const a = item.id, A = S.by[a];
    if (!A) return [];
    if (drop === 'motif') {
      const b = t.dataset.id, B = S.by[b];
      if (!B || a === b) return [];
      return [
        {label: '⤵ merge into it', say: `merge “${A.name}” into “${B.name}”`, run: () => act({action: 'merge', source: a, target: b}, `⤵ merged “${A.name}” into “${B.name}”`)},
        {label: '⊂ a kind of it', say: `“${A.name}” is a kind of “${B.name}”`, run: () => act({action: 'parent', id: a, parent: b}, `⊂ “${A.name}” is a kind of “${B.name}”`)},
        {label: '⊃ it’s a kind of this', say: `“${B.name}” is a kind of “${A.name}”`, run: () => act({action: 'parent', id: b, parent: a}, `⊃ “${B.name}” is a kind of “${A.name}”`)},
        {label: '↔ related', say: 'related, but different', run: () => act({action: 'relate', a, b}, `↔ related “${A.name}” and “${B.name}”`)},
        {label: '≠ not the same', say: 'different motifs: stop suggesting them as a pair', run: () => act({action: 'not_same', a, b}, `≠ “${A.name}” and “${B.name}” are different`)},
      ];
    }
    if (drop === 'claim' && S.claim) {
      if (motifsOf(S.claim.claim).some((e) => e.id === a)) return [];
      return [{label: '＋ file the claim here', say: `file the claim in “${A.name}”`, run: () => claimAction('add', a)}];
    }
    if (drop === 'group') {
      const g = t.dataset.g || null;
      if ((A.group || null) === g) return [];
      const name = g ? (S.data.groups.find((x) => x.id === g) || {}).name : 'no group';
      return [{label: '📁 move to ' + (g ? 'this group' : 'no group'), say: `put “${A.name}” in ${name}`, run: () => act({action: 'group_assign', id: a, group: g}, `📁 “${A.name}” → ${name}`)}];
    }
    if (drop === 'trash') {
      return [{label: '🗑️ delete it', say: 'delete the motif (its claims aren’t filed again)', run: () =>
        confirm(`Delete “${A.name}”? Its ${A.claims.length} claims won't be filed again.`) && act({action: 'delete', id: a}, `🗑️ deleted “${A.name}”`)}];
    }
    return [];
  }
  function batch(steps, done) {
    steps = steps.filter(Boolean);
    if (!steps.length) return;
    return act(steps.length === 1 ? steps[0] : {action: 'batch', steps}, done);
  }

  // ---------- drag and drop (pointer events: mouse, pen, a long press on touch) ----------
  const menu = $('#dz-menu'), ghost = $('#ghost');
  let drag = null, pinned = null;
  function itemOf(el) {
    if (el.dataset.drag === 'motif') return {kind: 'motif', id: el.dataset.id};
    const one = {claim: el.dataset.claim, source: el.dataset.source, src: el.dataset.src, ref: el.dataset.ref};
    const p = el.closest('[data-panel]');
    if (p && el.classList.contains('sel')) {
      const i = +p.dataset.panel;
      const cs = $$('.wb-claim.sel', p).map((x) => ({claim: x.dataset.claim, source: x.dataset.source, src: x.dataset.src, ref: x.dataset.ref}));
      if (cs.length && S.sel[i].size) return {kind: 'claim', claims: cs};
    }
    return {kind: 'claim', claims: [one]};
  }
  function label(item) { return item.kind === 'motif' ? '🧩 ' + (S.by[item.id] || {}).name : '💬 ' + claimsName(item); }
  function showMenu(t, list, pin, px, py) {
    menu.innerHTML = `<div class="dz-title">${pin ? 'drop it as…' : 'let go on a choice'}</div>` + list.map((z, k) => `<button class="dz-zone" data-zone="${k}" title="${esc(z.say || '')}">${esc(z.label)}</button>`).join('')
      + (pin ? '<button class="dz-zone dz-cancel" data-zone="cancel">cancel</button>' : '');
    menu.hidden = false;
    // Beside the pointer, so the choices are a short move away (to the left of it near the window's right edge)
    const m = menu.getBoundingClientRect();
    let x = px + 16, y = py - 14;
    if (x + m.width > innerWidth - 8) x = Math.max(8, px - m.width - 16);
    if (y + m.height > innerHeight - 8) y = Math.max(8, innerHeight - m.height - 8);
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    menu._zones = list;
    menu._target = t;
  }
  function hideMenu() { menu.hidden = true; menu._zones = null; menu._target = null; pinned = null; }
  function scrollerOf(el) { return el && el.closest('[data-scroll]'); }

  document.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0 || pinned) return;
    const h = ev.target.closest('[data-drag]');
    if (!h || ev.target.closest('button, input, textarea, select, a, dialog, .dz-menu')) return;
    drag = {h, x: ev.clientX, y: ev.clientY, on: false, touch: ev.pointerType === 'touch', timer: null, id: ev.pointerId};
    if (drag.touch) drag.timer = setTimeout(() => { if (drag && !drag.on) start(ev); }, 350);
  });
  function start(ev) {
    drag.on = true;
    drag.item = itemOf(drag.h);
    document.body.classList.add('dragging');
    ghost.hidden = false;
    ghost.textContent = label(drag.item);
    move(ev);
  }
  function move(ev) {
    ghost.style.left = ev.clientX - 12 + 'px';  // below-left of the pointer (the choices pop up to its right)
    ghost.style.top = ev.clientY + 14 + 'px';
    const el = document.elementFromPoint(ev.clientX, ev.clientY);
    $$('.dz-zone.hot').forEach((z) => z.classList.remove('hot'));
    const z = el && el.closest('.dz-zone');
    if (z) {
      z.classList.add('hot');
      ghost.textContent = (menu._zones[+z.dataset.zone] || {}).say || z.textContent;
    } else {
      const t = el && el.closest('[data-drop]');
      if (t && t !== menu._target) {
        $$('.dz-target').forEach((x) => x.classList.remove('dz-target'));
        const list = zones(drag.item, t);
        if (list.length) { t.classList.add('dz-target'); showMenu(t, list, false, ev.clientX, ev.clientY); } else hideMenu();
      } else if (!t && !(el && el.closest('.dz-menu'))) {
        $$('.dz-target').forEach((x) => x.classList.remove('dz-target'));
        hideMenu();
      }
      ghost.textContent = label(drag.item);
    }
    // Scroll the pane (or the window) when near its edge
    const sc = scrollerOf(el);
    drag.scroll = 0;
    if (sc) {
      const r = sc.getBoundingClientRect();
      drag.scroll = ev.clientY < r.top + 50 ? -1 : ev.clientY > r.bottom - 50 ? 1 : 0;
      drag.scroller = sc;
    }
    // Near the side of the open motifs' row: scroll it sideways to reach the panels out of view
    const row = $('#panels'), rr = row.getBoundingClientRect();
    drag.side = ev.clientY > rr.top && ev.clientY < rr.bottom ? (ev.clientX < rr.left + 40 && ev.clientX > rr.left - 30 ? -1 : ev.clientX > rr.right - 40 && ev.clientX < rr.right + 30 ? 1 : 0) : 0;
  }
  setInterval(() => {
    if (!drag || !drag.on) return;
    if (drag.scroll && drag.scroller) drag.scroller.scrollTop += drag.scroll * 14;
    if (drag.side) $('#panels').scrollLeft += drag.side * 18;
  }, 30);
  document.addEventListener('pointermove', (ev) => {
    if (!drag || ev.pointerId !== drag.id) return;
    if (!drag.on) {
      const far = Math.hypot(ev.clientX - drag.x, ev.clientY - drag.y);
      if (drag.touch) { if (far > 8) { clearTimeout(drag.timer); drag = null; } return; }
      if (far < 6) return;
      start(ev);
    }
    ev.preventDefault();
    move(ev);
  }, {passive: false});
  document.addEventListener('touchmove', (ev) => { if (drag && drag.on) ev.preventDefault(); }, {passive: false});
  function end(ev, cancel) {
    if (!drag) return;
    clearTimeout(drag.timer);
    const was = drag;
    drag = null;
    document.body.classList.remove('dragging');
    ghost.hidden = true;
    $$('.dz-target').forEach((x) => x.classList.remove('dz-target'));
    if (!was.on) return;
    was.ended = Date.now();
    lastDragEnd = Date.now();
    if (cancel) { hideMenu(); return; }
    const el = document.elementFromPoint(ev.clientX, ev.clientY);
    const z = el && el.closest('.dz-zone');
    if (z && menu._zones) { const run = menu._zones[+z.dataset.zone]; hideMenu(); if (run) run.run(); return; }
    const t = el && el.closest('[data-drop]');
    if (t && menu._zones && t === menu._target) {
      if (menu._zones.length === 1) { const run = menu._zones[0]; hideMenu(); run.run(); return; }
      pinned = t;
      showMenu(t, menu._zones, true, ev.clientX, ev.clientY);  // let go on the target itself: the choices stay up to click
      return;
    }
    hideMenu();
  }
  let lastDragEnd = 0;
  document.addEventListener('pointerup', (ev) => end(ev, false));
  document.addEventListener('pointercancel', (ev) => end(ev, true));
  menu.addEventListener('click', (ev) => {
    const z = ev.target.closest('.dz-zone');
    if (!z || !pinned) return;
    const run = z.dataset.zone === 'cancel' ? null : menu._zones[+z.dataset.zone];
    hideMenu();
    if (run) run.run();
  });

  // ---------- clicks ----------
  document.addEventListener('click', async (ev) => {
    if (Date.now() - lastDragEnd < 250) { ev.preventDefault(); ev.stopPropagation(); return; }
    const t = ev.target;
    if (pinned && !t.closest('.dz-menu')) { hideMenu(); return; }
    const inPanel = t.closest('[data-panel]');
    if (inPanel && +inPanel.dataset.panel !== S.active && !t.closest('[data-close]')) {
      S.active = +inPanel.dataset.panel;
      $$('.wb-panel').forEach((p) => p.classList.toggle('active', +p.dataset.panel === S.active && S.open.length > 1));
    }
    const d = (k) => { const el = t.closest('[data-' + k + ']'); return el && el.dataset[k.replace(/-(\w)/g, (m, c) => c.toUpperCase())]; };
    let v;
    if ((v = d('view'))) { S.view = v; store.set('view', v); return render(); }
    if ((v = d('tab'))) { S.tab = v; store.set('tab', v); renderTabs(); return renderInbox(); }
    if ((v = d('fold'))) { S.folded.has(v) ? S.folded.delete(v) : S.folded.add(v); store.set('folded', [...S.folded]); return renderTree(); }
    if ((v = d('open2'))) return openMotif(v, true);
    if (t.closest('[data-close]')) return closePanel(+d('close'));
    if (t.id === 'close-all') { S.open = []; resetSelection(); store.set('open', S.open); return render(); }
    if ((v = d('compare'))) { for (const x of v.split('|')) if (S.by[x] && !S.open.includes(x)) openMotif(x, true); return; }
    if ((v = d('rename'))) { const e = S.by[v]; const name = prompt('Rename the motif:', e.name); if (name && name.trim() && name.trim() !== e.name) act({action: 'rename', id: v, name: name.trim()}, `✎ renamed to “${name.trim()}”`); return; }
    if ((v = d('done'))) { const e = S.by[v]; return act({action: 'done', id: v, done: e.done !== 'done'}, e.done === 'done' ? '↺ not done' : `✓ “${e.name}” done`); }
    if ((v = d('alone'))) { const e = S.by[v]; return act({action: 'stands_alone', id: v, alone: !e.stands_alone}, e.stands_alone ? '🧍 suggestions back on' : `🧍 “${e.name}” stands alone`); }
    if ((v = d('alone1'))) return act({action: 'stands_alone', id: v, alone: true}, `🧍 “${S.by[v].name}” stands alone`);
    if ((v = d('delete'))) { const e = S.by[v]; if (confirm(`Delete “${e.name}”?${e.claims.length ? ` Its ${e.claims.length} claims won't be filed again.` : ''}`)) act({action: 'delete', id: v}, `🗑️ deleted “${e.name}”`); return; }
    if ((v = d('unparent'))) { const [c, p] = v.split('|'); return act({action: 'parent', id: c, parent: p, on: false}, `“${S.by[c].name}” is no longer a kind of “${S.by[p].name}”`); }
    if ((v = d('unrelate'))) { const [a, b] = v.split('|'); return act({action: 'unrelate', a, b}, '↔ unrelated'); }
    if ((v = d('keepnote'))) return act({action: 'keep_note', id: v}, '✓ kept the draft note');
    if ((v = d('savenote'))) return saveNote(v);
    if ((v = d('grename'))) { const g = S.data.groups.find((x) => x.id === v); const name = prompt('Rename the group:', g.name); if (name && name.trim()) act({action: 'group_rename', group: v, name: name.trim()}, '✎ group renamed'); return; }
    if ((v = d('gdelete'))) { if (confirm('Delete the group? Its motifs stay, ungrouped.')) act({action: 'group_delete', group: v}, '🗑️ group deleted'); return; }
    if ((v = d('pair'))) {
      const [kind, a, b] = v.split('|'), A = S.by[a], B = S.by[b];
      const body = {merge: {action: 'merge', source: a, target: b}, under: {action: 'parent', id: a, parent: b}, related: {action: 'relate', a, b}, notsame: {action: 'not_same', a, b}}[kind];
      const say = {merge: `⤵ merged “${A.name}” into “${B.name}”`, under: `⊂ “${A.name}” is a kind of “${B.name}”`, related: '↔ related', notsame: '≠ marked different'}[kind];
      return act(body, say);
    }
    if ((v = d('verdict'))) return verdict(v);
    if ((v = d('similar'))) { const [id, i] = v.split('|'); S.extra[id] = {kind: 'similar', items: await getJSON('/motif-similar.json?id=' + id).catch(() => [])}; return fillExtra(id, +i); }
    if ((v = d('closeextra'))) { delete S.extra[v]; return renderPanels(); }
    if ((v = d('bulk'))) return bulk(...v.split('|'));
    if (t.id === 'delete-empty') { const ids = motifs().filter(isEmpty).map((e) => e.id); if (confirm(`Delete ${ids.length} empty motifs?`)) batch(ids.map((id) => ({action: 'delete', id})), `🗑️ deleted ${ids.length} empty motifs`); return; }
    if (t.id === 'add-motif') { const name = prompt('Name the new motif:'); if (name && name.trim()) { const before = new Set(Object.keys(S.by)); if (await act({action: 'add', name: name.trim()}, `✨ made “${name.trim()}”`)) { const n = Object.keys(S.by).find((x) => !before.has(x)); if (n) openMotif(n); } } return; }
    if (t.id === 'add-group') { const name = prompt('Name the new group:'); if (name && name.trim()) act({action: 'group_add', name: name.trim()}, `📁 made “${name.trim()}”`); return; }
    if (t.id === 'help-btn') return $('#help').showModal();
    if ((v = d('cl'))) { const [kind, id] = v.split('|'); return claimAction(kind, id); }
    // claim buttons
    const li = t.closest('.wb-claim');
    if (li && t.closest('[data-inspect]')) return inspect(li);
    if (li && t.closest('.wb-ctext') && !t.closest('[data-select]') && !li.closest('.wb-inspect')) return inspect(li);
    if (li && t.closest('button')) {
      const b = t.closest('button'), c = li.dataset.claim, src = li.dataset.source;
      if (b.dataset.check) return act({action: 'check', claim: c, id: src, answer: 'yes'}, '✓ checked');
      if (b.dataset.unfile) return act({action: 'unfile', claim: c, id: src}, '✕ taken out');
      if (b.dataset.nomotif) { if (confirm('No motif: take it out of every motif, for good?')) act({action: 'no_motif', claim: c}, '∅ no motif'); return; }
      if (b.dataset.correct) { const text = prompt('Correct the wording (the summary, not the source):', c); if (text && text.trim() && text.trim() !== c) act({action: 'correct', claim: c, text: text.trim()}, '✎ corrected'); return; }
      if (b.dataset.detail) return detail(li);
      if (b.dataset.addhere) { const to = b.dataset.addhere; const step = src ? {action: 'also', claim: c, source: src, target: to} : {action: 'file', claim: c, id: to, source: li.dataset.src, ref: li.dataset.ref}; await act(step, `＋ added to “${S.by[to].name}”`); const i = S.open.indexOf(to); if (S.extra[to] && i >= 0) { S.extra[to].items = S.extra[to].items.filter((x) => x.claim !== c); fillExtra(to, i); } return; }
      if (b.dataset.reject) { const to = b.dataset.reject; await act({action: 'reject', claim: c, id: to}, '✕ won’t suggest it again'); const i = S.open.indexOf(to); if (S.extra[to] && i >= 0) { S.extra[to].items = S.extra[to].items.filter((x) => x.claim !== c); fillExtra(to, i); } return; }
    }
    // selecting claims in an open motif
    if (li && t.closest('[data-select]')) {
      const p = li.closest('[data-panel]');
      if (!p) return;
      const i = +p.dataset.panel, rows = $$('.wb-claim', p), k = rows.indexOf(li);
      if (ev.shiftKey && S.last[i] !== null) {
        const [lo, hi] = [Math.min(S.last[i], k), Math.max(S.last[i], k)];
        rows.slice(lo, hi + 1).forEach((r) => S.sel[i].add(r.dataset.claim));
      } else S.sel[i].has(li.dataset.claim) ? S.sel[i].delete(li.dataset.claim) : S.sel[i].add(li.dataset.claim);
      S.last[i] = k;
      return renderPanels();
    }
    if ((v = d('open'))) return openMotif(v, ev.shiftKey || ev.metaKey || ev.ctrlKey);
  });
  function bulk(kind, i) {
    i = +i;
    const id = S.open[i], cs = [...S.sel[i]];
    if (kind === 'clear') { S.sel[i].clear(); return renderPanels(); }
    if (kind === 'unfile') return batch(cs.map((c) => ({action: 'unfile', claim: c, id})), `🗑️ took ${cs.length} out`);
    if (kind === 'check') return batch(cs.map((c) => ({action: 'check', claim: c, id, answer: 'yes'})), `✓ checked ${cs.length}`);
    if (kind === 'no_motif' && confirm(`No motif for ${cs.length} claims: out of every motif, for good?`)) return batch(cs.map((c) => ({action: 'no_motif', claim: c})), `∅ ${cs.length} claims: no motif`);
  }
  async function detail(li) {
    const box = $('.wb-detail', li);
    if (!box.hidden) { box.hidden = true; return; }
    box.hidden = false;
    box.textContent = '⏳';
    const x = await getJSON('/claim-detail.json?claim=' + encodeURIComponent(li.dataset.claim)).catch(() => null);
    if (!x) { box.textContent = '😬 couldn’t load it'; return; }
    box.innerHTML = detailHTML(x, li.dataset.claim);
  }
  function detailHTML(x, claim) {
    const lab = x.label || {};
    return [
      `<b>${esc(x.kind)}</b>`,
      x.title ? (x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>` : esc(x.title)) : '',
      x.quote ? `🗣️ “${esc(x.quote)}”${x.side ? ' · ' + esc(x.side) : ''}` : '',
      x.people ? `🧶 told by ${x.people} people` : '',
      (x.examples || []).slice(0, 3).map((t) => `<q>${esc(t)}</q>`).join(''),
      x.summary ? esc(x.summary) : '',
      ['genre', 'villain', 'victim', 'hero'].filter((k) => lab[k]).map((k) => `${k}: ${esc(lab[k])}`).join(' · '),
      (() => { const w = [].concat(x.model_words || []).filter((m) => m && m !== claim); return w.length ? `the model's words: ${w.map((m) => '“' + esc(m) + '”').join(' · ')}` : ''; })(),
    ].filter(Boolean).map((s) => `<div>${s}</div>`).join('');
  }
  async function verdict(answer) {
    const x = JSON.parse($('#inbox').dataset.check || 'null');
    if (!x) return;
    if (answer === 'skip') { S.checkAt += 1; return renderInbox(); }
    await act({action: 'check', claim: x.claim, id: x.id, answer}, answer === 'yes' ? '✓ yes' : answer === 'no' ? '✗ taken out' : '🤷 not sure');
  }
  function saveNote(id) {
    const ta = $(`textarea[data-note="${id}"]`);
    if (ta) act({action: 'note', id, note: ta.value.trim()}, '💾 note saved');
  }

  // ---------- typing ----------
  let qTimer = null;
  $('#q').addEventListener('input', (ev) => {
    S.q = ev.target.value;
    clearTimeout(qTimer);
    qTimer = setTimeout(async () => {
      const words = qWords();
      S.claimHits = words.length && S.q.length > 2 ? await getJSON('/claims.json?q=' + encodeURIComponent(words.filter((w) => !w.startsWith('#')).join(' '))).catch(() => []) : [];
      renderTree();
    }, 180);
    renderTree();
  });
  $('#q').addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { const first = $('#tree .wb-row'); if (first) openMotif(first.dataset.id, ev.shiftKey); }
    if (ev.key === 'Escape') { ev.target.value = ''; S.q = ''; S.claimHits = []; renderTree(); }
  });
  $('#sort').addEventListener('change', (ev) => { S.sort = ev.target.value; store.set('sort', S.sort); renderTree(); });
  document.addEventListener('input', (ev) => {
    const t = ev.target;
    if (t.dataset.note !== undefined) { const b = $(`[data-savenote="${t.dataset.note}"]`); if (b) b.disabled = t.value.trim() === ((S.by[t.dataset.note] || {}).note || ''); }
    if (t.id === 'cl-q') { S.claimQ = t.value; claimResults(); }
    if (t.id === 'unfiled-q') { S.unfiledQ = t.value; clearTimeout(unfiledTimer); unfiledTimer = setTimeout(loadUnfiled, 200); }
    if (t.dataset.claimsearch !== undefined) {
      const [id, i] = t.dataset.claimsearch.split('|');
      clearTimeout(t._timer);
      t._timer = setTimeout(async () => {
        if (!t.value.trim()) { delete S.extra[id]; $('#extra-' + i).innerHTML = ''; return; }
        S.extra[id] = {kind: 'search', q: t.value, items: await getJSON('/claims.json?q=' + encodeURIComponent(t.value)).catch(() => [])};
        fillExtra(id, +i);
      }, 220);
    }
  });
  document.addEventListener('change', (ev) => {
    const t = ev.target;
    if (t.dataset.group !== undefined) act({action: 'group_assign', id: t.dataset.group, group: t.value || null}, '📁 moved');
  });
  document.addEventListener('keydown', (ev) => {
    const typing = ev.target.closest && ev.target.closest('input, textarea, select');
    if (ev.key === 'Escape') { if (drag) end(ev, true); hideMenu(); }
    if (ev.target.dataset && ev.target.dataset.note !== undefined && ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); saveNote(ev.target.dataset.note); return; }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z' && !typing) { ev.preventDefault(); undo(); return; }
    if (typing || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (ev.key === '/') { ev.preventDefault(); $('#q').focus(); return; }
    if (S.tab === 'check' && $('#inbox').dataset.check) {
      const k = {y: 'yes', n: 'no', u: 'unsure', s: 'skip'}[ev.key.toLowerCase()];
      if (k) { ev.preventDefault(); verdict(k); }
    }
  });

  // ---------- toast ----------
  let toastTimer = null;
  function toast(text, bad, withUndo) {
    const t = $('#toast');
    t.hidden = false;
    t.className = 'wb-toast' + (bad ? ' bad' : '');
    t.innerHTML = esc(text) + (withUndo ? ' <button class="wb-mini" id="toast-undo">↶ undo</button>' : '');
    const u = $('#toast-undo');
    if (u) u.addEventListener('click', undo);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, bad ? 7000 : 4500);
  }

  reload().catch((e) => { $('#panels').innerHTML = `<p class="wb-faint">😬 couldn’t load the index: ${esc(e.message)}</p>`; });
})();
