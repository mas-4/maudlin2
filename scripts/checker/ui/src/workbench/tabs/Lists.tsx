// The inbox's lists: ✅ sure and 🚫 misfits (a claim a row, a page at a time), ⏸ held, ✨ to shape, 🔎 claims,
// 🔗 pairs, 1️⃣ singles, 📥 unfiled, 🫙 empty
import { useEffect, useRef, useState } from 'react'
import { sure as confirm, toast } from '../../components/Feedback'
import { getJSON } from '../../lib/api'
import { act, batch } from '../act'
import { Chip, claimDrag, ClaimText, FitChip, useClaimHead } from '../bits'
import { useQueue, type Judging } from '../judge'
import { isEmpty, isSingle, motifsOf, SOURCE, useWorkbench, type Model } from '../model'
import { holdClaim, openClaim, openMotif, quickDecide } from '../ops'
import { mark, setWB, useWB } from '../store'
import type { ClaimHit, Proposal } from '../types'
import { ProposalCard } from './Proposals'

const QUICK_PER = [10, 25, 50, 100]
const pct = (x: number) => Math.round(x * 100)

/** ✅ sure (every waiting motif past the sure line; untick what doesn't fit, then pass the page: the ticked pass and a
 * claim with any motif unticked goes to ⏸ held) and 🚫 misfits (likely out, none ticked: tick the ones that don't fit) */
export function QuickTab({ kind, j }: { kind: 'sure' | 'out'; j: Judging | null }) {
  const { model: m } = useWorkbench()
  const per = useWB((s) => s.quickper)
  const page0 = useWB((s) => s.quickPage[kind] ?? 0)
  const snap = useWB((s) => s.quickSnap[kind])
  const unticked = useWB((s) => s.unticked), outTicked = useWB((s) => s.outTicked)
  const rows = m?.data.confidence && j ? (kind === 'sure' ? j.sure : j.out) : null
  const pages = Math.max(1, Math.ceil((rows?.length ?? 0) / per)), page = Math.min(page0, pages - 1)
  // The page holds still while it's read (Oct 25: the worker filing split claims saved the index every minute, the
  // lists were read again each time, and rows slid off the page or vanished mid-read). Its rows are the ones it opened
  // with, kept until it's passed or turned; one decided, held or rescored meanwhile stays in its place, greyed, and
  // claims that came in wait for the next page. Passing acts on the rows shown and nothing else
  const stale = !snap || snap.page !== page || snap.per !== per
  const slice = (from: { claim: string; ids: string[] }[]) => from.slice(page * per, (page + 1) * per).map(({ claim, ids }) => ({ claim, ids }))
  const keep = (next: { claim: string; ids: string[] }[] | null) => setWB((s) => {
    const all = { ...s.quickSnap }
    if (next) all[kind] = { page, per, rows: next }
    else delete all[kind]
    return { quickSnap: all }
  })
  useEffect(() => {
    if (rows && stale) keep(slice(rows))
  })
  if (!m || !j) return <p className="faint">⏳ thinking…</p>
  const conf = m.data.confidence
  if (!conf || !rows) return <p className="faint">The confidence model hasn't been trained yet.</p>
  const shown = stale ? slice(rows) : snap.rows
  if (!rows.length && !shown.length) return <div className="welcome"><div className="hero">{kind === 'sure' ? '✅' : '🚫'}</div><p>{kind === 'sure' ? 'No sure claims waiting.' : 'No likely misfits waiting.'}</p></div>
  const live = new Map(rows.map((r) => [r.claim, r.ids]))
  const on = (r: { claim: string; ids: string[] }) => r.ids.filter((id) => live.get(r.claim)?.includes(id))
  const gone = (claim: string) => live.has(claim) ? '' : !j.why[claim] || !j.waiting(claim).length ? 'done or held since this page opened'
    : kind === 'sure' ? 'no longer sure since this page opened: it wants its card in 🎯' : 'no longer a likely misfit since this page opened'
  const here = new Set(shown.map((r) => r.claim))
  const came = stale ? 0 : slice(rows).filter((r) => !here.has(r.claim)).length
  const ticked = (k: string) => (kind === 'sure' ? !unticked.includes(k) : outTicked.includes(k))
  const pairs = shown.flatMap((r) => on(r).map((id) => r.claim + '|' + id))
  const next = () => keep(slice(rows.filter((r) => !here.has(r.claim)))) // the page passed: the rows after it, as they are now
  const pager = (
    <div className="pager">
      <button className="btn" disabled={!page} onClick={() => setWB((s) => ({ quickPage: { ...s.quickPage, [kind]: page - 1 } }))}>◀</button>
      <span>page {page + 1} of {pages}</span>
      <button className="btn" disabled={page >= pages - 1} onClick={() => setWB((s) => ({ quickPage: { ...s.quickPage, [kind]: page + 1 } }))}>▶</button>
      <label className="faint">rows a page <select value={per} onChange={(e) => setWB({ quickper: +e.target.value, quickPage: {} })}>{QUICK_PER.map((n) => <option key={n}>{n}</option>)}</select></label>
    </div>
  )
  const pass = () => { // the sure claims' ticked motifs on the page, passed in one undoable step
    const yes = pairs.filter(ticked), no = pairs.filter((k) => !ticked(k))
    if (!yes.length && !no.length) return toast('nothing on this page')
    // a claim with a motif unticked is held, to look at later, in the same step (Oct 19, the person: "it automatically
    // holds the unchecked ones"); the unticked go in the log too, for the tab's tally (sure_tally)
    const held = [...new Set(no.map((k) => k.slice(0, k.lastIndexOf('|'))))]
    setWB((s) => ({ unticked: s.unticked.filter((k) => !no.includes(k)) }))
    next()
    void quickDecide(yes.map((k) => [k, 'yes']), [`🎯 passed ${yes.length} sure filing${yes.length === 1 ? '' : 's'}`, held.length ? `⏸ held ${held.length}` : ''].filter(Boolean).join(', '),
      { quick: 'sure', unticked: no }, held.map((claim) => ({ action: 'hold', claim, from: 'sure' })))
  }
  const takeOut = (keep: boolean) => { // the likely misfits ticked on the page taken out; with keep, the unticked said to fit
    const out = pairs.filter(ticked), rest = pairs.filter((k) => !ticked(k))
    if (!out.length && !(keep && rest.length)) return toast('nothing ticked')
    if (!keep) rest.forEach((k) => mark('quickSkip', k)) // looked at, left: for its card
    setWB((s) => ({ outTicked: s.outTicked.filter((k) => !pairs.includes(k)) }))
    next()
    void quickDecide([...out.map((k) => [k, 'out'] as [string, 'out']), ...(keep ? rest.map((k) => [k, 'yes'] as [string, 'yes']) : [])],
      [out.length ? `✕ took out ${out.length}` : '', keep && rest.length ? `✓ ${rest.length} fit` : ''].filter(Boolean).join(', '))
  }
  let head
  if (kind === 'sure') { // how the sure claims have fared with you: clean, or needing you (an untick, a take-out, a hold)
    const t = conf.tally ?? [], week = t.reduce((n, d) => ({ clean: n.clean + d.clean, needed: n.needed + d.needed }), { clean: 0, needed: 0 })
    const fared = (d: { clean: number; needed: number }) => `${d.clean} of ${d.clean + d.needed} passed clean (${pct(d.clean / (d.clean + d.needed))}%)`
    head = <>
      {t.length > 0 && <p className="tally">📏 With you: {t[0].day === new Date().toLocaleDateString('en-CA') ? 'today' : t[0].day} {fared(t[0])}{t.length > 1 ? `; the last week ${fared(week)}` : ''}. Every untick, take-out or hold counts as needing you.</p>}
      <p className="faint" title={`Tested on your past checks, held out: ${pct(conf.at_sure.precision)}% of filings at ${pct(conf.sure_at)}% or more were ones you kept; holds and unticks don't count there`}>
        ✅ <b>{rows.length} sure claim{rows.length === 1 ? '' : 's'}</b> ({pct(conf.at_sure.precision)}% right in the model's own test): every motif waiting on them is past the sure line. Untick any that don't fit, then pass the page: the ticked pass, and a claim with any motif unticked goes to ⏸ held, to look at later. Your ticks stay as you leave them when you turn the page. The page holds still while you read it.</p>
    </>
  } else {
    const o = conf.at_out
    head = <p className="faint">🚫 <b>{rows.length} claim{rows.length === 1 ? '' : 's'} with a likely misfit</b> ({o?.removed != null ? `held out, you took out ${pct(o.removed)}% of filings under ${pct(conf.out_at)}%` : `under ${pct(conf.out_at)}%`}). The model is never sure of a no, so none come ticked: tick the motifs that don't fit. Take out the ticked and leave the rest for 🎯 claims to judge, or take out the ticked and say the rest fit.</p>
  }
  return (
    <>
      {head}
      {pager}
      {came > 0 && <p className="faint quicknew">🆕 {came} more came in or back since this page opened; they show when you pass or turn the page. <button className="mini" onClick={() => keep(null)}>🔄 show them now</button></p>}
      <div className="quicklist">{shown.map((r) => <QuickRow key={r.claim} kind={kind} r={r} on={on(r)} gone={gone(r.claim)} j={j} ticked={ticked} />)}</div>
      <div className="quickbar">
        {kind === 'sure' ? <button className="btn yes" title="the ticked pass; a claim with any motif unticked goes to ⏸ held" onClick={pass}>✓ pass the ticked, ⏸ hold the rest</button>
          : <><button className="btn no" onClick={() => takeOut(false)}>✕ take out the ticked</button>
            <button className="btn" title="the ticked out, every unticked one on this page checked as fitting" onClick={() => takeOut(true)}>✕ take out the ticked, ✓ the rest fit</button></>}
      </div>
    </>
  )
}

/** A quick tab's row as the page opened with it: `on`, its motifs still waiting as they were (the rest were decided
 * since, and pass without them); `gone`, why it left the list since, greyed and passed with nothing */
function QuickRow({ kind, r, on, gone, j, ticked }: { kind: 'sure' | 'out'; r: { claim: string; ids: string[] }; on: string[]; gone: string; j: Judging; ticked: (k: string) => boolean }) {
  const h = useClaimHead(r.claim, r.ids)
  return (
    <div className={gone ? 'sureline quickgone' : 'sureline'} {...h.drag}>
      <span>{h.head}</span>
      {gone && <span className="faint">· {gone}</span>}
      <span className="quickmotifs">
        {r.ids.map((id) => {
          const k = r.claim + '|' + id, live = on.includes(id)
          return <label key={id} className={live ? 'quickmotif' : 'quickmotif quickoff'} title={live ? undefined : 'decided since this page opened: passing leaves it as it is'}>
            <input type="checkbox" checked={live && ticked(k)} disabled={!live}
              onChange={(e) => mark(kind === 'sure' ? 'unticked' : 'outTicked', k, kind === 'sure' ? !e.target.checked : e.target.checked)} />
            {j.fits[k] != null && <FitChip fit={j.fits[k]} />} <Chip id={id} /></label>
        })}
        {kind === 'out' && !gone && <button className="mini" title="keep it aside to look at later: out of the lists, into ⏸ held" onClick={() => void holdClaim(r.claim, true)}>⏸ hold</button>}
      </span>
    </div>
  )
}

/** ⏸ Claims put on hold to look at later: out of the judging lists until taken off hold */
export function HeldTab() {
  const { model: m } = useWorkbench()
  const q = useQueue<{ claim: string; at: string; waiting: number }[]>('held')
  if (q.error) return <p className="faint">😬 {(q.error as Error).message}</p>
  if (!m || !q.data) return <p className="faint">⏳ thinking…</p>
  if (!q.data.length) return <div className="welcome"><div className="hero">⏸</div><p>Nothing on hold. ⏸ hold a claim from its card, or from ✅ sure or 🚫 misfits, to look at it later without it coming back each time.</p></div>
  return <>
    <p className="faint">⏸ Claims you put on hold to look at later. They stay out of 🎯 claims to judge, ✅ sure and 🚫 misfits until you take them off hold. Click one to work on it, or drag it onto a motif.</p>
    {q.data.map((x) => <HeldRow key={x.claim} m={m} x={x} />)}
  </>
}
function HeldRow({ m, x }: { m: Model; x: { claim: string; at: string; waiting: number } }) {
  const h = useClaimHead(x.claim)
  return (
    <div className="sureline" {...h.drag}>
      <span>{h.head}</span>
      <span className="quickmotifs"><span className="faint">held {new Date(x.at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · {x.waiting ? `${x.waiting} motif${x.waiting === 1 ? '' : 's'} waiting` : 'nothing waiting'}</span>
        {motifsOf(m, x.claim).map((e) => <Chip key={e.id} id={e.id} />)}
        <button className="btn" title="back into the queues" onClick={() => void holdClaim(x.claim, false)}>▶ take off hold</button></span>
    </div>
  )
}

/** ✨ To shape: today's most useful motif-level decisions, a short list that teaches the models most per minute */
export function TodayTab() {
  const { model: m } = useWorkbench()
  const [more, setMore] = useState(false)
  const q = useQueue<{ items: { kind: string; id?: string; proposal?: Proposal }[]; picked: number; done: number }>(more ? 'today-more' : 'today')
  const decided = useWB((s) => s.decided)
  if (q.error) return <p className="faint">😬 {(q.error as Error).message}</p>
  if (!m || !q.data) return <p className="faint">⏳ thinking…</p>
  const cards = q.data.items.flatMap((x, i) => {
    if (x.kind === 'new motif' && x.id) {
      const e = m.by[x.id]
      if (!e || e.done) return []
      const groups = (e.groups ?? []).map((g) => m.data.groups.find((y) => y.id === g)?.name ?? g)
      return [<div key={x.id} className="card unck"><div className="today-why">✨ the model made this motif and nobody has shaped it yet</div>
        <div className="sug"><Chip id={e.id} /> <span className="faint">{e.claims.length} claim{e.claims.length === 1 ? '' : 's'}</span>
          <span className="sbtns"><button className="btn yes" title="it's a good motif as it stands: keep its note, genre and groups" onClick={() => void act({ action: 'done', id: e.id, done: true }, `✅ “${e.name}” is done`)}>✅ keep it as it is</button></span></div>
        <div className="faint">{e.note ? '📝 ' + e.note : 'no note yet'}{e.facets?.genre ? ` · 🎭 ${e.facets.genre}${e.by_model?.genre ? ' 🤖' : ''}` : ''}{groups.length ? ' · 📁 ' + groups.join(', ') : ''}</div>
        <div className="faint">or click it to open it: rename it, change the note, fold it into another, or delete it</div></div>]
    }
    if (x.kind === 'proposal' && x.proposal && !decided.includes('p:' + x.proposal.id)) {
      return [<ProposalCard key={x.proposal.id + i} p={x.proposal} m={m} today />]
    }
    return []
  })
  const done = q.data.picked - cards.length
  return cards.length ? <>
    <p className="faint">✨ To shape: the motifs the model made that nobody has shaped yet, and its likeliest proposals. The claims to judge are in 🎯, each claim whole. <b>{done} of {q.data.picked} done today.</b></p>
    {cards}
  </> : <div className="welcome"><div className="hero">🎉</div><p>Done for today: all {q.data.picked} of today's most useful decisions are made. The models learn from them tonight; a new set tomorrow.</p>
    <p><button className="btn" title="another twenty of the most useful decisions, if you'd like to keep going" onClick={() => setMore(true)}>🎯 20 more</button></p></div>
}

/** 🔎 Every claim with all the words typed (or its #id), filed or not, each once with the motifs it's in */
export function FindTab() {
  const { model: m } = useWorkbench()
  const q = useWB((s) => s.findQ)
  const [unfiled, setUnfiled] = useState<ClaimHit[]>([])
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => { // claims not filed yet come from the server
    clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      const w = q.toLowerCase().split(/\s+/).filter((x) => x && !x.startsWith('#'))
      setUnfiled(w.length && q.length > 2 ? await getJSON<ClaimHit[]>('/claims.json', { q: w.join(' ') }).catch(() => []) : [])
    }, 200)
  }, [q])
  if (!m) return null
  const w = q.toLowerCase().split(/\s+/).filter(Boolean)
  const by = new Map<string, { c: { claim: string; id: string; source: string; ref?: string }; ids: string[] }>()
  if (w.length) for (const e of m.data.entries) for (const c of e.claims) {
    const hay = (c.claim + ' #' + c.id).toLowerCase()
    if (!w.every((x) => hay.includes(x))) continue
    const x = by.get(c.claim) ?? { c, ids: [] }
    x.ids.push(e.id)
    by.set(c.claim, x)
  }
  const local = [...by.values()], loose = unfiled.filter((c) => !c.motifs.length)
  return <>
    <label className="addsearch">🔎 <input type="search" autoFocus placeholder="words from a claim, or its #id" value={q} autoComplete="off" onChange={(e) => setWB({ findQ: e.target.value })} /></label>
    {!w.length ? <p className="faint">🔎 Type words from a claim, or its #id: every claim that has them, filed or not, each once with the motifs it's in.</p>
      : !local.length && !loose.length ? <p className="faint">🦗 no claim has all those words</p> : <>
        <p className="faint">{local.length} filed{loose.length ? `, ${loose.length} not filed yet` : ''} · click one to open it, or drag it onto a motif</p>
        <ul className="claims">
          {local.slice(0, 40).map(({ c, ids }) => <ClaimLine key={c.claim} c={c} from={ids[0]} meta={<>#{c.id} · in {ids.map((i) => <Chip key={i} id={i} />)}</>} />)}
          {loose.slice(0, 20).map((c) => <ClaimLine key={c.claim} c={c} from="" unfiled meta={<>📥 not filed · {SOURCE[c.source] || c.source}</>} />)}
        </ul>
      </>}
  </>
}

function ClaimLine({ c, from, meta, unfiled }: { c: { claim: string; source: string; ref?: string }; from: string; meta: React.ReactNode; unfiled?: boolean }) {
  return (
    <li className={'claim mini' + (unfiled ? ' unfiled' : '')} {...claimDrag(c, from)}>
      <ClaimText claim={c.claim} className="ctext" onOpen={() => openClaim(c.claim, { src: c.source, ref: c.ref })} />
      <span className="meta">{meta}</span>
    </li>
  )
}

/** 🔗 Pairs that may be one motif: filed together, or alike in name */
export function PairsTab() {
  const { model: m } = useWorkbench()
  const q = useQueue<{ similar: { a: string; b: string; score: number }[]; shared: { a: string; b: string; shared: string[] }[]; note?: string | null }>('pairs')
  if (q.error) return <p className="faint">😬 {(q.error as Error).message}</p>
  if (!m || !q.data) return <p className="faint">⏳ thinking…</p>
  const seen = new Set(m.data.not_same.map((p) => [...p].sort().join('|')))
  const ok = (a: string, b: string) => m.by[a] && m.by[b] && a !== b && !seen.has([a, b].sort().join('|'))
    && !m.by[a].parents.includes(b) && !m.by[b].parents.includes(a) && !m.by[a].related.includes(b)
  const shared = q.data.shared.filter((p) => ok(p.a, p.b)), similar = q.data.similar.filter((p) => ok(p.a, p.b))
  return <>
    {q.data.note && <p className="faint">{q.data.note}</p>}
    <h3>🤝 filed together <i>{shared.length}</i></h3>
    {shared.map((p) => <PairCard key={p.a + p.b} m={m} a={p.a} b={p.b} why={`${p.shared.length} shared claim${p.shared.length === 1 ? '' : 's'}`} example={p.shared[0]} />)}
    {!shared.length && <p className="faint">🦗 none</p>}
    <h3>👯 similar names <i>{similar.length}</i></h3>
    {similar.map((p) => <PairCard key={p.a + p.b} m={m} a={p.a} b={p.b} why={'alike ' + p.score} />)}
    {!similar.length && <p className="faint">🦗 none</p>}
  </>
}

export function pairAction(m: Model, kind: 'merge' | 'under' | 'related' | 'notsame', a: string, b: string) {
  const A = m.by[a], B = m.by[b]
  const body = { merge: { action: 'merge', source: a, target: b }, under: { action: 'parent', id: a, parent: b }, related: { action: 'relate', a, b }, notsame: { action: 'not_same', a, b } }[kind]
  const say = { merge: `⤵ merged “${A.name}” into “${B.name}”`, under: `↳ “${A.name}” rests on “${B.name}”`, related: '↔ related', notsame: '≠ marked different' }[kind]
  return act(body, say)
}

function PairCard({ m, a, b, why, example }: { m: Model; a: string; b: string; why: string; example?: string }) {
  return (
    <div className="card">
      <div className="pair"><Chip id={a} /> <span className="faint">&amp;</span> <Chip id={b} /></div>
      <p className="faint">{why}{example ? ': “' + example.slice(0, 120) + '”' : ''}</p>
      <div className="sbtns">
        <button className="mini" title="open both, one under the other" onClick={() => { openMotif(a, true); openMotif(b, true) }}>⧉ compare</button>
        <button className="mini" title="merge the first into the second" onClick={() => void pairAction(m, 'merge', a, b)}>⤵ merge →</button>
        <button className="mini" title="merge the second into the first" onClick={() => void pairAction(m, 'merge', b, a)}>← merge ⤵</button>
        <button className="mini" title="the first rests on the second: a kind of it, or a case, argument or figure that tells it" onClick={() => void pairAction(m, 'under', a, b)}>↳ rests on →</button>
        <button className="mini" title="the second rests on the first" onClick={() => void pairAction(m, 'under', b, a)}>← rests on ↰</button>
        <button className="mini" onClick={() => void pairAction(m, 'related', a, b)}>↔ related</button>
        <button className="mini" title="different motifs: stop suggesting" onClick={() => void pairAction(m, 'notsame', a, b)}>≠ not the same</button>
      </div>
    </div>
  )
}

/** 1️⃣ Motifs with one claim and no links, each with the motifs it might join */
export function SinglesTab() {
  const { model: m } = useWorkbench()
  const q = useQueue<{ id: string; claim: string; source: string; suggest: { id: string; same_claim?: boolean; score?: number }[] }[]>('singles')
  if (q.error) return <p className="faint">😬 {(q.error as Error).message}</p>
  if (!m || !q.data) return <p className="faint">⏳ thinking…</p>
  const items = q.data.filter((s) => m.by[s.id] && isSingle(m, m.by[s.id]))
  if (!items.length) return <div className="welcome"><div className="hero">🎉</div><p>No singles waiting.</p></div>
  return <>{items.map((s) => (
    <div key={s.id} className="card">
      <div><Chip id={s.id} /> <button className="mini" title="it stands alone: stop suggesting" onClick={() => void act({ action: 'stands_alone', id: s.id, alone: true }, `🧍 “${m.by[s.id].name}” stands alone`)}>🧍</button></div>
      <p className="claim mini" {...claimDrag({ claim: s.claim, source: s.source }, s.id)}><span className="ctext">{s.claim}</span></p>
      {s.suggest.filter((x) => m.by[x.id]).map((x) => (
        <div key={x.id} className="sug"><Chip id={x.id} /> <span className="faint">{x.same_claim ? '🎯 same claim' : 'alike ' + (x.score ?? '')}</span>
          <span className="sbtns">
            <button className="mini" title="merge the single into it" onClick={() => void pairAction(m, 'merge', s.id, x.id)}>⤵</button>
            <button className="mini" title="the single rests on it" onClick={() => void pairAction(m, 'under', s.id, x.id)}>↳</button>
            <button className="mini" title="related" onClick={() => void pairAction(m, 'related', s.id, x.id)}>↔</button>
            <button className="mini" title="open both" onClick={() => { openMotif(s.id, true); openMotif(x.id, true) }}>⧉</button>
          </span></div>
      ))}
    </div>
  ))}</>
}

/** 📥 Claims not filed in any motif yet: search them, drag one onto a motif */
export function UnfiledTab() {
  const q = useWB((s) => s.unfiledQ)
  const [items, setItems] = useState<ClaimHit[] | null>(null)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => setItems(await getJSON<ClaimHit[]>('/claims.json', { q }).catch(() => [])), 200)
  }, [q])
  const rows = (items ?? []).filter((c) => !c.motifs.length)
  return <>
    <label className="addsearch">🔎 <input type="search" placeholder="search claims not filed yet" value={q} onChange={(e) => setWB({ unfiledQ: e.target.value })} /></label>
    <ul className="claims">
      {items === null ? <li className="faint">⏳</li> : rows.length ? rows.map((c) => <ClaimLine key={c.claim} c={c} from="" unfiled meta={<>📥 {SOURCE[c.source] || c.source}</>} />)
        : <li className="faint">🦗 none: every claim matching has a motif</li>}
    </ul>
  </>
}

/** 🫙 Motifs with no claims and nothing resting on them */
export function EmptyTab() {
  const { model: m } = useWorkbench()
  if (!m) return null
  const empty = m.data.entries.filter((e) => isEmpty(m, e))
  if (!empty.length) return <div className="welcome"><div className="hero">✨</div><p>No empty motifs.</p></div>
  return <>
    <p><button className="btn" onClick={async (ev) => {
      if (await confirm(`Delete ${empty.length} empty motifs?`, '🗑️ delete them', ev.currentTarget)) void batch(empty.map((e) => ({ action: 'delete', id: e.id })), `🗑️ deleted ${empty.length} empty motifs`)
    }}>🗑️ delete all {empty.length}</button></p>
    {empty.map((e) => (
      <div key={e.id} className="sug"><Chip id={e.id} /> <span className="faint">{e.curated ? '✋ made by hand' : ''} {(e.first_seen ?? '').slice(0, 10)}</span>
        <span className="sbtns"><button className="mini" onClick={async (ev) => {
          if (await confirm(`Delete “${e.name}”?`, '🗑️ delete it', ev.currentTarget)) void act({ action: 'delete', id: e.id }, `🗑️ deleted “${e.name}”`)
        }}>🗑️</button></span></div>
    ))}
  </>
}

