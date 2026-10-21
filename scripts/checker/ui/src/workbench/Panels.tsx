// The middle pane: the open motifs, one under another; a click on the left opens a motif in the outlined one, ⧉ adds
import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { ask, sure } from '../components/Feedback'
import { getJSON } from '../lib/api'
import { act, batch } from './act'
import { Chip, claimDrag, Told } from './bits'
import { Detail, motifText, sharedWith } from './Detail'
import { justDragged } from './DragLayer'
import { COLORS, isSingle, newCount, noteState, SOURCE, useWorkbench, type Model } from './model'
import { closePanel, copyText, openClaim, setTab } from './ops'
import { getWB, setWB, useWB } from './store'
import type { Claim, ClaimHit, Entry } from './types'

const NONE: string[] = [] // one empty selection for every panel (a new [] each read would never settle)

export function Panels() {
  const { model: m } = useWorkbench()
  const open = useWB((s) => s.open)
  const active = useWB((s) => s.active)
  if (!m) return <section className="pane work-pane"><p className="faint">⏳</p></section>
  const ids = open.filter((id) => m.by[id])
  return (
    <section className="pane work-pane" aria-label="Open motifs">
      {ids.length > 1 ? (
        <div className="work-head"><b>{ids.length}</b> open, one under another · a click opens in the outlined one; ⧉ adds another{' '}
          <button className="mini" onClick={() => setWB({ open: [], sel: {}, selLast: {} })}>✕ close all</button></div>
      ) : ids.length === 1 ? <div className="work-head">⧉ beside a motif opens another under this one, as many as you like · Shift-click in the list selects several</div> : null}
      <div className="panels" data-scroll>
        {ids.length ? ids.map((id, i) => <Panel key={id} m={m} e={m.by[id]} i={i} active={i === active && ids.length > 1} />) : (
          <div className="welcome"><div className="hero">👈 pick a motif</div>
            <p>Click one on the left to open it here; ⧉ opens another under it. <b>Shift-click</b> in the list selects a run of motifs, <b>Ctrl-click</b> one more, to drag together.</p>
            <p>Then drag: claims onto motifs, motifs onto motifs, motifs onto groups. Hover a target to see your choices. 🫳</p>
            <p className="faint">The inbox on the right has decisions waiting: 🎯 claims to judge, 🔗 pairs, 1️⃣ singles, 📥 unfiled claims.</p></div>
        )}
      </div>
    </section>
  )
}

function Panel({ m, e, i, active }: { m: Model; e: Entry; i: number; active: boolean }) {
  const kids = m.kids[e.id] ?? []
  const shared = sharedWith(m, e)
  const ns = noteState(e)
  const bm = e.by_model ?? {}
  const order = [...e.claims].sort((a, b) => Number(!!b.new) - Number(!!a.new))
  const sel = useWB((s) => s.sel[e.id] ?? NONE)
  const [extra, setExtra] = useState<{ kind: 'similar' | 'search'; q?: string; items: ClaimHit[] } | null>(null)
  const name = (id: string) => m.by[id]?.name ?? id
  const toggleSel = (claim: string, k: number, shift: boolean) => {
    const s = getWB(), now = s.sel[e.id] ?? [], last = s.selLast[e.id]
    let next: string[]
    if (shift && last != null) {
      const [lo, hi] = [Math.min(last, k), Math.max(last, k)]
      next = [...new Set([...now, ...order.slice(lo, hi + 1).map((c) => c.claim)])]
    } else next = now.includes(claim) ? now.filter((c) => c !== claim) : [...now, claim]
    setWB({ sel: { ...s.sel, [e.id]: next }, selLast: { ...s.selLast, [e.id]: k } })
  }
  const clearSel = () => setWB((s) => ({ sel: { ...s.sel, [e.id]: [] } }))
  const bulk = async (kind: string, anchor: Element) => {
    if (kind === 'unfile') await batch(sel.map((c) => ({ action: 'unfile', claim: c, id: e.id })), `🗑️ took ${sel.length} out`)
    if (kind === 'check') await batch(sel.map((c) => ({ action: 'check', claim: c, id: e.id, answer: 'yes' })), `✓ checked ${sel.length}`)
    if (kind === 'no_motif' && await sure(`No motif for ${sel.length} claims: out of every motif, for good?`, 'yes, do it', anchor)) {
      await batch(sel.map((c) => ({ action: 'no_motif', claim: c })), `∅ ${sel.length} claims: no motif`)
    }
    clearSel()
  }
  return (
    <article className={`panel p${i % COLORS}` + (active ? ' active' : '')} data-drop="motif" data-id={e.id} data-panel={i}
      onClickCapture={() => { if (getWB().active !== i) setWB({ active: i }) }}>
      <header className="phead">
        <div className="titlerow">
          <Title e={e} />
          <button className="btn close" title="close this motif" onClick={(ev) => { ev.stopPropagation(); closePanel(i) }}>✕</button>
        </div>
        <span className="pid">{e.id} · {e.claims.length} claim{e.claims.length === 1 ? '' : 's'}{e.curated ? ' · ✋ by hand' : ''}{e.first_seen ? ' · since ' + e.first_seen.slice(0, 10) : ''}<Told e={e} /></span>
        <div className="pbar">
          {e.done === 'done' ? <><span className="state done" title="you've looked over its claims; it can appear on the site">✅ Done</span>
            <button className="mini" title="it goes back to not done, and off the site" onClick={() => void act({ action: 'done', id: e.id, done: false }, `“${e.name}” is not done any more`)}>unmark done</button></>
            : e.done === 'new' ? <><span className="state new" title="marked done, but claims came in since; the site shows only the ones you saw">🆕 Done, {newCount(e)} new since</span>
              <button className="btn yes" title="you've looked at the new claims too" onClick={() => void act({ action: 'done', id: e.id, done: true }, `✅ “${e.name}” is done`)}>mark done again</button></>
              : <><span className="state todo" title="not looked over yet; it stays off the site">⏳ Not done yet</span>
                <button className="btn yes" title="you've looked over its claims: it can go on the site" onClick={() => void act({ action: 'done', id: e.id, done: true }, `✅ “${e.name}” is done`)}>mark as done</button></>}
          <span className="pbar-end">
            <button className="mini" title="rename" onClick={(ev) => void renameMotif(e, ev.currentTarget)}>✎ rename</button>
            {m.data.tellings_of?.[e.id] ? <button className="mini" title="the different stories told inside it, drafted by Gemma: make the good ones motifs of their own, resting on this one"
              onClick={() => { setWB({ tellingsFor: e.id }); setTab('tellings') }}>🧩 {m.data.tellings_of[e.id]} tellings</button> : null}
            <button className="mini" title="copy everything about it: name, note, groups, genre, what it rests on and what rests on it, related (with their notes) and every claim"
              onClick={() => void copyText(motifText(m, e))}>📋 copy</button>
            {(isSingle(m, e) || e.stands_alone) && <button className={'mini' + (e.stands_alone ? ' on' : '')} title="a single motif that needs no partner"
              onClick={() => void act({ action: 'stands_alone', id: e.id, alone: !e.stands_alone }, e.stands_alone ? '🧍 suggestions back on' : `🧍 “${e.name}” stands alone`)}>🧍 {e.stands_alone ? 'stands alone' : 'stands alone?'}</button>}
            <button className={'mini' + (e.watch ? ' on' : '')} title={e.watch ? 'a watch list: its claims are plain reports, filed again each week as the index grows (click to stop)' : 'make it a watch list, like Straight news: its claims are plain reports, filed again each week in case they are later told as a motif'}
              onClick={() => void act({ action: 'watch', id: e.id, on: !e.watch }, e.watch ? `👁 “${e.name}” isn't watched now` : `👁 “${e.name}” is a watch list`)}>👁 {e.watch ? 'watched' : 'watch?'}</button>
            <button className="mini" title="delete this motif (its claims aren't filed again)" onClick={async (ev) => {
              if (await sure(`Delete “${e.name}”?${e.claims.length ? ` Its ${e.claims.length} claims won't be filed again.` : ''}`, '🗑️ delete it', ev.currentTarget)) void act({ action: 'delete', id: e.id }, `🗑️ deleted “${e.name}”`)
            }}>🗑️</button>
          </span>
        </div>
      </header>
      <div className="rels">
        <span className="rlabel">📁 groups</span>
        <div className="rchips">
          {(e.groups ?? []).map((g) => {
            const guess = (bm.groups ?? []).includes(g)
            return <span key={g} className={'gtag' + (guess ? ' guess' : '')} title={guess ? "the model's guess: mark the motif done to keep it, ✕ to drop it" : undefined}>
              {guess ? '🤖' : '📁'} {m.data.groups.find((x) => x.id === g)?.name ?? g}
              <button className="x" title="out of this group" onClick={() => void act({ action: 'group_member', id: e.id, group: g, on: false }, '📁 out of the group')}>✕</button></span>
          })}
          <GroupPicker m={m} e={e} />
        </div>
        <span className="rlabel">🎭 genre</span>
        <div className="rchips">
          <select title="its genre" value={e.facets?.genre ?? ''} onChange={(ev) => void act({ action: 'facet', id: e.id, facet: 'genre', value: ev.target.value || null }, `🎭 ${ev.target.value || 'no genre'}`)}>
            <option value="">no genre</option>{(m.data.facets.genre ?? []).map((g) => <option key={g}>{g}</option>)}
          </select>
          {bm.genre && bm.genre === e.facets?.genre && <span className="ntag" title="mark the motif done to keep it, or pick another">🤖 the model's guess</span>}
        </div>
        <span className="rlabel" title="it only makes sense given these: a kind of them, or a case, argument or figure that tells them">↳ rests on</span>
        <div className="rchips">{e.parents.length ? e.parents.map((p) => <Chip key={p} id={p}><button className="x" title="doesn't rest on it"
          onClick={() => void act({ action: 'parent', id: e.id, parent: p, on: false }, `“${e.name}” no longer rests on “${name(p)}”`)}>✕</button></Chip>) : <span className="faint">—</span>}</div>
        <span className="rlabel">⤷ rest on it</span>
        <div className="rchips">{kids.length ? kids.map((k) => <Chip key={k} id={k}><button className="x" title="doesn't rest on this"
          onClick={() => void act({ action: 'parent', id: k, parent: e.id, on: false }, `“${name(k)}” no longer rests on “${e.name}”`)}>✕</button></Chip>) : <span className="faint">—</span>}</div>
        <span className="rlabel">↔ related</span>
        <div className="rchips">{e.related.length ? e.related.map((r) => (
          <span key={r} className="rel"><Chip id={r}><button className="x" title="not related" onClick={() => void act({ action: 'unrelate', a: e.id, b: r }, '↔ unrelated')}>✕</button></Chip>
            <RelNote m={m} a={e.id} b={r} /></span>
        )) : <span className="faint">—</span>}</div>
        {shared.length > 0 && <>
          <span className="rlabel">🤝 shares claims</span>
          <details className="rchips sharedfold"><summary>with {shared.length} motif{shared.length === 1 ? '' : 's'}</summary>
            {shared.map(([o, n]) => <Chip key={o} id={o}><b className="shared">{n}</b></Chip>)}</details>
        </>}
      </div>
      <Note e={e} ns={ns} />
      {sel.length > 0 && (
        <div className="selbar">☑️ <b>{sel.length}</b> selected: drag them anywhere, or
          <button className="btn" onClick={(ev) => void bulk('unfile', ev.currentTarget)}>🗑️ take out</button>
          <button className="btn" onClick={(ev) => void bulk('no_motif', ev.currentTarget)}>∅ no motif</button>
          <button className="btn" onClick={(ev) => void bulk('check', ev.currentTarget)}>✓ check all</button>
          <button className="btn" onClick={clearSel}>clear</button></div>
      )}
      <ul className="claims">
        {order.length ? order.map((c, k) => <ClaimRow key={c.claim} e={e} c={c} selected={sel.includes(c.claim)} onSelect={(shift) => toggleSel(c.claim, k, shift)} />)
          : <li className="empty">🫙 no claims: drag some here, or delete it</li>}
      </ul>
      <div className="more">
        <button className="btn" onClick={async () => setExtra({ kind: 'similar', items: await getJSON<ClaimHit[]>('/motif-similar.json', { id: e.id }).catch(() => []) })}>🧲 more like this</button>
        <ClaimSearch onResults={setExtra} />
      </div>
      {extra && <Extra m={m} e={e} x={extra} onClose={() => setExtra(null)} onDone={(claim) => setExtra({ ...extra, items: extra.items.filter((c) => c.claim !== claim) })} />}
    </article>
  )
}

async function renameMotif(e: Entry, anchor: Element) {
  const n = await ask('Rename the motif', e.name, { anchor })
  if (n && n !== e.name) void act({ action: 'rename', id: e.id, name: n }, `✎ renamed to “${n}”`)
}

/** The open motif's name edits where it is: click it, type, Enter or click away saves, Esc puts it back. It drags too */
function Title({ e }: { e: Entry }) {
  const [editing, setEditing] = useState(false)
  const [v, setV] = useState(e.name)
  const done = useRef(false)
  const finish = (save: boolean) => {
    if (done.current) return
    done.current = true
    setEditing(false)
    const n = v.trim()
    if (save && n && n !== e.name) void act({ action: 'rename', id: e.id, name: n }, `✎ renamed to “${n}”`)
  }
  if (editing) {
    return (
      <h2 className="pname"><input className="title-in" autoFocus value={v} aria-label="the motif's name" onFocus={(ev) => ev.target.select()}
        onChange={(ev) => setV(ev.target.value)} onBlur={() => finish(true)}
        onKeyDown={(ev) => { if (ev.key === 'Enter') { ev.preventDefault(); finish(true) } if (ev.key === 'Escape') { ev.preventDefault(); finish(false) } }} /></h2>
    )
  }
  return (
    <h2 className="pname" data-drag="motif" data-id={e.id} title="click to rename · drag onto another motif or a group"
      onClick={() => { if (justDragged()) return; done.current = false; setV(e.name); setEditing(true) }}>{e.name}</h2>
  )
}

/** Type to find a group and pick it: the motif goes in it as well; a new name and Enter makes a new group with it in */
function GroupPicker({ m, e }: { m: Model; e: Entry }) {
  const [v, setV] = useState('')
  const mine = e.groups ?? []
  const list = 'gl-' + e.id
  const add = (name: string, enter: boolean) => {
    const n = name.trim()
    if (!n) return
    const g = m.data.groups.find((x) => x.name.toLowerCase() === n.toLowerCase())
    if (g) {
      setV('')
      if (!mine.includes(g.id)) void act({ action: 'group_member', id: e.id, group: g.id }, `📁 in ${g.name} too`)
    } else if (enter) {
      setV('')
      void act({ action: 'group_new', name: n, id: e.id }, `📁 new group ${n}, with it in`)
    }
  }
  return (
    <>
      <input className="gadd" list={list} placeholder="＋ group… type to find" autoComplete="off" value={v}
        title="type to find a group and pick it to put it in as well (a motif can be in several); a new name and Enter makes a new group with it in"
        onChange={(ev) => {
          setV(ev.target.value)
          if ((ev.nativeEvent as InputEvent).inputType === 'insertReplacementText' || !(ev.nativeEvent as InputEvent).inputType) add(ev.target.value, false) // picked from the list
        }}
        onKeyDown={(ev) => { if (ev.key === 'Enter') { ev.preventDefault(); add(v, true) } }} />
      <datalist id={list}>{m.data.groups.filter((g) => !mine.includes(g.id)).map((g) => <option key={g.id} value={g.name} />)}</datalist>
    </>
  )
}

/** A related link's reason, written in place of its ✎ (Enter or clicking away saves; empty takes it away) */
function RelNote({ m, a, b }: { m: Model; a: string; b: string }) {
  const why = m.by[a]?.related_notes?.[b] ?? ''
  const [editing, setEditing] = useState(false)
  const [v, setV] = useState(why)
  const done = useRef(false)
  if (!editing) {
    return <button className={'relnote' + (why ? ' has' : '')} title={why ? 'the reason: click to change it' : "say how they're related (a case of it, a rival telling, told together…)"}
      onClick={() => { done.current = false; setV(why); setEditing(true) }}>{why || '✎ why?'}</button>
  }
  const na = m.by[a]?.name ?? a, nb = m.by[b]?.name ?? b
  const finish = (save: boolean) => {
    if (done.current) return
    done.current = true
    setEditing(false)
    if (save && v.trim() !== why) void act({ action: 'relate', a, b, note: v.trim() }, v.trim() ? '↔ reason saved' : '↔ reason taken away')
  }
  return (
    <>
      <input className="relnote-in" autoFocus list={`rel-${a}-${b}`} value={v} placeholder="how they’re related (pick or type)"
        onChange={(ev) => setV(ev.target.value)} onBlur={() => finish(true)}
        onKeyDown={(ev) => { if (ev.key === 'Enter') { ev.preventDefault(); finish(true) } if (ev.key === 'Escape') { ev.preventDefault(); finish(false) } }} />
      <datalist id={`rel-${a}-${b}`}>{[`${na} answers ${nb}`, `${nb} answers ${na}`, `mirror: ${na} and ${nb}, the same move turned around`,
        'sibling: the same shape, another topic', 'a case of it, not a sibling'].map((o) => <option key={o} value={o} />)}</datalist>
    </>
  )
}

/** The note, saved as you leave it (Enter too; Shift+Enter a new line). What you're typing stays through any redraw */
function Note({ e, ns }: { e: Entry; ns: string }) {
  const [note, setNote] = useState(e.note ?? '')
  const [notThis, setNotThis] = useState(e.not_this ?? '')
  const focused = useRef(false)
  useEffect(() => { if (!focused.current) setNote(e.note ?? '') }, [e.note])
  useEffect(() => { setNotThis(e.not_this ?? '') }, [e.not_this])
  const saveNote = () => { focused.current = false; if (note.trim() !== (e.note ?? '')) void act({ action: 'note', id: e.id, note: note.trim() }, '💾 note saved') }
  const saveNotThis = () => { if (notThis.trim() !== (e.not_this ?? '')) void act({ action: 'not_this', id: e.id, text: notThis.trim() }, notThis.trim() ? "🚫 saved what it isn't" : '🚫 taken away') }
  const enter = (ev: React.KeyboardEvent<HTMLElement>) => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); (ev.target as HTMLElement).blur() } }
  return (
    <div className={'note ' + ns}>
      <label>📝 note <span className="ntag">{ns === 'none' ? 'none yet' : ns === 'draft' ? '🤖 draft by ' + (e.note_by === 'claude' ? 'Claude' : 'the model') : 'yours'}</span></label>
      <textarea rows={2} value={note} placeholder="what this motif is, in a sentence (saves when you click away or press Enter; Shift+Enter for a new line)"
        onFocus={() => { focused.current = true }} onChange={(ev) => setNote(ev.target.value)} onBlur={saveNote} onKeyDown={enter} />
      {ns === 'draft' && <div className="nbtns"><button className="btn" onClick={() => void act({ action: 'keep_note', id: e.id }, '✓ kept the draft note')}>✓ keep the draft</button></div>}
      <label className="notthis">🚫 not this <input value={notThis} onChange={(ev) => setNotThis(ev.target.value)} onBlur={saveNotThis} onKeyDown={enter}
        placeholder="what it isn't, though it looks like it (the filing model and the judge read this)" title="one line on what to keep out: saves when you click away or press Enter" /></label>
      {(e.carrying ?? []).length > 0 && <p className="carried" title="its phrase dictionary so far: the carrying words you've given its filings">🗣 tellers say: {e.carrying!.map(([p, n], i) => <span key={p}>{i > 0 && ' · '}<b>“{p}”</b>{n > 1 && ` ×${n}`}</span>)}</p>}
    </div>
  )
}

function ClaimRow({ e, c, selected, onSelect }: { e: Entry; c: Claim; selected: boolean; onSelect: (shift: boolean) => void }) {
  const [detail, setDetail] = useState(false)
  const click = (ev: MouseEvent) => {
    if (justDragged() || (ev.target as Element).closest('button, a')) return
    onSelect(ev.shiftKey)
  }
  return (
    <li className={'claim' + (selected ? ' sel' : '')} {...claimDrag(c, e.id)} data-drop="sameclaim">
      <span className="ctext" onClick={click}>
        {c.new && <b className="b-new">NEW</b>}{c.checked === 'yes' ? <b title="checked: belongs here">✓</b> : c.checked === 'unsure' ? <b title="checked: not sure">🤷</b> : null}
        {(c.variants ?? []).length > 0 && <b className="ways" title={'also told as: ' + c.variants!.join(' · ')}>≡ {c.variants!.length + 1} ways</b>}
        {c.claim}
        {(c.carrying ?? []).length > 0 && <i className="carrytag" title="carrying words"> 🗣 {c.carrying!.map((p) => '“' + p + '”').join(' ')}</i>}
      </span>
      <span className="meta"><a className="cid" title="open it on the right" onClick={() => openClaim(c.claim, { src: c.source, ref: c.ref })}>#{c.id}</a> · {SOURCE[c.source] || c.source || ''}</span>
      <span className="cbtns">
        <button className="mini" title="open it on the right: its source and every motif it's in, to reassign" onClick={() => openClaim(c.claim, { src: c.source, ref: c.ref })}>🔍</button>
        {c.checked !== 'yes' && <button className="mini" title="yes, it belongs here" onClick={() => void act({ action: 'check', claim: c.claim, id: e.id, answer: 'yes' }, '✓ checked')}>✓</button>}
        <button className="mini" title="take it out of this motif" onClick={() => void act({ action: 'unfile', claim: c.claim, id: e.id }, '✕ taken out')}>✕</button>
        <button className="mini" title="no motif: tells no recurring story" onClick={async (ev) => { if (await sure('No motif: take it out of every motif, for good?', 'yes, do it', ev.currentTarget)) void act({ action: 'no_motif', claim: c.claim }, '∅ no motif') }}>∅</button>
        <button className="mini" title="correct the wording" onClick={async (ev) => {
          const text = await ask('Correct the wording (our summary, not the source)', c.claim, { multiline: true, anchor: ev.currentTarget })
          if (text && text !== c.claim) void act({ action: 'correct', claim: c.claim, text }, '✎ corrected')
        }}>✎</button>
        <button className="mini" title="where it came from" onClick={() => setDetail(!detail)}>ⓘ</button>
      </span>
      {detail && <Detail claim={c.claim} />}
    </li>
  )
}

function ClaimSearch({ onResults }: { onResults: (x: { kind: 'search'; q: string; items: ClaimHit[] } | null) => void }) {
  const timer = useRef<number | undefined>(undefined)
  return (
    <label className="addsearch">📥 add claims <input type="search" placeholder="search every claim…" onChange={(ev) => {
      const q = ev.target.value
      clearTimeout(timer.current)
      timer.current = window.setTimeout(async () => {
        onResults(q.trim() ? { kind: 'search', q, items: await getJSON<ClaimHit[]>('/claims.json', { q }).catch(() => []) } : null)
      }, 220)
    }} /></label>
  )
}

function Extra({ m, e, x, onClose, onDone }: { m: Model; e: Entry; x: { kind: 'similar' | 'search'; q?: string; items: ClaimHit[] }; onClose: () => void; onDone: (claim: string) => void }) {
  const add = async (c: ClaimHit) => {
    const src = c.motifs[0]?.id ?? ''
    await act(src ? { action: 'also', claim: c.claim, source: src, target: e.id } : { action: 'file', claim: c.claim, id: e.id, source: c.source, ref: c.ref }, `＋ added to “${e.name}”`)
    onDone(c.claim)
  }
  return (
    <div className="extra">
      <h3>{x.kind === 'similar' ? '🧲 more like this' : `📥 claims matching “${x.q}”`} <button className="mini" onClick={onClose}>✕</button></h3>
      <ul className="claims">
        {x.items.map((c) => {
          const here = c.motifs.some((y) => y.id === e.id)
          return (
            <li key={c.claim} className={'claim mini' + (c.motifs.length ? '' : ' unfiled')} {...claimDrag(c, c.motifs[0]?.id ?? '')}>
              <span className="ctext">{c.claim}</span>
              <span className="meta">{c.motifs.length ? <>in {c.motifs.map((y) => <Chip key={y.id} id={y.id} />)}</> : <>📥 not filed · {SOURCE[c.source] || c.source}</>}{x.kind === 'similar' && c.score != null ? ` · ${c.score}` : ''}</span>
              <span className="cbtns">
                {here ? '✓ here' : <button className="mini" title="add it here" onClick={() => void add(c)}>＋</button>}
                {x.kind === 'similar' && <button className="mini" title="not this motif: don't suggest it again" onClick={async () => { await act({ action: 'reject', claim: c.claim, id: e.id }, '✕ won’t suggest it again'); onDone(c.claim) }}>✕</button>}
              </span>
            </li>
          )
        })}
        {!x.items.length && <li className="faint">🦗 {x.kind === 'similar' ? 'nothing close' : 'none'}</li>}
      </ul>
      {m && null}
    </div>
  )
}
