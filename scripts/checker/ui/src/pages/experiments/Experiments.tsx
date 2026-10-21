// 🧪 Experiments: every experiment by its folklore figure, with its paper (the hypothesis written before it ran), its
// results, case by case what happened (failures first), and the pipeline it is tested against. Above them the GPU
// queue, Ma'at's weekly weighings of the judge, and the stories production cut. Read straight from the experiments' own
// records (scripts/experiments/lab.py); the only write is the person's verdict on a case.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useJSON } from '../../lib/queries'
import { CasesPane } from './Cases'
import { Markdown } from './Markdown'
import type { Experiment, Overview, Paper } from './types'
import './experiments.css'

// The list's sections, in this order; any status not named here comes after them
const ORDER = ['running', 'queued', 'answered', 'in production', 'your call', 'unproven', 'not yet', 'not kept', 'planned']
const STATUS_EMOJI: Record<string, string> = {
  running: '🏃', queued: '⏳', waiting: '⏳', answered: '✅', done: '✅', 'in production': '🏭', 'your call': '🙋',
  unproven: '🤔', 'not yet': '🌱', 'not kept': '🗑️', planned: '📝', failed: '💥', blocked: '🚧',
}
type Tab = 'paper' | 'results' | 'cases' | 'pipeline'

const when = (at: string) => at.slice(0, 16).replace('T', ' ')
const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v * 100)}%`)
const slug = (s: string) => s.replace(/[^a-z]+/gi, '-').toLowerCase()

function Chip({ status, label, emoji }: { status: string; label?: string; emoji?: string }) {
  return (
    <span className={`ex-chip ex-s-${slug(status)}`}>
      <span aria-hidden="true">{emoji ?? STATUS_EMOJI[status] ?? '•'}</span> {label ?? status}
    </span>
  )
}

export function Experiments() {
  const { data, error, isLoading, dataUpdatedAt } = useJSON<Overview>('/experiments.json', undefined, { refetchInterval: 60_000 })
  const location = useLocation()
  const navigate = useNavigate()
  const code = decodeURIComponent(location.hash.slice(1)) || null
  const [q, setQ] = useState('')
  const [tab, setTab] = useState<Tab>('paper')
  const detail = useRef<HTMLDivElement>(null)
  const picked = data?.experiments.find((e) => e.code === code)

  useEffect(() => {
    const was = document.title
    document.title = picked ? `🧪 ${picked.figure}` : '🧪 Experiments'
    return () => { document.title = was }
  }, [picked])

  const pick = (c: string) => {
    navigate({ pathname: location.pathname, search: location.search, hash: c }, { replace: true })
    // stacked on a narrow screen, the detail is below the list: bring it up
    if (matchMedia('(max-width: 900px)').matches) requestAnimationFrame(() => detail.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  return (
    <main className="ex-page">
      <header className="ex-head">
        <h1>🧪 Experiments</h1>
        <p className="ex-sub">
          Every experiment: its paper (the hypothesis written before it ran), its results, and case by case what happened,
          failures first. Read straight from the experiments' own records.
        </p>
        {data && <span className="faint">🔄 read at {new Date(dataUpdatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}, again every minute</span>}
      </header>
      {error && !data && <div className="ex-empty">😬 The experiments didn't load: {error.message}</div>}
      <Top data={data} loading={isLoading} />
      <div className="ex-main">
        <ExperimentList experiments={data?.experiments} q={q} setQ={setQ} code={code} pick={pick} />
        <div className="ex-card ex-detail" ref={detail} style={{ ['--pop' as string]: 'var(--yellow)' }}>
          {picked ? (
            <Detail e={picked} all={data!.experiments} tab={tab} setTab={setTab} />
          ) : (
            <div className="ex-empty ex-pick">👈 Pick an experiment{code && data ? ' (the one in the link is no longer in the catalog)' : ''}</div>
          )}
        </div>
      </div>
    </main>
  )
}

/** The three cards across the top: the queue, Ma'at, and the stories cut in production */
function Top({ data, loading }: { data?: Overview; loading: boolean }) {
  const wait = <div className="faint">{loading ? '⏳ loading…' : '–'}</div>
  return (
    <div className="ex-top">
      <section className="ex-card ex-hop" style={{ ['--pop' as string]: 'var(--teal)' }}>
        <h3>⏳ The queue</h3>
        {data ? <Queue data={data} /> : wait}
      </section>
      <section className="ex-card ex-hop" style={{ ['--pop' as string]: 'var(--purple)' }}>
        <h3>⚖️ Ma'at, the fixed yardstick</h3>
        {data ? <Maat data={data} /> : wait}
      </section>
      <section className="ex-card ex-hop" style={{ ['--pop' as string]: 'var(--orange)' }}>
        <h3>✂️ Stories cut in production</h3>
        {data ? <Seams data={data} /> : wait}
      </section>
    </div>
  )
}

function Queue({ data }: { data: Overview }) {
  const q = data.queue
  if (!q.length) return <div className="faint">🦗 empty</div>
  const open = q.filter((s) => s.status !== 'done')
  return (
    <div>
      {open.slice(0, 10).map((s) => (
        <div key={s.id} className="ex-qstep">
          <Chip status={s.status} /> {s.step}
          {s.tries > 0 && <span className="faint"> (try {s.tries + 1})</span>}
          {s.status === 'running' && s.started && <span className="faint"> · since {when(s.started)}</span>}
        </div>
      ))}
      {!open.length && <div className="faint">😴 nothing waiting</div>}
      {open.length > 10 && <div className="faint">and {open.length - 10} more</div>}
      <div className="faint">{q.length - open.length} steps done · runs one at a time under the GPU lease</div>
    </div>
  )
}

const MAAT_SHOWN = 10

function Maat({ data }: { data: Overview }) {
  const m = data.maat
  if (!m.length) return <div className="faint">🌱 not weighed yet: it runs after Pandora, then every Sunday night</div>
  const shown = m.slice(-MAAT_SHOWN)
  const sets = [...new Map(m.map((r) => [r.set ?? '', r.filings])).entries()]
  const named = sets.some(([s]) => s)
  return (
    <div className="ex-scroll">
      <table className="ex-table">
        <thead>
          <tr>
            <th>weighed</th>
            {named && <th>set</th>}
            <th>AUC</th>
            <th>right when sure</th>
            <th>kept passing as sure</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r, n) => (
            <tr key={n}>
              <td>{when(r.at)}</td>
              {named && <td>{r.set}</td>}
              <td>{r.auc == null ? '–' : r.auc.toFixed(3)}</td>
              <td>{pct(r['right when sure'])}</td>
              <td>{pct(r['kept that pass'])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="faint">
        {m.length > MAAT_SHOWN && `the latest ${MAAT_SHOWN} of ${m.length} weighings · `}
        the same {named ? sets.map(([s, n]) => `${n} (${s})`).join(' and ') : m[0].filings} decisions every week, never trained on
      </div>
    </div>
  )
}

function Seams({ data }: { data: Overview }) {
  const s = data.seams
  if (!s.length) return <div className="faint">🌱 none weighed yet: the hourly run asks Gemma about each cut under 0.6</div>
  return (
    <div>
      {s.slice(-8).reverse().map((c, n) => (
        <div key={n} className="ex-seam">
          <Chip status={c.cut ? 'done' : 'waiting'} label={c.cut ? 'cut' : 'kept whole'} emoji={c.cut ? '✂️' : '🔗'} /> <b>{c.a[0]}</b>{' '}
          <span className="faint">|</span> {c.b[0]}
          <div className="faint">{c.reason}</div>
        </div>
      ))}
    </div>
  )
}

/** The catalog, found by figure, question, result or family, in sections by status */
function ExperimentList({ experiments, q, setQ, code, pick }: { experiments?: Experiment[]; q: string; setQ: (s: string) => void; code: string | null; pick: (c: string) => void }) {
  const groups = useMemo(() => {
    const f = q.trim().toLowerCase()
    const out = new Map<string, Experiment[]>()
    for (const e of experiments ?? []) {
      if (f && !`${e.figure} ${e.question} ${e.result} ${e.family} ${e.why}`.toLowerCase().includes(f)) continue
      out.set(e.status, [...(out.get(e.status) ?? []), e])
    }
    const rank = (s: string) => ORDER.indexOf(s) + 1 || 99
    return [...out.entries()].sort(([a], [b]) => rank(a) - rank(b))
  }, [experiments, q])
  return (
    <nav className="ex-card ex-list" aria-label="experiments">
      <input
        className="ex-find"
        type="search"
        value={q}
        onChange={(ev) => setQ(ev.target.value)}
        onKeyDown={(ev) => {
          if (ev.key === 'Escape') setQ('')
          if (ev.key === 'Enter' && groups.length) pick(groups[0][1][0].code)
        }}
        placeholder="🔎 find an experiment"
        autoComplete="off"
      />
      {!experiments && <div className="faint">⏳ loading…</div>}
      {experiments && !groups.length && <div className="ex-empty">🤷 No experiment matches “{q}”.</div>}
      {groups.map(([status, list]) => (
        <div key={status}>
          <h4>
            <span aria-hidden="true">{STATUS_EMOJI[status] ?? '•'}</span> {status} ({list.length})
          </h4>
          {list.map((e) => (
            <button key={e.code} className={'ex-item' + (e.code === code ? ' on' : '')} onClick={() => pick(e.code)} aria-current={e.code === code}>
              <b>
                {e.figure}
                {e.cases && <span title="has a case-by-case record"> 🔍</span>}
                {!e.paper && <span className="faint"> no paper</span>}
              </b>
              <span>{e.result || e.question}</span>
            </button>
          ))}
        </div>
      ))}
    </nav>
  )
}

function Detail({ e, all, tab, setTab }: { e: Experiment; all: Experiment[]; tab: Tab; setTab: (t: Tab) => void }) {
  const tabs: [Tab, string][] = [
    ['paper', '📄 paper'],
    ['results', `📈 results (${e.lines.length})`],
    ...(e.cases ? [['cases', '🔍 case by case'] as [Tab, string]] : []),
    ['pipeline', '🧭 the pipeline'],
  ]
  const shown: Tab = tabs.some(([k]) => k === tab) ? tab : 'paper'
  // the pipeline paper comes with any experiment's paper: one without a paper borrows another's
  const pipelineFrom = e.paper ? e.code : (all.find((x) => x.paper)?.code ?? e.code)
  return (
    <article>
      <h2>{e.figure}</h2>
      <div className="faint">
        {e.why}
        {e.family && ` · ${e.family}`}
      </div>
      <div className="ex-question">
        {e.question} <Chip status={e.status} />
      </div>
      {e.result && (
        <div className="ex-result">
          <b>Result:</b> {e.result}
        </div>
      )}
      <div className="ex-tabs" role="tablist">
        {tabs.map(([k, name]) => (
          <button key={k} role="tab" aria-selected={k === shown} className={k === shown ? 'on' : ''} onClick={() => setTab(k)}>
            {name}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {shown === 'paper' && <PaperPane code={e.code} pipeline={false} />}
        {shown === 'pipeline' && <PaperPane code={pipelineFrom} pipeline />}
        {shown === 'results' && <Results e={e} />}
        {shown === 'cases' && <CasesPane key={e.code} code={e.code} />}
      </div>
    </article>
  )
}

function PaperPane({ code, pipeline }: { code: string; pipeline: boolean }) {
  const { data, error, isLoading } = useJSON<Paper>('/experiment-paper.json', { code })
  if (isLoading) return <div className="ex-loading">⏳ fetching the paper…</div>
  if (error) return <div className="ex-empty">😬 The paper didn't load: {error.message}</div>
  const text = pipeline ? data?.pipeline : data?.text
  if (!text) return <div className="ex-empty">🌱 No paper yet: planned experiments get theirs, with the hypothesis, before they run.</div>
  return (
    <>
      {!pipeline && data?.file && <div className="faint">📄 papers/{data.file}</div>}
      <Markdown text={text} />
    </>
  )
}

function Results({ e }: { e: Experiment }) {
  if (!e.lines.length) return <div className="ex-empty">🦗 No results recorded yet.</div>
  return (
    <ul className="ex-lines">
      {e.lines.slice().reverse().map((l, n) => (
        <li key={n}>
          <time dateTime={l.at}>{when(l.at)}</time>
          {l.line}
        </li>
      ))}
    </ul>
  )
}
