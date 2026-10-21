// The checker's pages, in the nav's order: the workbench and the map first (where the person works), then the other
// views, then the single-purpose pages and other tools. A page not yet ported links to the old one (scripts/checker/
// templates), which still runs beside this app until every page here does all it did.
import type { ReactNode } from 'react'

export type Section = 'main' | 'motifs' | 'other'
export interface Page {
  path: string
  emoji: string
  name: string
  section: Section
  old: string // the old page's path
  element?: () => ReactNode
}

export const PAGES: Page[] = [
  { path: '/workbench', emoji: '🧰', name: 'Motif workbench', section: 'main', old: '/motif-workbench' },
  { path: '/map', emoji: '🕸️', name: 'Motif map', section: 'main', old: '/motif-map' },
  { path: '/dashboard', emoji: '📈', name: 'Dashboard', section: 'main', old: '/dashboard' },
  { path: '/experiments', emoji: '🧪', name: 'Experiments', section: 'main', old: '/experiments' },
  { path: '/flow', emoji: '🌊', name: 'Flow', section: 'main', old: '/flow' },
  { path: '/live', emoji: '🧠', name: 'Live', section: 'main', old: '/live' },
  { path: '/check', emoji: '✅', name: 'check', section: 'motifs', old: '/motifs' },
  { path: '/empty', emoji: '🫙', name: 'empty', section: 'motifs', old: '/motif-empty' },
  { path: '/notes', emoji: '📝', name: 'notes', section: 'motifs', old: '/motif-notes' },
  { path: '/labels', emoji: '🏷️', name: 'label check', section: 'other', old: '/' },
  { path: '/names', emoji: '👥', name: 'names', section: 'other', old: '/entities' },
]
