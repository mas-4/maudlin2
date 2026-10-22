// ⏳ in the nav while changes are saving: how many are still in line (lib/api.ts), so a quick run of presses shows
// it's being kept up with, and nothing needs pressing twice
import { useSyncExternalStore } from 'react'
import { watchWrites, writesWaiting } from '../lib/api'

export function Saving() {
  const n = useSyncExternalStore(watchWrites, writesWaiting)
  if (!n) return null
  return <span className="nav-saving" title="your changes are saved in the order you made them">⏳ saving{n > 1 ? ` ${n}` : ''}…</span>
}
