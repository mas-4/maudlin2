// The shelf: groups and genres side by side above the panes. A chip each, with its count: click it to show only its
// motifs on the left (again to show all), drop a motif on it to put it in, ✎ renames, 📝 describes, ✕ removes
import { useRef, type PointerEvent as RPE } from 'react'
import { ask, sure } from '../components/Feedback'
import { act } from './act'
import { genreColor, groupName, useWorkbench, type Model } from './model'
import { getWB, setWB, useWB, type Shelf as ShelfFilter } from './store'

export const noteOf = (m: Model, kind: string, id: string) =>
  (kind === 'group' ? m.data.groups.find((g) => g.id === id)?.note : m.data.facet_notes?.genre?.[id]) ?? ''

export async function editShelf(m: Model, how: 'rename' | 'note' | 'delete', kind: 'group' | 'genre', id: string, anchor?: Element | null) {
  const name = kind === 'group' ? m.data.groups.find((g) => g.id === id)?.name ?? id : id
  if (how === 'rename') {
    const n = await ask(kind === 'group' ? 'Rename the group' : 'Rename the genre (on every motif that has it)', name, { anchor })
    if (!n || n === name) return
    const f = getWB().shelfFilter
    if (kind === 'genre' && f?.kind === 'genre' && f.id === id) setWB({ shelfFilter: { kind, id: n } })
    return act(kind === 'group' ? { action: 'group_rename', group: id, name: n } : { action: 'facet_rename', facet: 'genre', value: id, to: n }, `✎ renamed to “${n}”`)
  }
  if (how === 'note') {
    const now = noteOf(m, kind, id)
    const n = await ask(kind === 'group' ? 'Describe the group: what its motifs have in common (empty: none)' : 'Describe the genre: what kind of thing its motifs are (empty: none)', now, { multiline: true, empty: true, anchor })
    if (n === null || n === now) return
    return act(kind === 'group' ? { action: 'group_note', group: id, note: n } : { action: 'facet_note', facet: 'genre', value: id, note: n }, n ? '📝 described' : '📝 description gone')
  }
  if (!(await sure(kind === 'group' ? `Delete the group “${name}”? Its motifs stay.` : `Remove the genre “${name}”? Its motifs will have no genre.`, '✕ yes', anchor))) return
  const f = getWB().shelfFilter
  if (f?.kind === kind && f.id === id) setWB({ shelfFilter: null })
  return act(kind === 'group' ? { action: 'group_delete', group: id } : { action: 'facet_remove', facet: 'genre', value: id }, `✕ “${name}” gone`)
}

export function Shelf() {
  const { model: m } = useWorkbench()
  const filter = useWB((s) => s.shelfFilter)
  const height = useWB((s) => s.shelf)
  const folded = useWB((s) => s.shelfFolded)
  const box = useRef<HTMLElement>(null)
  if (!m) return null
  const ms = m.data.entries
  const genres = m.data.facets.genre ?? []
  const chip = (kind: 'group' | 'genre', id: string, label: string, n: number, color: string, tools: boolean) => {
    const on = filter?.kind === kind && filter.id === id
    const note = noteOf(m, kind, id)
    return (
      <span key={kind + id} className={'schip' + (on ? ' on' : '')} style={{ ['--g' as string]: color }}
        data-drop={kind === 'group' ? 'group' : 'facet'} data-g={id} {...(kind === 'group' && id ? { 'data-drag': 'group' } : {})}
        title={(note ? note + '\n\n' : '') + 'click: show only these · drop a motif here'}
        onClick={(ev) => { if (!(ev.target as Element).closest('button')) setWB({ shelfFilter: on ? null : ({ kind, id } as ShelfFilter) }) }}>
        {label} <i>{n}</i>
        {tools && <>
          <button className="x" title="rename" onClick={(e) => void editShelf(m, 'rename', kind, id, e.currentTarget)}>✎</button>
          <button className="x" title={note ? 'edit the description' : 'describe it: the models read it'} onClick={(e) => void editShelf(m, 'note', kind, id, e.currentTarget)}>📝</button>
          <button className="x" title={kind === 'group' ? 'delete the group (its motifs stay)' : 'remove the genre (its motifs keep none)'} onClick={(e) => void editShelf(m, 'delete', kind, id, e.currentTarget)}>✕</button>
        </>}
      </span>
    )
  }
  const add = (kind: 'group' | 'genre') => (
    <input className="shelfnew" placeholder={kind === 'group' ? '＋ new group, Enter' : '＋ new genre, Enter'}
      onKeyDown={(e) => {
        const n = e.currentTarget.value.trim()
        if (e.key !== 'Enter' || !n) return
        e.currentTarget.value = ''
        void act(kind === 'group' ? { action: 'group_add', name: n } : { action: 'facet_value', facet: 'genre', value: n }, `${kind === 'group' ? '📁' : '🎭'} made “${n}”`)
      }} />
  )
  // the bar under the shelf: drag it down for a taller shelf, up for a shorter one (remembered; double-click resets)
  const resize = (ev: RPE<HTMLDivElement>) => {
    ev.preventDefault()
    const bar = ev.currentTarget, start = ev.clientY
    const was = Math.max(...[...(box.current?.querySelectorAll('.shelfbox') ?? [])].map((b) => b.getBoundingClientRect().height))
    let h = was
    try { bar.setPointerCapture(ev.pointerId) } catch { /* a synthetic or ended pointer */ }
    document.body.classList.add('resizing-shelf')
    const move = (e: PointerEvent) => { h = Math.round(Math.min(innerHeight * 0.6, Math.max(40, was + e.clientY - start))); setWB({ shelf: h }) }
    const done = () => { bar.removeEventListener('pointermove', move); document.body.classList.remove('resizing-shelf') }
    bar.addEventListener('pointermove', move)
    bar.addEventListener('pointerup', done, { once: true })
    bar.addEventListener('lostpointercapture', done, { once: true })
  }
  // Folded (Oct 22: on a laptop the shelf took 136 of 768 px), it's one line: what it holds, and the filter in force.
  // It opens by itself while something is dragged, so it's still somewhere to drop a motif on a group or genre
  const shown = filter && (filter.kind === 'group' ? (filter.id ? '📁 ' + groupName(m, filter.id) : '🗃️ in no group') : (filter.id ? '🎭 ' + filter.id : '❔ no genre yet'))
  const fold = (
    <button className="shelf-fold" title={folded ? 'show the groups and genres' : 'fold the shelf to one line (it opens while you drag)'}
      onClick={() => setWB({ shelfFolded: !folded })}>
      {folded ? '▸' : '▾'} 📁 {m.data.groups.length} groups · 🎭 {genres.length} genres{folded && shown ? <> · showing only <b>{shown}</b></> : ''}
    </button>
  )
  return (
    <section ref={box} className={'shelf' + (folded ? ' folded' : '')} aria-label="Groups and genres" style={height ? { ['--shelf-h' as string]: `min(${height}px, 60vh)` } : undefined}>
      {fold}
      {folded && shown && <button className="mini" title="show every motif again" onClick={() => setWB({ shelfFilter: null })}>✕ show all</button>}
      <div className="shelfboxes">
      <div className="shelfbox">
        <b className="shelfhead">📁 groups</b>
        {m.data.groups.map((g) => chip('group', g.id, '📁 ' + g.name, ms.filter((e) => (e.groups ?? []).includes(g.id)).length, '#8a5cff', true))}
        {chip('group', '', '🗃️ in no group', ms.filter((e) => !(e.groups ?? []).length).length, '#bbb', false)}
        {add('group')}
      </div>
      <div className="shelfbox">
        <b className="shelfhead">🎭 genres</b>
        {genres.map((v) => chip('genre', v, '🎭 ' + v, ms.filter((e) => e.facets?.genre === v).length, genreColor(genres, v), true))}
        {chip('genre', '', '❔ no genre yet', ms.filter((e) => !e.facets?.genre).length, '#bbb', false)}
        {add('genre')}
      </div>
      </div>
      <div className="hsplit" title="drag down to make the shelf taller (double-click: back to the default)" onPointerDown={resize} onDoubleClick={() => setWB({ shelf: null })} />
    </section>
  )
}
