import { NavLink } from 'react-router-dom'
import { PAGES } from '../lib/routes'
import { Undo } from './Undo'
import { VersionWatch } from './VersionWatch'

const LABELS = { motifs: 'motif pages', other: 'other tools' } as const

export function Nav() {
  let section = ''
  return (
    <nav className="nav">
      {PAGES.map((p) => {
        const label = p.section !== section && p.section !== 'main' ? LABELS[p.section] : null
        section = p.section
        return (
          <span key={p.path} className="nav-item">
            {label && <span className="nav-label">{label}</span>}
            <NavLink to={p.path} className={`nav-${p.section}`}>
              {p.emoji} {p.name}
            </NavLink>
          </span>
        )
      })}
      <VersionWatch />
      <Undo />
    </nav>
  )
}
