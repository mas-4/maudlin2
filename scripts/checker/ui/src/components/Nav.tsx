import { useEffect, useRef } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { PAGES } from '../lib/routes'
import { SavedStates } from './SavedStates'
import { Saving } from './Saving'
import { Undo } from './Undo'
import { VersionWatch } from './VersionWatch'

const LABELS = { motifs: 'motif pages', other: 'other tools' } as const

// The nav, on one line (Oct 22: two lines on a laptop, with the judging card left 311 px of 768): the main pages as
// pills, the rest under ⋯ more
export function Nav() {
  const where = useLocation().pathname
  const more = useRef<HTMLDetailsElement>(null)
  const main = PAGES.filter((p) => p.section === 'main'), rest = PAGES.filter((p) => p.section !== 'main')
  useEffect(() => { if (more.current) more.current.open = false }, [where]) // a page picked: the menu closes
  useEffect(() => { // and a click elsewhere closes it
    const away = (e: PointerEvent) => { if (more.current?.open && !more.current.contains(e.target as Node)) more.current.open = false }
    addEventListener('pointerdown', away)
    return () => removeEventListener('pointerdown', away)
  }, [])
  const here = rest.find((p) => where.startsWith(p.path))
  return (
    <nav className="nav">
      {main.map((p) => (
        <NavLink key={p.path} to={p.path} className="nav-main">
          {p.emoji} {p.name}
        </NavLink>
      ))}
      <details className="nav-more" ref={more}>
        <summary className={here ? 'active' : ''}>{here ? `${here.emoji} ${here.name}` : '⋯ more'}</summary>
        <div className="nav-menu">
          {(['motifs', 'other'] as const).map((sec) => (
            <div key={sec}>
              <span className="nav-label">{LABELS[sec]}</span>
              {rest.filter((p) => p.section === sec).map((p) => (
                <NavLink key={p.path} to={p.path}>
                  {p.emoji} {p.name}
                </NavLink>
              ))}
            </div>
          ))}
        </div>
      </details>
      <VersionWatch />
      <span className="nav-right">
        <Saving />
        <SavedStates />
        <Undo />
      </span>
    </nav>
  )
}
