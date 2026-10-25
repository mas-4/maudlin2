// One claim, whole: where it came from, every motif it's in (✓ fits or ✕ take out each, with its fit), where it might
// belong instead, adding it to another motif, and claims like it. With a check bar on top it is 🎯 claims to judge.
import { useEffect, useRef, useState } from 'react'
import { toast } from '../../components/Feedback'
import { getJSON } from '../../lib/api'
import { client, useJSON } from '../../lib/queries'
import { act, batch } from '../act'
import { Chip, claimDrag, ClaimText, FitChip } from '../bits'
import { Detail } from '../Detail'
import { whyHere, type Judging } from '../judge'
import { matches, motifsOf, SORTS, SOURCE, useWorkbench, words, type Model } from '../model'
import { claimAction, correctClaim, goBack, holdClaim, renamed, splitByHand } from '../ops'
import { getWB, mark, setWB, useWB } from '../store'
import type { ClaimHit, Entry } from '../types'

const TAB_NAMES: Record<string, string> = { judge: '🎯 claims to judge', sure: '✅ sure', misfits: '🚫 misfits', held: '⏸ held', today: '✨ to shape', find: '🔎 claims', pairs: '🔗 pairs', singles: '1️⃣ singles', proposals: '💡 proposals', claims: '📥 unfiled' }

export function ClaimView({ claim, j, check }: { claim: { claim: string; src?: string; ref?: string } | null; j: Judging | null; check?: { left: number } }) {
  const { model: m } = useWorkbench()
  const back = useWB((s) => s.back)
  const held = m?.data.held ?? []
  if (!m) return null
  if (!claim) {
    return <div className="welcome"><div className="hero">🔍</div><p>Click a claim’s 🔍 or its #id (or a claim in the search results) to open it here: where it came from, every motif it’s in, and where to move it.</p></div>
  }
  const c = claim.claim
  const ins = motifsOf(m, c)
  const first = ins[0], rec = first?.claims.find((x) => x.claim === c)
  const src = rec?.source || claim.src || ''
  const why = j ? whyHere(m, j, c) : ''
  return (
    <div className={check ? 'checking' : ''}>
      {!check && back && <button className="btn back" title="back to the list, where you were (or your browser's back)"
        onClick={() => (history.state?.wb === 'claim' ? history.back() : goBack())}>← back to {TAB_NAMES[back.tab] ?? 'the list'}</button>}
      {check && (
        <div className="checkbar">
          <span className="faint">{check.left} claim{check.left === 1 ? '' : 's'} to judge{why ? ' · here for: ' + why : ''} · judge it whole: tick each motif that fits, take out the rest, add what's missing, then ✓ all fit</span>
          <span className="checkbtns">
            <button className="btn" title="the claim before" onClick={() => verdict('prev', j)}>◀ <kbd>←</kbd></button>
            <button className="btn yes" title="every motif left fits: tick them all and go on" onClick={() => verdict('allyes', j)}>✓ all fit, next <kbd>Y</kbd></button>
            <button className="btn" title="keep it aside to look at later: out of the claims to judge, into ⏸ held" onClick={() => verdict('hold', j)}>⏸ hold <kbd>H</kbd></button>
            <button className="btn" title="leave it for now" onClick={() => verdict('next', j)}>next ▶ <kbd>→</kbd></button>
          </span>
        </div>
      )}
      <div className="inspect" data-drop="claim" data-claim={c} data-src={src} data-ref={rec?.ref || claim.ref || ''}>
        <blockquote className="claim big" {...claimDrag({ claim: c, source: src, ref: rec?.ref || claim.ref }, first?.id ?? '')}>
          <BigText claim={c} />
          <span className="meta">{rec ? '#' + rec.id + ' · ' : ''}{SOURCE[src] || src} · drag me onto a motif ·{' '}
            <button className="mini" title="correct the wording (our summary, not the source)" onClick={() => document.querySelector<HTMLElement>('.bigtext')?.click()}>✎ correct wording</button>{' '}
            <button className="mini" title="it tells several things: split it into one claim per telling (the original stays as the telling)" onClick={(ev) => void splitByHand(c, ev.currentTarget)}>✂️ split</button></span>
        </blockquote>
        {(rec?.variants ?? []).length > 0 && <p className="faint">≡ also told as: {rec!.variants!.map((v) => '“' + v + '”').join(' · ')}</p>}
        <h3>🧩 all its motifs <i>{ins.length}</i> <span className="faint">take one away with ✕, add more below or by dropping a motif here</span></h3>
        {ins.map((e) => <MotifRow key={e.id} m={m} e={e} claim={c} j={j} />)}
        {!ins.length && <p className="faint">📥 not in any motif</p>}
        <Better m={m} claim={c} j={j} />
        <Sources claim={c} />
        <h3>➕ add it to another motif</h3>
        <AddTo m={m} claim={claim} ins={ins} />
        <div className="sbtns clacts">
          <button className="btn" onClick={(ev) => void claimAction(claim, 'new', '', ev.currentTarget)}>✨ new motif with it</button>
          {ins.length > 0 && <button className="btn" onClick={(ev) => void claimAction(claim, 'nomotif', '', ev.currentTarget)}>∅ no motif</button>}
          {held.includes(c) ? <button className="btn" title="on hold: back into the queues" onClick={() => void holdClaim(c, false)}>⏸ on hold · ▶ take off</button>
            : ins.length > 0 && !check ? <button className="btn" title="keep it aside to look at later: out of the queues, into ⏸ held" onClick={() => void holdClaim(c, true)}>⏸ hold</button> : null}
        </div>
        <SimilarFold claim={c} filed={ins.length > 0} />
      </div>
    </div>
  )
}

/** 📜 where it came from, under the motifs (Oct 22: above them, on a laptop the motifs being judged sat below the fold
    on every card): a few lines, and the rest a press away; folded again for the next claim */
function Sources({ claim }: { claim: string }) {
  // opened once, it stays open for the next claims (Oct 22, the person: "I can't expand this window to read it better")
  const open = useWB((s) => s.sourcesOpen)
  const flip = () => setWB({ sourcesOpen: !open })
  return (
    <>
      <h3>📜 where it came from <button className="mini" onClick={flip}>{open ? '▴ shorter' : '▾ all of it'}</button></h3>
      <div className={'cl-detail' + (open ? ' open' : '')}><Detail claim={claim} /></div>
      <button className="more-bar" onClick={flip}>{open ? '▴ show it shorter' : '▾ read all of where it came from'}</button>
    </>
  )
}

/** The claim's words: click to correct them in place (Enter saves, Esc puts them back) */
function BigText({ claim }: { claim: string }) {
  const [editing, setEditing] = useState(false)
  const [v, setV] = useState(claim)
  const done = useRef(false)
  useEffect(() => { setEditing(false); setV(claim) }, [claim])
  if (!editing) return <span className="bigtext" title="click to correct the wording" onClick={() => { done.current = false; setV(claim); setEditing(true) }}>{claim}</span>
  const finish = (save: boolean) => {
    if (done.current) return
    done.current = true
    setEditing(false)
    if (save) void correctClaim(claim, v.trim())
  }
  return (
    <span className="bigtext">
      <textarea className="claim-in" rows={3} autoFocus value={v} aria-label="the claim's wording" onFocus={(e) => e.target.select()}
        onChange={(e) => setV(e.target.value)} onBlur={() => finish(true)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); finish(true) } if (e.key === 'Escape') { e.preventDefault(); finish(false) } }} />
      <span className="faint">Enter saves · Esc cancels</span>
    </span>
  )
}

function MotifRow({ m, e, claim, j }: { m: Model; e: Entry; claim: string; j: Judging | null }) {
  const r = e.claims.find((x) => x.claim === claim)!
  const doubt = !!j?.doubts(claim, e.id)
  const fit = j?.fits[claim + '|' + e.id]
  const [carry, setCarry] = useState((r.carrying ?? []).join('; '))
  useEffect(() => setCarry((r.carrying ?? []).join('; ')), [r.carrying])
  const saveCarry = () => { if (carry.trim() !== (r.carrying ?? []).join('; ')) void act({ action: 'carrying', claim, id: e.id, text: carry.trim() }, carry.trim() ? '🗣 carrying words saved' : '🗣 taken away') }
  return (
    <div className={'motifrow' + (r.checked === 'yes' && !doubt ? ' fits' : '') + (doubt ? ' doubt' : '')}>
      <Chip id={e.id} />
      <span className="sbtns">
        {(r.checked !== 'yes' || doubt) && fit != null && <FitChip fit={fit} unsure={j?.unsure.has(claim + '|' + e.id)} />}
        {doubt ? <button className="btn yes" title="you said it fits; the model now doubts it: does it still?" onClick={() => void claimAction({ claim }, 'check', e.id)}>🧐 ✓ still fits</button>
          : r.checked === 'yes' ? <span className="fits">✓ fits</span>
            : <button className="btn yes" title="it belongs here" onClick={() => void claimAction({ claim }, 'check', e.id)}>✓ fits</button>}
        <button className="btn no" title="take it out of this motif" onClick={() => void claimAction({ claim }, 'unfile', e.id)}>✕ take out</button>
      </span>
      {e.note ? <span className="mnote">{e.note}</span> : <span className="mnote faint">no note yet</span>}
      <label className="carry" title="the tellers' own words that carry this motif here (“religion of peace”): saves when you click away or press Enter; ; between phrases">
        🗣 <input value={carry} placeholder="carrying words, if the tellers have a phrase for it" onChange={(ev) => setCarry(ev.target.value)} onBlur={saveCarry}
          onKeyDown={(ev) => { if (ev.key === 'Enter') { ev.preventDefault(); (ev.target as HTMLElement).blur() } }} /></label>
      {m && null}
    </div>
  )
}

/** Where a weakly filed claim might belong instead: the model's best fits among your motifs it isn't in */
function Better({ m, claim, j }: { m: Model; claim: string; j: Judging | null }) {
  const { data } = useJSON<{ id: string; fit: number }[]>('/better.json', { claim }, { staleTime: Infinity, refetchOnWindowFocus: false })
  const rejected = useWB((s) => s.rejected)
  const ins = motifsOf(m, claim), inIds = new Set(ins.map((e) => e.id))
  const shown = (data ?? []).filter((b) => m.by[b.id] && !inIds.has(b.id) && !rejected.includes(claim + '|' + b.id))
  if (!shown.length) return null
  const from = j?.waiting(claim).find((id) => j.doubts(claim, id))
  return (
    <div className="cl-better">
      <h3>🤖 might fit better <span className="faint">your motifs it isn't in, by fit: ＋ adds it there, then ✕ the weak one above</span></h3>
      {shown.map((b) => (
        <div key={b.id} className="motifrow better">
          <Chip id={b.id} />
          <span className="sbtns">
            <FitChip fit={b.fit} />
            {from && <button className="btn" data-move="1" title={`move it: out of “${m.by[from].name}” (which the model doubts), into this one`} onClick={() => {
              mark('decided', claim + '|' + from)
              void batch([{ action: 'also', claim, source: from, target: b.id }, { action: 'check', claim, id: from, answer: 'no' }], `⇄ moved to “${m.by[b.id].name}”`)
            }}>⇄ move</button>}
            <button className="btn yes" title="file it here too (then ✕ the weak one if it doesn't belong there)" onClick={() => {
              const first = motifsOf(m, claim)[0]
              void act(first ? { action: 'also', claim, source: first.id, target: b.id } : { action: 'file', claim, id: b.id, source: '' }, `＋ filed in “${m.by[b.id].name}”`)
            }}>＋ add</button>
            <button className="mini" title="not this motif: don't suggest it again" onClick={() => { mark('rejected', claim + '|' + b.id); void act({ action: 'reject', claim, id: b.id }, `✕ won’t suggest “${m.by[b.id].name}” again`) }}>✕</button>
          </span>
          {m.by[b.id].note ? <span className="mnote">{m.by[b.id].note}</span> : <span className="mnote faint">no note yet</span>}
        </div>
      ))}
    </div>
  )
}

/** Find a motif to add the claim to (＋ first, where the eye lands), or start a new one named what was typed */
function AddTo({ m, claim, ins }: { m: Model; claim: { claim: string; src?: string; ref?: string }; ins: Entry[] }) {
  const q = useWB((s) => s.claimQ)
  const make = useRef<HTMLButtonElement>(null)
  const w = words(q), inIds = new Set(ins.map((e) => e.id))
  const found = w.length ? m.data.entries.filter((e) => !inIds.has(e.id) && matches(e, w)).sort(SORTS.size).slice(0, 12) : []
  const typed = q.trim(), taken = m.data.entries.some((e) => e.name.toLowerCase() === typed.toLowerCase())
  return (
    <>
      <label className="addsearch">🔎 <input type="search" placeholder="find a motif" value={q} autoComplete="off" onChange={(e) => setWB({ claimQ: e.target.value })}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); make.current?.focus() } }} /></label>
      <div className="cl-results">
        {!w.length ? <p className="faint">type to find a motif, or drag the claim onto one</p> : <>
          {found.map((e) => <div key={e.id} className="sug pick"><span className="pickbtns"><button className="btn yes" title="file it here too"
            onClick={() => { setWB({ claimQ: '' }); void claimAction(claim, 'add', e.id) }}>＋ add</button></span><Chip id={e.id} /></div>)}
          {!found.length && <p className="faint">🦗 no motif matches</p>}
          {!taken && <button ref={make} className="btn yes newnamed" onClick={() => void claimAction(claim, 'newnamed')}>✨ new motif “{typed}” with it</button>}
        </>}
      </div>
    </>
  )
}

/** ≡ claims like this one, folded until asked for (Oct 22: it was the heaviest thing a card asked the checker for, and
    sat at the bottom of every card, slowing the save before it); opened once, it stays open for the next cards */
function SimilarFold({ claim, filed }: { claim: string; filed: boolean }) {
  const open = useWB((s) => s.similarOpen)
  return (
    <details className="similar-fold" open={open} onToggle={(e) => { const o = (e.currentTarget as HTMLDetailsElement).open; if (o !== open) setWB({ similarOpen: o }) }}>
      <summary><h3>≡ claims like this one <span className="faint">closest in meaning; fold one in if it's the same claim told another way</span></h3></summary>
      {open && <Similar claim={claim} filed={filed} />}
    </details>
  )
}

/** Claims closest in meaning: fold that one into this one (if this one is filed), or this one into that one */
function Similar({ claim, filed }: { claim: string; filed: boolean }) {
  const { data, error } = useJSON<ClaimHit[]>('/claim-similar.json', { claim }, { staleTime: Infinity, refetchOnWindowFocus: false })
  if (error) return <ul className="claims"><li className="faint">😬 couldn’t compare (are the embeddings up?)</li></ul>
  if (!data) return <ul className="claims"><li className="faint">⏳</li></ul>
  return (
    <ul className="claims">
      {data.map((x) => (
        <li key={x.claim} className={'claim mini' + (x.motifs.length ? '' : ' unfiled')} {...claimDrag(x, x.motifs[0]?.id ?? '')}>
          <ClaimText claim={x.claim} className="ctext" />
          <span className="meta">{x.motifs.length ? <>in {x.motifs.map((y) => <Chip key={y.id} id={y.id} />)}</> : <>📥 not filed · {SOURCE[x.source] || x.source || ''}</>} · alike {x.score?.toFixed(2)}</span>
          <span className="cbtns show">
            {filed ? <button className="mini" title="the same claim: fold it into this one" onClick={() => void act({ action: 'same_claim', variant: x.claim, canonical: claim }, '≡ folded into this claim')}>≡ same claim</button>
              : x.motifs.length ? <button className="mini" title="the same claim: fold this one into it" onClick={async () => {
                if (await act({ action: 'same_claim', variant: claim, canonical: x.claim }, '≡ folded into the other claim')) renamed(claim, x.claim)
              }}>≡ same (keep that)</button> : null}
          </span>
        </li>
      ))}
      {!data.length && <li className="faint">🦗 nothing close</li>}
    </ul>
  )
}

// ---------- the claims to judge: where you are, and the verdicts ----------
/** ◀ goes back along the claims you've seen (even one finished, which has left the list); ▶ on; ✓ all fit; ⏸ hold */
export function verdict(answer: 'next' | 'prev' | 'hold' | 'allyes', j: Judging | null) {
  const s = getWB()
  const x = currentCheck(j)
  if (!x || !j) return
  const trail = [...s.checkTrail], forward = [...s.checkForward]
  if (answer === 'next') {
    if (s.checkBack) return setWB({ checkBack: forward.pop() ?? null, checkForward: forward }) // stepping forward again through the trail
    trail.push(x.claim)
    // still to check: step past it; finished: the next claim has slid into its place
    const at = j.items.findIndex((i) => i.claim === x.claim)
    return setWB({ checkTrail: trail, checkAt: at >= 0 ? at + 1 : s.checkAt, checkHere: null })
  }
  if (answer === 'prev') {
    if (!trail.length) return toast('◀ that’s the first one you’ve seen')
    if (s.checkBack) forward.push(s.checkBack)
    return setWB({ checkForward: forward, checkBack: trail.pop()!, checkTrail: trail })
  }
  const step = () => s.checkBack ? setWB({ checkBack: forward.pop() ?? null, checkForward: forward }) : setWB({ checkTrail: [...trail, x.claim], checkHere: null })
  if (answer === 'hold') { // kept aside: the next claim slides into its place
    step()
    return void holdClaim(x.claim, true)
  }
  // every motif still waiting fits: the new filings and the doubted ones alike (marked answered first, so the next
  // claim slides in at once)
  const left = j.waiting(x.claim)
  left.forEach((id) => mark('decided', x.claim + '|' + id))
  step()
  if (!left.length) return
  void batch(left.map((id) => ({ action: 'check', claim: x.claim, id, answer: 'yes' })), `✓ ${left.length} motif${left.length === 1 ? '' : 's'} fit`)
}

/** The claim the check bar is on: one stepped back to, the one pinned there, or the next waiting */
export function currentCheck(j: Judging | null): { claim: string; source: string } | null {
  const s = getWB()
  if (!j) return null
  if (s.checkBack) return { claim: s.checkBack, source: '' }
  if (s.checkHere) return s.checkHere
  const x = j.items[s.checkAt % Math.max(j.items.length, 1)]
  return x ? { claim: x.claim, source: x.source } : null
}

export function JudgeTab({ j }: { j: Judging | null }) {
  const back = useWB((s) => s.checkBack), here = useWB((s) => s.checkHere)
  useWB((s) => s.checkAt)
  const x = currentCheck(j)
  // The claim on screen stays until next ▶ or ✓ all fit: ticking or taking out its last motif, adding one, or
  // rewording it leaves it here for the next edit
  useEffect(() => {
    if (x && !back && !here) setWB({ checkHere: x })
  // oxlint-disable-next-line react-hooks/exhaustive-deps -- by the claim's words: x is a fresh object every render
  }, [x?.claim, back, here])
  // The next two claims' sources and better fits, read while this one is judged, so each card comes up whole
  useEffect(() => {
    if (!j || !x) return
    const at = j.items.findIndex((i) => i.claim === x.claim)
    for (const next of j.items.slice(at + 1, at + 3)) {
      void client.prefetchQuery({ queryKey: ['/claim-detail.json', { claim: next.claim }], queryFn: () => getJSON('/claim-detail.json', { claim: next.claim }), staleTime: 60_000 })
      void client.prefetchQuery({ queryKey: ['/better.json', { claim: next.claim }], queryFn: () => getJSON('/better.json', { claim: next.claim }), staleTime: Infinity })
    }
  // oxlint-disable-next-line react-hooks/exhaustive-deps -- by the claim's words: x is a fresh object every render
  }, [j, x?.claim])
  useEffect(() => { // the keys, while judging (not while typing)
    const key = (ev: KeyboardEvent) => {
      const t = ev.target as HTMLElement | null
      if (t?.closest?.('input, textarea, select') || ev.ctrlKey || ev.metaKey || ev.altKey) return
      const k = ({ y: 'allyes', h: 'hold', arrowright: 'next', j: 'next', s: 'next', arrowleft: 'prev', k: 'prev' } as const)[ev.key.toLowerCase() as 'y']
      if (k) { ev.preventDefault(); verdict(k, j); return }
      const move = ev.key.toLowerCase() === 'm' && document.querySelector<HTMLElement>('.cl-better [data-move]') // m: out of the doubted motif, into its best fit
      if (move) { ev.preventDefault(); move.click() }
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [j])
  if (!j) return <p className="faint">⏳ thinking…</p>
  if (!x) return <div className="welcome"><div className="hero">🎉</div><p>No claim waiting for you.</p></div>
  return <ClaimView claim={{ claim: x.claim, src: x.source }} j={j} check={{ left: j.items.length }} />
}
