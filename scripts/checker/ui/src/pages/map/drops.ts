// The map's own drop targets, added to the workbench's drag engine while the map is shown (zones.ts extendZones):
// 📌 the desk, ＋ new group, a claim onto ✨ as a copy in a new motif (also_new), and a motif out of a group it's
// already in. Over a dot, the workbench's motif choices, with a link already there offered undone instead (as the old
// map did): ✕ doesn't rest on it, ✕ unrelate.
import { ask } from '../../components/Feedback'
import { act } from '../../workbench/act'
import { currentModel, groupName } from '../../workbench/model'
import { setWB } from '../../workbench/store'
import type { DragItem, Zone } from '../../workbench/types'
import { claimsName } from '../../workbench/zones'

export interface MapDrops {
  pin: (ids: string[]) => void // onto the desk
  made: (id: string) => void // a motif just made: picked on the map
}

const clear = () => setWB({ msel: [] })

/** A new group, named in a card by what was pressed or dropped on, with these motifs in it (none: an empty group) */
export async function newGroup(anchor: Element | null, ids: string[]) {
  const n = await ask(ids.length ? `Name the new group (${ids.length} motif${ids.length === 1 ? '' : 's'} in it)` : 'Name the new group', '', { anchor })
  if (!n) return false
  return act({ action: 'group_new', name: n, ...(ids.length ? { ids } : {}) }, `📁 new group ${n}${ids.length ? `, with ${ids.length} in it` : ''}`)
}

export function mapZones(item: DragItem, t: HTMLElement, base: () => Zone[], h: MapDrops): Zone[] | null {
  const m = currentModel()
  if (!m) return null
  const drop = t.dataset.drop
  const nameOf = (id: string) => m.by[id]?.name ?? id
  if (drop === 'desk') {
    const ids = item.kind === 'motifs' ? item.ids : item.kind === 'motif' ? [item.id] : [...new Set(item.claims.map((c) => c.source).filter((id) => m.by[id]))]
    if (!ids.length) return []
    return ids.length === 1
      ? [{ label: '📌 open on the desk', say: `keep “${nameOf(ids[0])}” open on the desk, on the right, while you work`, run: () => h.pin(ids) }]
      : [{ label: `📌 all ${ids.length} on the desk`, say: `keep all ${ids.length} open on the desk, on the right`, run: () => { h.pin(ids); clear() } }]
  }
  if (drop === 'newgroup') {
    if (item.kind === 'claim') return []
    const ids = item.kind === 'motif' ? [item.id] : item.ids
    return [{ label: '📁 a new group', say: ids.length === 1 ? `start a new group with “${nameOf(ids[0])}” in it` : `start a new group with all ${ids.length} in it`,
      run: () => newGroup(t, ids).then((ok) => ok && clear()) }]
  }
  if (drop === 'newmotif' && item.kind === 'claim' && item.claims.length === 1 && m.by[item.claims[0].source]) {
    const c = item.claims[0]
    return [{ label: '✨ new motif', say: `start a new motif with ${claimsName([c])}, keeping it where it is`,
      run: async () => {
        const n = await ask('Name the new motif', c.claim.slice(0, 80), { anchor: t })
        if (!n) return
        const before = new Set(currentModel()?.data.entries.map((e) => e.id))
        if (await act({ action: 'also_new', claim: c.claim, source: c.source, name: n }, `✨ made “${n}”`)) {
          const made = currentModel()?.data.entries.find((e) => !before.has(e.id))
          if (made) h.made(made.id)
        }
      } }]
  }
  if (drop === 'group' && item.kind === 'motif') {
    const g = t.dataset.g, A = m.by[item.id]
    if (!g || !A || !(A.groups ?? []).includes(g)) return null
    const gname = groupName(m, g)
    return [{ label: '✕ out of this group', say: `take “${A.name}” out of ${gname}`,
      run: () => act({ action: 'group_member', id: A.id, group: g, on: false }, `✕ “${A.name}” out of ${gname}`) }]
  }
  if (drop === 'motif' && item.kind === 'motif') {
    const A = m.by[item.id], B = m.by[t.dataset.id ?? '']
    if (!A || !B || A.id === B.id) return null
    return base().flatMap((z): Zone[] => {
      const sign = z.label.split(' ')[0]
      if (sign === '↳' && A.parents.includes(B.id)) {
        return [{ label: '✕ doesn’t rest on it', say: `“${A.name}” no longer rests on “${B.name}”`,
          run: () => act({ action: 'parent', id: A.id, parent: B.id, on: false }, `✕ “${A.name}” no longer rests on “${B.name}”`) }]
      }
      if (sign === '↰' && B.parents.includes(A.id)) {
        return [{ label: '✕ it doesn’t rest on this', say: `“${B.name}” no longer rests on “${A.name}”`,
          run: () => act({ action: 'parent', id: B.id, parent: A.id, on: false }, `✕ “${B.name}” no longer rests on “${A.name}”`) }]
      }
      if (sign === '↔' && A.related.includes(B.id)) {
        return [{ label: '✕ unrelate', say: `“${A.name}” and “${B.name}” no longer linked as related`,
          run: () => act({ action: 'unrelate', a: A.id, b: B.id }, `✕ “${A.name}” and “${B.name}” no longer related`) }]
      }
      return [z]
    })
  }
  return null
}
