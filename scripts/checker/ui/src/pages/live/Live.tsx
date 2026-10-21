// 🧠 Live: the filing pipeline as it runs (GET /live.json, app/analysis/trace_view.py). The eight stages left to
// right with their last hour and last day, lighting up as claims pass through; a feed of what just happened, asked for
// again every 4 seconds while the tab is visible; and any claim's whole journey through the stages, kept in the hash
// (#claim=<key>) so it can be linked to
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { getJSON } from '../../lib/api'
import { client, useJSON } from '../../lib/queries'
import { HEX_ID, KIND_LABEL, hhmm, when } from './format'
import { Journey, type GridMode } from './Journey'
import type { Counts, Found, Gloss, Journey as J, LiveEvent, Pick, Stage, Stream } from './types'
import './live.css'

const FEED_MAX = 250
const POLL_MS = 4000
const FLASH_MS = 2000

// an event in the feed: the same event can come again (a poll asks from the last time it saw, inclusive)
const sig = (e: LiveEvent) => `${e.t}|${e.s}|${e.k}|${e.line}`
interface FeedItem extends LiveEvent { sig: string; at: number } // at: when it arrived here, 0 for the first load

const claimInHash = (hash: string) => {
  const m = hash.match(/claim=([^&]+)/)
  return m ? decodeURIComponent(m[1]) : null
}

export function Live() {
  useEffect(() => {
    const was = document.title
    document.title = '🧠 Live'
    return () => { document.title = was }
  }, [])

  // ---------- the stream: the first load, then only what's new ----------
  const first = useJSON<Stream>('/live.json', undefined, { staleTime: 0, refetchOnWindowFocus: false })
  const [stages, setStages] = useState<Stage[]>([])
  const [examples, setExamples] = useState<Record<string, Pick[]>>({})
  const [glossary, setGlossary] = useState<Record<string, Gloss>>({})
  const [counts, setCounts] = useState<Counts | null>(null)
  const [feed, setFeed] = useState<FeedItem[]>([])
  const seen = useRef(new Set<string>())
  const since = useRef<string | null>(null)
  const stageEls = useRef<Record<string, HTMLDivElement | null>>({})

  const pulse = useCallback((stage: string) => {
    stageEls.current[stage]?.animate(
      [
        { background: '#ffc400', transform: 'scale(1.06)', boxShadow: '0 0 0 0 rgba(255,196,0,.8)' },
        { transform: 'scale(1)', boxShadow: '0 0 0 14px rgba(255,196,0,0)' },
      ],
      { duration: 1300, easing: 'ease-out' },
    )
  }, [])

  const addEvents = useCallback((evs: LiveEvent[], fresh: boolean) => {
    const add = evs.filter((e) => !seen.current.has(sig(e)))
    if (!add.length) return
    for (const e of add) {
      seen.current.add(sig(e))
      if (!since.current || e.t > since.current) since.current = e.t
    }
    const at = fresh ? Date.now() : 0
    setFeed((f) => [...add.slice().reverse().map((e) => ({ ...e, sig: sig(e), at })), ...f].slice(0, FEED_MAX))
    if (fresh) new Set(add.map((e) => e.s)).forEach(pulse)
  }, [pulse])

  useEffect(() => {
    const D = first.data
    if (!D || D.error) return
    if (D.stages) setStages(D.stages)
    if (D.examples) setExamples(D.examples)
    if (D.glossary) setGlossary(D.glossary)
    setCounts(D.counts)
    if (!since.current || D.now > since.current) since.current = D.now
    addEvents(D.events, false)
  }, [first.data, addEvents])

  // every 4 seconds while the tab is visible, from the last event seen: react-query holds the interval back while
  // document.visibilityState is hidden, and asks at once when the tab is shown again
  const ready = !!first.data && !first.data.error
  const poll = useQuery<Stream>({
    queryKey: ['/live.json', 'poll'],
    queryFn: () => getJSON<Stream>('/live.json', { since: since.current ?? '' }),
    enabled: ready,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 0,
    gcTime: 0,
    retry: 0,
  })
  useEffect(() => {
    const D = poll.data
    if (!D || D.error) return
    setCounts(D.counts)
    addEvents(D.events, true)
  }, [poll.data, addEvents])
  const offline = first.isError || poll.isError

  // ---------- the stage filter ----------
  const [off, setOff] = useState<Set<string>>(new Set())
  const toggle = (s: string) => setOff((o) => {
    const n = new Set(o)
    if (n.has(s)) n.delete(s)
    else n.add(s)
    return n
  })
  // a stage clicked: the feed shows only it (clicked again: everything)
  const only = (s: string) => setOff((o) => {
    const rest = stages.filter((x) => x.id !== s).map((x) => x.id)
    const already = o.size === rest.length && rest.every((x) => o.has(x))
    return already ? new Set() : new Set(rest)
  })
  const selected = stages.length > 1 && off.size === stages.length - 1 ? stages.find((s) => !off.has(s.id))?.id : undefined
  const emoji = useMemo(() => Object.fromEntries(stages.map((s) => [s.id, s.emoji])), [stages])

  // ---------- examples and search ----------
  const [kind, setKind] = useState('recent')
  const [q, setQ] = useState('')
  const [typed, setTyped] = useState('') // q, 300ms after the last key
  useEffect(() => {
    const t = window.setTimeout(() => setTyped(q.trim()), 300)
    return () => clearTimeout(t)
  }, [q])
  const found = useJSON<Found>('/live.json', { q: typed }, { enabled: !!typed })
  const searching = !!q.trim()

  // ---------- one claim's journey, named in the hash ----------
  const loc = useLocation()
  const navigate = useNavigate()
  const ref = claimInHash(loc.hash)
  const journey = useJSON<J>('/live.json', { claim: ref ?? undefined }, { enabled: !!ref, staleTime: 60_000, refetchOnWindowFocus: false })
  const [mode, setMode] = useState<GridMode>('push')
  const box = useRef<HTMLDivElement>(null)
  const scrollTo = useRef(false)

  const openJourney = useCallback((k: string) => {
    if (k === ref && journey.data) {
      box.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
    scrollTo.current = true
    navigate({ hash: 'claim=' + encodeURIComponent(k) }, { replace: true })
  }, [navigate, ref, journey.data])
  const closeJourney = () => navigate({ hash: '' }, { replace: true })

  useEffect(() => {
    const D = journey.data
    if (!D || D.error) return
    // named by its #id or words: the hash takes its full key (the answer is the same, so it's kept for that key)
    if (ref && D.claim.k !== ref) {
      client.setQueryData(['/live.json', { claim: D.claim.k }], D)
      navigate({ hash: 'claim=' + D.claim.k }, { replace: true })
      return
    }
    if (scrollTo.current) {
      scrollTo.current = false
      requestAnimationFrame(() => box.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    }
  }, [journey.data, ref, navigate])

  const gl = useCallback((f: string): Gloss => glossary[f] || journey.data?.glossary?.[f] || [f, ''], [glossary, journey.data])

  const onSearchKey = (ev: KeyboardEvent<HTMLInputElement>) => {
    if (ev.key === 'Enter' && HEX_ID.test(q.trim())) openJourney(q.trim())
  }

  const firstError = first.error ? (first.error as Error).message : first.data?.error
  const now = Date.now()
  const shownFeed = feed.filter((e) => !off.has(e.s))
  const picks: Pick[] = searching ? (found.data?.found ?? []) : (examples[kind] ?? [])

  return (
    <div className="lv">
      <h1>🧠 Live: the filing pipeline as it runs</h1>
      <p className="lv-sub">
        Every claim goes left to right: it's written from what people tell, the filing model restates its shape, some twenty signals score every motif and
        the best are shortlisted, the filing model picks among them, the confidence model gives each filing a fit, and you decide. Each stage lights up as
        claims pass through it (the counts are the last hour; the bars, the last day). Click a claim in the feed, an example, or search, to follow it
        through every stage with the real data: the posts, its shape, the signals that fired for each motif, the model's picks and reasons, and what pushed
        its fit up or down.
      </p>

      <div className="lv-card">
        <div className="lv-pipe">
          {stages.map((s, i) => {
            const bars = counts?.per_hour[s.id] ?? []
            const most = Math.max(1, ...bars)
            const last = counts?.last_hour[s.id] ?? 0
            return (
              <div key={s.id} ref={(el) => { stageEls.current[s.id] = el }} role="button" tabIndex={0}
                className={'lv-stage' + (last > 0 ? ' active' : '') + (selected === s.id ? ' sel' : '')}
                title={`${s.what}\n(click: show only this stage in the feed; again: all)`}
                onClick={() => only(s.id)} onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); only(s.id) } }}>
                <div className="emo" aria-hidden="true">{s.emoji}</div>
                <b>{i + 1}. {s.name}</b>
                <div className="n">{last}</div>
                <div className="faint">last hour</div>
                <div className="spark">
                  {bars.map((n, h) => (
                    <i key={h} style={{ height: n ? `${Math.max(8, (100 * n) / most)}%` : '3%' }} title={`${n} at ${counts?.hours[h]}:00`} />
                  ))}
                </div>
                <div className="faint">{counts?.day[s.id] ?? 0} in a day</div>
              </div>
            )
          })}
        </div>
        {first.data && !first.data.error && (
          <div className="faint lv-pipenote">
            {first.data.traced_since
              ? `Traced since ${first.data.traced_since}; before that, a claim's journey is rebuilt from the logs. Your verdicts come from the curation log.`
              : 'Nothing traced yet: the trace begins filling at the next hourly run. Your verdicts come from the curation log; older claims are rebuilt from the logs.'}
          </div>
        )}
      </div>

      <div className="lv-two">
        <div className="lv-card">
          <h3>
            📡 claims passing through{' '}
            <span className={'lv-status' + (offline ? ' off' : '')} title={offline ? "the last ask for news didn't get through" : 'asking for news every 4 seconds while this tab is shown'}>
              {offline ? '○ offline' : '● live'}
            </span>
          </h3>
          {stages.length > 0 && (
            <div className="faint lv-filter">
              show:{' '}
              {stages.map((s) => (
                <button key={s.id} className={'lv-chip' + (off.has(s.id) ? '' : ' on')} onClick={() => toggle(s.id)}>{s.emoji} {s.name}</button>
              ))}
            </div>
          )}
          <div className="lv-feed">
            {firstError ? <p className="faint">⚠️ {firstError}</p>
              : !first.data ? <p className="faint">⏳ loading…</p>
                : !feed.length ? <p className="faint">🦗 Nothing in the last two days yet. Pick an example on the right to follow a claim.</p>
                  : !shownFeed.length ? <p className="faint">🙈 Nothing from the stages shown; turn more on above.</p>
                    : shownFeed.map((e) => {
                      const verdict = e.s === 'decided' ? (e.kept === true ? ' kept' : e.kept === false ? ' out' : '') : ''
                      return (
                        <div key={e.sig} className={'lv-ev' + verdict + (e.at && now - e.at < FLASH_MS ? ' new' : '')} role="button" tabIndex={0}
                          title="follow this claim through every stage"
                          onClick={() => openJourney(e.k)} onKeyDown={(ev) => { if (ev.key === 'Enter') openJourney(e.k) }}>
                          <span className="t">{hhmm(e.t)}<br />{e.t.slice(5, 10)}</span>
                          <span title={e.s}>{emoji[e.s] || '•'}</span>
                          <span>
                            <span className="c">{e.c || '#' + e.k.slice(0, 6)}</span>
                            <span className="l">{e.line}</span>
                          </span>
                        </div>
                      )
                    })}
          </div>
        </div>

        <div className="lv-card">
          <h3>🔎 follow a claim</h3>
          <div className="lv-search">
            <input type="search" value={q} placeholder="words of a claim, or its #id" aria-label="search claims"
              onChange={(ev) => setQ(ev.target.value)} onKeyDown={onSearchKey} />
          </div>
          <div>
            {Object.keys(examples).map((k) => (
              <button key={k} className={'lv-chip' + (!searching && kind === k ? ' on' : '')} onClick={() => { setKind(k); setQ('') }}>
                {KIND_LABEL[k] || k} <span className="faint">{examples[k].length}</span>
              </button>
            ))}
          </div>
          <div className="lv-picks">
            {searching && (typed !== q.trim() || found.isFetching) && !found.data ? <p className="faint">⏳ looking…</p>
              : found.error && searching ? <p className="faint">⚠️ {(found.error as Error).message}</p>
                : picks.length ? picks.map((x) => (
                  <div key={x.k} className="lv-claimline" role="button" tabIndex={0} onClick={() => openJourney(x.k)}
                    onKeyDown={(ev) => { if (ev.key === 'Enter') openJourney(x.k) }}>
                    <span className="faint">#{x.k.slice(0, 6)}{x.t ? ' · ' + when(x.t) : ''}</span>
                    <br />{x.c}
                    {x.note && <><br /><span className="faint">{x.note}</span></>}
                  </div>
                ))
                  : <p className="faint">{searching ? (HEX_ID.test(q.trim()) ? 'no claim matches (Enter follows that #id anyway)' : 'no claim matches') : 'none yet'}</p>}
          </div>
        </div>
      </div>

      <div className="lv-journey" ref={box}>
        {ref && (
          journey.isPending ? <div className="lv-card"><p className="faint">🧭 following the claim…</p></div>
            : journey.error ? <div className="lv-card"><p>⚠️ {(journey.error as Error).message}</p></div>
              : journey.data?.error ? <div className="lv-card"><p>⚠️ {journey.data.error}</p></div>
                : journey.data && (
                  <Journey J={journey.data} gl={gl} glossary={Object.keys(glossary).length ? glossary : journey.data.glossary}
                    mode={mode} setMode={setMode} onOpen={openJourney} onClose={closeJourney} />
                )
        )}
      </div>
    </div>
  )
}
