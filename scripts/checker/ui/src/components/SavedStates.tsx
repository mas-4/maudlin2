// 💾 saved states in the nav: save the motif index and proposals by name, and go back to a saved one later (a whole
// stretch of changes at once, where undo steps back one). Going back saves what's there first, so it can be gone back
// on too, and asks right there in the row first
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { postJSON } from '../lib/api'
import { useJSON } from '../lib/queries'
import { steppedBack } from '../lib/undo'
import { toast } from './Feedback'

interface Saved { id: number; name: string; at: string; kind: string; changes_since: number }
interface WentBack { went_back: { to: { name: string }; reverted: number; saved_first: unknown } }

const when = (at: string) => new Date(at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })

export function SavedStates() {
  const [open, setOpen] = useState(false)
  const [asking, setAsking] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const list = useJSON<Saved[]>('/checkpoints.json', {}, { enabled: open })
  useEffect(() => { // closed by Esc or a click outside
    if (!open) return
    const key = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const click = (e: PointerEvent) => !box.current?.parentElement?.contains(e.target as Node) && setOpen(false)
    addEventListener('keydown', key)
    addEventListener('pointerdown', click)
    return () => {
      removeEventListener('keydown', key)
      removeEventListener('pointerdown', click)
    }
  }, [open])

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await postJSON('/checkpoint', { name: name.trim() })
      toast(`💾 saved “${name.trim() || 'saved state'}”`)
      setName('')
      void list.refetch()
    } catch (err) {
      toast('Couldn’t save: ' + (err as Error).message, true)
    } finally {
      setBusy(false)
    }
  }
  async function goBack(id: number) {
    setBusy(true)
    try {
      const d = await postJSON<WentBack>('/checkpoint', { action: 'go back', id })
      await steppedBack()
      const n = d.went_back.reverted
      toast(`↩ back to “${d.went_back.to.name}”: ${n} change${n === 1 ? '' : 's'} taken back (what was there is saved)`)
      setAsking(null)
    } catch (err) {
      toast('Couldn’t go back: ' + (err as Error).message, true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="saved-wrap">
      <button className="nav-states" onClick={() => setOpen(!open)} title="save the state of the motif index to come back to, or go back to a saved one">
        💾 states
      </button>
      {open && (
        <div className="saved" ref={box}>
          <div className="saved-head">
            <b>💾 Saved states</b>
            <button className="mini" onClick={() => setOpen(false)} title="close">✕</button>
          </div>
          <form className="saved-form" onSubmit={save}>
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="name this state, e.g. before the Plots sweep" maxLength={120} autoComplete="off" />
            <button className="btn yes" type="submit" disabled={busy}>💾 save</button>
          </form>
          {list.isLoading && <p className="faint">⏳ fetching…</p>}
          {list.data && !list.data.length && <p className="faint">Nothing saved yet. Save one before a big sweep, and you can go back to it in one step.</p>}
          {list.data?.map((c) => (
            <div className="saved-row" key={c.id}>
              <div>
                <b>{c.name}</b>{' '}
                <span className="faint">
                  {when(c.at)}{c.kind !== 'manual' ? ' · ' + c.kind : ''} · {c.changes_since} change{c.changes_since === 1 ? '' : 's'} since
                </span>
              </div>
              {asking === c.id ? (
                <span className="saved-ask">
                  <span className="faint">go back? what’s there now is saved first</span>{' '}
                  <button className="btn yes" disabled={busy} onClick={() => void goBack(c.id)}>↩ yes, go back</button>{' '}
                  <button className="mini" onClick={() => setAsking(null)}>no</button>
                </span>
              ) : (
                <button className="mini" onClick={() => setAsking(c.id)}>↩ go back</button>
              )}
            </div>
          ))}
        </div>
      )}
    </span>
  )
}
