// 🌊 Flow: news stories into retellings over time (GET /flow.json, app/analysis/flow.py). A row per news story we
// followed that was later told as a motif, its filings as dots on the days they were told. Click a dot or a motif to
// follow that motif across stories; click a story to read its filings. Read only: the workbench is where they change.
import { useCallback, useEffect, useMemo, useState, type MouseEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useJSON } from '../../lib/queries'
import { claimLink, motifLink } from '../../workbench/model'
import { genreColor, plural, shown, SOURCES, summary, type Filing, type FlowData, type Sort, type Source, type Story } from './data'
import { Timeline, type Tip } from './Timeline'
import './flow.css'

export function Flow() {
  const { data, error, isLoading } = useJSON<FlowData>('/flow.json')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<Sort>('first')
  const [plain, setPlain] = useState(true)
  const [sources, setSources] = useState<Set<Source>>(() => new Set(SOURCES.map((s) => s.key)))
  const [picked, setPicked] = useState<string | null>(null) // the motif followed
  const [story, setStory] = useState<number | null>(null) // the story whose panel is open
  const [tip, setTip] = useState<Tip | null>(null)

  const rows = useMemo(() => (data ? shown(data, { q, sort, plain, sources }, picked) : []), [data, q, sort, plain, sources, picked])
  // a dot, a chip or a link picks a motif or a story; picking the same one again lets it go
  const onMotif = useCallback((id: string) => { setStory(null); setPicked((p) => (p === id ? null : id)) }, [])
  const onStory = useCallback((id: number) => { setPicked(null); setStory((s) => (s === id ? null : id)) }, [])
  const close = useCallback(() => { setPicked(null); setStory(null) }, [])
  const open = picked !== null || story !== null
  useEffect(() => {
    if (!open) return
    const key = (ev: KeyboardEvent) => { if (ev.key === 'Escape') close() }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [open, close])

  const toggle = (k: Source) => setSources((s) => {
    const n = new Set(s)
    if (!n.delete(k)) n.add(k)
    return n
  })

  return (
    <main className="flow-page">
      <h1 className="flow-title">🌊 Flow: news stories into retellings</h1>
      <p className="flow-sub">
        Each row is a news story we followed that was later told as a motif. The pale bar is its life on the front pages;
        each dot is a claim about it filed in a motif, on the day it was told, coloured by the motif's genre: ● people
        online, ■ a fact-check, ▲ the shows, ◆ the Focus Group. Hollow dashed dots are plain reporting (a watched motif,
        like Straight news): the baseline. A dashed outline is a filing nobody has checked yet. Click a dot or a motif to
        follow that motif across stories; click a story to read its filings.
      </p>
      {error ? <div className="flow-card flow-bad">😵 couldn't load the flow: {error.message}</div>
        : isLoading || !data ? <div className="flow-card">⏳ loading…</div> : (
          <>
            <Cards data={data} onMotif={onMotif} />
            <div className="flow-bar">
              <input type="search" placeholder="🔎 find a story or motif…" value={q} onChange={(e) => setQ(e.target.value)} />
              <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="sort the stories">
                <option value="first">first in the news</option>
                <option value="motifs">most motifs</option>
                <option value="lag">slowest to be told</option>
              </select>
              <label><input type="checkbox" checked={plain} onChange={(e) => setPlain(e.target.checked)} /> plain reporting</label>
              {SOURCES.map((s) => (
                <label key={s.key}><input type="checkbox" checked={sources.has(s.key)} onChange={() => toggle(s.key)} /> {s.mark} {s.label}</label>
              ))}
              <span className="flow-key">
                {data.genres.map((g) => <span key={g}><i style={{ background: genreColor(data.genres, g) }} />{g}</span>)}
              </span>
              <span className="faint">{plural(rows.length, 'story', 'stories')} shown</span>
            </div>
            <Timeline data={data} rows={rows} picked={picked} story={story} onMotif={onMotif} onStory={onStory} onTip={setTip} />
            {open && (
              <div className="flow-pop" role="dialog" aria-label="details">
                <button type="button" className="flow-close" title="close (Esc)" onClick={close}>✕</button>
                {picked ? <MotifPanel data={data} id={picked} onStory={onStory} />
                  : <StoryPanel data={data} s={data.stories.find((x) => x.id === story)} onMotif={onMotif} />}
              </div>
            )}
            {tip && <TipCard data={data} tip={tip} />}
          </>
        )}
    </main>
  )
}

/** The cards on top: what's here, how long the news takes to be told, the motifs fed by the most stories */
function Cards({ data, onMotif }: { data: FlowData; onMotif: (id: string) => void }) {
  const sum = useMemo(() => summary(data), [data])
  const most = Math.max(...sum.bins, 1)
  return (
    <div className="flow-top">
      <div className="flow-card">
        <h3>🧵 what's here</h3>
        <p className="faint">
          <b className="flow-big">{sum.told}</b> stories told as <b className="flow-big">{sum.motifs}</b> motifs, in {data.filings} filings
          that carry their news story (people online since their group was tied to a story; fact-checks by their story
          card; the shows and the Focus Group carry none yet).
        </p>
      </div>
      <div className="flow-card">
        <h3>⏱️ days from the news to the first telling</h3>
        <div className="flow-lagbars">
          {sum.bins.map((n, i) => (
            <div key={i} style={{ height: `${(100 * n) / most}%` }} title={plural(n, 'story', 'stories')}>
              <span>{i === 0 ? '≤0' : i === 8 ? '8+' : i}</span>
            </div>
          ))}
        </div>
        <p className="faint flow-lagnote">
          {sum.median !== null && `median ${sum.median} day(s); ≤0 means told the day it broke, or before we saw it`}
        </p>
      </div>
      <div className="flow-card">
        <h3>🧲 motifs fed by the most stories</h3>
        {sum.hubs.map(([id, m]) => (
          <MotifChip key={id} data={data} id={id} onMotif={onMotif}> <b>{m.stories}</b></MotifChip>
        ))}
      </div>
    </div>
  )
}

/** A motif as a chip outlined in its genre's colour; clicking it follows the motif */
function MotifChip({ data, id, onMotif, children }: { data: FlowData; id: string; onMotif: (id: string) => void; children?: ReactNode }) {
  const m = data.motifs[id]
  return (
    <button type="button" className="flow-chip" style={{ borderColor: genreColor(data.genres, m?.genre) }} title={`follow ${m?.name ?? id} across stories · ${id}`}
      onClick={() => onMotif(id)}>
      {m?.name ?? id}{children}
    </button>
  )
}

/** A link into the workbench: in this app on a plain click, a new tab on a middle or modified click */
function WbLink({ href, title, children }: { href: string; title?: string; children: ReactNode }) {
  const nav = useNavigate()
  const go = (ev: MouseEvent) => {
    if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return
    ev.preventDefault()
    nav(href.replace(/^\/ui/, ''))
  }
  return <a href={href} title={title} onClick={go}>{children}</a>
}

const after = (f: Filing) => (f.lag === null ? '' : `, ${f.lag}d after`)

/** A claim in a panel, with its way into the workbench's claim view */
function Claim({ f }: { f: Filing }) {
  return (
    <>
      “{f.claim}” <WbLink href={claimLink(f.claim)} title="open this claim in the workbench">🔍</WbLink>
    </>
  )
}

/** A motif followed: the stories that fed it, in the order they were told */
function MotifPanel({ data, id, onStory }: { data: FlowData; id: string; onStory: (id: number) => void }) {
  const m = data.motifs[id]
  const hits = useMemo(() => data.stories.flatMap((s) => s.filings.filter((f) => f.motif === id).map((f) => ({ f, s })))
    .sort((a, b) => a.f.date.localeCompare(b.f.date)), [data, id])
  if (!m) return <p className="faint">🤷 this motif isn't in the flow any more</p>
  return (
    <>
      <p className="faint">🧩 motif · {m.genre || 'no genre'}{m.plain ? ' · plain reporting' : ''}</p>
      <h2>{m.name}</h2>
      <p className="faint">fed by {plural(m.stories, 'news story', 'news stories')}, in the order they were told:</p>
      <ol>
        {hits.map(({ f, s }, i) => (
          <li key={i}>
            <b>{f.date}</b> · <button type="button" className="flow-link" onClick={() => onStory(s.id)}>{s.label}</button><br />
            <Claim f={f} /> <span className="faint">{f.source}{after(f)}{f.checked ? '' : ' · not checked yet'}</span>
          </li>
        ))}
      </ol>
      <p><WbLink href={motifLink(id)}>🧰 open it in the workbench</WbLink></p>
    </>
  )
}

/** A story's panel: its days in the news and every motif it was told as */
function StoryPanel({ data, s, onMotif }: { data: FlowData; s: Story | undefined; onMotif: (id: string) => void }) {
  if (!s) return <p className="faint">🤷 this story isn't in the flow any more</p>
  return (
    <>
      <p className="faint">📰 news story #{s.id}{s.first && s.last ? ` · in the news ${s.first.slice(0, 10)} to ${s.last.slice(0, 10)}` : ''}</p>
      <h2>{s.label}</h2>
      <p className="faint">told as {plural(s.motifs, 'motif')}:</p>
      <ol>
        {s.filings.map((f, i) => (
          <li key={i}>
            <b>{f.date}</b> · <MotifChip data={data} id={f.motif} onMotif={onMotif} /><br />
            <Claim f={f} /> <span className="faint">{f.source}{after(f)}{f.plain ? ', plain reporting' : ''}{f.checked ? '' : ' · not checked yet'}</span>
          </li>
        ))}
      </ol>
    </>
  )
}

/** The tooltip over a dot: the motif, the claim, the story and when it was told */
function TipCard({ data, tip }: { data: FlowData; tip: Tip }) {
  const { f, s } = tip
  const m = data.motifs[f.motif]
  // beside the pointer, above it near the bottom of the window
  const at = tip.y > innerHeight - 180 ? { bottom: innerHeight - tip.y + 14 } : { top: tip.y + 14 }
  return (
    <div className="flow-tip" style={{ left: Math.max(8, Math.min(tip.x + 14, innerWidth - 380)), ...at }}>
      <b>{m?.name ?? f.motif}</b> <span className="faint">{m?.genre || 'no genre'}{f.plain ? ', plain reporting' : ''}</span><br />
      “{f.claim}”<br />
      <span className="faint">
        {s.label}<br />
        {f.source} · {f.date}{f.lag === null ? '' : ` · ${f.lag} day(s) after it broke`}{f.checked ? '' : ' · not checked yet'}
        {f.tie === 'same issue' ? ' · tied as the same issue, not event' : ''}
      </span>
    </div>
  )
}
