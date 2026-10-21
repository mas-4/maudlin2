// A motif's card, shared by the details box that follows the picked motif and the cards on the 📌 desk: its name and
// note edited in place, its facts, what it rests on, what rests on it and what it's related to (each with ✕ to take the
// link away and ＋ to add one), the motifs it shares claims with, and its claims (drag one onto a dot to file it there).
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { act } from '../../workbench/act'
import { claimDrag } from '../../workbench/bits'
import { sharedWith } from '../../workbench/Detail'
import { groupColor, motifLink, SOURCE, type Model } from '../../workbench/model'

/** A text box that grows to its text and saves when left (a single line also on Enter); Esc puts it back. What's being
 * typed survives a redraw: the saved value only replaces it while the box isn't being typed in */
function EditText({ value, onSave, single, className, placeholder, title }: {
  value: string; onSave: (v: string) => void; single?: boolean; className: string; placeholder?: string; title?: string
}) {
  const [v, setV] = useState(value)
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { if (document.activeElement !== ref.current) setV(value) }, [value])
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = el.scrollHeight + 'px'
  }, [v])
  return (
    <textarea ref={ref} className={className} rows={1} value={v} placeholder={placeholder} title={title}
      onChange={(e) => setV(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Escape') { e.stopPropagation(); setV(value); requestAnimationFrame(() => ref.current?.blur()) }
        if (e.key === 'Enter' && single) { e.preventDefault(); ref.current?.blur() }
      }}
      onBlur={() => {
        const t = v.trim()
        if (single && !t) return setV(value) // a name can't be emptied
        if (t !== value.trim()) onSave(t)
      }} />
  )
}

type How = 'up' | 'down' | 'rel'

/** A linked motif: click goes to it on the map, middle-click opens it in the workbench; drag it, drop on it */
function MotifChip({ m, id, onGo, children }: { m: Model; id: string; onGo: (id: string) => void; children?: ReactNode }) {
  const e = m.by[id]
  if (!e) return null
  return (
    <span className="chip" data-drag="motif" data-drop="motif" data-id={id} title={`${e.note || e.name} · ${id}`}
      onClick={(ev) => { if (!(ev.target as Element).closest('button')) onGo(id) }}
      onAuxClick={(ev) => { if (ev.button === 1) { ev.preventDefault(); open(motifLink(id), '_blank') } }}
      onMouseDown={(ev) => { if (ev.button === 1) ev.preventDefault() }}>
      {e.name}<i>{e.claims.length}</i>{children}
    </span>
  )
}

function LinkRow({ m, id, label, ids, how, onGo }: { m: Model; id: string; label: string; ids: string[]; how: How; onGo: (id: string) => void }) {
  const [adding, setAdding] = useState(false)
  const [bad, setBad] = useState(false)
  const e = m.by[id]
  const unlink = (other: string) => {
    const o = m.by[other]?.name ?? other
    if (how === 'rel') return act({ action: 'unrelate', a: id, b: other }, `✕ “${e.name}” and “${o}” no longer related`)
    if (how === 'up') return act({ action: 'parent', id, parent: other, on: false }, `✕ “${e.name}” no longer rests on “${o}”`)
    return act({ action: 'parent', id: other, parent: id, on: false }, `✕ “${o}” no longer rests on “${e.name}”`)
  }
  const add = (text: string) => {
    const v = text.trim().toLowerCase()
    const other = m.data.entries.find((x) => x.name.toLowerCase() === v || x.id.toLowerCase() === v)
    if (!other || other.id === id) return setBad(true)
    setAdding(false)
    if (how === 'rel') return act({ action: 'relate', a: id, b: other.id }, `↔ related “${e.name}” and “${other.name}”`)
    if (how === 'up') return act({ action: 'parent', id, parent: other.id }, `↳ “${e.name}” rests on “${other.name}”`)
    return act({ action: 'parent', id: other.id, parent: id }, `↳ “${other.name}” rests on “${e.name}”`)
  }
  const shown = ids.filter((i) => m.by[i])
  return (
    <p className="mm-crow">
      <b>{label}</b>{' '}
      {shown.length ? shown.map((i) => (
        <MotifChip key={i} m={m} id={i} onGo={onGo}>
          <button className="mm-unlink" title="take this link away" onClick={() => void unlink(i)}>✕</button>
        </MotifChip>
      )) : <span className="faint">—</span>}{' '}
      {adding ? (
        <input className={'mm-linkname' + (bad ? ' bad' : '')} list="mm-names" autoFocus
          placeholder={(how === 'up' ? 'a broader motif' : how === 'down' ? 'a narrower motif' : 'a related motif') + ', then Enter'}
          onChange={() => setBad(false)}
          onBlur={() => setAdding(false)}
          onKeyDown={(ev) => {
            if (ev.key === 'Escape') { ev.stopPropagation(); setAdding(false) }
            if (ev.key === 'Enter') void add(ev.currentTarget.value)
          }} />
      ) : <button className="mm-addlink" title="add one" onClick={() => { setBad(false); setAdding(true) }}>＋</button>}
    </p>
  )
}

export function Card({ m, id, onGo, folded }: { m: Model; id: string; onGo: (id: string) => void; folded?: boolean }) {
  const e = m.by[id]
  if (!e) return null
  const shared = sharedWith(m, e)
  const facts = [
    e.id,
    e.done === 'done' ? '✅ done' : e.done === 'new' ? '🆕 done, new claims since' : '⏳ not done',
    e.first_seen ? 'since ' + e.first_seen : '',
    e.curated ? '✋ named by hand' : '🤖 named by the model',
    e.facets?.genre ? '🎭 ' + e.facets.genre : '',
  ].filter(Boolean)
  const src = (s: string) => SOURCE[s] ?? s ?? ''
  return (
    <>
      <h3 className="mm-chead" data-drag="motif" data-drop="motif" data-id={e.id} title="drag by the 🧩 onto a dot, a name or the 📌">
        <span className="mm-grip">🧩</span>
        <EditText className="mm-cname" single value={e.name} title="its name: edit, then Enter"
          onSave={(v) => void act({ action: 'rename', id: e.id, name: v }, `✎ renamed to “${v}”`)} />
      </h3>
      <div className="mm-cfacts">
        {facts.map((f) => <span key={f}>{f}</span>)}
        {(e.groups ?? []).map((g) => (
          <span key={g} className="mm-gtag" style={{ ['--g' as string]: groupColor(m.data.groups.findIndex((x) => x.id === g)) }}>
            📁 {m.data.groups.find((x) => x.id === g)?.name ?? g}
          </span>
        ))}
      </div>
      <EditText className="mm-cnote" value={e.note ?? ''} placeholder="a scope note: what kind of story it covers" title="its scope note: saved when you click away"
        onSave={(v) => void act({ action: 'note', id: e.id, note: v }, v ? '📝 note saved' : '📝 note gone')} />
      <LinkRow m={m} id={e.id} label="↳ rests on" ids={e.parents} how="up" onGo={onGo} />
      <LinkRow m={m} id={e.id} label="⤷ rest on it" ids={m.kids[e.id] ?? []} how="down" onGo={onGo} />
      <LinkRow m={m} id={e.id} label="↔ related" ids={e.related} how="rel" onGo={onGo} />
      <p className="mm-crow">
        <b>🤝 shares claims with</b>{' '}
        {shared.length ? shared.map(([o, n]) => <MotifChip key={o} m={m} id={o} onGo={onGo}><span className="faint"> ×{n}</span></MotifChip>)
          : <span className="faint">—</span>}
      </p>
      <p className="mm-crow">
        <b>{e.claims.length} claim{e.claims.length === 1 ? '' : 's'}</b> <span className="faint">✓ you checked it · 🆕 filed since you marked it done</span>
      </p>
      {!folded && (
        <ul className="mm-claims">
          {e.claims.map((c) => (
            <li key={c.claim} {...claimDrag(c, e.id)} title="drag onto a dot or a name to file it there">
              {c.checked === 'yes' ? '✓ ' : ''}{c.new ? '🆕 ' : ''}{c.claim}{' '}
              <span className="mm-csrc">{c.ref && /^https?:/.test(c.ref) ? <a href={c.ref} target="_blank" rel="noopener">{src(c.source)}</a> : src(c.source)}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
