// ↶ undo in the nav: what the newest change was, and Ctrl/⌘+Z outside a text field. The server refuses when the
// index changed since (an hourly run filing claims): the reason is shown, nothing lost
import { useEffect } from 'react'
import { useJSON } from '../lib/queries'
import { undo } from '../lib/undo'

export function Undo() {
  const { data } = useJSON<{ what: string | null }>('/undo.json')
  const what = data?.what
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !t?.closest?.('input, textarea, select, [contenteditable]')) {
        e.preventDefault()
        if (what) void undo()
      }
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [what])
  return (
    <span className="nav-undo">
      <button disabled={!what} onClick={() => void undo()} title="undo your last change (Ctrl+Z)">
        ↶ undo
      </button>
      {what && <span title={what}>last: {what}</span>}
    </span>
  )
}
