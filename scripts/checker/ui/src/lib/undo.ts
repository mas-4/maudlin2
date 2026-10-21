// ↶ undo: the newest change, from the checker's one undo stack (the index, the names). Everything shown is fetched
// again after, since a step back may touch any view
import { postJSON } from './api'
import { client } from './queries'
import { toast } from '../components/Feedback'

const after = new Set<() => void>()

/** Run fn after each undo, once everything shown has been fetched again (a page's own session state to set right) */
export function onUndo(fn: () => void) {
  after.add(fn)
  return () => void after.delete(fn)
}

export async function undo() {
  try {
    const out = await postJSON<{ undid: string }>('/undo', {})
    await client.invalidateQueries()
    after.forEach((fn) => fn())
    toast('↶ undid: ' + out.undid)
  } catch (e) {
    toast('Can’t undo: ' + (e as Error).message, true)
  }
}
