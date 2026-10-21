// 💡 The model's proposals (each one change: ✓ does it, undoable like doing it by hand; ✕ and it won't suggest it
// again), ✂️ the claim organizer's splits, 🧩 a big motif's tellings; and after a ✕, what was wrong with it, in a line
import { useState, useSyncExternalStore } from 'react'
import { toast } from '../../components/Feedback'
import { postJSON } from '../../lib/api'
import { act } from '../act'
import { Chip, FitChip, WordDiff } from '../bits'
import { useQueue } from '../judge'
import { useWorkbench, type Model } from '../model'
import { mark, setWB, useWB } from '../store'
import type { Action, Proposal, SplitProposal, TellingMotif } from '../types'

// ---------- after a ✕: what was wrong, kept with the draft (app/analysis/critiques.py); not an undo step ----------
let why: { id: string; text: React.ReactNode; how: string } | null = null
const whyListeners = new Set<() => void>()
function askWhy(id: string, text: React.ReactNode, how: string) {
  why = { id, text, how }
  whyListeners.forEach((l) => l())
}
export function WhyBar() {
  const w = useSyncExternalStore((l) => { whyListeners.add(l); return () => whyListeners.delete(l) }, () => why)
  const [v, setV] = useState('')
  if (!w) return null
  const close = () => { why = null; setV(''); whyListeners.forEach((l) => l()) }
  return (
    <div className="why">
      <span>{w.how === 'rejected' ? '✕' : '🌱'} {w.how}: <b>{w.text}</b></span>
      <input autoFocus placeholder="what was wrong with it? (optional, Enter keeps it: it teaches the proposer)" aria-label="what was wrong" value={v}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={async (e) => {
          if (e.key === 'Escape') return close()
          if (e.key !== 'Enter' || !v.trim()) return
          const ok = await postJSON('/critique', { proposal: w.id, why: v.trim() }).then(() => true, () => false)
          close()
          toast(ok ? '📝 kept what was wrong' : '😬 couldn’t keep it', !ok)
        }} />
      <button className="mini" title="skip" onClick={close}>✕</button>
    </div>
  )
}

/** A proposal as a sentence; a typo fix shows the words it changes; a new motif its claims, each ticked */
function ProposalText({ p, m, ticks }: { p: Proposal; m: Model; ticks?: { on: boolean[]; set: (i: number, v: boolean) => void } }) {
  const a = p.args
  const ch = (id: string) => <Chip id={id} />
  switch (p.kind) {
    case 'split': return <>✂️ split “{a.claim}”</>
    case 'rename': return <>✏️ rename {ch(a.id)} to “<WordDiff a={a.from} b={a.to} />”</>
    case 'note': return <>📝 fix the note of {ch(a.id)}: “<WordDiff a={a.from} b={a.to} />”</>
    case 'parent': return <>↳ {ch(a.id)} rests on {ch(a.parent)}</>
    case 'relate': return <>↔ {ch(a.a)} and {ch(a.b)} are related</>
    case 'merge': return <>⤵ {ch(a.a)} is the same motif as {ch(a.b)}: merge it in</>
    case 'unrelate': return <>✂️ {ch(a.a)} and {ch(a.b)} aren't related: take the link away</>
    case 'unparent': return <>✂️ {ch(a.id)} doesn't rest on {ch(a.parent)}: take the link away</>
    case 'genre': return <>🎭 {ch(a.id)} is {a.genre}</>
    case 'new_motif': return <>✨ a new motif “{a.name}”{a.genre ? ` 🎭 ${a.genre}` : ''}: {a.note}
      {ticks && <ul className="propclaims">{(a.claims as { claim: string; in?: string }[]).map((c, i) => (
        <li key={i}><label><input type="checkbox" checked={ticks.on[i]} title="untick a claim that doesn't fit: ✓ files only the ticked ones" onChange={(e) => ticks.set(i, e.target.checked)} /> {c.claim}</label>
          {c.in && <span className="faint"> (now in {ch(c.in)})</span>}</li>))}</ul>}</>
    case 'new_group': return <>🫧 a new group “{a.name}”: {(a.members as string[]).map((x) => <Chip key={x} id={x} />)}</>
    case 'group': return <>📁 put {ch(a.id)} in {m.data.groups.find((g) => g.id === a.group)?.name ?? a.group}</>
    default: return <>{p.kind}</>
  }
}

/** A rests-on or merge proposal the other way round (⇅): agreed they belong together, not on the direction */
const flipped = (a: Action): Action => a.action === 'parent' ? { ...a, id: a.parent, parent: a.id } : { ...a, source: a.target, target: a.source }

export async function decideProposals(m: Model, ps: Proposal[], how: 'yes' | 'no' | 'seed' | 'flip', kept?: Record<string, boolean[]>) {
  if (!ps.length) return
  const steps: Action[] = ps.map((p) => how === 'no' ? { action: 'proposal_reject', proposal: p.id }
    : how === 'flip' ? { ...flipped(p.do), proposal: p.id }
      : p.kind === 'new_motif' ? { ...p.do, proposal: p.id, claims: how === 'seed' ? [] : (p.do.claims as unknown[]).filter((_, i) => kept?.[p.id]?.[i] ?? true) }
        : { ...p.do, proposal: p.id })
  ps.forEach((p) => mark('decided', 'p:' + p.id)) // off the lists in place
  const ok = await act(steps.length === 1 ? steps[0] : { action: 'batch', steps },
    `${how === 'flip' ? '⇅ approved the other way round:' : how === 'seed' ? '🌱 kept as a seed:' : how === 'yes' ? '✓ approved' : '✕ rejected'} ${ps.length} proposal${ps.length === 1 ? '' : 's'}`)
  const p0 = ps[0], trimmed = how !== 'no' && p0.kind === 'new_motif' && (steps[0].claims as unknown[]).length < (p0.do.claims as unknown[]).length
  if (ok && ps.length === 1 && (how === 'no' || trimmed)) {
    askWhy(p0.id, <ProposalText p={p0} m={m} />, how === 'no' ? 'rejected' : (steps[0].claims as unknown[]).length ? 'kept, some claims left out' : 'kept as a seed')
  }
}

export function ProposalCard({ p, m, today, checked, onCheck }: { p: Proposal; m: Model; today?: boolean; checked?: boolean; onCheck?: (v: boolean) => void }) {
  const [ticks, setTicks] = useState<boolean[]>(() => (p.kind === 'new_motif' ? (p.args.claims as unknown[]).map(() => true) : []))
  const kept = { [p.id]: ticks }
  return (
    <div className="card prop">
      {today && <div className="today-why">💡 the model proposes</div>}
      <label className="propline">
        {onCheck && <input type="checkbox" checked={!!checked} onChange={(e) => onCheck(e.target.checked)} />}{' '}
        <ProposalText p={p} m={m} ticks={p.kind === 'new_motif' ? { on: ticks, set: (i, v) => setTicks(ticks.map((t, k) => (k === i ? v : t))) } : undefined} />
      </label>
      {p.fit != null && <FitChip fit={p.fit} title={`best fit: how likely you are to approve it, learned from your decisions${p.judge ? `; the judge's ${p.judge.score}/10${p.judge.reason ? `: ${p.judge.reason}` : ''}` : ''}`} />}
      <span className="sbtns">
        <button className="mini" title={p.kind === 'new_motif' ? 'make it, with the ticked claims' : 'approve: do it'} onClick={() => void decideProposals(m, [p], 'yes', kept)}>✓</button>
        {p.kind === 'new_motif' && <button className="mini" title="keep the motif as a seed, with none of these claims: the filing can find it for the next telling" onClick={() => void decideProposals(m, [p], 'seed')}>🌱</button>}
        {(p.kind === 'parent' || p.kind === 'merge') && <button className="mini" title={p.kind === 'parent' ? 'yes, but the other way round: the second rests on the first' : 'yes, but the other way round: merge the second into the first'} onClick={() => void decideProposals(m, [p], 'flip')}>⇅</button>}
        <button className="mini" title="reject: don't suggest it again" onClick={() => void decideProposals(m, [p], 'no')}>✕</button>
      </span>
      {p.reason && <div className="faint">🤖 {p.reason}</div>}
    </div>
  )
}

export function ProposalsTab() {
  const { model: m } = useWorkbench()
  const q = useQueue<Proposal[]>('proposals')
  const decided = useWB((s) => s.decided)
  const [ticked, setTicked] = useState<Record<string, boolean>>({})
  if (q.error) return <p className="faint">😬 {(q.error as Error).message}</p>
  if (!m || !q.data) return <p className="faint">⏳ thinking…</p>
  const items = q.data.filter((p) => !decided.includes('p:' + p.id) && Object.values(p.do).every((v) => typeof v !== 'string' || !/^M\d+$/.test(v) || m.by[v]))
  if (!items.length) return <div className="welcome"><div className="hero">🎉</div><p>No proposals waiting. The proposer runs from <code>scripts/propose_motif_fixes.py</code>.</p></div>
  const likely = items.filter((p) => !p.unlikely), unlikely = items.filter((p) => p.unlikely)
  const isTicked = (p: Proposal) => ticked[p.id] ?? !!p.unlikely // the unlikely ones come ticked, to reject
  const card = (p: Proposal) => <ProposalCard key={p.id} p={p} m={m} checked={isTicked(p)} onCheck={(v) => setTicked({ ...ticked, [p.id]: v })} />
  return <>
    <p className="faint">💡 The model's suggestions, each one change. ✓ does it (undoable, like doing it by hand); ✕ and it won't suggest it again. 🎯 is the best fit: how likely you are to approve it, learned from your decisions (best first).</p>
    <div className="sbtns propbar">
      <label><input type="checkbox" checked={likely.length > 0 && likely.every(isTicked)} onChange={(e) => setTicked({ ...ticked, ...Object.fromEntries(likely.map((p) => [p.id, e.target.checked])) })} /> all</label>
      <button className="btn" onClick={() => void decideProposals(m, likely.filter(isTicked), 'yes')}>✓ approve ticked</button>
      <button className="btn no" onClick={() => void decideProposals(m, likely.filter(isTicked), 'no')}>✕ reject ticked</button>
    </div>
    {likely.map(card)}
    {unlikely.length > 0 && <details className="propfold"><summary>🤖 probably not: {unlikely.length} you'd likely reject</summary>
      <p className="faint">Most like these you've rejected. Skim them, untick any worth keeping, then <button className="btn no" onClick={() => void decideProposals(m, unlikely.filter(isTicked), 'no')}>✕ reject the ticked</button></p>
      {unlikely.map(card)}</details>}
  </>
}

/** ✂️ Claims whose posts seem to tell several things: a claim per telling, each editable (emptied, it drops) */
export function SplitsTab() {
  const { model: m } = useWorkbench()
  const q = useQueue<SplitProposal[]>('splits')
  const decided = useWB((s) => s.decided)
  if (q.error) return <p className="faint">😬 {(q.error as Error).message}</p>
  if (!m || !q.data) return <p className="faint">⏳ thinking…</p>
  const items = q.data.filter((p) => !decided.includes('s:' + p.id))
  if (!items.length) return <div className="welcome"><div className="hero">✂️</div><p>No splits proposed yet. The claim organizer proposes them; you can also split a claim yourself with ✂️ in its pane.</p></div>
  return <>
    <p className="faint">✂️ Claims whose posts seem to tell several things. Each card splits one into a claim per telling: reword any (empty one drops it), then ✂️ split. The new claims are filed at the next hourly run and reach 🎯; the original stays as the telling. ✕ keeps it whole. Neither teaches the filer “wrong motif”.</p>
    {items.map((p) => <SplitCard key={p.id} m={m} p={p} />)}
  </>
}

function SplitCard({ m, p }: { m: Model; p: SplitProposal }) {
  const [kids, setKids] = useState(p.children.map((c) => c.claim))
  const a = p.args, triggers = Object.keys(a.triggers ?? {})
  const decide = async (yes: boolean) => {
    const children = kids.map((k) => k.trim()).filter(Boolean)
    if (yes && !children.length) return toast('✂️ no claims left to split into', true)
    mark('decided', 's:' + p.id)
    const ok = await act(yes ? { action: 'split', proposal: p.id, children } : { action: 'split_reject', proposal: p.id }, yes ? `✂️ split into ${children.length}` : '✕ kept whole')
    if (!ok) return mark('decided', 's:' + p.id, false)
    const edited = yes && children.join('\n') !== p.children.map((c) => c.claim).join('\n')
    if (!yes || edited) askWhy(p.id, <>✂️ split “{a.claim}”</>, yes ? 'split, reworded' : 'rejected')
  }
  return (
    <div className="card splitcard">
      <p className="split-claim">{a.claim}</p>
      <div className="faint">now in {p.filings.length ? p.filings.map((f) => m.by[f.id] ? <Chip key={f.id} id={f.id} /> : <span key={f.id}>{f.name} </span>) : '—'} · {a.posts ?? 0} posts read{triggers.length ? ' · looked at for: ' + triggers.join(', ') : ''}</div>
      <ol className="children">{p.children.map((c, i) => (
        <li key={i}><textarea rows={2} aria-label={`new claim ${i + 1}`} value={kids[i]} onChange={(e) => setKids(kids.map((k, j) => (j === i ? e.target.value : k)))} />
          <span className="faint">{c.names?.length ? 'tells ' + c.names.join(', ') + ' · ' : ''}{c.posts} post{c.posts === 1 ? '' : 's'}</span>
          {(c.texts ?? []).length > 0 && <details className="childposts"><summary>its posts</summary><ul>{c.texts!.map((t, k) => <li key={k}>{t}</li>)}</ul></details>}</li>
      ))}</ol>
      <span className="sbtns"><button className="btn yes" title="split it into these claims (undoable)" onClick={() => void decide(true)}>✂️ split it so</button>
        <button className="btn no" title="it's one telling: keep it whole" onClick={() => void decide(false)}>✕ keep it whole</button></span>
      {p.reason && <div className="faint">🤖 {p.reason}</div>}
    </div>
  )
}

/** 🧩 A big motif opened into the stories told inside it (Pandora): each made a motif of its own, resting on it */
export function TellingsTab() {
  const { model: m } = useWorkbench()
  const q = useQueue<TellingMotif[]>('tellings')
  const decided = useWB((s) => s.decided)
  const forId = useWB((s) => s.tellingsFor)
  if (q.error) return <p className="faint">😬 {(q.error as Error).message}</p>
  if (!m || !q.data) return <p className="faint">⏳ thinking…</p>
  const motifs = q.data.filter((x) => m.by[x.id]).map((x) => ({ ...x, tellings: x.tellings.filter((t) => !decided.includes('t:' + t.key)) })).filter((x) => x.tellings.length)
  if (!motifs.length) return <div className="welcome"><div className="hero">🧩</div><p>No tellings waiting.</p></div>
  const first = forId && motifs.some((x) => x.id === forId) ? forId : motifs[0].id
  return <>
    <p className="faint">🧩 Your biggest motifs, each opened into the different stories told inside it (Gemma's drafts). Make a good one a motif of its own: it rests on the broader one, and its ticked claims move there (untick “take them out” to keep them in both). Edit the name and note first if they're off. ✕ if it isn't a telling. Neither teaches the filer “wrong motif”.</p>
    {motifs.map((x) => (
      <details key={x.id} className="tmotif" open={x.id === first} ref={(el) => { if (el && x.id === forId) { el.scrollIntoView({ block: 'start' }); setWB({ tellingsFor: null }) } }}>
        <summary><Chip id={x.id} /> <b>{x.tellings.length}</b> telling{x.tellings.length === 1 ? '' : 's'} <span className="faint">of {x.claims} claims</span></summary>
        {x.note && <p className="faint">{x.note}</p>}
        {x.tellings.map((t) => <TellingCard key={t.key} t={t} parent={x.id} parentName={x.name} />)}
      </details>
    ))}
  </>
}

function TellingCard({ t, parent, parentName }: { t: TellingMotif['tellings'][number]; parent: string; parentName: string }) {
  const [name, setName] = useState(t.name)
  const [note, setNote] = useState(t.note)
  const [ticks, setTicks] = useState(t.claims.map(() => true))
  const [move, setMove] = useState(true)
  const decide = async (how: 'yes' | 'seed' | 'no') => {
    const claims = how === 'seed' ? [] : t.claims.filter((_, i) => ticks[i])
    if (how === 'yes' && !claims.length) return toast('🧩 tick a claim, or keep it as a 🌱 seed', true)
    mark('decided', 't:' + t.key)
    const n = name.trim(), nt = note.trim()
    const ok = await act(how === 'no' ? { action: 'telling_reject', key: t.key } : { action: 'telling', key: t.key, parent, name: n, note: nt, claims, move,
      ...(n !== t.name || nt !== t.note ? { draft: { name: t.name, note: t.note } } : {}) },
    how === 'no' ? '✕ not a telling' : `🧩 “${n}” made a motif${claims.length ? `, ${claims.length} claim${claims.length === 1 ? '' : 's'}` : ' (a seed)'}`, ['tellings'])
    if (!ok) mark('decided', 't:' + t.key, false)
    setWB({ tellingsFor: parent })
  }
  return (
    <div className="card motiftelling">
      <input className="tname" value={name} aria-label="its name" onChange={(e) => setName(e.target.value)} />
      <textarea className="tnote" rows={2} value={note} aria-label="its note" onChange={(e) => setNote(e.target.value)} />
      <ul className="propclaims">{t.claims.map((c, i) => <li key={i}><label><input type="checkbox" checked={ticks[i]} onChange={(e) => setTicks(ticks.map((x, k) => (k === i ? e.target.checked : x)))} /> {c}</label></li>)}</ul>
      <label className="faint"><input type="checkbox" checked={move} onChange={(e) => setMove(e.target.checked)} /> take them out of <Chip id={parent} /></label>
      <span className="sbtns">
        <button className="btn yes" title={`make it a motif of its own, resting on ${parentName}, with the ticked claims`} onClick={() => void decide('yes')}>✓ make it</button>
        <button className="btn" title="make it a motif with no claims yet: the filing can find it for the next telling" onClick={() => void decide('seed')}>🌱 seed</button>
        <button className="btn no" title="not a telling of its own" onClick={() => void decide('no')}>✕</button>
      </span>
    </div>
  )
}
