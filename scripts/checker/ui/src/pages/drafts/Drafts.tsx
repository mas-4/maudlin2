// 📣 drafts (Nov 1): the Bluesky posts the hourly run would make, a dry run before the account goes live
// (app/post_drafts.py). Nothing here posts. Each draft gets 👍 or 👎 and, for a 👎, a note on what's wrong; the
// tallies per format at the top say which formats earn their keep. Marks are saved at once (POST /post-draft-mark).
import { useState } from 'react'
import { useJSON, useWrite } from '../../lib/queries'
import { ask, toast } from '../../components/Feedback'
import './drafts.css'

interface Format { id: string; emoji: string; name: string; what: string; up: number; down: number; drafts: number }
interface Draft { key: string; format: string; text: string; link: string; about: string; chars: number; event: string
  made: string; seen: string; mark: 'up' | 'down' | null; note?: string }
interface DraftData { formats: Format[]; drafts: Draft[]; limit: number }

/** A stored UTC minute ("2026-11-01T20:00") as Eastern time, for a reader in the US */
const eastern = (iso: string) => new Date(iso + 'Z').toLocaleString('en-US', { timeZone: 'America/New_York',
  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) + ' ET'

export function Drafts() {
  const data = useJSON<DraftData>('/post-drafts.json')
  const [only, setOnly] = useState<string | null>(null)
  const [unmarked, setUnmarked] = useState(false)
  if (data.isPending) return <main className="page dr-page"><p className="empty">⏳ fetching drafts…</p></main>
  if (data.isError) return <main className="page dr-page"><p className="empty">😵 Couldn’t load the drafts: {data.error.message}</p></main>
  const d = data.data
  const fmt = Object.fromEntries(d.formats.map((f) => [f.id, f]))
  const shown = d.drafts.filter((x) => (!only || x.format === only) && (!unmarked || !x.mark))
  return (
    <main className="page dr-page">
      <section className="card dr-intro">
        <h1>📣 Bluesky drafts</h1>
        <p>
          What the account would post, drafted by each hourly run. Nothing is posted. 👍 a draft you’d send as it
          is, 👎 one you wouldn’t (say why). After the dry run, the formats that earn their keep go live.
        </p>
      </section>
      <section className="dr-formats">
        {d.formats.map((f) => (
          <button key={f.id} type="button" className={'dr-format' + (only === f.id ? ' on' : '')} title={f.what}
            onClick={() => setOnly(only === f.id ? null : f.id)}>
            <span className="dr-femoji">{f.emoji}</span>
            <span className="dr-fname">{f.name}</span>
            <span className="dr-tally">{f.drafts} drafts · 👍 {f.up} · 👎 {f.down}</span>
          </button>
        ))}
      </section>
      <p className="dr-filters">
        <label><input type="checkbox" checked={unmarked} onChange={(e) => setUnmarked(e.target.checked)} /> only unmarked</label>
        <span className="faint">{shown.length} shown</span>
      </p>
      {shown.length ? shown.map((x) => <DraftCard key={x.key} x={x} f={fmt[x.format]} limit={d.limit} />)
        : <p className="dr-none">🦗 No drafts here yet. The next hourly run makes some.</p>}
    </main>
  )
}

function DraftCard({ x, f, limit }: { x: Draft; f?: Format; limit: number }) {
  const write = useWrite<{ key: string; mark: string | null; note?: string }>('/post-draft-mark')
  const set = async (mark: 'up' | 'down') => {
    const next = x.mark === mark ? null : mark
    let note: string | undefined
    if (next === 'down') {
      const said = await ask('What’s wrong with it? (optional)', x.note ?? '', { multiline: true, empty: true })
      if (said === null) return
      note = said
    }
    write.mutate({ key: x.key, mark: next, note }, { onError: (e) => toast('Couldn’t save: ' + e.message, true) })
  }
  return (
    <section className={'card dr-card' + (x.mark ? ' ' + x.mark : '')}>
      <p className="dr-meta">
        <span>{f ? `${f.emoji} ${f.name}` : x.format}</span>
        <span className="faint">{eastern(x.made)}{x.seen !== x.made ? ` · still current ${eastern(x.seen)}` : ''}</span>
      </p>
      <div className="dr-post">
        <p className="dr-text">{x.text}</p>
        <a className="dr-link" href={x.link} target="_blank" rel="noopener">🔗 {x.link.replace(/^https?:\/\//, '')}</a>
      </div>
      <p className="dr-foot">
        <span className={'dr-chars' + (x.chars > limit ? ' over' : '')}>{x.chars}/{limit}</span>
        {x.about.startsWith('http') && <a className="faint" href={x.about} target="_blank" rel="noopener">source</a>}
        <span className="dr-marks">
          <button type="button" className={'dr-mark' + (x.mark === 'up' ? ' chosen' : '')} onClick={() => void set('up')}>👍</button>
          <button type="button" className={'dr-mark' + (x.mark === 'down' ? ' chosen' : '')} onClick={() => void set('down')}>👎</button>
        </span>
      </p>
      {x.note && <p className="dr-note">📝 {x.note}</p>}
    </section>
  )
}
