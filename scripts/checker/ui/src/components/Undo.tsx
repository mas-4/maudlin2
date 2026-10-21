// ↶ undo: the newest change to the index (or the names), from the checker's undo stack. Ctrl+Z outside a text field.
// The server refuses when the index changed since (an hourly run filing claims): the reason is shown, nothing lost.
import { useEffect } from 'react'
import { useJSON, useWrite } from '../lib/queries'

export function Undo() {
  const { data } = useJSON<{ what: string | null }>('/undo.json')
  const undo = useWrite<Record<string, never>, { undid: string }>('/undo')
  const what = data?.what
  const run = () => {
    if (!what || undo.isPending) return
    undo.mutate({}, { onError: (e) => alert(`Can’t undo: ${e.message}`) })
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !t?.closest('input, textarea, [contenteditable]')) {
        e.preventDefault()
        run()
      }
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  })
  return (
    <span className="nav-undo">
      <button disabled={!what || undo.isPending} onClick={run} title="undo your last change (Ctrl+Z)">
        {undo.isPending ? '⏳' : '↶'} undo
      </button>
      {what && <span title={what}>undo: {what}</span>}
    </span>
  )
}
