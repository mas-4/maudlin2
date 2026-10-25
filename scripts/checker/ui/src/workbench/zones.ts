// What a drop does: the choices offered when something is carried over a target, each saying in full what it does.
// Ported choice for choice from the old workbench (scripts/checker/static/workbench.js, zones()).
import { ask, sure } from '../components/Feedback'
import { act, batch } from './act'
import { claimAction, makeNew, newGroupOf } from './ops'
import { currentModel, motifsOf } from './model'
import { getWB, setWB } from './store'
import type { Carried, DragItem, Zone } from './types'

export function claimsName(cs: Carried[] | { claim: string }[]) {
  return cs.length === 1 ? '“' + cs[0].claim.slice(0, 60) + '…”' : cs.length + ' claims'
}

/** A page's own drop targets and choices (the map's 📌 desk, ＋ new group…), asked first. It is handed the workbench's
 * choices for the same drop, to keep or adjust; null leaves the drop to them as they are */
export type ZoneExtra = (item: DragItem, t: HTMLElement, base: () => Zone[]) => Zone[] | null
let extra: ZoneExtra | null = null
/** Add a page's choices while it is shown; the function returned takes them away again */
export function extendZones(fn: ZoneExtra) {
  extra = fn
  return () => { if (extra === fn) extra = null }
}

export function zones(item: DragItem, t: HTMLElement): Zone[] {
  return (extra && extra(item, t, () => workbenchZones(item, t))) ?? workbenchZones(item, t)
}

function workbenchZones(item: DragItem, t: HTMLElement): Zone[] {
  const m = currentModel()
  if (!m) return []
  const drop = t.dataset.drop
  const S = getWB()
  if (drop === 'sameclaim' || (drop === 'claim' && item.kind === 'claim')) {
    // A claim dropped on a claim: one claim told two ways. Over a claim in an open motif, the motif's own choices too
    const target = t.dataset.claim ?? (drop === 'claim' ? S.claim?.claim : undefined) // the card's own claim
    const panelEl = drop === 'sameclaim' ? (t.closest('[data-drop="motif"]') as HTMLElement | null) : null
    const base = panelEl ? zones(item, panelEl) : []
    if (item.kind !== 'claim' || !target || !motifsOf(m, target).length) return base
    const folding = item.claims.filter((c) => c.claim !== target)
    if (!folding.length) return base
    return [...base, {
      label: '≡ the same claim as this one',
      say: `fold ${claimsName(folding)} into “${target.slice(0, 60)}…”: one claim, told ${folding.length + 1} ways`,
      run: () => batch(folding.map((c) => ({ action: 'same_claim', variant: c.claim, canonical: target })), `≡ ${claimsName(folding)} folded into one claim`),
    }]
  }
  if (item.kind === 'claim') {
    const cs = item.claims
    if (drop === 'motif') {
      const to = t.dataset.id!, e = m.by[to]
      if (!e) return []
      const has = new Set(e.claims.map((c) => c.claim))
      const todo = cs.filter((c) => !has.has(c.claim) || (c.source && c.source !== to))
      if (!todo.length || cs.every((c) => c.source === to)) return []
      const filed = cs.filter((c) => c.source && c.source !== to)
      if (filed.length) {
        return [
          { label: '⇢ move here', say: `move ${claimsName(cs)} into “${e.name}”`, run: () => batch(cs.map((c) =>
            c.source === to ? null : has.has(c.claim) ? { action: 'unfile', claim: c.claim, id: c.source }
              : c.source ? { action: 'move', claim: c.claim, source: c.source, target: to }
                : { action: 'file', claim: c.claim, id: to, source: c.src, ref: c.ref }), `⇢ moved ${claimsName(cs)} into “${e.name}”`) },
          { label: '＋ also here', say: `file ${claimsName(cs)} here too, keeping where it is`, run: () => batch(cs.map((c) =>
            has.has(c.claim) ? null : c.source ? { action: 'also', claim: c.claim, source: c.source, target: to }
              : { action: 'file', claim: c.claim, id: to, source: c.src, ref: c.ref }), `＋ filed ${claimsName(cs)} in “${e.name}” too`) },
        ]
      }
      return [{ label: '＋ file here', say: `file ${claimsName(cs)} in “${e.name}”`, run: () => batch(cs.map((c) =>
        has.has(c.claim) ? null : { action: 'file', claim: c.claim, id: to, source: c.src, ref: c.ref }), `＋ filed ${claimsName(cs)} in “${e.name}”`) }]
    }
    if (drop === 'newmotif') {
      const named = (mode: string) => async () => {
        const n = await ask('Name the new motif', cs.length === 1 ? cs[0].claim.slice(0, 80) : '', { anchor: t })
        if (n) await makeNew(n, cs.map((c) => ({ ...c, mode })))
      }
      return cs.some((c) => c.source)
        ? [{ label: '⇢ move into a new motif', say: `move ${claimsName(cs)} out into a new motif of their own`, run: named('move') },
          { label: '＋ copy into a new motif', say: `start a new motif with ${claimsName(cs)}, keeping where they are`, run: named('also') }]
        : [{ label: '✨ new motif', say: `start a new motif with ${claimsName(cs)}`, run: named('file') }]
    }
    if (drop === 'nomotif') {
      return [{ label: '∅ no motif', say: `no motif: ${claimsName(cs)} tells no recurring story; out of every motif, never filed again`,
        run: async () => (await sure(`Take ${claimsName(cs)} out of every motif, for good?`, 'yes, do it', t))
          && batch(cs.map((c) => ({ action: 'no_motif', claim: c.claim })), `∅ ${claimsName(cs)}: no motif`) }]
    }
    if (drop === 'trash') {
      const filed = cs.filter((c) => c.source)
      return filed.length ? [{ label: '🗑️ take out', say: `take ${claimsName(cs)} out of the motif you dragged from`,
        run: () => batch(filed.map((c) => ({ action: 'unfile', claim: c.claim, id: c.source })), `🗑️ took ${claimsName(cs)} out`) }] : []
    }
    return []
  }
  if (item.kind === 'motifs') { // several motifs selected in the list (Shift- or Ctrl-click), dropped together
    const ids = item.ids, n = `${ids.length} motifs`
    const clear = () => setWB({ msel: [] })
    if (drop === 'motif') {
      const b = t.dataset.id!, B = m.by[b], rest = ids.filter((i) => i !== b)
      if (!B || !rest.length) return []
      return [
        { label: `⤵ merge all ${rest.length} into it`, say: `merge all ${rest.length} into “${B.name}”`,
          run: async () => (await sure(`Merge ${rest.length} motifs into “${B.name}”?`, '⤵ merge them', t))
            && batch(rest.map((i) => ({ action: 'merge', source: i, target: b })), `⤵ merged ${rest.length} into “${B.name}”`).then(clear) },
        { label: '↳ all rest on it', say: `make each of the ${rest.length} rest on “${B.name}”`,
          run: () => batch(rest.map((i) => ({ action: 'parent', id: i, parent: b })), `↳ ${rest.length} rest on “${B.name}”`).then(clear) },
        { label: '↔ all related to it', say: `relate each of the ${rest.length} to “${B.name}”`,
          run: () => batch(rest.map((i) => ({ action: 'relate', a: i, b })), `↔ ${rest.length} related to “${B.name}”`).then(clear) },
        { label: '📁 a group of these', say: `start a new group with all ${rest.length + 1} in it`,
          run: () => newGroupOf(t, [b, ...rest]).then((ok) => ok && clear()) },
      ]
    }
    if (drop === 'facet') {
      const value = t.dataset.g || null
      return [{ label: value ? `🎭 all: ${value}` : '🎭 all: no genre', say: value ? `give ${n} the genre ${value}` : `take the genre off ${n}`,
        run: () => batch(ids.map((i) => ({ action: 'facet', id: i, facet: 'genre', value })), `🎭 ${n}: ${value || 'no genre'}`).then(clear) }]
    }
    if (drop === 'group') {
      const g = t.dataset.g || null
      const gname = m.data.groups.find((x) => x.id === g)?.name
      if (!g) return [{ label: '🗃️ all out of every group', say: `take ${n} out of every group`,
        run: () => batch(ids.map((i) => ({ action: 'group_assign', id: i, group: null })), `🗃️ ${n}: no group`).then(clear) }]
      return [
        { label: '📁 all into this group', say: `put ${n} in ${gname} as well, staying in their other groups`,
          run: () => batch(ids.filter((i) => !(m.by[i].groups ?? []).includes(g)).map((i) => ({ action: 'group_member', id: i, group: g })), `📁 ${n} in ${gname}`).then(clear) },
        { label: '⇢ all only this group', say: `move ${n} to ${gname} only, out of their other groups`,
          run: () => batch(ids.map((i) => ({ action: 'group_assign', id: i, group: g })), `📁 ${n} → ${gname}`).then(clear) },
      ]
    }
    if (drop === 'trash') {
      return [{ label: `🗑️ delete all ${ids.length}`, say: `delete all ${ids.length} motifs (their claims aren’t filed again)`,
        run: async () => (await sure(`Delete ${n}? Their claims won't be filed again.`, '🗑️ delete them', t))
          && batch(ids.map((i) => ({ action: 'delete', id: i })), `🗑️ deleted ${n}`).then(clear) }]
    }
    return []
  }
  // a motif
  const a = item.id, A = m.by[a]
  if (!A) return []
  if (drop === 'motif') {
    const b = t.dataset.id!, B = m.by[b]
    if (!B || a === b) return []
    return [
      { label: '⤵ merge into it', say: `merge “${A.name}” into “${B.name}”`, run: () => act({ action: 'merge', source: a, target: b }, `⤵ merged “${A.name}” into “${B.name}”`) },
      { label: '↳ rests on it', say: `make “${A.name}” rest on “${B.name}”`, run: () => act({ action: 'parent', id: a, parent: b }, `↳ “${A.name}” rests on “${B.name}”`) },
      { label: '↰ it rests on this', say: `make “${B.name}” rest on “${A.name}”`, run: () => act({ action: 'parent', id: b, parent: a }, `↰ “${B.name}” rests on “${A.name}”`) },
      { label: '↔ related', say: `relate “${A.name}” and “${B.name}”: related, but different`, run: () => act({ action: 'relate', a, b }, `↔ related “${A.name}” and “${B.name}”`) },
      { label: '≠ not the same', say: `“${A.name}” and “${B.name}” are different: stop suggesting them as a pair`, run: () => act({ action: 'not_same', a, b }, `≠ “${A.name}” and “${B.name}” are different`) },
      { label: '📁 a group of these', say: `start a new group with “${A.name}” and “${B.name}” in it`, run: () => newGroupOf(t, [a, b]) },
    ]
  }
  const on = drop === 'claim' ? (t.dataset.claim ? { claim: t.dataset.claim, src: t.dataset.src, ref: t.dataset.ref } : S.claim) : null
  if (on) { // a motif dropped on a claim card (🔍 claim, 🎯 claims to judge): that card's claim
    if (motifsOf(m, on.claim).some((e) => e.id === a)) return []
    return [{ label: '＋ file the claim here', say: `file the claim in “${A.name}”`, run: () => claimAction(on, 'add', a) }]
  }
  if (drop === 'facet') {
    const value = t.dataset.g || null
    if ((A.facets?.genre || null) === value) return []
    return [{ label: value ? '🎭 genre: ' + value : '🎭 no genre', say: value ? `give “${A.name}” the genre ${value}` : `take the genre off “${A.name}”`,
      run: () => act({ action: 'facet', id: a, facet: 'genre', value }, `🎭 “${A.name}”: ${value || 'no genre'}`) }]
  }
  if (drop === 'group') {
    const g = t.dataset.g || null, mine = A.groups ?? []
    if (!g) return mine.length ? [{ label: '🗃️ out of every group', say: `take “${A.name}” out of every group`,
      run: () => act({ action: 'group_assign', id: a, group: null }, `🗃️ “${A.name}”: no group`) }] : []
    if (mine.includes(g)) return []
    const gname = m.data.groups.find((x) => x.id === g)?.name
    const also = { label: '📁 into this group', say: mine.length ? `put “${A.name}” in ${gname} as well, staying in its other groups` : `put “${A.name}” in ${gname}`,
      run: () => act({ action: 'group_member', id: a, group: g }, `📁 “${A.name}” in ${gname}`) }
    return mine.length ? [also, { label: '⇢ only this group', say: `move “${A.name}” to ${gname} only, out of its other groups`,
      run: () => act({ action: 'group_assign', id: a, group: g }, `📁 “${A.name}” → ${gname}`) }] : [also]
  }
  if (drop === 'trash') {
    return [{ label: '🗑️ delete it', say: `delete “${A.name}” (its claims aren’t filed again)`,
      run: async () => (await sure(`Delete “${A.name}”? Its ${A.claims.length} claims won't be filed again.`, '🗑️ delete it', t))
        && act({ action: 'delete', id: a }, `🗑️ deleted “${A.name}”`) }]
  }
  return []
}

/** What a drag carries, from the element it starts on */
export function itemOf(el: HTMLElement): DragItem | null {
  const m = currentModel()
  if (!m) return null
  const S = getWB()
  if (el.dataset.drag === 'group') { // a group, from its folder in the list or its chip on the shelf: all its motifs
    const g = el.dataset.g!
    const ids = m.data.entries.filter((e) => (e.groups ?? []).includes(g)).map((e) => e.id)
    return ids.length ? { kind: 'motifs', ids, group: m.data.groups.find((x) => x.id === g)?.name } : null
  }
  if (el.dataset.drag === 'motif' && S.msel.length > 1 && S.msel.includes(el.dataset.id!)) {
    return { kind: 'motifs', ids: S.msel.filter((i) => m.by[i]) }
  }
  if (el.dataset.drag === 'motif') return { kind: 'motif', id: el.dataset.id! }
  const carried = (x: HTMLElement): Carried => ({ claim: x.dataset.claim!, source: x.dataset.source ?? '', src: x.dataset.src ?? '', ref: x.dataset.ref ?? '' })
  const p = el.closest('[data-panel]')
  if (p && el.classList.contains('sel')) { // a selected claim in an open motif: every selected one there
    const cs = [...p.querySelectorAll<HTMLElement>('.claim.sel')].map(carried)
    if (cs.length) return { kind: 'claim', claims: cs }
  }
  return { kind: 'claim', claims: [carried(el)] }
}

export function label(item: DragItem) {
  const m = currentModel()
  return item.kind === 'motifs' ? (item.group ? `📁 ${item.group}: ` : '🧩 ') + `${item.ids.length} motifs`
    : item.kind === 'motif' ? '🧩 ' + (m?.by[item.id]?.name ?? '') : '💬 ' + claimsName(item.claims)
}

/** A choice says what it does in full: the label's sign (⤵, ↳, 📁…) and its sentence; the short label alone if it has none */
export function zoneText(z: Zone) {
  if (!z.say) return z.label
  const sign = z.label.split(' ')[0]
  return /[\p{L}\p{N}]/u.test(sign) ? z.say : `${sign} ${z.say}`
}
