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

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw await failure(r)
  const text = await r.text()
  return (text ? JSON.parse(text) : null) as T
}
