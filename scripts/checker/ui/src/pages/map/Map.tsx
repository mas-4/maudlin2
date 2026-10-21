// 🕸️ The motif map: every motif as a dot, what rests on what as arrows, groups as soft areas, a dot's genre as its
// colour. Click a dot to gather its neighbourhood round it; drag dots, names and claims onto one another with the
// workbench's drag engine. 🫧 shows each group as a bubble, 🧲 lays the motifs out by their claims alone, 🌳 draws the
// rests-on links as a tree. Ported from the old map (scripts/checker/templates/map.html); its settings in this browser
// (the hidden groups, the desk) carry over under the same localStorage keys.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { client, useJSON } from '../../lib/queries'
import { DragLayer } from '../../workbench/DragLayer'
import { HoverCard } from '../../workbench/bits'
import { genreColor, groupColor, useWorkbench } from '../../workbench/model'
import { setWB, useWB } from '../../workbench/store'
import { extendZones } from '../../workbench/zones'
import { Card } from './Card'
import { mapZones, newGroup } from './drops'
import { clusterColor, MapGraph, type ClaimMap, type Hooks, type MapOpts } from './graph'
import { List } from './List'
import '../../workbench/workbench.css' // the drag engine's ghost and menus, the motif chips and the hover card
import './map.css'

const recall = <T,>(k: string, d: T): T => {
  try {
    const v = localStorage.getItem(k)
    return v === null ? d : (JSON.parse(v) as T)
  } catch {
    return d
  }
}
const remember = (k: string, v: unknown) => {
  try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* a private window */ }
}

export function MotifMap() {
  const { model: m, error } = useWorkbench()
  const [showKind, setShowKind] = useState(true)
  const [related, setRelated] = useState<MapOpts['related']>('focus')
  const [sharedMin, setSharedMin] = useState(0)
  const [onlyLinked, setOnlyLinked] = useState(true)
  const [claimMode, setClaimMode] = useState(false)
  const [bubble, setBubble] = useState(false)
  const [tree, setTree] = useState(false)
  const [chipsFolded, setChipsFolded] = useState(() => { try { return localStorage.getItem('map-chips-folded') === '1' } catch { return false } })
  const [keyOpen, setKeyOpen] = useState(false)
  const [hidden, setHidden] = useState(() => new Set(recall<string[]>('map-hidden-groups', [])))
  const [pickedGenre, setPickedGenre] = useState<string | null>(null)
  const [pickedCluster, setPickedCluster] = useState<number | null>(null)
  const [q, setQ] = useState('')
  const [focus, setFocus] = useState<string | null>(null)
  const [count, setCount] = useState('')
  const [desk, setDesk] = useState(() => recall<string[]>('map-desk', []))
  const [foldedCards, setFoldedCards] = useState<Set<string>>(() => new Set())
  const msel = useWB((s) => s.msel)
  const claims = useJSON<ClaimMap>('/motif-claim-map.json', undefined, { enabled: claimMode })
  const svg = useRef<SVGSVGElement>(null)
  const area = useRef<HTMLDivElement>(null)
  const graph = useRef<MapGraph | null>(null)
  const [params, setParams] = useSearchParams()

  // the map's selection is the workbench's (so a drag of one selected dot carries them all), empty on the way in and out
  useEffect(() => {
    setWB({ msel: [] })
    return () => setWB({ msel: [] })
  }, [])
  useEffect(() => { // the page is the whole window: the list and the desk scroll, not the page
    document.body.classList.add('mm-page')
    return () => document.body.classList.remove('mm-page')
  }, [])

  const hooks = useMemo<Hooks>(() => ({
    onFocus: setFocus,
    onCount: setCount,
    onToggle: (id) => setWB((s) => ({ msel: s.msel.includes(id) ? s.msel.filter((x) => x !== id) : [...s.msel, id] })),
    onBox: (ids) => setWB((s) => ({ msel: [...new Set([...s.msel, ...ids])] })),
    onClearSel: () => setWB({ msel: [] }),
  }), [])
  useEffect(() => {
    const g = new MapGraph(svg.current!, area.current!, hooks)
    graph.current = g
    return () => { g.destroy(); graph.current = null }
  }, [hooks])

  const opts = useMemo<MapOpts>(() => ({
    showKind, related, sharedMin, onlyLinked, claimMode, bubble, tree, hiddenGroups: hidden, pickedGenre, pickedCluster,
    term: q.trim().toLowerCase(), msel, desk: desk.length > 0,
  }), [showKind, related, sharedMin, onlyLinked, claimMode, bubble, tree, hidden, pickedGenre, pickedCluster, q, msel, desk])
  useEffect(() => { if (m) graph.current?.update(m, claims.data ?? null, opts) }, [m, claims.data, opts])

  // 🧲 read again after each change (filing changes what the claims say), as the old page did on every load
  const claimModeNow = useRef(claimMode)
  claimModeNow.current = claimMode
  const lastModel = useRef(m)
  useEffect(() => {
    if (lastModel.current && m !== lastModel.current && claimModeNow.current) void client.invalidateQueries({ queryKey: ['/motif-claim-map.json'] })
    lastModel.current = m
  }, [m])

  // opened from a link: ?motif=M12 goes to it once the map has laid out
  useEffect(() => {
    const id = params.get('motif')
    if (!m || !id) return
    setParams({}, { replace: true })
    if (m.by[id]) window.setTimeout(() => graph.current?.center(id), 800)
  }, [m, params, setParams])

  // remembered in this browser, under the old page's keys
  useEffect(() => remember('map-hidden-groups', [...hidden]), [hidden])
  useEffect(() => { try { localStorage.setItem('map-chips-folded', chipsFolded ? '1' : '') } catch { /* a private window */ } }, [chipsFolded])
  useEffect(() => {
    if (!m) return // before the index arrives every pinned motif would look gone
    const there = desk.filter((id) => m.by[id])
    if (there.length !== desk.length) setDesk(there)
    else remember('map-desk', desk)
  }, [m, desk])

  // Esc (outside a text box) or a click on the background lets the picked motif go; the window resized lays it out again
  useEffect(() => {
    const key = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape' && !(ev.target as Element | null)?.closest?.('input, textarea, select')) graph.current?.pick(null)
    }
    let t = 0
    const resize = () => { clearTimeout(t); t = window.setTimeout(() => graph.current?.resized(), 200) }
    addEventListener('keydown', key)
    addEventListener('resize', resize)
    return () => { removeEventListener('keydown', key); removeEventListener('resize', resize); clearTimeout(t) }
  }, [])

  // the map's own drop targets, beside the workbench's, while the map is shown
  useEffect(() => extendZones((item, t, base) => mapZones(item, t, base, {
    pin: (ids) => setDesk((d) => [...ids, ...d.filter((x) => !ids.includes(x))]),
    made: (id) => graph.current?.center(id),
  })), [])

  const go = (id: string) => graph.current?.center(id)
  const toggleClaims = () => {
    const on = !claimMode
    if (on) { setTree(false); setBubble(false) }
    setPickedCluster(null)
    setClaimMode(on)
  }
  const toggleTree = () => { if (!tree) setClaimMode(false); setTree(!tree) }
  const toggleBubble = () => { if (!bubble) setClaimMode(false); setBubble(!bubble) }
  const toggleGroup = (g: string) => setHidden((h) => { const n = new Set(h); if (n.has(g)) n.delete(g); else n.add(g); return n })

  const es = m?.data.entries ?? []
  const genres = m?.data.facets.genre ?? []
  const cm = claimMode ? claims.data : undefined
  return (
    <div className="mm">
      <div className="mm-bar">
        <input type="search" className="mm-search" placeholder="🔎 find a motif" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') graph.current?.findFirst(q)
            if (e.key === 'Escape') setQ('')
          }} />
        <button className="btn" title="the whole map in view" onClick={() => graph.current?.fit()}>⤢ fit</button>
        <span className="faint">{count}</span>
        <label className="mm-key" title="the rests-on lines: the map's structure">
          <input type="checkbox" checked={showKind} onChange={(e) => setShowKind(e.target.checked)} />{' '}
          <svg width="26" height="10"><line x1="0" y1="5" x2="18" y2="5" stroke="#0a8f7e" strokeWidth="2" /><path d="M18,1 L26,5 L18,9 z" fill="#0a8f7e" /></svg> rests on
        </label>
        <label className="mm-key" title="related lines: drawn for the motif you pick or point at (they still shape the map), for every motif, or not at all">
          <svg width="24" height="10"><line x1="0" y1="5" x2="24" y2="5" stroke="#ff4fa3" strokeWidth="2" strokeDasharray="5 4" /></svg> related:{' '}
          <select value={related} onChange={(e) => setRelated(e.target.value as MapOpts['related'])}>
            <option value="focus">the picked one's</option><option value="all">all</option><option value="none">none</option>
          </select>
        </label>
        <label className="mm-key" title="grey lines between motifs holding at least this many of the same claims (told together; not a sign they're related)">
          <svg width="24" height="10"><line x1="0" y1="5" x2="24" y2="5" stroke="#9aa0a6" strokeWidth="2" /></svg>{' '}
          <select value={sharedMin} onChange={(e) => setSharedMin(+e.target.value)}>
            <option value="0">no shared-claim lines</option><option value="1">sharing 1+ claims</option><option value="2">sharing 2+</option><option value="3">sharing 3+</option>
          </select>
        </label>
        <label className="mm-key"><input type="checkbox" checked={onlyLinked} onChange={(e) => setOnlyLinked(e.target.checked)} /> only linked motifs</label>
        <button className={'btn' + (bubble ? ' on' : '')} onClick={toggleBubble}
          title="each group as one bubble until you open it (click a bubble); drop a motif on one to put it in the group">🫧 groups</button>
        <button className={'btn' + (claimMode ? ' on' : '')} onClick={toggleClaims}
          title="the motifs by their claims alone, none of your groups, genres or links: drawn together when they hold the same claims (grey: told together, not a sign they're related) or their claims read alike (purple), coloured by the clusters that makes">
          {claimMode && claims.isFetching ? '⏳' : '🧲'} claims
        </button>
        <button className={'btn' + (tree ? ' on' : '')} onClick={toggleTree}
          title="the rests-on links as a tree: what rests on nothing at the top, each motif a row below the deepest one it rests on (motifs outside them hidden)">🌳 tree</button>
        <button className={'btn' + (!chipsFolded ? ' on' : '')} onClick={() => setChipsFolded(!chipsFolded)}
          title="show or hide the group and genre chips (they open by themselves while you drag)">📁🎭 chips</button>
        <button className={'btn' + (keyOpen ? ' on' : '')} onClick={() => setKeyOpen(!keyOpen)} title="what the dots and lines mean, and how to work the map">ℹ️ key</button>
        <span className="mm-drops" aria-label="Drop here">
          <span className="mm-drop" data-drop="newmotif" title="drop a claim here to start a new motif with it">✨ new motif</span>
          <span className="mm-drop" data-drop="nomotif" title="drop a claim here: it tells no recurring story">∅ no motif</span>
          <span className="mm-drop" data-drop="trash" title="drop a claim to take it out of its motif, or a motif to delete it">🗑️ take out</span>
        </span>
      </div>
      {m && (
        <div className={'mm-bar mm-chips' + (chipsFolded ? ' folded' : '')}>
          {cm ? (
            <span className="mm-chiprow" title="the clusters the claims make: click one to pick out its motifs">
              🧲 {cm.clusters.map((c) => (
                <span key={c.id} className={'mm-chip' + (pickedCluster === c.id ? ' on' : '')} style={{ ['--g' as string]: clusterColor(c.id) }}
                  title={c.names.join(', ')} onClick={() => setPickedCluster(pickedCluster === c.id ? null : c.id)}>
                  {c.label} <i>{c.size}</i>
                </span>
              ))}
            </span>
          ) : (
            <span className="mm-chiprow" title="click a group to hide or show its area; drag a motif onto it to put it in (or take it out)">
              📁 {m.data.groups.map((g, k) => (
                <span key={g.id} className={'mm-chip' + (hidden.has(g.id) ? ' off' : '')} style={{ ['--g' as string]: groupColor(k) }}
                  data-drop="group" data-g={g.id} title={g.note || undefined} onClick={() => toggleGroup(g.id)}>
                  {g.name} <i>{es.filter((e) => (e.groups ?? []).includes(g.id)).length}</i>
                </span>
              ))}
              <span className="mm-chip mm-gnew" style={{ ['--g' as string]: '#8a8f98' }} data-drop="newgroup"
                title="click to make a new group, or drop a motif here to start one with it" onClick={(e) => void newGroup(e.currentTarget, [])}>＋ new group</span>
            </span>
          )}
          <span className="mm-chiprow" title="a dot's colour is its genre: click one to pick out its motifs; drag a motif onto one to give it that genre">
            🎭 {[...genres, ''].map((v) => (
              <span key={v || '-'} className={'mm-chip' + (pickedGenre === v ? ' on' : '')} style={{ ['--g' as string]: v ? genreColor(genres, v) : '#bbb' }}
                data-drop="facet" data-g={v} onClick={() => setPickedGenre(pickedGenre === v ? null : v)}>
                {v || 'no genre'} <i>{es.filter((e) => (e.facets?.genre ?? '') === v).length}</i>
              </span>
            ))}
          </span>
        </div>
      )}
      {keyOpen && (
        <div className="mm-bar mm-keyrow">
          <span className="mm-key" title="a dot's outline: its place in the rests-on links">
            <svg width="16" height="16"><circle cx="8" cy="8" r="6" fill="#fff" stroke="#1f1f2e" strokeWidth="3.5" /></svg> others rest on it{' '}
            <svg width="16" height="16"><circle cx="8" cy="8" r="6" fill="#fff" stroke="#1f1f2e" strokeWidth="2" strokeDasharray="3 2" /></svg> rests on one · fill: its genre · size: its claims
          </span>
          <span className="faint">
            Click a dot to pick it: its neighbourhood stays, the rest fades, and the map zooms to it; Esc or a click on the background brings it all back.
            Names show where they fit; zoom in for more, point at a dot for its name. Scroll to zoom, drag the background to pan, Shift-drag to select
            (or Ctrl/⌘/Shift-click dots). Drag a dot, a name on the left or a claim in a motif's box onto a dot or a name: its choices pop up; let go on
            one. 🧲 claims lays the motifs out by their claims alone, ignoring your groups, genres and links: grey lines join motifs holding the same claims
            (told together, not a sign they're related), faint purple ones motifs whose claims read alike; the colours are the clusters that makes (click a
            cluster's chip to pick it out).
          </span>
        </div>
      )}
      <datalist id="mm-names">{es.map((e) => <option key={e.id} value={e.name}>{e.id}</option>)}</datalist>
      <main className="mm-main">
        {m ? <List m={m} q={q} focus={focus} onGo={go} /> : <div className="mm-list" />}
        <div className={'mm-graph' + (desk.length ? ' desk-open' : '')} ref={area}>
          <svg ref={svg} className="mm-net" />
          {!m && <p className="mm-wait">{error ? `😬 couldn’t load the index: ${(error as Error).message}` : '⏳ loading the motifs…'}</p>}
          {msel.length > 0 && (
            <div className="mm-selbar">
              ☑️ <b>{msel.length}</b> selected · drag any of them to move them all{' '}
              <button className="mini" onClick={() => setWB({ msel: [] })}>✕ clear</button>
            </div>
          )}
          <div className="mm-deskdrop" data-drop="desk" title="drop a motif here to keep it open on the desk">📌{desk.length > 0 && <i>{desk.length}</i>}</div>
          {m && focus && m.by[focus] && (
            <div className="mm-info">
              <button className="mm-x" title="close" onClick={() => graph.current?.pick(null)}>✕</button>
              <Card m={m} id={focus} onGo={go} />
            </div>
          )}
          {m && desk.length > 0 && (
            <div className="mm-desk" data-scroll>
              {desk.map((id) => (
                <div key={id} className={'mm-dcard' + (foldedCards.has(id) ? ' closed' : '')}>
                  <button className="mm-x" title="take it off the desk" onClick={() => setDesk((d) => d.filter((x) => x !== id))}>✕</button>
                  <button className="mm-x" title="fold or unfold its claims"
                    onClick={() => setFoldedCards((f) => { const n = new Set(f); if (n.has(id)) n.delete(id); else n.add(id); return n })}>
                    {foldedCards.has(id) ? '▸' : '▾'}
                  </button>
                  <Card m={m} id={id} onGo={go} folded={foldedCards.has(id)} />
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
      <DragLayer />
      <HoverCard />
    </div>
  )
}
