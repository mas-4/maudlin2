// Every change in the workbench: one action (app/analysis/motif_actions.py) posted to /workbench, which answers with the
// whole index as it now is. Changes wait their turn in one line (lib/api.ts postJSON), so a press is never refused;
// the button pressed shows ⏳ until its own change is saved, and the nav counts what's still saving. The same change
// pressed again while it waits is sent once. Then the toast, with ↶ undo.
import { postJSON } from '../lib/api'
import { client } from '../lib/queries'
import { toast } from '../components/Feedback'
import type { Action, WBState } from './types'

let pressed: Element | null = null
document.addEventListener('pointerdown', (ev) => {
  pressed = (ev.target as Element | null)?.closest?.('button, .btn') ?? null
}, true)

/** The queues a change makes stale at once (the rest are read again when their tab is opened) */
const AFTER_ANY = ['pairs', 'singles']
const inLine = new Map<string, Promise<boolean>>() // the changes waiting, by their words: a second press joins the first

export function act(body: Action, done?: string, stale: string[] = []): Promise<boolean> {
  const words = JSON.stringify(body)
  const same = inLine.get(words)
  if (same) return same
  const btn = pressed?.isConnected ? pressed : null
  btn?.classList.add('busy')
  const run = (async () => {
    try {
      const out = await postJSON<WBState>('/workbench', body)
      client.setQueryData(['/workbench.json', {}], out)
      for (const kind of [...AFTER_ANY, ...stale]) void client.invalidateQueries({ queryKey: ['/workbench-queue.json', { kind }] })
      void client.invalidateQueries({ queryKey: ['/undo.json'] })
      if (done) toast(done, false, true)
      return true
    } catch (e) {
      toast('😬 ' + ((e as Error).message || 'that didn’t work'), true)
      void client.invalidateQueries({ queryKey: ['/workbench.json'] })
      return false
    } finally {
      inLine.delete(words)
      btn?.classList.remove('busy')
    }
  })()
  inLine.set(words, run)
  return run
}

/** Several steps as one undoable change; one step sent bare; nothing to do, nothing sent */
export function batch(steps: (Action | null | undefined | false)[], done?: string, extra?: Record<string, unknown>, stale?: string[]) {
  const real = steps.filter(Boolean) as Action[]
  if (!real.length && !extra) return Promise.resolve(false)
  return act(real.length === 1 && !extra ? real[0] : { action: 'batch', steps: real, ...extra }, done, stale)
}
