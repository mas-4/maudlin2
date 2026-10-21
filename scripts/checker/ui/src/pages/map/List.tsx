// The list left of the map: the groups with their motifs, the rests-on links as a nested list (what rests on a motif
// under it; one resting on two shows under both), the related motifs outside them, and everything else. Click one to
// go to it on the map; drag one onto a dot, a chip or the 📌. A search narrows it (a match's broader motifs and its
// group stay, to show where it is).
import type { ReactNode } from 'react'
import { groupColor, words, type Model } from '../../workbench/model'
import type { Entry } from '../../workbench/types'

const az = (a: Entry, b: Entry) => a.name.localeCompare(b.name)

export function List({ m, q, focus, onGo }: { m: Model; q: string; focus: string | null; onGo: (id: string) => void }) {
  const w = words(q)
  const hit = (text: string) => { const t = text.toLowerCase(); return w.every((x) => t.includes(x)) }
  const es = m.data.entries
  const kidsOf = (id: string) => (m.kids[id] ?? []).map((k) => m.by[k]).filter(Boolean).sort(az)
  const row = (e: Entry, depth: number, key: string, meta: ReactNode) => (
    <div key={key} className={'row mm-row' + (e.id === focus ? ' on' : '')} style={{ ['--depth' as string]: depth }}
      data-drag="motif" data-drop="motif" data-id={e.id} onClick={() => onGo(e.id)}>
      <span className="mm-rname">🧩 {e.name}</span> <span className="faint">{meta}</span>
    </div>
  )
  // a motif and what rests on it, nested; shown if it or anything under it matches the search
  const item = (e: Entry, depth: number, path: Set<string>, key: string): ReactNode => {
    const p = new Set(path).add(e.id)
    const kids = path.has(e.id) ? [] : kidsOf(e.id).map((k) => item(k, depth + 1, p, key + '>' + k.id)).filter(Boolean)
    if (w.length && !hit(e.name) && !kids.length) return null
    return [row(e, depth, key, <>{e.claims.length}{e.related.length ? ' · ↔ ' + e.related.length : ''}</>), ...kids]
  }
  const roots = es.filter((e) => !e.parents.length && kidsOf(e.id).length).sort(az)
  const rel = es.filter((e) => !e.parents.length && !kidsOf(e.id).length && e.related.length).sort(az)
  // every motif somewhere in the list: those the sections above don't hold, A to Z
  const listed = new Set<string>()
  const walk = (e: Entry) => { if (listed.has(e.id)) return; listed.add(e.id); kidsOf(e.id).forEach(walk) }
  roots.forEach(walk)
  rel.forEach((e) => listed.add(e.id))
  const rest = es.filter((e) => !listed.has(e.id) && !e.parents.length && !(e.groups ?? []).length).sort(az)

  const groups = m.data.groups.map((g, k) => {
    const ms = es.filter((e) => (e.groups ?? []).includes(g.id)).sort(az)
    const shown = w.length ? ms.filter((e) => hit(e.name)) : ms
    if (w.length && !shown.length && !hit('📁 ' + g.name)) return null
    return (
      <div key={g.id} className="mm-lgroup">
        <b style={{ color: groupColor(k) }}>📁 {g.name}</b>
        {shown.map((e) => row(e, 1, g.id + '/' + e.id, e.claims.length))}
      </div>
    )
  }).filter(Boolean)
  const tree = roots.map((e) => item(e, 0, new Set(), 'r/' + e.id)).filter(Boolean)
  const related = rel.filter((e) => !w.length || hit(e.name))
    .map((e) => row(e, 0, 'rel/' + e.id, '↔ ' + e.related.map((r) => m.by[r]?.name ?? r).join(', ')))
  const others = rest.filter((e) => !w.length || hit(e.name)).map((e) => row(e, 0, 'x/' + e.id, e.claims.length))
  const searching = w.length > 0
  return (
    <div className="mm-list" data-scroll>
      {groups.length > 0 && <><h3>Groups</h3>{groups}</>}
      {(!searching || tree.length > 0) && <>
        <h3>Rests on</h3>
        {!searching && <p className="faint">Motifs with what rests on them under them (one resting on two shows under both). Click one to find it on the map.</p>}
        {tree.length ? tree : <p className="faint">Nothing rests on anything yet.</p>}
      </>}
      {(!searching || related.length > 0) && <>
        <h3>Related, outside the rests-on links</h3>
        {related.length ? related : <p className="faint">None.</p>}
      </>}
      {(!searching || others.length > 0) && <>
        <h3>Everything else <span className="faint">{rest.length}</span></h3>
        {!searching && <p className="faint">No links, no related, no group yet. Click one to put it on the map.</p>}
        {others}
      </>}
    </div>
  )
}
