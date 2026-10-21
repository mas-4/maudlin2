# Porting the checker to React: the parity checklist

The old checker's front end, page by page and tab by tab, as inventoried on Oct 21 (WB = scripts/checker/static/
workbench.js, T/ = scripts/checker/templates/). A page is ported when everything listed under it works in the new app.
Then its nav entry points here, and the old template goes. Tick items with [x] as they land.

Decisions for the port:
- **One write route.** Every motif change goes to POST /workbench as a named action (app/analysis/motif_actions.py). The
  old /motif-board and /motif-verdict routes stay for the old pages until those go.
- **One drag engine.** The workbench's: hovering a target opens a menu of choices beside the pointer, each saying in
  full what it does. drag.js (map, names) is replaced by it.
- **One way to ask and confirm.** An in-page card for both; no `alert`, `confirm` or `prompt`. One toast with an undo
  button.
- **Version banner on every page,** over the whole app's build.
- **Not ported (superseded):** ✅ check (→ 🎯), 🫙 empty page (→ the 🫙 tab), 📝 notes page (→ the 📝/🗒️ views). Ask
  the person before dropping them.
- **Bugs fixed in the port, not in the old pages:**
  - `.wb-split` was both the column bar and the split card class.
  - The stats tiles used site classes the checker never loaded.
  - Live and flow linked to `#M…`, which the workbench ignores.
  - The dashboard's refresh never asked for fresh data.
  - The map deleted a motif without asking.

## 0. Shell (all pages)

- [x] Nav: sections main / motif pages / other tools, current page marked.
- [x] Undo: GET /undo.json `{what}`, POST /undo, Ctrl/⌘+Z outside text fields. Refresh everything after.
- [x] Version check: GET /version.json every 60s; offer a reload when it changes.
- [ ] 💾 saved states: GET /checkpoints.json `[{id,name,at,kind,changes_since}]`.
  - Save: POST /checkpoint `{name}`.
  - Go back: POST /checkpoint `{action:'go back', id}`, after asking "go back? what's there now is saved first". The
    reply is `{went_back:{to,reverted,saved_first}, state}`.
- [ ] Toast after each write, with "↶ undo"; errors show for 7s.
- [ ] Ask card and sure card: anchored to the pressed element. Enter saves, Shift+Enter gives a newline, Esc or a
  click outside cancels.
- [ ] Hover card on a motif chip or row (350ms): name, id, claims, done, genre, note, rests on, rest on it, first 4
  claims.
- [ ] Deep links: `?motif=M12`, `?claim=<text>`. ↗ and middle-click open in a new tab.

## 1. 🧰 Workbench

Data: GET /workbench.json, which is `workbench_state()` (validate.py) = `mi.board()` plus:
- Top level: `groups[{id,name,note}]`, `facets.genre[]`, `facet_notes.genre{}`, `to_check`, `second_look`, `held[]`,
  `proposals`, `splits`, `tellings`, `tellings_of{id:n}`, `not_same[[a,b]]`.
- `confidence{sure_at, auc, at_sure{precision}, out_at, at_out{removed}, tally[{day,clean,needed}]}`.
- Per entry: `id, name, note, note_by, not_this, parents, related, related_notes, groups, facets.genre,
  by_model{genre,groups}, done, curated, first_seen, told{events,span}, attested, stands_alone, watch,
  carrying[[phrase,n]]`.
- Per claim: `claim, id (6-hex), source, ref, checked, new, variants[], carrying[]`.

Each write is POST /workbench and returns the whole state. Redraw from it. While saving: the pressed button shows ⏳,
the cursor shows progress, and a second press says "⏳ still saving…". A batch is `{action:'batch', steps}` (one
undo step); the server fills in "$1", "$2"… with motifs made earlier in the batch.

Items decided in this session are hidden at once: `decided` (`claim|motif`, `p:id`, `t:key`, `s:id`), `rejected`,
`quickSkip`, `unticked`, `outTicked`.

Kept in localStorage (`wb-`): `open`, `view`, `sort`, `tab`, `folded`, `groupby`, `quickper`, `cols`, `shelf`.

### 1.1 Top bar and shelf
- [ ] Motif search over id, name and note. `/` focuses it, Enter opens the first match (Shift+Enter beside the
  others), Esc clears.
- [ ] Stats line: "N attested of N motifs · N filings · N with 2+ · N not done".
- [ ] Drop targets: ✨ new motif, ∅ no motif, 🗑️ take out.
- [ ] 📦 export: links to `/motif-export?format=md|csv|json|ttl&scope=verified|all`.
- [ ] 📈 pace: GET /pace.json `{days[{day,arrived,judged}], today, steady, waiting, clear_in_14}`.
  - Paired bars, arrived #e8590c and judged #1c7ed6, with a dashed "hold steady" line. The scale is capped at
    2.5×steady, and a bar clipped by the cap is labelled "N↑".
  - "as a table" fold.
- [ ] ❓ help dialog.
- [ ] Shelf: 📁 group chips and 🎭 genre chips with counts, plus "🗃️ in no group" and "❔ no genre yet".
  - Clicking a chip filters the tree to it. Dropping on a chip opens its menu, and a group chip can be dragged (it
    carries the group's motifs).
  - Tools on a group chip: ✎ `group_rename`, 📝 `group_note`, ✕ `group_delete` (after sure). On a genre chip:
    `facet_rename`, `facet_note`, `facet_remove`.
  - "＋ new group" (`group_add`) and "＋ new genre" (`facet_value`).
- [ ] Resizable columns (left ≥180px, right ≥240px, ≤60% each; double-click resets) and shelf height (40px–60vh).
  Narrower than 1000px, the panes stack.

### 1.2 Left: the motif tree
- [ ] Views, each with a count: 🗂️ all · 1️⃣ singles · 📝 no note · 🗒️ draft notes · 🤖 model-made · ⏳ not done
  · 🆕 new claims · ❔ unchecked · 🎭 no genre · 🫙 empty.
- [ ] Sort: biggest, A–Z, newest, oldest. Group by: 📁 group, 🎭 genre, 🧩 none.
- [ ] Tree only in the all view with no search or filter; otherwise a flat list.
  - A motif nests under what it rests on and appears in each of its groups.
  - Fold state is kept under the keys `g:<by>:<id>` and `m:<id>`.
- [ ] Section header: draggable, with 📝, ✎ and 🗑️ tools; it is also a drop target (group, or genre).
- [ ] Row badges: ✓ done · 🆕N · 📝 faint · 🤖 · 🧍 · count · 📁N.
  - Open rows are tinted with their panel's colour (6 colours).
  - Hover tools: ✕ out of this group (`group_member on:false`), ⧉ open as an extra panel.
- [ ] Multi-select: Shift-click selects a run, Ctrl/⌘-click toggles one. Bar: "☑️ N selected · drag any of them to
  move them all ✕ clear".
- [ ] ＋ motif: ask for a name, `add{name}`, then open it.

### 1.3 Middle: open motif panels (at most 8; the oldest goes)
- [ ] Title edits in place (Enter or blur saves `rename`, Esc restores); it is also a drag handle.
- [ ] Meta line: id, claim count, ✋ by hand, since, 🗓 N occasions or 📍 one occasion.
- [ ] Status bar:
  - Done state, with its button: `done{id,done}`.
  - ✎ rename.
  - 🧩 N tellings: jumps to that tab.
  - 📋 copy the motif as text.
  - 🧍 stands alone (only for singles): `stands_alone`.
  - 👁 watch: `watch`.
  - 🗑️ delete, after sure.
- [ ] Relations:
  - 📁 groups: tags with ✕. The picker matches a name or creates one with `group_new{name,id}`. 🤖 marks the model's
    guess.
  - 🎭 genre select: `facet`, with 🤖 for the model's guess.
  - ↳ rests on and ⤷ rest on it, each with ✕: `parent on:false`.
  - ↔ related with ✕ (`unrelate`), and an inline reason editor offering 5 phrasings (`relate{a,b,note}`; empty
    removes the reason).
  - 🤝 shares claims (computed here).
- [ ] Note: `note` on blur or Enter. Drafts being typed survive a redraw. "✓ keep the draft" (`keep_note`). 🚫 not this
  (`not_this`). "🗣 tellers say: …".
- [ ] Claims, new first: NEW, ✓, 🤷, "≡ N ways", carrying words, `#id`, source.
  - Hover tools: 🔍 · ✓ `check yes` · ✕ `unfile` · ∅ `no_motif` (after sure) · ✎ `correct` · ⓘ inline detail.
  - Click selects, Shift selects a run. Selection bar: 🗑️ batch `unfile` · ∅ batch `no_motif` · ✓ batch `check`.
  - Each claim is a drop target (≡ same claim).
- [ ] 🧲 more like this: GET /motif-similar.json?id=, with ＋ (`also`/`file`) and ✕ (`reject`).
- [ ] 📥 add claims: GET /claims.json?q= (220ms debounce), ＋ or "✓ here".

### 1.4 Drag and drop (one engine)
- [ ] Sources: motif (or the selected motifs), group (its motifs), claim (or the selected claims).
- [ ] Mouse starts after 6px, touch after a 350ms hold. Buttons, inputs and links are left alone.
- [ ] A menu opens beside the pointer, with the path to it kept open. Letting go runs the choice, or the only choice;
  otherwise the menu stays pinned.
- [ ] Ghost label. A group tray above the tree for a single motif. Panes scroll at their edges. Esc cancels. The click
  that ends a drag is swallowed.
- [ ] Choices:
  - claim → motif: ⇢ move here or ＋ also here (`move`/`also`/`file`).
  - claim → claim: ≡ `same_claim`.
  - claim → ✨: move, copy or new → `new_with{name, claims:[{claim,source,src,ref,mode}]}`, then open it.
  - claim → ∅: `no_motif`. claim → 🗑️: `unfile`.
  - motif → motif: ⤵ `merge`, ↳ / ↰ `parent`, ↔ `relate`, ≠ `not_same`, 📁 `group_new{name,ids}`.
  - motif → genre: `facet`. motif → group: `group_member`, or "only this group" `group_assign`. motif → 🗑️:
    `delete` (after sure).
  - motifs → any of these: batches, with sure before a merge-all or a delete.

### 1.5 Right: inbox tabs (counts on each)
- [ ] 📊 stats: GET /workbench-metrics.json.
  - 🩺 health banner and 10 tiles.
  - Day bars: ✨ new motifs, 🤖 how filed, ✋ your changes, ☑️ checks.
  - Tables: 🤖 how good the machine is, 🧱 shape by day.
- [ ] 🎯 claims to judge: kind=judge `[{claim, source, reasons[{kind,id,fit,refiled?}], fits{}, unsure[], better[]}]`,
  least sure first, one claim at a time.
  - Check bar: "N claims to judge · here for …", ◀ ←, "✓ all fit, next Y" (batch `check yes`), "⏸ hold H", "next ▶
    →".
  - A trail for back and forward. The claim stays shown after an edit.
  - Keys: y, h, →/j/s, ←/k, m (the first ⇄ move).
  - Rows tinted green for fits and orange for doubts ("🧐 ✓ still fits"), with fit chips "🎯 N%" and ⚠️ when it can
    never pass as sure.
- [ ] ✅ sure and 🚫 misfits, both from the judge queue:
  - sure: every waiting filing has a fit of `sure_at` or more, and none is doubted, unsure or skipped.
  - misfits: under `out_at`.
  - Pager: 10/25/50/100. Ticks persist across pages.
  - Sure: a tally line, then "✓ pass the ticked, ⏸ hold the rest", sending `{action:'batch', steps:[check…, hold{claim,
    from:'sure'}…], quick:'sure', unticked:[…]}`.
  - Misfits: "✕ take out the ticked", and the same while also ✓ the rest.
- [ ] ⏸ held: kind=held `[{claim, at, waiting}]`, with ▶ `unhold`.
- [ ] ✨ to shape: kind=today `{items, picked, done}`.
  - New motif cards: "✅ keep it as it is" (`done`).
  - Proposal cards.
  - "🎯 20 more" fetches kind=today-more.
- [ ] 🔎 claims: search the loaded claims, plus /claims.json for unfiled ones (40 + 20 shown).
- [ ] 🔍 claim:
  - The big claim: click to edit (`correct`), ✂️ split (`split{claim,children}`); it is a drop target.
  - ≡ variants.
  - 📜 where it came from: /claim-detail.json — kind, split_from, title, url, context, quote, side, people, tellings[],
    all_posts/examples/posts, summary, label, piece, model_words — with 📋 copy.
  - 🧩 all its motifs: fit, ✓, ✕, and carrying words (`carrying{claim,id,text}`, split on ";").
  - 🤖 might fit better (/better.json): ⇄ move (`also` + `check no`, only when a filing is doubted), ＋, ✕ `reject`.
  - ➕ add it to another motif: search 12, ＋, and ✨ new motif with the typed name.
  - Buttons: ✨ new motif with it, ∅ no motif, ⏸ hold / ▶ take off.
  - ≡ claims like this one (/claim-similar.json): same claim either way, following to the kept one.
  - "← back to <tab>" when opened from a list.
- [ ] 🔗 pairs: kind=pairs `{similar[{a,b,score}], shared[{a,b,shared}], note}`. Pairs already decided are filtered
  out.
  - Each card: ⧉ compare, merge either way, rests on either way, ↔ related, ≠ not the same.
- [ ] 1️⃣ singles: kind=singles `[{id, claim, source, suggest[{id, same_claim, score}]}]`. 🧍 marks a motif standing
  alone; each suggestion has ⤵, ↳, ↔ and ⧉.
- [ ] 💡 proposals: kind=proposals `[{id, kind, args, reason, fit, judge, unlikely, do}]`.
  - Each kind written as a sentence, with word diffs for renames and notes. A new_motif lists its claims with ticks.
  - Per card: ✓ (`{...do, proposal}`), 🌱 seed, ⇅ flip, ✕ `proposal_reject`.
  - Bulk approve or reject the ticked. A "🤖 probably not" fold holds the unlikely ones.
  - After a rejection or a trim, ask why: POST /critique `{proposal, why}`.
- [ ] ✂️ splits: kind=splits.
  - Editable child claims.
  - "✂️ split it so" (`split{proposal,children}`) or "✕ keep it whole" (`split_reject`), then ask why.
- [ ] 🧩 tellings: kind=tellings, one fold per motif.
  - Each telling: editable name and note, claim ticks, "take them out of <motif>".
  - ✓ `telling{key,parent,name,note,claims,move,draft}`, 🌱 seed, ✕ `telling_reject`.
- [ ] 📥 unfiled: /claims.json?q=, unfiled only, draggable.
- [ ] 🫙 empty: computed here. 🗑️ each, or "delete all N" as one batch after sure.

## 2. 🕸️ Map (T/map.html)
- [ ] Data:
  - GET /workbench.json, the superset of /motif-board.json.
  - 🧲 mode: GET /motif-claim-map.json `{nodes, clusters, links}`.
- [ ] D3 force layout:
  - Forces: links by kind, charge -160, collide, group-home, a weak pull across groups.
  - Group blobs, rests-on arrows, dot size 5+3√claims.
  - Dot fill is the genre colour; a thick outline means others rest on it, a dashed one that it rests on another.
  - Labels placed greedily. Positions kept per mode. Zoom 0.15–5×, pan by dragging.
- [ ] Controls:
  - Search: highlight matches, Enter centres the first.
  - ⤢ fit.
  - Line toggles: rests on; related (the picked one's / all / none); shared claims (none, 1+, 2+, 3+); only linked.
  - Modes: 🫧 bubbles, 🧲 claims, 🌳 tree, 📁🎭 chips, ℹ️ key.
- [ ] Chips: groups toggle visibility (`map-hidden-groups`), genres pick one out, ＋ new group; in 🧲 mode, clusters.
- [ ] 🌳 tree: rows by depth, barycentre ordering, families packed on shelves.
- [ ] 🫧 bubbles: a closed group is one bubble; clicking opens it.
- [ ] Focus: click gathers the neighbourhood (rests-on 2 steps up and down, related at the sides) and fades the rest.
  Esc or a background click resets. Hovering shows related lines.
- [ ] Card shared by the info box and the desk:
  - Editable name and note; facts.
  - Rows for rests on, rest on it and related, each with ✕ unlink and ＋ add (`relate`/`parent`).
  - 🤝 shares claims; the claims themselves.
- [ ] 📌 desk: pinned cards (`map-desk`).
- [ ] Multi-select: Ctrl/⌘/Shift-click, or Shift-drag a box.
- [ ] Drag (the one engine), with the map's extra targets: 📌 pin, ＋ new group, `also_new` for a claim onto ✨, and
  out of a group. Delete asks first.
- [ ] Left list: groups, rests-on (nested), related, the rest. Clicking one centres it.

## 3. 📈 Dashboard (T/dashboard.html)
- [ ] GET /dashboard.json every 120s; 🔄 asks for `fresh=1`.
- [ ] Sections:
  - 🩺 keeping up: runs with a 45-minute line, feeds, GPU temperature with an 83°C line, model loads.
  - 📥 came in. 🧵 sagas. ⚙️ made of it. 🧩 index. 🧠 models. 🖐️ curation.
- [ ] Stacked bars and lines, redrawn when the size changes.

## 4. 🧪 Experiments (T/experiments.html)
- [ ] GET /experiments.json every 60s: `{queue, maat, seams, experiments[{code,figure,why,family,question,status,
  result,lines,cases,paper}]}`.
- [ ] List: search, grouped by status. Tabs: 📄 paper (/experiment-paper.json, Markdown), 📈 results, 🔍 cases
  (/experiment-cases.json), 🧭 pipeline. The selection lives in the hash `#code`.
- [ ] Cases: filter by kind; blind rows highlighted; verdict buttons (POST /experiment-verdict `{code,key,verdict}`,
  pressed again to clear).

## 5. 🌊 Flow (T/flow.html)
- [ ] GET /flow.json `{stories, motifs, genres, filings}`.
- [ ] Top cards: totals, a lag histogram with its median, hub motifs.
- [ ] Timeline, 110px a day:
  - A story's life as a bar.
  - Dots by source: ● posts, ■ fact-check, ▲ shows, ◆ focus group. Hollow dashed for plain reports; a dashed outline
    for unchecked.
  - A today line. Opens at the latest days.
- [ ] Filters: search, sort (first, most motifs, slowest), plain reports, sources.
- [ ] Tooltip. Click a motif to follow it across stories, click a story for its panel. Links open the workbench with
  `?motif=`.

## 6. 🧠 Live (T/live.html)
- [ ] GET /live.json; poll `?since=` every 4s while the tab is visible; ● live / ○ offline.
- [ ] Pipeline strip: 8 stages, last-hour counts, sparkline, pulse. Click a stage to filter the feed.
- [ ] Feed: 250 events, new ones flash.
- [ ] Follow a claim: example chips, search (`?q=`, 300ms), a hex id.
- [ ] Journey (`?claim=`):
  - Cards: written, shape, layers.
  - Each pass: the shortlist's neuron grid (motifs × signals, coloured by push or value, with weight bars), then the
    pick.
  - The confidence model: fit bar against the sure line, pushes, signals.
  - Verdicts, split, downstream, 📖 glossary.
  - The journey lives in the hash `#claim=`.

## 7. Other tools
- [ ] 👥 names: suggested merges and every subject, with search and sort.
  - POST /entities: `merge{source,target}`, `not_same{a,b}`, `unmerge{name}`.
  - Rename is a merge into the typed name. Drag one subject onto another.
- [ ] 🏷️ label check: headlines with mood, spice and feelings (the model's pick dashed). POST /verdict `{headline_id,
  model, mood, spice, feelings}`. Needs a JSON route for its batch (it is server-rendered today).
