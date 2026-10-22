// The workbench's bar: the motif search, the counts, the drops (new motif, no motif, take out), 📦 export, 📈 pace, ❓
import { useEffect, useRef, useState } from 'react'
import { useJSON } from '../lib/queries'
import { useWorkbench } from './model'
import { openMotif } from './ops'
import { setWB, useWB } from './store'

export function TopBar() {
  const { model } = useWorkbench()
  const q = useWB((s) => s.q)
  const search = useRef<HTMLInputElement>(null)
  useEffect(() => { // '/' finds a motif, wherever you are (not while typing)
    const key = (ev: KeyboardEvent) => {
      const t = ev.target as HTMLElement | null
      if (ev.key === '/' && !t?.closest?.('input, textarea, select') && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
        ev.preventDefault()
        search.current?.focus()
      }
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [])
  const es = model?.data.entries ?? []
  const filings = es.reduce((n, e) => n + e.claims.length, 0)
  return (
    <header className="wb-bar">
      <h1 title="Motif workbench">🧰 <span className="t">Motif workbench</span></h1>
      <label className="wb-search">🔎 <input ref={search} type="search" value={q} autoComplete="off"
        placeholder="find a motif by name, note or M-number  (press /)"
        onChange={(e) => setWB({ q: e.target.value })}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            const first = document.querySelector<HTMLElement>('.tree .row')
            if (first) openMotif(first.dataset.id!, e.shiftKey)
          }
          if (e.key === 'Escape') setWB({ q: '' })
        }} /></label>
      {model && (
        <span className="wb-stats">
          <b>{es.filter((e) => e.attested).length}</b> attested <span className="faint" title="told about two or more different events (the rest are placed: one event so far)">of</span>{' '}
          <b>{es.length}</b> motifs · <b>{filings}</b> filings · <b>{es.filter((e) => e.claims.length > 1).length}</b> with 2+ ·{' '}
          <b>{es.filter((e) => e.done !== 'done').length}</b> not done
        </span>
      )}
      <span className="wb-drops" aria-label="Drop here">
        <span className="drop" data-drop="newmotif" title="drop claims here to start a new motif">✨ new motif</span>
        <span className="drop" data-drop="nomotif" title="drop claims here: they tell no recurring story">∅ no motif</span>
        <span className="drop" data-drop="trash" title="drop a claim to take it out of its motif, or a motif to delete it">🗑️ take out</span>
      </span>
      <Popover label="📦 export" title="download the motif index">
        <div className="export-menu">
          <p>✅ <b>verified</b> (what the site shows)</p>
          {exportLinks('verified', ['📄 readable (.md)', '📊 spreadsheet (.csv)', '🧱 data (.json)', '🕸️ SKOS (.ttl)'])}
          <p>🧩 <b>everything</b> (unverified too)</p>
          {exportLinks('all', ['📄 .md', '📊 .csv', '🧱 .json', '🕸️ .ttl'])}
        </div>
      </Popover>
      <Popover label="📈 pace" title="your pace: claims judged a day against what arrives, and how many hold the queue steady" wide>
        <Pace />
      </Popover>
      <Help />
    </header>
  )
}

const exportLinks = (scope: string, labels: string[]) =>
  ['md', 'csv', 'json', 'ttl'].map((f, i) => <a key={f} href={`/motif-export?format=${f}&scope=${scope}`} download>{labels[i]}</a>)

/** A button that opens a box beneath it, toward the side with room; a click elsewhere closes it */
function Popover({ label, title, wide, children }: { label: string; title: string; wide?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const [left, setLeft] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const me = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    if (box.current && box.current.getBoundingClientRect().left < 0) setLeft(true)
    const away = (ev: MouseEvent) => { if (!me.current?.contains(ev.target as Node)) setOpen(false) }
    document.addEventListener('click', away)
    return () => document.removeEventListener('click', away)
  }, [open])
  return (
    <span className="popover" ref={me}>
      <button className="btn" title={title} onClick={() => { setLeft(false); setOpen(!open) }}>{label}</button>
      {open && <div ref={box} className={'pop' + (wide ? ' wide' : '') + (left ? ' left' : '')}>{children}</div>}
    </span>
  )
}

// 📈 pace (Oct 18, the person: "how many am i at? ... a graph overview and how many to finish to hold steady"): claims
// judged a day against claims that arrived, and the day's target. Read fresh each time it opens
interface PaceData { days: { day: string; arrived: number | null; judged: number }[]; today: number; steady: number | null; waiting: number; clear_in_14?: number }
const PACE = { arrived: '#e8590c', judged: '#1c7ed6' } // validated for colour blindness
function Pace() {
  const { data: p, error } = useJSON<PaceData>('/pace.json', undefined, { refetchInterval: 0 })
  if (error) return <p>😬 couldn’t count</p>
  if (!p) return <p className="faint">⏳ counting…</p>
  const left = p.steady != null ? p.steady - p.today : null
  return (
    <>
      <p className="pace-big">Today: <b>{p.today}</b> judged{left != null && (left > 0 ? <> · <b>{left}</b> more to hold steady today</> : <> · 🎉 steady: <b>{-left}</b> over today's {p.steady}</>)}</p>
      <p className="faint">{p.waiting} claims waiting.{p.clear_in_14 ? ` About ${p.clear_in_14} a day clears them in two weeks.` : ''} Steady is the median of claims arriving a day over the last week.</p>
      <PaceChart p={p} />
      <p className="pace-key"><span><i style={{ background: PACE.arrived }} /> arrived</span> <span><i style={{ background: PACE.judged }} /> you judged</span> <span><i className="dash" /> hold steady</span></p>
      <details className="pace-table"><summary className="faint">as a table</summary>
        <table><thead><tr><th>day</th><th>arrived</th><th>judged</th></tr></thead>
          <tbody>{[...p.days].reverse().map((d) => <tr key={d.day}><td>{d.day}</td><td>{d.arrived ?? '–'}</td><td>{d.judged}</td></tr>)}</tbody></table>
      </details>
    </>
  )
}

function PaceChart({ p }: { p: PaceData }) {
  const days = p.days, W = 460, H = 170, L = 30, B = 22, T = 10, slot = (W - L) / days.length, bw = Math.max(4, slot / 2 - 3)
  // a one-off day (the Oct 15 refile, 755) would flatten the rest: the scale stops at 2.5 times the steady pace
  const top = Math.max(10, Math.ceil((p.steady || 10) * 2.5), ...days.map((d) => d.judged))
  const y = (v: number) => T + (H - T - B) * (1 - Math.min(v, top) / top)
  const bar = (x: number, v: number | null, color: string, what: string, day: string) => v == null ? null : (
    <g key={what + day}>
      <rect x={x} y={y(v)} width={bw} height={Math.max(0, y(0) - y(v))} rx={2} fill={color}><title>{day}: {v} {what}</title></rect>
      {v > top && <text x={x + bw / 2} y={T + 9} textAnchor="middle" className="pace-num">{v}↑</text>}
    </g>
  )
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pace-svg" role="img" aria-label={`claims arrived and judged a day, last ${days.length} days`}>
      {[0, Math.round(top / 2), top].map((v) => (
        <g key={v}><line x1={L} x2={W} y1={y(v)} y2={y(v)} className="pace-grid" /><text x={L - 4} y={y(v) + 4} textAnchor="end" className="pace-axis">{v}</text></g>
      ))}
      {days.map((d, i) => {
        const x = L + i * slot + 2, label = d.day.slice(5).replace('-', '/')
        return (
          <g key={d.day}>
            {bar(x, d.arrived, PACE.arrived, 'claims arrived', label)}{bar(x + bw + 1, d.judged, PACE.judged, 'claims you judged', label)}
            {i % 2 !== days.length % 2 && <text x={x + bw} y={H - 6} textAnchor="middle" className="pace-axis">{label}</text>}
          </g>
        )
      })}
      {p.steady != null && (
        <g><line x1={L} x2={W} y1={y(p.steady)} y2={y(p.steady)} className="pace-steady" /><text x={W} y={y(p.steady) - 4} textAnchor="end" className="pace-axis">hold steady {p.steady}</text></g>
      )}
    </svg>
  )
}

function Help() {
  const dlg = useRef<HTMLDialogElement>(null)
  return (
    <>
      <button className="btn" title="how this works" onClick={() => dlg.current?.showModal()}>❓</button>
      <dialog ref={dlg} className="help">
        <h2>🧰 How the workbench works</h2>
        <p><b>Left:</b> every motif, by group, with what rests on a motif nested under it. The chips at the top are views (singles, no note, drafts…). Click a motif to open it; ⧉ opens it under the first; <b>Shift-click</b> selects a run of motifs in the list (<b>Ctrl-click</b> one more) to drag together; a plain click opens in the outlined panel.</p>
        <p><b>Middle:</b> the open motif: rename it, write its note, mark it done, and work its claims. Click claims to select several (Shift-click for a run).</p>
        <p><b>Right:</b> the inbox: claims to judge, one at a time with every motif they're in (✓ fits or ✕ take out each; <kbd>Y</kbd> all fit, <kbd>→</kbd> next, <kbd>←</kbd> back, <kbd>H</kbd> hold), pairs that may be one motif, single motifs, claims not filed yet, empty motifs.</p>
        <p><b>Drag anything onto anything</b> (hold a moment on a phone): a claim onto a motif files or moves it; a claim onto another claim says they're the same claim told two ways; a motif onto a motif merges, nests or relates them; a motif onto a group moves it there, onto a genre gives it that genre. Hover a target and its choices pop up; let go on one. The drops in the top bar start a new motif, say "no motif", or take a claim out.</p>
        <p><b>Columns:</b> drag the bars between the panes to make one wider (double-click a bar to reset). Hover a motif to see its note and claims.</p>
        <p><b>📦 Export</b> downloads the index: only verified motifs (what the site shows) or everything, as a readable catalog, a spreadsheet (a row per claim), JSON, or SKOS for linking to other catalogs.</p>
        <p><b>Keys:</b> <kbd>/</kbd> search motifs · <kbd>Ctrl</kbd>+<kbd>Z</kbd> undo · <kbd>Esc</kbd> cancel a drag or close a menu.</p>
        <form method="dialog"><button className="btn">got it 👍</button></form>
      </dialog>
    </>
  )
}
