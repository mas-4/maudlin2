// Every change in the workbench: one action (app/analysis/motif_actions.py) posted to /workbench, which answers with the
// whole index as it now is. While it saves, the button pressed shows ⏳ and the page's cursor waits; a second press is
// refused with a word (Oct 19: presses that showed nothing were pressed again). Then the toast, with ↶ undo.
import { postJSON } from '../lib/api'
import { client } from '../lib/queries'
import { toast } from '../components/Feedback'
import { getWB, setWB } from './store'
import type { Action, WBState } from './types'

let pressed: Element | null = null
document.addEventListener('pointerdown', (ev) => {
  pressed = (ev.target as Element | null)?.closest?.('button, .btn') ?? null
}, true)

/** The queues a change makes stale at once (the rest are read again when their tab is opened) */
const AFTER_ANY = ['pairs', 'singles']

export async function act(body: Action, done?: string, stale: string[] = []): Promise<boolean> {
  if (getWB().acting) {
    toast('⏳ still saving the last change…')
    return false
  }
  const btn = pressed?.isConnected ? pressed : null
  setWB({ acting: true })
  btn?.classList.add('busy')
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
    setWB({ acting: false })
    btn?.classList.remove('busy')
  }
}

/** Several steps as one undoable change; one step sent bare; nothing to do, nothing sent */
export function batch(steps: (Action | null | undefined | false)[], done?: string, extra?: Record<string, unknown>, stale?: string[]) {
  const real = steps.filter(Boolean) as Action[]
  if (!real.length && !extra) return Promise.resolve(false)
  return act(real.length === 1 && !extra ? real[0] : { action: 'batch', steps: real, ...extra }, done, stale)
}
