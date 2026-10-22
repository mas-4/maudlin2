// The checker's pages, in the nav's order: the workbench and the map first (where the person works), then the other
// views, then the other tools. Since Oct 22 the old pages (scripts/checker/templates) are gone, and their addresses
// lead here (validate.py OLD_PAGES); the old ✅ check, 🫙 empty and 📝 notes pages went with them, their work being the
// workbench's 🎯 judge tab, its 🫙 empty part and its 📝 and 🗒️ views.
export type Section = 'main' | 'other'
export interface Page {
  path: string
  emoji: string
  name: string
  section: Section
}

export const PAGES: Page[] = [
  { path: '/workbench', emoji: '🧰', name: 'Motif workbench', section: 'main' },
  { path: '/map', emoji: '🕸️', name: 'Motif map', section: 'main' },
  { path: '/dashboard', emoji: '📈', name: 'Dashboard', section: 'main' },
  { path: '/experiments', emoji: '🧪', name: 'Experiments', section: 'main' },
  { path: '/flow', emoji: '🌊', name: 'Flow', section: 'main' },
  { path: '/live', emoji: '🧠', name: 'Live', section: 'main' },
  { path: '/labels', emoji: '🏷️', name: 'label check', section: 'other' },
  { path: '/names', emoji: '👥', name: 'names', section: 'other' },
]
