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
    checkAt: 0, extra: {}, claimHits: [], groupBy: store.get('groupby', 'group'),
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
    ['nogenre', '🎭 no genre', (e) => !(e.facets || {}).genre],
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
    // Sections: the person's groups, or a facet's values (genre)
    const by = S.groupBy;
    const groups = by === 'genre' ? [...(S.data.facets.genre || []).map((v) => ({id: v, name: v})), {id: '', name: 'no genre yet'}]
      : [...S.data.groups, {id: '', name: 'Ungrouped'}];
    let html = '';
    if (words.length) html += claimHitsHTML(words);
    if (flat) {
      html += `<div class="wb-group"><div class="wb-ghead">${shown.length} motif${shown.length === 1 ? '' : 's'}</div>${shown.map((e) => row(e, 0, false)).join('')}</div>`;
    } else {
      const ids = new Set(shown.map((e) => e.id));
      shownIds = ids;
      for (const g of groups) {
        const inG = shown.filter((e) => sectionsOf(e).includes(g.id));
        if (!inG.length && !g.id) continue;
        // Roots: no parent in this section. Kinds nest under their parents wherever those are (a motif with two parents
        // shows under both), and in their own groups too: a motif can be in several groups
        const roots = inG.filter((e) => !e.parents.some((p) => ids.has(p) && sectionsOf(S.by[p]).includes(g.id)));
        const fold = 'g:' + by + ':' + g.id, folded = S.folded.has(fold) || (by === 'genre' && !inG.length);
        html += `<div class="wb-group${inG.length ? '' : ' wb-empty-sec'}" data-drop="${by === 'genre' ? 'facet' : 'group'}" data-g="${esc(g.id)}">
          <div class="wb-ghead"><button class="wb-fold" data-fold="${esc(fold)}">${folded ? '▸' : '▾'}</button>
            <span class="wb-gname">${by === 'genre' ? '🎭 ' : g.id ? '📁 ' : '🗃️ '}${esc(g.name)}</span> <i>${inG.length}</i>
            ${g.id && by !== 'genre' ? `<span class="wb-gtools"><button class="wb-mini" data-grename="${g.id}" title="rename">✎</button><button class="wb-mini" data-gdelete="${g.id}" title="delete the group (its motifs stay)">🗑️</button></span>` : ''}</div>
          ${folded ? '' : roots.map((e) => branch(e, 0, g.id, new Set())).join('')}</div>`;
      }
    }
    $('#tree').innerHTML = html || '<p class="wb-empty">🦗 nothing here</p>';
  }
  const sectionsOf = (e) => (S.groupBy === 'genre' ? [(e.facets || {}).genre || ''] : (e.groups || []).length ? e.groups : ['']);
  let shownIds = new Set();
  function branch(e, depth, gid, seen) {
    if (seen.has(e.id)) return '';
    seen = new Set(seen).add(e.id);
    const kids = (S.kids[e.id] || []).map((k) => S.by[k]).filter((k) => k && shownIds.has(k.id)).sort(SORTS[S.sort]);
    const folded = S.folded.has('m:' + e.id);
    return row(e, depth, kids.length ? (folded ? '▸' : '▾') : '', gid) + (folded ? '' : kids.map((k) => branch(k, depth + 1, gid, seen)).join(''));
  }
  function row(e, depth, fold, gid) {
    const n = newCount(e), ns = noteState(e);
    const badges = [e.done === 'done' ? '<b title="done">✓</b>' : '', n ? `<b class="b-new" title="new since done">🆕${n}</b>` : '',
      ns === 'none' ? '<b title="no note yet" class="b-faint">📝</b>' : ns === 'draft' ? '<b title="the note is a draft">🤖</b>' : '',
      e.stands_alone ? '<b title="stands alone">🧍</b>' : ''].join('');
    const open = S.open.indexOf(e.id);
    return `<div class="wb-row${open >= 0 ? ' open o' + (open % COLORS) : ''}" style="--depth:${depth}" data-drag="motif" data-drop="motif" data-id="${e.id}" data-open="${e.id}">
      ${fold ? `<button class="wb-fold" data-fold="m:${e.id}">${fold}</button>` : '<span class="wb-fold-sp"></span>'}
      <span class="wb-rname">${esc(e.name)}</span>${gid !== undefined && S.groupBy !== 'genre' ? elsewhere(e, gid) : ''}<span class="wb-badges">${badges}</span><i class="wb-n">${e.claims.length}</i>
      <button class="wb-mini wb-side" data-open2="${e.id}" title="open it too, under the others (compare)">⧉</button></div>`;
  }
  // The other groups a motif is in, beside it in the tree (it shows in each, and under its broader motif)
  function elsewhere(e, gid) {
    const other = (e.groups || []).filter((g) => g !== gid).map((g) => (S.data.groups.find((x) => x.id === g) || {}).name).filter(Boolean);
    return other.length ? `<span class="wb-also" title="also in ${esc(other.join(', '))}">📁${other.length > 1 ? other.length : ''}</span>` : '';
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
        <p>Click one on the left to open it here; <b>Shift-click</b> or ⧉ opens another under it.</p>
        <p>Then drag: claims onto motifs, motifs onto motifs, motifs onto groups. Hover a target to see your choices. 🫳</p>
        <p class="wb-faint">The inbox on the right has decisions waiting: ✅ checks, 🔗 pairs, 1️⃣ singles, 📥 unfiled claims.</p></div>`;
      return;
    }
    box.dataset.count = S.open.length;
    $('#work-head').innerHTML = S.open.length > 1 ? `<b>${S.open.length}</b> open, one under another · a click opens in the outlined one; <b>Shift-click</b> or ⧉ adds another <button class="wb-mini" id="close-all">✕ close all</button>`
      : 'Shift-click a motif (or ⧉) to open another under this one, as many as you like';
    // A note being written survives a re-render (any action anywhere redraws the panels; Oct 6 notes were lost so)
    const drafts = {};
    document.querySelectorAll('textarea[data-note]').forEach((t) => {
      if (t.value.trim() !== ((S.by[t.dataset.note] || {}).note || '')) drafts[t.dataset.note] = {v: t.value, at: t.selectionStart, focus: document.activeElement === t};
    });
    box.innerHTML = S.open.map((id, i) => panel(S.by[id], i)).join('');
    S.open.forEach((id, i) => { if (S.extra[id]) fillExtra(id, i); });
    for (const [id, d] of Object.entries(drafts)) {
      const t = $(`textarea[data-note="${id}"]`);
      if (!t) continue;
      t.value = d.v;
      if (d.focus) { t.focus(); t.setSelectionRange(d.at, d.at); }
    }
  }
  function panel(e, i) {
    const kids = S.kids[e.id] || [];
    const mine = e.groups || [];
    const groups = S.data.groups.filter((g) => !mine.includes(g.id)).map((g) => `<option value="${g.id}">📁 ${esc(g.name)}</option>`).join('');
    const tags = mine.map((g) => `<span class="wb-gtag">📁 ${esc((S.data.groups.find((x) => x.id === g) || {}).name || g)}<button class="wb-x" data-ungroup="${e.id}|${g}" title="out of this group">✕</button></span>`).join('');
    const ns = noteState(e);
    const shared = {};
    for (const c of e.claims) for (const o of motifs()) if (o.id !== e.id && o.claims.some((x) => x.claim === c.claim)) shared[o.id] = (shared[o.id] || 0) + 1;
    const sharedIds = Object.keys(shared).sort((a, b) => shared[b] - shared[a]);
    const order = [...e.claims].sort((a, b) => (b.new - a.new));
    const sel = S.sel[i] || (S.sel[i] = new Set());
    return `<article class="wb-panel p${i % COLORS}${i === S.active && S.open.length > 1 ? ' active' : ''}" data-drop="motif" data-id="${e.id}" data-panel="${i}">
      <header class="wb-phead">
        <div class="wb-titlerow"><h2 class="wb-pname" data-drag="motif" data-id="${e.id}" title="click to rename · drag onto another motif or a group">${esc(e.name)}</h2>
          <button class="wb-btn wb-close" data-close="${i}" title="close this motif">✕</button></div>
        <span class="wb-pid">${e.id} · ${e.claims.length} claim${e.claims.length === 1 ? '' : 's'}${e.curated ? ' · ✋ by hand' : ''}${e.first_seen ? ' · since ' + esc(e.first_seen.slice(0, 10)) : ''}</span>
        <span class="wb-ptools">
          <button class="wb-btn" data-rename="${e.id}" title="rename">✎ rename</button>
          ${e.done === 'done' ? `<span class="wb-state done" title="you've looked over its claims; it can appear on the site">✅ Done</span><button class="wb-mini" data-done="${e.id}" title="it goes back to not done, and off the site">unmark done</button>`
            : e.done === 'new' ? `<span class="wb-state new" title="marked done, but claims came in since; the site shows only the ones you saw">🆕 Done, ${newCount(e)} new since</span><button class="wb-btn yes" data-done="${e.id}" title="you've looked at the new claims too">mark done again</button>`
            : `<span class="wb-state todo" title="not looked over yet; it stays off the site">⏳ Not done yet</span><button class="wb-btn yes" data-done="${e.id}" title="you've looked over its claims: it can go on the site">mark as done</button>`}
          ${tags}${groups ? `<select data-group="${e.id}" title="put it in a group as well (a motif can be in several)"><option value="">📁 ＋ group…</option>${groups}</select>` : ''}
          <select data-genre="${e.id}" title="its genre"><option value="">🎭 no genre</option>${(S.data.facets.genre || []).map((g) => `<option${(e.facets || {}).genre === g ? ' selected' : ''}>${esc(g)}</option>`).join('')}</select>
          ${isSingle(e) || e.stands_alone ? `<button class="wb-btn${e.stands_alone ? ' on' : ''}" data-alone="${e.id}" title="a single motif that needs no partner">🧍 ${e.stands_alone ? 'stands alone' : 'stands alone?'}</button>` : ''}
          <button class="wb-btn" data-delete="${e.id}" title="delete this motif (its claims aren't filed again)">🗑️</button>
        </span>
      </header>
      <div class="wb-rels">
        <div><span class="wb-rlabel">↳ a kind of</span> ${e.parents.map((p) => chip(p, `<button class="wb-x" data-unparent="${e.id}|${p}" title="not a kind of it">✕</button>`)).join(' ') || '<span class="wb-faint">—</span>'}</div>
        <div><span class="wb-rlabel">⤷ its kinds</span> ${kids.map((k) => chip(k, `<button class="wb-x" data-unparent="${k}|${e.id}" title="not a kind of this">✕</button>`)).join(' ') || '<span class="wb-faint">—</span>'}</div>
        <div><span class="wb-rlabel">↔ related</span> ${e.related.map((r) => chip(r, `<button class="wb-x" data-unrelate="${e.id}|${r}" title="not related">✕</button>`)).join(' ') || '<span class="wb-faint">—</span>'}</div>
        ${sharedIds.length ? `<div><span class="wb-rlabel">🤝 shares claims with</span> ${sharedIds.slice(0, 8).map((o) => chip(o, `<b class="wb-shared">${shared[o]}</b>`)).join(' ')}</div>` : ''}
      </div>
      <div class="wb-note ${ns}">
        <label>📝 note <span class="wb-ntag">${ns === 'none' ? 'none yet' : ns === 'draft' ? '🤖 draft by ' + (e.note_by === 'claude' ? 'Claude' : 'the model') : 'yours'}</span></label>
        <textarea data-note="${e.id}" rows="2" placeholder="what this motif is, in a sentence (saves when you click away or press Enter; Shift+Enter for a new line)">${esc(e.note || '')}</textarea>
        ${ns === 'draft' ? `<div class="wb-nbtns"><button class="wb-btn" data-keepnote="${e.id}">✓ keep the draft</button></div>` : ''}
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
    const ways = c.variants && c.variants.length ? `<b class="wb-ways" title="also told as: ${esc(c.variants.join(' · '))}">≡ ${c.variants.length + 1} ways</b>` : '';
    return `<li class="wb-claim${selected ? ' sel' : ''}" ${claimData(c, e.id)} data-drop="sameclaim">
      <span class="wb-ctext" data-select="1">${tags}${ways}${esc(c.claim)}</span>
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
  const TABS = [['stats', '📊'], ['claim', '🔍 claim'], ['check', '✅ check'], ['pairs', '🔗 pairs'], ['singles', '1️⃣ singles'], ['claims', '📥 unfiled'], ['empty', '🫙 empty']];
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
    if (tab === 'stats') return renderStats(box);
    if (tab === 'check') {
      const q = await queue('check');
      if (S.tab !== tab) return;
      // One claim at a time (the biggest motifs' first), with every motif it's in to tick or take away
      const seen = new Set(), items = [];
      for (const x of (q.error ? [] : q)) {
        if (seen.has(x.claim)) continue;
        seen.add(x.claim);
        if (motifsOf(x.claim).some((e) => e.claims.some((c) => c.claim === x.claim && !c.checked))) items.push(x);
      }
      // ◀ goes back along the claims you've seen (even one you've finished, which has left the list)
      // The claim on screen stays until next ▶ or ✓ all fit: ticking or taking out its last motif, adding one, or
      // rewording it leaves it here for the next edit (it used to jump to the next claim)
      const back = S.checkBack;
      S.checkItems = items;
      let x;
      if (back) x = {claim: back, source: (motifsOf(back)[0] || {claims: []}).claims.find((c) => c.claim === back)?.source || ''};
      else if (S.checkHere) x = S.checkHere;
      else {
        x = items[S.checkAt % Math.max(items.length, 1)];
        if (x) S.checkHere = {claim: x.claim, source: x.source};
      }
      if (!x) { box.innerHTML = '<div class="wb-welcome"><div class="wb-big">🎉</div><p>Nothing to check right now.</p></div>'; S.queues.check = null; return; }
      S.claim = {claim: x.claim, src: x.source, from: null};
      renderClaim(box, true, items.length);
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
  // ---------- the catalog's numbers, now and day by day ----------
  async function renderStats(box) {
    box.innerHTML = '<p class="wb-faint">⏳</p>';
    const m = await getJSON('/workbench-metrics.json').catch((e) => ({error: e.message}));
    if (S.tab !== 'stats') return;
    if (m.error) { box.innerHTML = `<p class="wb-faint">😬 ${esc(m.error)}</p>`; return; }
    const n = m.now;
    const tile = (emoji, big, small, color) => `<li style="--sticker: ${color}"><span class="sticker-emoji">${emoji}</span><b>${big}</b><span>${small}</span></li>`;
    const days = m.days;
    // A small bar chart per measure: one bar a day (stacked when there are parts), the day under it
    const bars = (title, keys, colors, note) => {
      const totals = days.map((d) => keys.reduce((t, k) => t + (d[k] || 0), 0));
      const peak = Math.max(1, ...totals);
      if (!totals.some(Boolean)) return '';
      return `<div class="wb-stat"><h3>${title}</h3><div class="wb-daybars">${days.map((d, i) => `<div class="wb-daybar" title="${d.day}: ${keys.map((k) => `${k.replace(/_/g, ' ')} ${d[k] || 0}`).join(', ')}">
        <div class="wb-stack" style="height: ${Math.round(100 * totals[i] / peak)}%">${keys.map((k, j) => d[k] ? `<span style="flex: ${d[k]}; background: ${colors[j]}"></span>` : '').join('')}</div>
        <i>${totals[i] || ''}</i><small>${d.day.slice(5)}</small></div>`).join('')}</div>
        ${keys.length > 1 ? `<p class="wb-faint">${keys.map((k, j) => `<span class="sc-key" style="--key: ${colors[j]}"></span>${k.replace(/^\w+_/, '').replace(/_/g, ' ')}`).join(' · ')}${note ? ' · ' + note : ''}</p>` : note ? `<p class="wb-faint">${note}</p>` : ''}</div>`;
    };
    // The shape over days, from the daily snapshots (they begin Oct 6)
    const shaped = days.filter((d) => d.shape);
    const line = (key, label) => shaped.length ? `<tr><td>${label}</td>${shaped.map((d) => `<td>${d.shape[key]}%</td>`).join('')}</tr>` : '';
    box.innerHTML = `<div class="wb-stats-tab">
      <h3>📊 the catalog now</h3>
      <ul class="story-stickers wb-stat-tiles">
        ${tile('🧩', n.motifs, 'motifs', '#00c2a8')}${tile('💬', n.claims, `claims (${n.filings} filings, ${n.per_motif} a motif)`, '#3a86ff')}
        ${tile('1️⃣', n.singles + '%', 'single-claim motifs', '#ffc400')}${tile('🌳', n.in_tree + '%', 'in the kinds tree', '#8a5cff')}
        ${tile('🎭', n.with_genre + '%', 'with a genre', '#ff6b1a')}${tile('✅', n.done + '%', 'done by you', '#7fd97a')}
        ${tile('📝', n.your_notes + '%', 'with your note', '#ff4fa3')}${tile('☑️', n.checked + '%', 'of filings checked', '#a9a9b8')}
        ${tile('∅', n.no_motif, 'claims with no motif', '#e2e2ea')}${tile('≡', n.variants, 'claims folded in as the same', '#ece4ff')}
      </ul>
      ${bars('✨ new motifs a day', ['new_motifs'], ['#00c2a8'], 'the model makes most; a merge doesn\'t take one back')}
      ${bars('🤖 how the model filed claims', ['filed_matched', 'filed_new', 'filed_none'], ['#3a86ff', '#ffc400', '#c9c9d4'], 'counted from Oct 6: into motifs already there, into a new one, or none')}
      ${bars('✋ your changes a day', ['actions'], ['#ff4fa3'], 'merges, moves, kinds, notes, checks… in the curation log')}
      ${bars('☑️ your checks', ['checks_yes', 'checks_no', 'checks_unsure'], ['#7fd97a', '#ff6b6b', '#c9c9d4'])}
      ${shaped.length ? `<div class="wb-stat"><h3>🧱 the shape, day by day</h3><table class="wb-shape"><tr><th></th>${shaped.map((d) => `<th>${d.day.slice(5)}</th>`).join('')}</tr>
        ${line('singles', 'single-claim')}${line('two_plus', '2+ claims')}${line('in_tree', 'in the tree')}${line('with_genre', 'with a genre')}${line('done', 'done')}${line('your_notes', 'your notes')}</table>
        <p class="wb-faint">a snapshot after each filing run, from Oct 6</p></div>` : ''}
    </div>`;
  }

  // ---------- one claim, inspected: where it came from, every motif it's in, and moving it ----------
  function motifsOf(text) { return motifs().filter((e) => e.claims.some((c) => c.claim === text)); }
  function inspect(li) {
    S.claim = {claim: li.dataset.claim, src: li.dataset.src, ref: li.dataset.ref, from: null};
    S.tab = 'claim';
    S.claimQ = '';
    renderTabs();
    renderInbox();
  }
  function renderClaim(box, check, left) {
    const c = S.claim;
    if (!c) {
      box.innerHTML = '<div class="wb-welcome"><div class="wb-big">🔍</div><p>Click a claim’s 🔍 or its #id (or a claim in the search results) to open it here: where it came from, every motif it’s in, and where to move it.</p></div>';
      return;
    }
    const ins = motifsOf(c.claim);
    const first = ins[0], rec = first && first.claims.find((x) => x.claim === c.claim);
    const src = (rec && rec.source) || c.src || '';
    const verdict = check ? `<div class="wb-checkbar">
        <span class="wb-faint">${left} claim${left === 1 ? '' : 's'} to check (${S.data.to_check} filings) · tick each motif that fits, take away the rest</span>
        <span class="wb-checkbtns">
          <button class="wb-btn" data-verdict="prev" title="the claim before">◀ <kbd>←</kbd></button>
          <button class="wb-btn yes" data-verdict="allyes" title="every motif left fits: tick them all and go on">✓ all fit, next <kbd>Y</kbd></button>
          <button class="wb-btn" data-verdict="next" title="leave it for now">next ▶ <kbd>→</kbd></button>
        </span></div>` : '';
    box.classList.toggle('checking', !!check);
    box.innerHTML = verdict + `<div class="wb-inspect" data-drop="claim">
      <blockquote class="wb-claim big" ${claimData({claim: c.claim, source: src, ref: (rec && rec.ref) || c.ref}, first ? first.id : '')}><span class="wb-bigtext" title="click to correct the wording">${esc(c.claim)}</span>
        <span class="wb-meta">${rec ? '#' + rec.id + ' · ' : ''}${esc(SOURCE[src] || src)} · drag me onto a motif · <button class="wb-mini" data-editclaim="1" title="correct the wording (our summary, not the source)">✎ correct wording</button></span></blockquote>
      ${rec && rec.variants && rec.variants.length ? `<p class="wb-faint">≡ also told as: ${rec.variants.map((v) => '“' + esc(v) + '”').join(' · ')}</p>` : ''}
      <h3>🧩 all its motifs <i>${ins.length}</i> <span class="wb-faint">take one away with ✕, add more below or by dropping a motif here</span></h3>
      ${ins.map((e) => { const r = e.claims.find((x) => x.claim === c.claim); return `<div class="wb-motifrow${r.checked === 'yes' ? ' fits' : ''}">${chip(e.id)}
        ${e.note ? `<span class="wb-mnote">${esc(e.note)}</span>` : '<span class="wb-mnote wb-faint">no note yet</span>'}
        <span class="wb-sbtns">${r.checked === 'yes' ? '<span class="wb-fits">✓ fits</span>' : `<button class="wb-btn yes" data-cl="check|${e.id}" title="it belongs here">✓ fits</button>`}
        <button class="wb-btn no" data-cl="unfile|${e.id}" title="take it out of this motif">✕ take out</button></span></div>`; }).join('')
        || '<p class="wb-faint">📥 not in any motif</p>'}
      <h3>➕ add it to another motif</h3>
      <label class="wb-addsearch">🔎 <input type="search" id="cl-q" placeholder="find a motif" value="${esc(S.claimQ || '')}" autocomplete="off"></label>
      <div id="cl-results"></div>
      <div class="wb-sbtns wb-clacts">
        <button class="wb-btn" data-cl="new|">✨ new motif with it</button>
        ${ins.length ? '<button class="wb-btn" data-cl="nomotif|">∅ no motif</button>' : ''}
      </div>
      <h3>📜 where it came from</h3><div class="wb-detail" id="cl-detail">⏳</div>
      <h3>≡ claims like this one <span class="wb-faint">closest in meaning; fold one in if it's the same claim told another way</span></h3>
      <ul class="wb-claims" id="cl-similar"><li class="wb-faint">⏳</li></ul>
    </div>`;
    claimResults();
    getJSON('/claim-detail.json?claim=' + encodeURIComponent(c.claim)).then((x) => {
      const d = $('#cl-detail');
      if (d) d.innerHTML = detailHTML(x, c.claim);
    }).catch(() => { const d = $('#cl-detail'); if (d) d.textContent = '😬 couldn’t load it'; });
    loadSimilarClaims(c.claim, ins.length > 0);
  }
  async function loadSimilarClaims(claim, filed) {
    const items = await getJSON('/claim-similar.json?claim=' + encodeURIComponent(claim)).catch(() => null);
    const box = $('#cl-similar');
    if (!box || !S.claim || S.claim.claim !== claim) return;
    if (!items) { box.innerHTML = '<li class="wb-faint">😬 couldn’t compare (are the embeddings up?)</li>'; return; }
    box.innerHTML = items.map((x) => {
      const src = x.motifs[0] ? x.motifs[0].id : '';
      // Fold that one into this one (if this one is filed); or, for a claim not filed yet, keep that one instead
      const fold = filed ? `<button class="wb-mini" data-fold-in="1" title="the same claim: fold it into this one">≡ same claim</button>`
        : x.motifs.length ? `<button class="wb-mini" data-fold-to="1" title="the same claim: fold this one into it">≡ same (keep that)</button>` : '';
      return `<li class="wb-claim mini${x.motifs.length ? '' : ' unfiled'}" ${claimData(x, src)}><span class="wb-ctext">${esc(x.claim)}</span>
        <span class="wb-meta">${x.motifs.length ? 'in ' + x.motifs.map((m) => chip(m.id)).join(' ') : '📥 not filed · ' + esc(SOURCE[x.source] || x.source || '')} · alike ${x.score.toFixed(2)}</span>
        <span class="wb-cbtns wb-show">${fold}</span></li>`;
    }).join('') || '<li class="wb-faint">🦗 nothing close</li>';
  }
  function claimResults() {
    const box = $('#cl-results');
    if (!box || !S.claim) return;
    const words = (S.claimQ || '').toLowerCase().split(/\s+/).filter(Boolean);
    const ins = motifsOf(S.claim.claim), inIds = new Set(ins.map((e) => e.id));
    if (!words.length) { box.innerHTML = '<p class="wb-faint">type to find a motif, or drag the claim onto one</p>'; return; }
    const found = motifs().filter((e) => !inIds.has(e.id) && words.every((w) => (e.id + ' ' + e.name + ' ' + (e.note || '')).toLowerCase().includes(w)))
      .sort(SORTS.size).slice(0, 12);
    // The button first, where the eye lands after typing; the motif's name after it (clicking it opens the motif). No
    // 'move here' (Oct 6: never used, easy to hit by mistake): add it, then ✕ it out of the old one
    box.innerHTML = found.map((e) => `<div class="wb-sug wb-pick"><span class="wb-pickbtns">
        <button class="wb-btn yes" data-cl="add|${e.id}" title="file it here too">＋ add</button></span>${chip(e.id)}</div>`).join('')
      || '<p class="wb-faint">🦗 no motif matches</p>';
    // A new motif named what was typed, offered whatever else matched (unless a motif already has that very name)
    const typed = S.claimQ.trim(), taken = motifs().some((e) => e.name.toLowerCase() === typed.toLowerCase());
    if (!taken) box.innerHTML += `<button class="wb-btn yes wb-newnamed" data-cl="newnamed|" id="cl-new">✨ new motif “${esc(typed)}” with it</button>`;
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
    if (kind === 'newnamed') {
      const n = (S.claimQ || '').trim();
      if (!n) return;
      S.claimQ = '';
      return act({action: 'new_with', name: n, claims: [{claim: c.claim, source: first ? first.id : '', src, ref, mode: 'also'}]}, `✨ made “${n}”`);
    }
    if (kind === 'new') {
      return ask(null, 'Name the new motif', (S.claimQ || '').trim() || c.claim.slice(0, 80)).then((n) => n && act({action: 'new_with', name: n, claims: [{claim: c.claim, source: first ? first.id : '', src, ref, mode: 'also'}]}, `✨ made “${n}”`));
    }
    if (kind === 'correct') {
      return ask(null, 'Correct the wording (our summary, not the source)', c.claim, true).then((text) => {
        if (text && text !== c.claim) act({action: 'correct', claim: c.claim, text}, '✎ corrected').then((ok) => { const old = c.claim; if (ok) { S.claim.claim = text; renamed(old, text); renderInbox(); } });
      });
    }
    if (kind === 'nomotif') return sure(null, 'No motif: take it out of every motif, for good?').then((ok) => ok && act({action: 'no_motif', claim: c.claim}, '∅ no motif'));
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
    if (drop === 'sameclaim' || (drop === 'claim' && item.kind === 'claim')) {
      // A claim dropped on a claim: one claim told two ways. Over a claim in an open motif, the motif's own choices too
      const target = drop === 'claim' ? S.claim && S.claim.claim : t.dataset.claim;
      const panelEl = drop === 'sameclaim' && t.closest('[data-drop="motif"]');
      const base = panelEl ? zones(item, panelEl) : [];
      if (item.kind !== 'claim' || !target || !motifsOf(target).length) return base;
      const folding = item.claims.filter((c) => c.claim !== target);
      if (!folding.length) return base;
      return [...base, {label: '≡ the same claim as this one', say: `fold ${claimsName({claims: folding})} into “${target.slice(0, 60)}…”: one claim, told ${folding.length + 1} ways`,
        run: () => batch(folding.map((c) => ({action: 'same_claim', variant: c.claim, canonical: target})), `≡ ${claimsName({claims: folding})} folded into one claim`)}];
    }
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
        const named = (mode) => () => ask(t, 'Name the new motif', cs.length === 1 ? cs[0].claim.slice(0, 80) : '')
          .then((name) => name && act({action: 'new_with', name, claims: cs.map((c) => ({...c, mode}))}, `✨ made “${name}”`));
        return cs.some((c) => c.source)
          ? [{label: '⇢ move into a new motif', say: 'move them out into a motif of their own', run: named('move')},
            {label: '＋ copy into a new motif', say: 'start a new motif with them, keeping where they are', run: named('also')}]
          : [{label: '✨ new motif', say: 'start a new motif with them', run: named('file')}];
      }
      if (drop === 'nomotif') {
        return [{label: '∅ no motif', say: 'they tell no recurring story: out of every motif, never filed again', run: () =>
          sure(t, `Take ${claimsName(item)} out of every motif, for good?`).then((ok) => ok && batch(cs.map((c) => ({action: 'no_motif', claim: c.claim})), `∅ ${claimsName(item)}: no motif`))}];
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
    if (drop === 'facet') {
      const value = t.dataset.g || null;
      if (((A.facets || {}).genre || null) === value) return [];
      return [{label: value ? '🎭 genre: ' + value : '🎭 no genre', say: `“${A.name}” is a ${value || 'motif of no genre yet'}`,
        run: () => act({action: 'facet', id: a, facet: 'genre', value}, `🎭 “${A.name}”: ${value || 'no genre'}`)}];
    }
    if (drop === 'group') {
      const g = t.dataset.g || null, mine = A.groups || [];
      if (!g) return mine.length ? [{label: '🗃️ out of every group', say: `“${A.name}” in no group`, run: () => act({action: 'group_assign', id: a, group: null}, `🗃️ “${A.name}”: no group`)}] : [];
      if (mine.includes(g)) return [];
      const name = (S.data.groups.find((x) => x.id === g) || {}).name;
      const also = {label: '📁 into this group', say: mine.length ? `“${A.name}” in ${name} as well, staying in its others` : `put “${A.name}” in ${name}`,
        run: () => act({action: 'group_member', id: a, group: g}, `📁 “${A.name}” in ${name}`)};
      return mine.length ? [also, {label: '⇢ only this group', say: `“${A.name}” moves to ${name}, out of its others`,
        run: () => act({action: 'group_assign', id: a, group: g}, `📁 “${A.name}” → ${name}`)}] : [also];
    }
    if (drop === 'trash') {
      return [{label: '🗑️ delete it', say: 'delete the motif (its claims aren’t filed again)', run: () =>
        sure(t, `Delete “${A.name}”? Its ${A.claims.length} claims won't be filed again.`, '🗑️ delete it').then((ok) => ok && act({action: 'delete', id: a}, `🗑️ deleted “${A.name}”`))}];
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
    groupTray(drag.item);
    move(ev);
  }
  // Dragging a motif: every group (or genre) pinned above the tree as a drop, so one far up the list is in reach
  function groupTray(item) {
    const tray = $('#gtray');
    if (!item || item.kind !== 'motif') { tray.hidden = true; return; }
    const genre = S.groupBy === 'genre';
    const all = genre ? [...(S.data.facets.genre || []).map((v) => ({id: v, name: v})), {id: '', name: 'no genre'}]
      : [...S.data.groups, {id: '', name: 'no group'}];
    tray.innerHTML = `<span class="wb-faint">${genre ? '🎭 genres' : '📁 groups'}:</span>` + all.map((g) =>
      `<span class="wb-gchip" data-drop="${genre ? 'facet' : 'group'}" data-g="${esc(g.id)}">${genre ? '🎭' : g.id ? '📁' : '🗃️'} ${esc(g.name)}</span>`).join('');
    tray.hidden = false;
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
    $('#gtray').hidden = true;
    $$('.dz-target').forEach((x) => x.classList.remove('dz-target'));
    if (!was.on) return;
    was.ended = Date.now();
    lastDragEnd = Date.now();
    if (cancel) { hideMenu(); return; }
    const el = document.elementFromPoint(ev.clientX, ev.clientY);
    const z = el && el.closest('.dz-zone');
    if (z && menu._zones) { const run = menu._zones[+z.dataset.zone]; lastAnchor = menu._target; hideMenu(); if (run) run.run(); return; }
    const t = el && el.closest('[data-drop]');
    if (t && menu._zones && t === menu._target) {
      if (menu._zones.length === 1) { const run = menu._zones[0]; lastAnchor = t; hideMenu(); run.run(); return; }
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
    lastAnchor = menu._target;
    hideMenu();
    if (run) run.run();
  });

  // ---------- clicks ----------
  document.addEventListener('click', async (ev) => {
    if (Date.now() - lastDragEnd < 250) { ev.preventDefault(); ev.stopPropagation(); return; }
    const t = ev.target;
    if (t.closest('.wb-ask')) return;
    lastAnchor = t;
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
    if ((v = d('rename'))) return editTitle(v);
    if (t.closest('.wb-pname') && !t.closest('input')) return editTitle(t.closest('[data-panel]').dataset.id);
    if ((v = d('done'))) { const e = S.by[v]; return act({action: 'done', id: v, done: e.done !== 'done'}, e.done === 'done' ? `“${e.name}” is not done any more` : `✅ “${e.name}” is done`); }
    if ((v = d('alone'))) { const e = S.by[v]; return act({action: 'stands_alone', id: v, alone: !e.stands_alone}, e.stands_alone ? '🧍 suggestions back on' : `🧍 “${e.name}” stands alone`); }
    if ((v = d('alone1'))) return act({action: 'stands_alone', id: v, alone: true}, `🧍 “${S.by[v].name}” stands alone`);
    if ((v = d('delete'))) { const e = S.by[v]; return sure(t, `Delete “${e.name}”?${e.claims.length ? ` Its ${e.claims.length} claims won't be filed again.` : ''}`, '🗑️ delete it').then((ok) => ok && act({action: 'delete', id: v}, `🗑️ deleted “${e.name}”`)); }
    if ((v = d('unparent'))) { const [c, p] = v.split('|'); return act({action: 'parent', id: c, parent: p, on: false}, `“${S.by[c].name}” is no longer a kind of “${S.by[p].name}”`); }
    if ((v = d('unrelate'))) { const [a, b] = v.split('|'); return act({action: 'unrelate', a, b}, '↔ unrelated'); }
    if ((v = d('keepnote'))) return act({action: 'keep_note', id: v}, '✓ kept the draft note');
    if ((v = d('ungroup'))) { const [id, g] = v.split('|'); return act({action: 'group_member', id, group: g, on: false}, '📁 out of the group'); }
    if ((v = d('grename'))) { const g = S.data.groups.find((x) => x.id === v); return ask(t, 'Rename the group', g.name).then((name) => name && act({action: 'group_rename', group: v, name}, '✎ group renamed')); }
    if ((v = d('gdelete'))) return sure(t, 'Delete the group? Its motifs stay, ungrouped.').then((ok) => ok && act({action: 'group_delete', group: v}, '🗑️ group deleted'));
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
    if (t.id === 'delete-empty') { const ids = motifs().filter(isEmpty).map((e) => e.id); return sure(t, `Delete ${ids.length} empty motifs?`, '🗑️ delete them').then((ok) => ok && batch(ids.map((id) => ({action: 'delete', id})), `🗑️ deleted ${ids.length} empty motifs`)); }
    if (t.id === 'add-motif') {
      const name = await ask(t, 'Name the new motif');
      if (!name) return;
      const before = new Set(Object.keys(S.by));
      if (await act({action: 'add', name}, `✨ made “${name}”`)) { const n = Object.keys(S.by).find((x) => !before.has(x)); if (n) openMotif(n); }
      return;
    }
    if (t.id === 'add-group' && S.groupBy === 'genre') return ask(t, 'A new genre').then((value) => value && act({action: 'facet_value', facet: 'genre', value}, `🎭 added “${value}”`));
    if (t.id === 'add-group') return ask(t, 'Name the new group').then((name) => name && act({action: 'group_add', name}, `📁 made “${name}”`));
    if (t.id === 'help-btn') return $('#help').showModal();
    if ((v = d('cl'))) { const [kind, id] = v.split('|'); return claimAction(kind, id); }
    if (t.closest('[data-editclaim]') || (t.closest('.wb-bigtext') && !t.closest('textarea'))) return editClaim();
    // claim buttons
    const li = t.closest('.wb-claim');
    if (li && t.closest('[data-inspect]')) return inspect(li);
    if (li && t.closest('.wb-ctext') && !t.closest('[data-select]') && !li.closest('.wb-inspect')) return inspect(li);
    if (li && t.closest('button')) {
      const b = t.closest('button'), c = li.dataset.claim, src = li.dataset.source;
      if (b.dataset.check) return act({action: 'check', claim: c, id: src, answer: 'yes'}, '✓ checked');
      if (b.dataset.unfile) return act({action: 'unfile', claim: c, id: src}, '✕ taken out');
      if (b.dataset.nomotif) return sure(b, 'No motif: take it out of every motif, for good?').then((ok) => ok && act({action: 'no_motif', claim: c}, '∅ no motif'));
      if (b.dataset.correct) return ask(b, 'Correct the wording (our summary, not the source)', c, true).then((text) => text && text !== c && act({action: 'correct', claim: c, text}, '✎ corrected'));
      if (b.dataset.detail) return detail(li);
      if (b.dataset.foldIn && S.claim) return act({action: 'same_claim', variant: c, canonical: S.claim.claim}, '≡ folded into this claim');
      if (b.dataset.foldTo && S.claim) { const keep = c, old = S.claim.claim; return act({action: 'same_claim', variant: old, canonical: keep}, '≡ folded into the other claim').then((ok) => { if (ok) { S.claim.claim = keep; S.claim.from = null; renamed(old, keep); renderInbox(); } }); }
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
    if (kind === 'no_motif') return sure(null, `No motif for ${cs.length} claims: out of every motif, for good?`).then((ok) => ok && batch(cs.map((c) => ({action: 'no_motif', claim: c})), `∅ ${cs.length} claims: no motif`));
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
      x.context ? `<div class="wb-transcript">🗣️ ${esc(x.context.before)}<mark>${esc(x.context.quote)}</mark>${esc(x.context.after)}${x.side ? ` <span class="wb-faint">· the voter: ${esc(x.side)}</span>` : ''}</div>`
        : x.quote ? `🗣️ “${esc(x.quote)}”${x.side ? ' · ' + esc(x.side) : ''}` : '',
      x.people ? `🧶 told by ${x.people} people` : '',
      (x.all_posts || []).length
        ? `<details class="wb-posts" open><summary>💬 all ${x.all_posts.reduce((n, p) => n + p.n, 0)} posts still kept (${x.all_posts.length} different)</summary>`
          + x.all_posts.map((p) => `<q>${esc(p.text)}${p.n > 1 ? ` <b class="wb-faint">×${p.n}</b>` : ''}${p.reply ? ' <span class="wb-faint">↩ reply</span>' : ''}${p.source === 'mastodon' ? ' <span class="wb-faint">🐘</span>' : ''}</q>`).join('') + '</details>'
        : (x.examples || []).map((t) => `<q>${esc(t)}</q>`).join('') + (x.posts > (x.examples || []).length ? `<span class="wb-faint">${(x.examples || []).length} of ${x.posts} posts: the report kept only a sample</span>` : ''),
      x.summary ? esc(x.summary) : '',
      ['genre', 'villain', 'victim', 'hero'].filter((k) => lab[k]).map((k) => `${k}: ${esc(lab[k])}`).join(' · '),
      (() => { const w = [].concat(x.model_words || []).filter((m) => m && m !== claim); return w.length ? `the model's words: ${w.map((m) => '“' + esc(m) + '”').join(' · ')}` : ''; })(),
    ].filter(Boolean).map((s) => `<div>${s}</div>`).join('');
  }
  async function verdict(answer) {
    const x = JSON.parse($('#inbox').dataset.check || 'null');
    if (!x) return;
    S.checkTrail = S.checkTrail || [];
    if (answer === 'next') {
      if (S.checkBack) S.checkBack = S.checkForward.pop() || null;  // stepping forward again through the trail
      else {
        S.checkTrail.push(x.claim);
        // still to check: step past it; finished: the next claim has slid into its place
        const at = (S.checkItems || []).findIndex((i) => i.claim === x.claim);
        if (at >= 0) S.checkAt = at + 1;
        S.checkHere = null;
      }
      return renderInbox();
    }
    if (answer === 'prev') {
      if (!S.checkTrail.length) { toast('◀ that’s the first one you’ve seen'); return; }
      S.checkForward = S.checkForward || [];
      if (S.checkBack) S.checkForward.push(S.checkBack);
      S.checkBack = S.checkTrail.pop();
      return renderInbox();
    }
    if (answer === 'allyes') {
      const left = motifsOf(x.claim).filter((e) => e.claims.some((c) => c.claim === x.claim && !c.checked));
      if (!S.checkBack) { S.checkTrail.push(x.claim); S.checkHere = null; }
      else S.checkBack = (S.checkForward || []).pop() || null;
      if (!left.length) return renderInbox();
      return batch(left.map((e) => ({action: 'check', claim: x.claim, id: e.id, answer: 'yes'})), `✓ ${left.length} motif${left.length === 1 ? '' : 's'} fit`);
    }
  }
  function saveNote(id) {
    const ta = $(`textarea[data-note="${id}"]`);
    if (ta && S.by[id] && ta.value.trim() !== (S.by[id].note || '')) act({action: 'note', id, note: ta.value.trim()}, '💾 note saved');
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
  document.addEventListener('keydown', (ev) => {
    if (ev.target.id === 'cl-q' && ev.key === 'Enter') {
      ev.preventDefault();
      const make = $('#cl-new');
      if (make) make.focus();
    }
  });
  document.addEventListener('change', (ev) => {
    const t = ev.target;
    if (t.dataset.group !== undefined && t.value) act({action: 'group_member', id: t.dataset.group, group: t.value}, '📁 in the group too');
    if (t.dataset.genre !== undefined) act({action: 'facet', id: t.dataset.genre, facet: 'genre', value: t.value || null}, `🎭 ${t.value || 'no genre'}`);
    if (t.id === 'groupby') { S.groupBy = t.value; store.set('groupby', S.groupBy); $('#add-group').textContent = S.groupBy === 'genre' ? '＋ genre' : '＋ group'; renderTree(); }
  });
  // A note saves as you leave it, like a title (there's no save button to forget)
  document.addEventListener('focusout', (ev) => {
    if (ev.target.dataset && ev.target.dataset.note !== undefined && ev.target.isConnected) saveNote(ev.target.dataset.note);
  });
  document.addEventListener('keydown', (ev) => {
    const typing = ev.target.closest && ev.target.closest('input, textarea, select');
    if (ev.key === 'Escape') { if (drag) end(ev, true); hideMenu(); }
    if (ev.target.dataset && ev.target.dataset.note !== undefined && ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); ev.target.blur(); return; }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z' && !typing) { ev.preventDefault(); undo(); return; }
    if (typing || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (ev.key === '/') { ev.preventDefault(); $('#q').focus(); return; }
    if (S.tab === 'check' && $('#inbox').dataset.check) {
      const k = {y: 'allyes', arrowright: 'next', j: 'next', s: 'next', arrowleft: 'prev', k: 'prev'}[ev.key.toLowerCase()];
      if (k) { ev.preventDefault(); verdict(k); }
    }
  });

  // ---------- in-page fields instead of the browser's prompt and confirm boxes ----------
  let askCard = null, lastAnchor = null;
  function closeAsk(value) {
    if (!askCard) return;
    const done = askCard._resolve;
    askCard.remove();
    askCard = null;
    done(value);
  }
  function askCardAt(anchor, html, submit) {
    closeAsk(null);
    return new Promise((resolve) => {
      const f = document.createElement('form');
      f.className = 'wb-ask';
      f.innerHTML = html;
      f._resolve = resolve;
      document.body.append(f);
      askCard = f;
      const a = [anchor, lastAnchor].find((x) => x && x.isConnected);
      const r = a ? a.getBoundingClientRect() : {left: innerWidth / 2 - 180, top: innerHeight / 3, bottom: innerHeight / 3};
      const m = f.getBoundingClientRect();
      let y = r.bottom + 6;
      if (y + m.height > innerHeight - 8) y = Math.max(8, r.top - m.height - 6);
      f.style.left = Math.max(8, Math.min(r.left, innerWidth - m.width - 8)) + 'px';
      f.style.top = y + 'px';
      const field = f.querySelector('input, textarea');
      (field || f.querySelector('button')).focus();
      if (field) field.select();
      f.addEventListener('submit', (ev) => { ev.preventDefault(); closeAsk(submit(f)); });
      f.addEventListener('click', (ev) => { if (ev.target.closest('[data-askcancel]')) closeAsk(null); });
      f.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') { ev.preventDefault(); closeAsk(null); }
        if (ev.key === 'Enter' && !ev.shiftKey && ev.target.tagName === 'TEXTAREA') { ev.preventDefault(); f.requestSubmit(); }
      });
    });
  }
  function ask(anchor, label, value = '', multiline = false) {
    const field = multiline ? `<textarea rows="3">${esc(value)}</textarea>` : `<input type="text" value="${esc(value)}">`;
    return askCardAt(anchor, `<label>${esc(label)}</label>${field}<div class="wb-askbtns"><button class="wb-btn yes" type="submit">💾 save</button>
      <button class="wb-btn" type="button" data-askcancel>cancel</button><span class="wb-faint">Enter saves · Esc cancels</span></div>`,
    (f) => f.querySelector('input, textarea').value.trim() || null);
  }
  function sure(anchor, text, ok = 'yes, do it') {
    return askCardAt(anchor, `<p>${esc(text)}</p><div class="wb-askbtns"><button class="wb-btn no" type="submit">${esc(ok)}</button>
      <button class="wb-btn" type="button" data-askcancel>cancel</button></div>`, () => true).then((v) => !!v);
  }
  document.addEventListener('pointerdown', (ev) => { if (askCard && !askCard.contains(ev.target)) closeAsk(null); }, true);
  // The open motif's name edits where it is: click it (or ✎), type, Enter or click away saves, Esc puts it back
  function editTitle(id) {
    const h = $(`.wb-panel[data-id="${id}"] .wb-pname`), e = S.by[id];
    if (!h || !e || h.querySelector('input')) return;
    h.innerHTML = `<input class="wb-title-in" value="${esc(e.name)}" aria-label="the motif's name">`;
    const inp = h.querySelector('input');
    inp.focus();
    inp.select();
    let over = false;
    const finish = (save) => {
      if (over) return;
      over = true;
      const v = inp.value.trim();
      if (save && v && v !== e.name) act({action: 'rename', id, name: v}, `✎ renamed to “${v}”`);
      else renderPanels();
    };
    inp.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
      if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
    });
    inp.addEventListener('blur', () => finish(true));
  }

  // The claim in the claim view edits where it is: a person's correction of our summary (never the source's words)
  function renamed(old, text) {  // the claim pinned in the check tab, now under other words
    if (S.checkHere && S.checkHere.claim === old) S.checkHere = {...S.checkHere, claim: text};
  }
  function editClaim() {
    const box = $('#inbox .wb-bigtext');
    if (!box || !S.claim || box.querySelector('textarea')) return;
    const old = S.claim.claim;
    box.innerHTML = `<textarea class="wb-claim-in" rows="3" aria-label="the claim's wording">${esc(old)}</textarea><span class="wb-faint">Enter saves · Esc cancels</span>`;
    const ta = box.querySelector('textarea');
    ta.focus();
    ta.select();
    let over = false;
    const finish = (save) => {
      if (over) return;
      over = true;
      const text = ta.value.trim();
      if (save && text && text !== old) {
        act({action: 'correct', claim: old, text}, '✎ corrected').then((ok) => { if (ok && S.claim) { S.claim.claim = text; renamed(old, text); renderInbox(); } });
      } else renderInbox();
    };
    ta.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); finish(true); }
      if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
    });
    ta.addEventListener('blur', () => finish(true));
  }

  // ---------- hover a motif: its note and a few claims ----------
  const hover = document.createElement('div');
  hover.className = 'wb-hover';
  hover.hidden = true;
  document.body.append(hover);
  let hoverTimer = null, hoverOn = null;
  document.addEventListener('mouseover', (ev) => {
    const c = ev.target.closest && ev.target.closest('.wb-chip, .wb-row');
    if (c === hoverOn) return;
    hoverOn = c;
    clearTimeout(hoverTimer);
    hover.hidden = true;
    if (!c || drag || !c.dataset.id) return;
    hoverTimer = setTimeout(() => {
      const e = S.by[c.dataset.id];
      if (!e || drag) return;
      const kids = (S.kids[e.id] || []).map((k) => S.by[k] && S.by[k].name).filter(Boolean);
      hover.innerHTML = `<b>${esc(e.name)}</b> <span class="wb-faint">${e.id} · ${e.claims.length} claim${e.claims.length === 1 ? '' : 's'}${e.done === 'done' ? ' · ✓ done' : ''}</span>
        ${(e.facets || {}).genre ? `<p>🎭 ${esc(e.facets.genre)}</p>` : ''}
        ${e.note ? `<p>📝 ${esc(e.note)}</p>` : '<p class="wb-faint">no note yet</p>'}
        ${e.parents.length ? `<p class="wb-faint">↳ a kind of ${e.parents.map((p) => esc((S.by[p] || {}).name || p)).join(', ')}</p>` : ''}
        ${kids.length ? `<p class="wb-faint">⤷ kinds: ${kids.map(esc).join(', ')}</p>` : ''}
        <ul>${e.claims.slice(0, 4).map((x) => `<li>${esc(x.claim)}</li>`).join('')}${e.claims.length > 4 ? `<li class="wb-faint">and ${e.claims.length - 4} more</li>` : ''}</ul>`;
      hover.hidden = false;
      const r = c.getBoundingClientRect(), m = hover.getBoundingClientRect();
      let x = r.left, y = r.bottom + 6;
      if (x + m.width > innerWidth - 8) x = innerWidth - m.width - 8;
      if (y + m.height > innerHeight - 8) y = Math.max(8, r.top - m.height - 6);
      hover.style.left = Math.max(8, x) + 'px';
      hover.style.top = y + 'px';
    }, 350);
  });
  document.addEventListener('pointerdown', () => { clearTimeout(hoverTimer); hover.hidden = true; }, true);

  // ---------- adjustable columns: drag the bars between the panes; the widths are remembered ----------
  const main = $('.wb-main');
  function setCols(c) {
    main.style.setProperty('--left', c.left + 'px');
    main.style.setProperty('--right', c.right + 'px');
  }
  let cols = store.get('cols', null);
  if (cols) setCols(cols);
  $$('.wb-split').forEach((bar) => bar.addEventListener('pointerdown', (ev) => {
    ev.preventDefault();
    const side = bar.dataset.split, start = ev.clientX;
    const box = main.getBoundingClientRect();
    const was = {left: $('.wb-tree').getBoundingClientRect().width, right: $('.wb-inbox').getBoundingClientRect().width};
    try { bar.setPointerCapture(ev.pointerId); } catch (e) { /* a synthetic or ended pointer */ }
    document.body.classList.add('resizing');
    const moveTo = (e) => {
      const dx = e.clientX - start, max = box.width * 0.6;
      cols = {left: was.left, right: was.right};
      if (side === 'left') cols.left = Math.min(max, Math.max(180, was.left + dx));
      else cols.right = Math.min(max, Math.max(240, was.right - dx));
      setCols(cols);
    };
    const done = () => { bar.removeEventListener('pointermove', moveTo); document.body.classList.remove('resizing'); store.set('cols', cols); };
    bar.addEventListener('pointermove', moveTo);
    bar.addEventListener('pointerup', done, {once: true});
    bar.addEventListener('lostpointercapture', done, {once: true});
  }));
  $$('.wb-split').forEach((bar) => bar.addEventListener('dblclick', () => { cols = null; store.set('cols', null); main.style.removeProperty('--left'); main.style.removeProperty('--right'); }));

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

  $('#groupby').value = S.groupBy;
  $('#add-group').textContent = S.groupBy === 'genre' ? '＋ genre' : '＋ group';
  reload().catch((e) => { $('#panels').innerHTML = `<p class="wb-faint">😬 couldn’t load the index: ${esc(e.message)}</p>`; });
})();

// The 📦 export menu opens toward the side with room (the button wraps to the left on a narrow window), and closes on a
// pick or a click anywhere else
document.querySelector('.wb-export')?.addEventListener('toggle', e => {
  const menu = e.target.querySelector('.wb-export-menu');
  menu.classList.remove('wb-export-left');
  if (e.target.open && menu.getBoundingClientRect().left < 0) menu.classList.add('wb-export-left');
});
document.addEventListener('click', e => {
  const menu = document.querySelector('.wb-export');
  if (menu && menu.open && (!(e.target instanceof Element) || !e.target.closest('.wb-export summary'))) menu.open = false;
});
