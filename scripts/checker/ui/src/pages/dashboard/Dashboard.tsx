// 📈 Everything at a glance (GET /dashboard.json, app/dashboard.py): is the hourly run keeping up, what came in, the
// sagas, what was made of it, the motif index, the models by their own tests and the person's curation. Fetched again
// every two minutes; 🔄 asks the server to work every part out afresh (the old page's refresh never did).
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { getJSON } from '../../lib/api'
import { useJSON } from '../../lib/queries'
import { toast } from '../../components/Feedback'
import { setWB } from '../../workbench/store'
import { Bars, Lines, OneBars, short, type Point, type Series } from './charts'
import { Card, Err, List, SagaTable, Section, Tile, Tiles, num, pct, when, type Saga } from './bits'
import './dashboard.css'

// The figures come in parts, and any part can be {error} instead of its usual shape, so each is read loosely
type Dash = Record<string, any> & { at: string }

const PATH = '/dashboard.json'

const KIND: Record<string, string> = {
  relate: '↔ related', parent: '↳ rests on', merge: '⤵ merge', rename: '✏️ rename', note: '📝 note typo',
  group: '📁 into a group', genre: '🎭 genre', unrelate: '✂️ not related', unparent: "✂️ doesn't rest on",
  new_group: '🫧 new group', new_motif: '✨ new motif',
}

const hour = (l: string) => l.slice(11, 13) + 'h'
const entries = (o: unknown): [string, any][] => (o && typeof o === 'object' && !Array.isArray(o) ? Object.entries(o).filter(([k]) => k !== 'error') : [])

export function Dashboard() {
  const qc = useQueryClient()
  const { data, error, isFetching } = useJSON<Dash>(PATH, undefined, { refetchInterval: 120_000 })
  const [fresh, setFresh] = useState(false)

  // 🔄: every part worked out again on the server, then shown in place of the cached figures
  const refresh = async () => {
    if (fresh) return
    setFresh(true)
    try {
      qc.setQueryData([PATH, {}], await getJSON<Dash>(PATH, { fresh: 1 }))
      toast('🔄 every figure worked out afresh')
    } catch (e) {
      toast('😬 ' + (e as Error).message, true)
    } finally {
      setFresh(false)
    }
  }

  const status = fresh ? '⏳ working every figure out afresh (it can take half a minute)…'
    : !data && !error ? '⏳ gathering (the first time takes half a minute)…'
    : isFetching ? '⏳ gathering…'
    : error && !data ? '😬 ' + (error as Error).message
    : `figures as of ${when(data!.at)} (each part refreshes in the background as you reload)`

  return (
    <main className="page dash">
      <h1 className="dash-title">📈 Everything at a glance</h1>
      <div className="dash-sub dash-status">
        <span>{status}</span> · <button className={'btn dash-refresh' + (fresh ? ' busy' : '')} onClick={refresh} disabled={fresh}>🔄 refresh</button>
        {error && data && <span className="dash-err"> 😬 the last fetch failed: {(error as Error).message}</span>}
      </div>
      {data && <Figures d={data} />}
    </main>
  )
}

function Figures({ d }: { d: Dash }) {
  const A = d.acquisition || {}, P = d.processing || {}, M = d.motifs || {}, X = d.models || {}, C = d.curation || {}, H = d.machine || {}
  const days: string[] = Array.isArray(A.days) ? A.days : []
  const lastDay = days[days.length - 1]
  const runs: { start: string; minutes: number; ok: boolean | null }[] = Array.isArray(d.runs) ? d.runs : []
  const last = runs[runs.length - 1] ?? ({} as Partial<(typeof runs)[number]>)
  const health = H.health || {}, problems: { outlet?: string; feed?: string; problem: string }[] = health.problems || []
  const loads: Record<string, Record<string, number>> = d['model loads'] || {}
  const loadHours = Object.keys(loads).filter((k) => k !== 'error')
  const modelsSeen = [...new Set(loadHours.flatMap((h) => Object.keys(loads[h])))]
  const loadSeries: Series = Object.fromEntries(modelsSeen.map((m) => [m, Object.fromEntries(loadHours.map((h) => [h, loads[h][m] || 0]))]))
  const today = new Date().toLocaleDateString('en-CA') // the hours are the machine's own time
  const reloadsToday = loadHours.filter((h) => h.slice(0, 10) === today).reduce((t, h) => t + Object.values(loads[h]).reduce((a, b) => a + b, 0), 0)
  const gpu: Point[] = Array.isArray(d.gpu) ? d.gpu : []
  const hot = gpu.length ? Math.max(...gpu.map((p) => p.temp as number)) : null
  const runMinutes = runs.filter((r) => r.ok !== null).map((r) => r.minutes)
  const side = A.side || {}
  const sideKinds = [...new Set(days.flatMap((x) => Object.keys(side[x] || {})))]
  const sideSeries: Series = Object.fromEntries(sideKinds.map((k) => [k, Object.fromEntries(days.map((x) => [x, (side[x] || {})[k] || 0]))]))
  const trKinds = ['whisper', 'from the show', 'failed or skipped']
  const tr = A.transcripts || {}
  const trSeries: Series = Object.fromEntries(trKinds.map((k) => [k, Object.fromEntries(days.map((x) => [x, (tr[x] || {})[k] || 0]))]))
  const mDays: Record<string, any>[] = Array.isArray(M.days) ? M.days : []
  const mdays = mDays.map((x) => x.day as string)
  const byDay = (k: string) => Object.fromEntries(mDays.map((x) => [x.day, x[k] || 0]))
  const cur: Record<string, { you?: number; claude?: number }> = C['per day'] || {}, cdays = Object.keys(cur)
  const now = M.now || {}
  const fc = X.confidence || {}, sl = X.shortlist || {}, rr = X.reranker || {}
  const props: Record<string, number> = P['open proposals'] || {}
  const audio = A['audio hours'] || {}
  const F = d['fact-checks'] || {}
  const S = d.sagas || {}, partsADay: Record<string, Record<string, number>> = S['parts a day'] || {}, sdays = Object.keys(partsADay)
  const sNames = [...new Set(sdays.flatMap((x) => Object.keys(partsADay[x])))]
  const hist: Point[] = Array.isArray(X.history) ? X.history : []
  const confRuns = hist.filter((h) => h.model === 'confidence'), shortRuns = hist.filter((h) => h.model === 'shortlist')
  const live: Point[] = Array.isArray(X.live) ? X.live : []
  const lastLive = (live[live.length - 1] ?? {}) as Record<string, any>
  const pctOf = (v: unknown) => (v ?? '—') + '%'

  return (
    <>
      <Section title="🩺 Is it keeping up?">
        <Card title="At a glance" wide>
          <Tiles>
            <Tile emoji={last.ok === null ? '⏳' : last.ok ? '✅' : '❌'} big={last.minutes != null ? last.minutes + ' min' : '—'}
              small={`last hourly run (${(last.start || '').slice(11, 16)}${last.ok === null ? ', going now' : ''}); the limit is 45`}
              tint={(last.minutes ?? 0) > 40 ? '#fff3ef' : '#effbf6'} />
            <Tile emoji="⏱️" big={runMinutes.length ? Math.round(runMinutes.reduce((a, b) => a + b, 0) / runMinutes.length) + ' min' : '—'}
              small={`average of ${runMinutes.length} runs in 48 h; ${runs.filter((r) => r.ok === false).length} failed`} />
            <Tile emoji={problems.length ? '🚨' : '💚'} big={problems.length || 'all in'}
              small={problems.length ? 'feeds or outlets not coming in' : 'every feed and outlet coming in as usual'}
              tint={problems.length ? '#fff3ef' : '#effbf6'} />
            <Tile emoji="🌡️" big={hot != null ? hot + '°C' : '—'} small="hottest the card got in 24 h (it runs at 83, its limit is 93)" />
            <Tile emoji="🔁" big={reloadsToday} small="models loaded into memory today (fewer is better)" />
            <Tile emoji="💽" big={num(H['disk free GB']) + ' GB'} small={`free on the data disk (${num(H['disk used %'])}% used)`} />
          </Tiles>
        </Card>
        <Card title="⏱️ Hourly runs, last 48 h (minutes)">
          <Err of={d.runs} />
          <Bars labels={runs.map((r) => r.start)} series={{
            ran: Object.fromEntries(runs.filter((r) => r.ok).map((r) => [r.start, r.minutes])),
            failed: Object.fromEntries(runs.filter((r) => r.ok === false).map((r) => [r.start, r.minutes])),
            'going now': Object.fromEntries(runs.filter((r) => r.ok === null).map((r) => [r.start, r.minutes])),
          }} opts={{ colors: { ran: '#2ec27e', failed: '#ff4d6d', 'going now': '#ffc400' }, line: 45, lineLabel: '45-minute limit', max: 50, fmt: hour }} />
        </Card>
        <Card title={problems.length ? '🚨 Not coming in' : '💚 Feeds and outlets'} sick={problems.length > 0}>
          {problems.length ? <List rows={problems.map((p) => [`${p.outlet || p.feed}: ${p.problem}`, ''])} /> : <>
            <p>Every outlet seen on its front page lately, every regular feed on its usual rhythm.</p>
            <p className="dash-sub">checked {when(health.at)} UTC</p>
          </>}
        </Card>
        <Card title="🎛️ The card, last 24 h">
          <Err of={d.gpu} />
          <Lines points={gpu} lines={[['temp', 100, '#ff4d6d'], ['load', 100, '#3a86ff']]} opts={{ danger: [83, 100, '83°C: slows itself'] }} />
          <p className="dash-sub">temperature (°C) and load (%), every ten minutes</p>
        </Card>
        <Card title="🔁 Models loaded into memory, per hour" wide>
          <Err of={loads} />
          <Bars labels={loadHours} series={loadSeries} opts={{ fmt: hour }} />
          <p className="dash-sub">each load is the card waiting: two models taking turns load each other again and again</p>
        </Card>
      </Section>

      <Section title="📥 What came in">
        <Card title="At a glance" wide>
          <Err of={A} />
          <Tiles>
            <Tile emoji="📰" big={num((A.headlines || {})[lastDay])} small="headlines new today" />
            <Tile emoji="🏢" big={num((A.outlets || {})[lastDay]) + ' / ' + num(A['outlets in all'])} small="outlets seen today" />
            <Tile emoji="📡" big={num(A['feeds in all'])} small="side feeds followed" />
            <Tile emoji="🎙️" big={num(audio[lastDay]) + ' h'} small="of shows transcribed today" />
            <Tile emoji="⏳" big={num(A['transcription backlog'])} small="episodes waiting to be transcribed" />
            <Tile emoji="🧵" big={num((A.stories || {})[lastDay])} small="new stories today" />
          </Tiles>
        </Card>
        <Card title="📰 Headlines a day"><OneBars labels={days} values={A.headlines || {}} name="headlines" /></Card>
        <Card title="🏢 Outlets seen a day"><OneBars labels={days} values={A.outlets || {}} name="outlets" /></Card>
        <Card title="📡 Side-feed items a day, by kind"><Bars labels={days} series={sideSeries} /></Card>
        <Card title="🎙️ Transcripts a day">
          <Bars labels={days} series={trSeries} opts={{ colors: { whisper: '#3a86ff', 'from the show': '#2ec27e', 'failed or skipped': '#ff4d6d' } }} />
          <p className="dash-sub">audio transcribed: {days.slice(-3).map((x) => short(x) + ' ' + (audio[x] || 0) + ' h').join(' · ')}</p>
        </Card>
        <Card title="🔎 Fact-checks, last 30 days">
          <Err of={F} />
          <Tiles>
            <Tile emoji="🔎" big={num(F['last 30 days'])} small="pieces" />
            <Tile emoji="📄" big={num(F['read from the piece'])} small="claims read from the piece itself" />
            <Tile emoji="🗒️" big={num(F['with a claim'])} small="with a claim" />
          </Tiles>
          <List rows={entries(F['by checker'])} />
          <p className="dash-sub">text from: {entries(F['text from']).map(([k, v]) => k + ' ' + v).join(' · ')}</p>
        </Card>
        <Card title="🧵 New stories a day"><OneBars labels={days} values={A.stories || {}} name="stories" /></Card>
      </Section>

      <Section title="🧵 Sagas">
        <Card title="At a glance" wide>
          <Err of={S} />
          <Tiles>
            <Tile emoji="🧵" big={num(S.sagas)} small="sagas so far" />
            <Tile emoji="🟢" big={num(S.now)} small="on the front pages now" />
            <Tile emoji="🧩" big={num(S.parts)} small="stories that are parts of one" />
            <Tile emoji="📊" big={S.stories ? Math.round((100 * S['stories in a saga']) / S.stories) + '%' : '—'}
              small={`of the last two weeks' ${num(S.stories)} stories are in a saga`} />
          </Tiles>
        </Card>
        <Card title="🟢 On the front pages now" wide>
          <SagaTable rows={(S.active || []) as Saga[]} />
          <p className="dash-sub">who carries it: the outlets on any of its parts, by lean (blue left, grey center, red right)</p>
        </Card>
        <Card title="🧩 New saga parts a day">
          <Bars labels={sdays} series={Object.fromEntries(sNames.map((n) => [n, Object.fromEntries(sdays.map((x) => [x, partsADay[x][n] || 0]))]))} />
        </Card>
        <Card title="🏔️ Biggest sagas"><SagaTable rows={(S.biggest || []) as Saga[]} /></Card>
      </Section>

      <Section title="⚙️ What was made of it">
        <Card title="Waiting for you" wide>
          <Err of={P} />
          <Tiles>
            <Tile emoji="✅" big={num(P['unchecked in your motifs'])} small="filings to check in your motifs" tint="#fff8db" />
            <Tile emoji="🔁" big={num(P['weak, up for a second look'])} small="confirmed ones the model doubts (second look)" />
            <Tile emoji="🤖" big={num(P['weak claims with suggestions'])} small="weak claims with a better motif suggested" />
            <Tile emoji="📥" big={num(P['claims with no motif'])} small="claims with no motif" />
            <Tile emoji="💡" big={num(Object.values(props).reduce((a, b) => a + b, 0))} small="open proposals" />
            <Tile emoji="🗣️" big={num(P['retold on the shows'])} small="claims retold across the shows" />
          </Tiles>
        </Card>
        <Card title="🗂️ Claims filed a day">
          <Bars labels={mdays} series={{ 'into a motif already there': byDay('filed_matched'), 'a new motif made': byDay('filed_new'), 'no motif': byDay('filed_none') }}
            opts={{ colors: { 'into a motif already there': '#2ec27e', 'a new motif made': '#ffc400', 'no motif': '#7a7a8c' } }} />
        </Card>
        <Card title="💡 Open proposals by kind">
          <List rows={entries(props).sort((a, b) => b[1] - a[1]).map(([k, n]) => [KIND[k] || k, n])} />
          <p className="dash-sub"><Link to="/workbench" onClick={() => setWB({ tab: 'proposals' })}>to the 💡 tab</Link></p>
        </Card>
        <Card title="📻 Episodes: news or evergreen">
          {entries(P.episodes).length ? <List rows={entries(P.episodes)} /> : <p className="dash-sub">🌱 labels start with the next hourly run</p>}
        </Card>
      </Section>

      <Section title="🧩 The motif index">
        <Card title="At a glance" wide>
          <Err of={M} />
          <Tiles>
            <Tile emoji="🧩" big={num(now.motifs)} small="motifs" />
            <Tile emoji="💬" big={num(now.claims)} small={`claims (${num(now.filings)} filings)`} />
            <Tile emoji="✅" big={pctOf(now.done)} small="marked done by you" />
            <Tile emoji="📝" big={pctOf(now.your_notes)} small="with your note" />
            <Tile emoji="🎭" big={pctOf(now.with_genre)} small="with a genre" />
            <Tile emoji="📁" big={pctOf(now.in_group)} small="in a group" />
            <Tile emoji="🌳" big={pctOf(now.in_tree)} small="in a rests-on tree" />
            <Tile emoji="☝️" big={pctOf(now.singles)} small="with one claim only" />
          </Tiles>
        </Card>
        <Card title="✨ New motifs and your checks a day">
          <Bars labels={mdays} series={{ 'new motifs': byDay('new_motifs'), 'your ✓': byDay('checks_yes'), 'your ✕': byDay('checks_no') }}
            opts={{ colors: { 'new motifs': '#ffc400', 'your ✓': '#2ec27e', 'your ✕': '#ff4d6d' } }} />
        </Card>
        <Card title="🎭 By genre"><List rows={entries(M['by genre'])} /></Card>
        <Card title="📁 By group"><List rows={entries(M['by group'])} /></Card>
        <Card title="🔥 Growing this week (new claims)"><List rows={((M['growing this week'] || []) as [string, number][]).filter(([, n]) => n)} /></Card>
        <Card title="🏔️ Biggest"><List rows={(M.biggest || []) as [string, number][]} /></Card>
        <Card title="🐣 Newest"><List rows={((M.newest || []) as [string, string][]).map(([n, day]) => [n, day.slice(5, 10).replace('-', '/')])} /></Card>
      </Section>

      <Section title="🧠 The models, by their own tests">
        <Card title="🎯 Filing confidence">
          <Err of={X} />
          <List rows={[['held-out AUC', fc.auc], ['sure from', pct(fc['sure at'])], ['right when sure', pct(fc['precision when sure'])],
            ['of your kept filings passable when sure', pct(fc['kept passable when sure'])], ['decisions learned from', fc.decisions],
            ['reranker', fc.reranker], ['trained', when(fc.at)]]} />
        </Card>
        <Card title="📋 Shortlist (your motifs in the top 12, held out)">
          <List rows={[['plain weights', pct(sl['plain top 12'])], ['every signal weighed', pct(sl['learned top 12'])], ['learned from claims', sl.claims], ['trained', when(sl.at)]]} />
        </Card>
        <Card title="🧑‍🏫 Reranker taught your decisions">
          <List rows={[['taught', when(rr.at)], ['examples', rr.examples], ['your decisions', rr.decisions]]} />
        </Card>
        <Card title="🎯 How often the model calls your decisions right, a day at a time" wide>
          <Lines points={live} lines={[['share_right', 1, '#3a86ff', 0.5], ['right_when_sure', 1, '#2ec27e', 0.5]]}
            opts={{ scale: true, empty: '🌱 collecting since Oct 9: each ✓ and ✕ is kept with the fit the model had given it' }} />
          {lastLive.at && <List rows={[[`decisions on ${String(lastLive.at).slice(5)}`, lastLive.decisions], ['the model called right', pct(lastLive.share_right)],
            [`of those it was sure of (${lastLive.sure}), you kept`, pct(lastLive.right_when_sure)]]} />}
          <p className="dash-sub">blue: calls right (a fit of 50%+ for a filing you kept, under 50% for one you took out) · green: of the filings it was sure of, the share you kept. Measured on the claims coming in, not a test on old ones.</p>
        </Card>
        <Card title="📈 Filing confidence, held-out AUC at each training">
          <Lines points={confRuns} lines={[['auc', 1, '#8a5cff', 0.75]]} opts={{ scale: true }} />
          <p className="dash-sub">{confRuns.length} trainings since {(confRuns[0]?.at ?? '—').slice(5, 10)}; decisions learned from: {confRuns.map((c) => c.decisions).join(' → ')}</p>
        </Card>
        <Card title="📈 Shortlist, your motif in the top 12 (held out)">
          <Lines points={shortRuns} lines={[['top12', 1, '#ffc400', 0.7], ['plain_top12', 1, '#7a7a8c', 0.7]]} opts={{ scale: true }} />
          <p className="dash-sub">yellow: every signal weighed · grey: the plain weights</p>
        </Card>
        <Card title="🧪 Latest experiment results" wide>
          <div className="dash-mono">{((X.experiments || []) as string[]).join('\n') || 'none yet'}</div>
        </Card>
      </Section>

      <Section title="🖐️ Your curation">
        <Card title="Changes a day: yours, by hand and through Claude">
          <Err of={C} />
          <Bars labels={cdays} series={{ 'by hand': Object.fromEntries(cdays.map((x) => [x, cur[x].you || 0])), 'through Claude': Object.fromEntries(cdays.map((x) => [x, cur[x].claude || 0])) }}
            opts={{ colors: { 'by hand': '#8a5cff', 'through Claude': '#00c2a8' } }} />
          <p className="dash-sub">each change counted, a batch by its steps</p>
        </Card>
        <Card title="This week, by kind of change"><List rows={entries(C['this week by kind'])} /></Card>
        <Card title="💾 Files"><List rows={entries(H['files MB']).map(([k, v]) => [k, v + ' MB'])} /></Card>
      </Section>
    </>
  )
}
