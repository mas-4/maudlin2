// 🏷️ label check (#121), the page the checker began as: is the language model's mood, spice (loaded wording) and
// feelings for a headline right? Each card is marked ✓ or corrected, then saved (POST /verdict), which writes the
// headline's hand labels straight into the database (so there is no undo here). The batch, from /labels.json
// (scripts/checker/labels.py), is drawn at random, so it is kept as first fetched: fetching again only updates the
// running agreement in the footer, and "more headlines" swaps in a fresh batch.
import { useState } from 'react'
import { useJSON } from '../../lib/queries'
import { postJSON } from '../../lib/api'
import { toast } from '../../components/Feedback'
import './labels.css'

type Measure = 'mood' | 'spice' | 'feelings'
interface Item { headline_id: number; title: string; agency: string; mood: number; spice: number; feelings: string[]; url: string | null }
interface Stats { headlines: number; mood: [number, number]; spice: [number, number]; feelings: [number, number]; mood_misses: [[number, number | null], number][] }
interface LabelData {
  items: Item[]
  stats: Stats
  moods: Record<string, [string, string]> // in JSON the keys are strings ("-2" … "2")
  spices: Record<string, [string, string]>
  feelings: string[]
  emoji: Record<string, string>
}
/** A card's marks: ✓ for a measure, or the value picked (several feelings) */
interface Marks { mood?: 'ok' | number; spice?: 'ok' | number; feelings?: 'ok' | string[] }
type Verdict = { ok: true } | { ok: false; should: number | string[] }

/** The choices for a numeric measure, in order (object keys like "-2" don't keep it) */
const scale = (m: Record<string, [string, string]>) => Object.keys(m).map(Number).sort((a, b) => a - b)

function verdict(marks: Marks, it: Item, m: Measure): Verdict | null {
  const v = marks[m]
  if (v === undefined) return null
  if (v === 'ok') return { ok: true }
  if (m === 'feelings') {
    const picked = v as string[]
    if (!picked.length) return null
    const same = picked.length === it.feelings.length && picked.every((e) => it.feelings.includes(e))
    return same ? { ok: true } : { ok: false, should: picked }
  }
  return v === it[m] ? { ok: true } : { ok: false, should: v as number } // picking the model's own value is agreeing with it
}

export function Labels() {
  const data = useJSON<LabelData>('/labels.json', undefined, { staleTime: Infinity, refetchOnWindowFocus: false })
  const [batch, setBatch] = useState<Item[] | null>(null)
  const [fetchingMore, setFetchingMore] = useState(false)
  const [done, setDone] = useState<Set<number>>(() => new Set())

  // The first batch fetched stays (an undo elsewhere fetches everything again) until "more headlines" asks for the next
  if (batch === null && data.data) setBatch(data.data.items)
  const more = async () => {
    setFetchingMore(true)
    const r = await data.refetch()
    setFetchingMore(false)
    if (r.data) {
      setBatch(r.data.items)
      setDone(new Set())
      window.scrollTo({ top: 0 })
    } else toast('Couldn’t fetch more: ' + (r.error?.message ?? 'no reply'), true)
  }

  if (data.isPending) return <main className="page lb-page"><p className="empty">⏳ picking headlines…</p></main>
  if (data.isError) return <main className="page lb-page"><p className="empty">😵 Couldn’t load the headlines: {data.error.message}</p></main>
  const d = data.data
  const items = batch ?? d.items
  const st = d.stats
  const pct = (k: 'mood' | 'spice' | 'feelings') => (st[k][1] ? `${Math.round((100 * st[k][0]) / st[k][1])}% of ${st[k][1]}` : '—')
  const mood = (v: number | null) => (v === null ? '?' : (d.moods[String(v)] ?? ['', String(v)]).join(' '))

  return (
    <main className="page lb-page">
      <section className="card lb-intro">
        <h1>🏷️ Label check</h1>
        <p>
          Is the model right? Tap ✓ for a label that’s right, or the value it should be (dashed: the model’s pick;
          tapping that counts as ✓). Feelings: tap every one the headline is likely to stir. Save each card; ask for more
          headlines at the bottom.
        </p>
      </section>
      {items.length ? items.map((it) => (
        <LabelCard key={it.headline_id} it={it} d={d} saved={done.has(it.headline_id)}
          onSaved={() => {
            setDone((s) => new Set(s).add(it.headline_id))
            void data.refetch() // the footer's agreement, with this verdict in it (the batch shown stays)
          }} />
      )) : <p className="lb-none">🦗 Nothing left to check from the last two days.</p>}
      <p className="lb-more">
        <button className={'btn' + (fetchingMore ? ' busy' : '')} disabled={fetchingMore} onClick={() => void more()}>🎲 more headlines</button>
        <span className="faint">{items.length - items.filter((it) => done.has(it.headline_id)).length} of {items.length} still to save here</span>
      </p>
      <footer className="lb-foot">
        So far: mood right {pct('mood')}, spice right {pct('spice')}, feelings right {pct('feelings')} ({st.headlines} headlines).
        {st.mood_misses.length > 0 && (
          <> Most common mood misses (model → should be): {st.mood_misses.map(([[m, s], n]) => `${mood(m)} → ${mood(s)} ×${n}`).join(' · ')}</>
        )}
      </footer>
    </main>
  )
}

function LabelCard({ it, d, saved, onSaved }: { it: Item; d: LabelData; saved: boolean; onSaved: () => void }) {
  const [marks, setMarks] = useState<Marks>({})
  const [saving, setSaving] = useState(false)
  const ready = (['mood', 'spice', 'feelings'] as const).every((m) => verdict(marks, it, m))
  const pick = (m: 'mood' | 'spice', v: number) => setMarks((x) => ({ ...x, [m]: v }))
  const feel = (e: string) => setMarks((x) => {
    const was = Array.isArray(x.feelings) ? x.feelings : []
    return { ...x, feelings: was.includes(e) ? was.filter((f) => f !== e) : [...was, e] }
  })
  const save = async () => {
    setSaving(true)
    try {
      const body = { headline_id: it.headline_id, model: { mood: it.mood, spice: it.spice, feelings: it.feelings },
        mood: verdict(marks, it, 'mood'), spice: verdict(marks, it, 'spice'), feelings: verdict(marks, it, 'feelings') }
      await postJSON('/verdict', body)
      toast('🏷️ saved: ' + it.title)
      onSaved()
    } catch (e) {
      toast('Couldn’t save: ' + (e as Error).message, true)
    } finally {
      setSaving(false)
    }
  }
  const okBtn = (m: Measure) => (
    <button type="button" className={'lb-opt lb-ok' + (marks[m] === 'ok' ? ' chosen' : '')} disabled={saved}
      onClick={() => setMarks((x) => ({ ...x, [m]: 'ok' }))}>✓ right</button>
  )
  const scaleRow = (m: 'mood' | 'spice', choices: Record<string, [string, string]>) => (
    <div className="lb-row">
      <b>{m}</b>
      <span className="lb-said">model: {(choices[String(it[m])] ?? ['', String(it[m])]).join(' ')}</span>
      {okBtn(m)}
      <span className="lb-pick">
        {scale(choices).map((v) => (
          <button key={v} type="button" disabled={saved}
            className={'lb-opt' + (v === it[m] ? ' model' : '') + (marks[m] === v ? ' chosen' : '')}
            onClick={() => pick(m, v)}>{choices[String(v)].join(' ')}</button>
        ))}
      </span>
    </div>
  )
  const picked = Array.isArray(marks.feelings) ? marks.feelings : []
  return (
    <section className={'card lb-card' + (saved ? ' done' : '')}>
      <p className="lb-outlet">📰 {it.agency}</p>
      <h2><a href={it.url || '#'} target="_blank" rel="noopener">{it.title}</a></h2>
      {scaleRow('mood', d.moods)}
      {scaleRow('spice', d.spices)}
      <div className="lb-row">
        <b>feelings</b>
        <span className="lb-said">model: {it.feelings.length ? it.feelings.map((e) => `${d.emoji[e] ?? ''} ${e}`).join(' ') : 'none'}</span>
        {okBtn('feelings')}
        <span className="lb-pick">
          {d.feelings.map((e) => (
            <button key={e} type="button" disabled={saved}
              className={'lb-opt' + (it.feelings.includes(e) ? ' model' : '') + (picked.includes(e) ? ' chosen' : '')}
              onClick={() => feel(e)}>{d.emoji[e]} {e}</button>
          ))}
        </span>
      </div>
      <button type="button" className={'btn lb-save' + (saving ? ' busy' : '')} disabled={!ready || saved || saving} onClick={() => void save()}>
        {saved ? '✅ saved' : '💾 save'}
      </button>
    </section>
  )
}
