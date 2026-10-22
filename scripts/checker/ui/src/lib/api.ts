// The checker's JSON API (scripts/validate.py): GET routes in its GET_JSON table, writes as named actions
// (app/analysis/motif_actions.py) posted to /workbench. One client, so every page fetches, fails and refreshes alike.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Params = Record<string, string | number | boolean | undefined | null>

export function url(path: string, params?: Params): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `${path}?${s}` : path
}

async function failure(r: Response): Promise<ApiError> {
  const text = await r.text()
  try {
    return new ApiError(r.status, JSON.parse(text).error ?? text)
  } catch {
    return new ApiError(r.status, text.replace(/<[^>]+>/g, ' ').trim().slice(0, 300) || r.statusText)
  }
}

export async function getJSON<T>(path: string, params?: Params): Promise<T> {
  const r = await fetch(url(path, params), { headers: { Accept: 'application/json' } })
  if (!r.ok) throw await failure(r)
  return r.json() as Promise<T>
}

async function send<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw await failure(r)
  const text = await r.text()
  return (text ? JSON.parse(text) : null) as T
}

// Every write, one at a time and in the order made (Oct 22: the workbench refused a press while the last change was
// saving, two to three seconds, and the person's quick ✓ ✓ ✓ bounced). A press is never refused now: it waits its turn.
// Undo and the saved states wait in the same line, so an undo takes back the last change made, not one still on its way
let tail: Promise<unknown> = Promise.resolve()
let waiting = 0
const watchers = new Set<() => void>()
const told = () => watchers.forEach((w) => w())

/** How many writes are waiting or on their way */
export const writesWaiting = () => waiting
export function watchWrites(fn: () => void) {
  watchers.add(fn)
  return () => void watchers.delete(fn)
}

export function postJSON<T>(path: string, body: unknown): Promise<T> {
  waiting++
  told()
  const run = tail.then(() => send<T>(path, body))
  tail = run.then(() => undefined, () => undefined).then(() => {
    waiting--
    told()
  })
  return run
}
