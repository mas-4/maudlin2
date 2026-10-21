// The left pane: every motif, in folders by group (or genre, or none), what rests on a motif nested under it. The
// views pick motifs (singles, no note, drafts…); a search or a view or a shelf filter shows a flat list instead
import type { MouseEvent, ReactNode } from 'react'
import { ask, sure } from '../components/Feedback'
import { act } from './act'
import { useCarrying, justDragged } from './DragLayer'
import { COLORS, matches, newCount, noteState, SORTS, useWorkbench, VIEWS, words, type Model } from './model'
import { addMotif, openMotif } from './ops'
import { editShelf, noteOf } from './Shelf'
import { getWB, setWB, useWB } from './store'
import type { Entry } from './types'

export function Tree() {
  const { model: m } = useWorkbench()
  const s = useWB((s) => s)
  const carrying = useCarrying()
  if (!m) return null
  const view = VIEWS.find((v) => v[0] === s.view) ?? VIEWS[0]
  const w = words(s.q)
  const f = s.shelfFilter
  const inShelf = (e: Entry) => !f ? true : f.kind === 'group' ? (f.id ? (e.groups ?? []).includes(f.id) : !(e.groups ?? []).length) : (e.facets?.genre ?? '') === f.id
  const shown = m.data.entries.filter((e) => view[2](m, e) && inShelf(e) && matches(e, w)).sort(SORTS[s.sort])
  const flat = s.view !== 'all' || w.length || f
  const by = s.groupby
  const genres = m.data.facets.genre ?? []
  const sectionsOf = (e: Entry) => by === 'none' ? [''] : by === 'genre' ? [e.facets?.genre ?? ''] : (e.groups ?? []).length ? e.groups! : ['']
  const shownIds = new Set(shown.map((e) => e.id))
  const order: string[] = [] // as the list shows them, for Shift-click runs
  const row = (e: Entry, depth: number, fold: string, gid?: string) => { order.push(e.id); return <Row key={(gid ?? '') + '/' + e.id + '/' + depth} m={m} e={e} depth={depth} fold={fold} gid={gid} order={order} /> }
  const branch = (e: Entry, depth: number, gid: string, seen: Set<string>): ReactNode[] => {
    if (seen.has(e.id)) return []
    seen = new Set(seen).add(e.id)
    const kids = (m.kids[e.id] ?? []).map((k) => m.by[k]).filter((k) => k && shownIds.has(k.id)).sort(SORTS[s.sort])
    const folded = s.folded.includes('m:' + e.id)
    return [row(e, depth, kids.length ? (folded ? '▸' : '▾') : '', gid), ...(folded ? [] : kids.flatMap((k) => branch(k, depth + 1, gid, seen)))]
  }
  let body: ReactNode
  if (flat) {
    const only = f && <> {f.kind === 'group' ? '📁 ' + (m.data.groups.find((g) => g.id === f.id)?.name ?? 'in no group') : '🎭 ' + (f.id || 'no genre yet')}{' '}
      <button className="mini" title="show every motif" onClick={() => setWB({ shelfFilter: null })}>✕</button></>
    body = (
      <div className="group">
        <div className="ghead">{shown.length} motif{shown.length === 1 ? '' : 's'}{only}</div>
        {f && noteOf(m, f.kind, f.id) && <div className="gnote">{noteOf(m, f.kind, f.id)}</div>}
        {shown.map((e) => row(e, 0, ''))}
      </div>
    )
  } else {
    const sections = by === 'none' ? [{ id: '', name: 'every motif' }]
      : by === 'genre' ? [...genres.map((v) => ({ id: v, name: v })), { id: '', name: 'no genre yet' }]
        : [...m.data.groups, { id: '', name: 'Ungrouped' }]
    body = sections.map((g) => {
      const inG = shown.filter((e) => sectionsOf(e).includes(g.id))
      if (!inG.length && !g.id) return null
      // Roots: rest on nothing in this section. What rests on a motif nests under it wherever that is (a motif with two
      // parents shows under both), and in its own groups too
      const roots = inG.filter((e) => !e.parents.some((p) => shownIds.has(p) && sectionsOf(m.by[p]).includes(g.id)))
      const key = 'g:' + by + ':' + g.id, folded = s.folded.includes(key) || (by === 'genre' && !inG.length)
      const kind = by === 'genre' ? 'genre' : 'group'
      return (
        <div key={key} className={'group' + (inG.length ? '' : ' empty-sec')} {...(by === 'none' ? {} : { 'data-drop': by === 'genre' ? 'facet' : 'group', 'data-g': g.id })}>
          <div className="ghead" {...(g.id && by === 'group' ? { 'data-drag': 'group', 'data-g': g.id, title: 'drag the group onto a genre to give all its motifs that genre' } : {})}>
            <button className="fold" onClick={() => toggleFold(key)}>{folded ? '▸' : '▾'}</button>
            <span className="gname">{by === 'none' ? '🧩 ' : by === 'genre' ? '🎭 ' : g.id ? '📁 ' : '🗃️ '}{g.name}</span> <i>{inG.length}</i>
            {g.id && by !== 'none' && (
              <span className="gtools">
                <button className="mini" title={`describe the ${kind}: the models read it`} onClick={(e) => void editShelf(m, 'note', kind, g.id, e.currentTarget)}>📝</button>
                {by === 'group' && <>
                  <button className="mini" title="rename" onClick={(e) => void renameGroup(m, g.id, e.currentTarget)}>✎</button>
                  <button className="mini" title="delete the group (its motifs stay)" onClick={async (e) => { if (await sure('Delete the group? Its motifs stay, ungrouped.', 'yes, do it', e.currentTarget)) void act({ action: 'group_delete', group: g.id }, '🗑️ group deleted') }}>🗑️</button>
                </>}
              </span>
            )}
          </div>
          {by !== 'none' && g.id && noteOf(m, kind, g.id) && <div className="gnote">{noteOf(m, kind, g.id)}</div>}
          {!folded && roots.flatMap((e) => branch(e, 0, g.id, new Set()))}
        </div>
      )
    })
  }
  const trayAll = by === 'genre' ? [...genres.map((v) => ({ id: v, name: v })), { id: '', name: 'no genre' }] : [...m.data.groups, { id: '', name: 'no group' }]
  return (
    <section className="pane tree-pane" aria-label="All motifs">
      <div className="pane-head">
        <div className="views">
          {VIEWS.map(([k, label, test]) => (
            <button key={k} className={'view' + (s.view === k ? ' on' : '')} onClick={() => setWB({ view: k })}>{label} <i>{m.data.entries.filter((e) => test(m, e)).length}</i></button>
          ))}
        </div>
        <div className="tree-tools">
          <select aria-label="sort" value={s.sort} onChange={(e) => setWB({ sort: e.target.value })}>
            <option value="size">biggest first</option><option value="az">A–Z</option>
            <option value="new">newest first</option><option value="old">oldest first</option>
          </select>
          <select aria-label="sort the motifs into" title="sort the motifs into your groups, or by genre" value={by} onChange={(e) => setWB({ groupby: e.target.value as 'group' })}>
            <option value="group">📁 by group</option><option value="genre">🎭 by genre</option><option value="none">🧩 no folders</option>
          </select>
          <button className="btn" title="a new empty motif" onClick={(e) => void addMotif(e.currentTarget)}>＋ motif</button>
        </div>
      </div>
      {carrying?.kind === 'motif' && ( // while a motif is carried: every group (or genre) as a drop, wherever the tree is scrolled
        <div className="gtray">
          <span className="faint">{by === 'genre' ? '🎭 genres' : '📁 groups'}:</span>
          {trayAll.map((g) => <span key={g.id} className="gchip" data-drop={by === 'genre' ? 'facet' : 'group'} data-g={g.id}>{by === 'genre' ? '🎭' : g.id ? '📁' : '🗃️'} {g.name}</span>)}
        </div>
      )}
      <div className="scroll tree" data-scroll>
        {s.msel.length > 0 && <div className="selbar">☑️ <b>{s.msel.length}</b> selected · drag any of them to move them all <button className="mini" onClick={() => setWB({ msel: [], mlast: null })}>✕ clear</button></div>}
        {body}
        {!shown.length && <p className="empty">🦗 nothing here</p>}
      </div>
    </section>
  )
}

const toggleFold = (key: string) => setWB((s) => ({ folded: s.folded.includes(key) ? s.folded.filter((k) => k !== key) : [...s.folded, key] }))
async function renameGroup(m: Model, id: string, anchor: Element) {
  const g = m.data.groups.find((x) => x.id === id)
  const n = await ask('Rename the group', g?.name ?? '', { anchor })
  if (n) void act({ action: 'group_rename', group: id, name: n }, '✎ group renamed')
}

function Row({ m, e, depth, fold, gid, order }: { m: Model; e: Entry; depth: number; fold: string; gid?: string; order: string[] }) {
  const open = useWB((s) => s.open.indexOf(e.id))
  const msel = useWB((s) => s.msel.includes(e.id))
  const by = useWB((s) => s.groupby)
  const n = newCount(e), ns = noteState(e)
  const others = gid !== undefined && by !== 'genre' ? (e.groups ?? []).filter((g) => g !== gid).map((g) => m.data.groups.find((x) => x.id === g)?.name).filter(Boolean) : []
  const click = (ev: MouseEvent) => {
    if (justDragged() || (ev.target as Element).closest('button')) return
    const s = getWB()
    if (ev.shiftKey || ev.ctrlKey || ev.metaKey) { // selecting motifs in the list
      if (ev.shiftKey && s.mlast) { // everything from the last one clicked to this one, as the list shows them
        const ids = [...new Set(order)], i = ids.indexOf(s.mlast), j = ids.indexOf(e.id)
        const add = i >= 0 && j >= 0 ? ids.slice(Math.min(i, j), Math.max(i, j) + 1) : [e.id]
        setWB({ msel: [...new Set([...s.msel, ...add])] })
      } else setWB({ msel: s.msel.includes(e.id) ? s.msel.filter((x) => x !== e.id) : [...s.msel, e.id], mlast: e.id })
      return
    }
    setWB({ msel: [], mlast: e.id }) // a plain click: the start of a run for the next Shift-click, and it opens
    openMotif(e.id)
  }
  return (
    <div className={'row' + (open >= 0 ? ' open o' + (open % COLORS) : '') + (msel ? ' msel' : '')} style={{ ['--depth' as string]: depth }}
      data-drag="motif" data-drop="motif" data-id={e.id} onClick={click}
      onAuxClick={(ev) => { if (ev.button === 1) { ev.preventDefault(); window.open(`/ui/workbench?motif=${e.id}`, '_blank') } }}>
      {fold ? <button className="fold" onClick={() => toggleFold('m:' + e.id)}>{fold}</button> : <span className="fold-sp" />}
      <span className="rname">{depth > 0 && <span className="faint">↳ </span>}{e.name}</span>
      {others.length > 0 && <span className="also" title={`also in ${others.join(', ')}`}>📁{others.length > 1 ? others.length : ''}</span>}
      <span className="badges">
        {e.done === 'done' && <b title="done">✓</b>}{n > 0 && <b className="b-new" title="new since done">🆕{n}</b>}
        {ns === 'none' ? <b title="no note yet" className="b-faint">📝</b> : ns === 'draft' ? <b title="the note is a draft">🤖</b> : null}
        {e.stands_alone && <b title="stands alone">🧍</b>}
      </span>
      <i className="n">{e.claims.length}</i>
      {gid && by === 'group' && (e.groups ?? []).includes(gid) && (
        <button className="mini side" title="take it out of this group" onClick={() => void act({ action: 'group_member', id: e.id, group: gid, on: false }, '📁 out of the group')}>✕</button>
      )}
      <button className="mini side" title="open it too, under the others (compare)" onClick={() => openMotif(e.id, true)}>⧉</button>
    </div>
  )
}
