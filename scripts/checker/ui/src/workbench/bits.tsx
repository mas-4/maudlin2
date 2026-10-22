// Small pieces the whole workbench uses: a motif as a chip, a filing's fit, a claim's head in a list, the hover card
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { claimLink, currentModel, motifLink, motifsOf, useWorkbench } from './model'
import { openClaim, openMotif } from './ops'
import type { Claim, Entry } from './types'

const modified = (ev: MouseEvent) => ev.shiftKey || ev.metaKey || ev.ctrlKey

/** A motif anywhere: click opens it (Shift/Ctrl/⌘ beside the others), middle-click a new tab, drag it, drop on it */
export function Chip({ id, children }: { id: string; children?: ReactNode }) {
  const { model } = useWorkbench()
  const e = model?.by[id]
  if (!e) return null
  return (
    <span className="chip" data-drag="motif" data-id={id} data-drop="motif" title={`${e.note || e.name} · ${id}`}
      onClick={(ev) => { if (!(ev.target as Element).closest('button')) openMotif(id, modified(ev)) }}
      onAuxClick={(ev) => { if (ev.button === 1) { ev.preventDefault(); open(motifLink(id), '_blank') } }}
      onMouseDown={(ev) => { if (ev.button === 1) ev.preventDefault() }}>
      {e.name}<i>{e.claims.length}</i>{children}
    </span>
  )
}

/** A filing's fit: the chance the person keeps it, learned from their own checks */
export function FitChip({ fit, unsure, title }: { fit: number; unsure?: boolean; title?: string }) {
  const pct = Math.round(fit * 100)
  return (
    <b className="fit" style={{ ['--fit' as string]: `${pct}%` }}
      title={title ?? `fit: the chance you keep this filing, learned from your own checks${unsure ? '. Never passed as sure: its motif was made for this claim alone, or too few of your checks have tested claims from where it came from' : ''}`}>
      🎯 {pct}%{unsure ? ' ⚠️' : ''}
    </b>
  )
}

/** The drag attributes of a claim: what it is, the motif it's carried from, where it came from */
export function claimDrag(c: { claim: string; source?: string; ref?: string }, from: string) {
  return { 'data-drag': 'claim', 'data-claim': c.claim, 'data-source': from, 'data-src': c.source ?? '', 'data-ref': c.ref ?? '' }
}

/** A claim in a list, as its row's head: click its words to open it whole (← back comes back here), ↗ a new tab; the
 * row carries the drag from the first motif it waits in */
export function useClaimHead(claim: string, ids?: string[]) {
  const m = currentModel()
  const from = (ids ?? []).find((id) => m?.by[id]) ?? (m ? motifsOf(m, claim)[0]?.id : undefined) ?? ''
  const rec: Partial<Claim> = (from && m?.by[from]?.claims.find((c) => c.claim === claim)) || { claim }
  return {
    drag: claimDrag({ claim, source: rec.source, ref: rec.ref }, from),
    head: (
      <>
        <span className="quicktext" title="click to open it whole (← back comes back here); drag it onto a motif to file it there too, or move it"
          onClick={() => openClaim(claim)}
          onAuxClick={(ev) => { if (ev.button === 1) { ev.preventDefault(); open(claimLink(claim), '_blank') } }}>
          {claim}
        </span>
        <a className="newtab" href={claimLink(claim)} target="_blank" title="open it in a new tab">↗</a>
      </>
    ),
  }
}

/** How many separate occasions its kept claims come from (app/analysis/motif_told.py): attested at two or more */
export function Told({ e }: { e: Entry }) {
  if (!e.told) return null
  return e.attested ? (
    <span className="told" title={`its kept claims come from ${e.told.events} separate occasions (told about different events), ${(e.told.span ?? []).join(' to ')}`}>
      {' '}· 🗓 {e.told.events} occasions
    </span>
  ) : (
    <span className="told placed" title="its kept claims all come from one occasion: a shape placed, not yet seen told again about something else">
      {' '}· 📍 one occasion
    </span>
  )
}

/** Hover a motif chip or row for its note and a few claims */
export function HoverCard() {
  const { model } = useWorkbench()
  const [at, setAt] = useState<{ id: string; rect: DOMRect } | null>(null)
  const card = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let timer: number | undefined, on: Element | null = null
    const over = (ev: Event) => {
      const c = (ev.target as Element).closest?.('.chip, .row')
      if (c === on) return
      on = c
      clearTimeout(timer)
      setAt(null)
      const id = (c as HTMLElement | null)?.dataset.id
      if (!c || !id || document.body.classList.contains('dragging')) return
      timer = window.setTimeout(() => setAt({ id, rect: c.getBoundingClientRect() }), 350)
    }
    const down = () => { clearTimeout(timer); setAt(null) }
    document.addEventListener('mouseover', over)
    document.addEventListener('pointerdown', down, true)
    return () => { document.removeEventListener('mouseover', over); document.removeEventListener('pointerdown', down, true) }
  }, [])
  useEffect(() => {
    const el = card.current
    if (!el || !at) return
    const m = el.getBoundingClientRect()
    let x = at.rect.left, y = at.rect.bottom + 6
    if (x + m.width > innerWidth - 8) x = innerWidth - m.width - 8
    if (y + m.height > innerHeight - 8) y = Math.max(8, at.rect.top - m.height - 6)
    el.style.left = Math.max(8, x) + 'px'
    el.style.top = y + 'px'
  }, [at])
  const e = at && model?.by[at.id]
  if (!e) return null
  const kids = (model.kids[e.id] ?? []).map((k) => model.by[k]?.name).filter(Boolean)
  return (
    <div ref={card} className="hover-card" style={{ left: -9999, top: -9999 }}>
      <b>{e.name}</b> <span className="faint">{e.id} · {e.claims.length} claim{e.claims.length === 1 ? '' : 's'}{e.done === 'done' ? ' · ✓ done' : ''}</span>
      {e.facets?.genre && <p>🎭 {e.facets.genre}</p>}
      {e.note ? <p>📝 {e.note}</p> : <p className="faint">no note yet</p>}
      {e.parents.length > 0 && <p className="faint">↳ rests on {e.parents.map((p) => model.by[p]?.name ?? p).join(', ')}</p>}
      {kids.length > 0 && <p className="faint">⤷ rest on it: {kids.join(', ')}</p>}
      <ul>
        {e.claims.slice(0, 4).map((x) => <li key={x.claim}>{x.claim}</li>)}
        {e.claims.length > 4 && <li className="faint">and {e.claims.length - 4} more</li>}
      </ul>
    </div>
  )
}

/** A typo fix or reworded note, word by word: what went (struck) and what came (marked) */
export function WordDiff({ a, b }: { a: string; b: string }) {
  const x = a.split(/(\s+)/), y = b.split(/(\s+)/)
  const L = Array.from({ length: x.length + 1 }, () => Array.from({ length: y.length + 1 }, () => 0))
  for (let i = x.length - 1; i >= 0; i--) for (let j = y.length - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1])
  const out: ReactNode[] = []
  let i = 0, j = 0
  while (j < y.length) {
    if (i < x.length && x[i] === y[j]) { out.push(y[j]); i++; j++ }
    else if (i < x.length && L[i + 1][j] >= L[i][j + 1]) out.push(<del key={`d${i}`}>{x[i++]}</del>)
    else out.push(<mark key={`m${j}`}>{y[j++]}</mark>)
  }
  while (i < x.length) out.push(<del key={`d${i}`}>{x[i++]}</del>)
  return <>{out}</>
}

export const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, '0')}` // 845 -> 14:05
export const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`
