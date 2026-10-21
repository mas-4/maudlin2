// The dashboard's small pieces: sections, cards, number stickers, two-column lists and the saga table
import type { CSSProperties, ReactNode } from 'react'

/** A number for show: thousands separated, a dash when there is none */
export const num = (n: unknown): string => (n == null ? '—' : typeof n === 'number' ? n.toLocaleString() : String(n))
/** A share as a whole percentage */
export const pct = (x: unknown): string => (typeof x === 'number' ? Math.round(x * 100) + '%' : '—')
/** "2026-10-21T11:24:17" as "2026-10-21 11:24:17" */
export const when = (t: unknown) => (typeof t === 'string' ? t.replace('T', ' ') : '')

/** A part of the figures that failed to gather comes as {error}: said in its card, the rest still shown */
export function Err({ of }: { of: unknown }) {
  const e = of && typeof of === 'object' && 'error' in of ? (of as { error: unknown }).error : null
  return e ? <p className="dash-err">😬 {String(e)}</p> : null
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="dash-section">
      <h2 className="dash-banner"><span>{title}</span></h2>
      <div className="dash-grid">{children}</div>
    </section>
  )
}

export function Card({ title, wide, sick, children }: { title: ReactNode; wide?: boolean; sick?: boolean; children: ReactNode }) {
  return (
    <section className={'dash-card' + (wide ? ' wide' : '') + (sick ? ' dash-sick' : '')}>
      <h3>{title}</h3>
      {children}
    </section>
  )
}

export function Tiles({ children }: { children: ReactNode }) {
  return <div className="dash-tiles">{children}</div>
}

/** A sticker: a big emoji and number, what it counts under them, on a light tint */
export function Tile({ emoji, big, small, tint }: { emoji: string; big: ReactNode; small: ReactNode; tint?: string }) {
  return (
    <div className="dash-tile" style={{ '--tint': tint ?? '#f6f6fb' } as CSSProperties}>
      <b><span aria-hidden="true">{emoji}</span> {big}</b>
      <span>{small}</span>
    </div>
  )
}

/** Name and number, one a line */
export function List({ rows }: { rows: [ReactNode, unknown][] }) {
  return (
    <ul className="dash-list">
      {rows.length ? rows.map(([a, b], i) => <li key={i}><span>{a}</span><b>{num(b)}</b></li>) : <li>—</li>}
    </ul>
  )
}

export interface Saga {
  name: string
  parts: number
  now?: boolean
  outlets: number
  first: string
  last?: string
  lean: { left: number; center: number; right: number }
  'parts now'?: number
}

/** Who carries a saga: the outlets on any of its parts, by lean */
function LeanBar({ l }: { l: Saga['lean'] }) {
  return (
    <span className="dash-lean" title={`left ${l.left}% · center ${l.center}% · right ${l.right}%`}>
      <i style={{ width: `${l.left}%`, background: '#3a86ff' }} />
      <i style={{ width: `${l.center}%`, background: '#b8b8c8' }} />
      <i style={{ width: `${l.right}%`, background: '#ff4d6d' }} />
    </span>
  )
}

export function SagaTable({ rows }: { rows: Saga[] }) {
  return (
    <div className="dash-table-wrap">
      <table className="dash-table">
        <thead><tr><th>saga</th><th>parts</th><th>outlets</th><th>who carries it</th><th>since</th></tr></thead>
        <tbody>
          {rows.map((g, i) => (
            <tr key={i}>
              <td>{g.now ? '🟢 ' : ''}{g.name}</td>
              <td>{g.parts}{g['parts now'] ? <> <span className="dash-sub">({g['parts now']} up)</span></> : null}</td>
              <td>{g.outlets}</td>
              <td><LeanBar l={g.lean} /></td>
              <td>{(g.first ?? '').slice(5, 10).replace('-', '/')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
