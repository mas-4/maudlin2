// The checker restarts on new code (it follows the checkout); an open tab finds out here and offers a reload, so it
// never posts to a server whose actions it no longer matches.
import { useEffect, useRef } from 'react'
import { useJSON } from '../lib/queries'

export function VersionWatch() {
  const { data } = useJSON<{ version: string }>('/version.json', undefined, { refetchInterval: 60_000 })
  const first = useRef<string | null>(null)
  useEffect(() => {
    if (data && first.current === null) first.current = data.version
  }, [data])
  if (!data || first.current === null || data.version === first.current) return null
  return (
    <button className="nav-new" onClick={() => location.reload()} title="the checker has new code">
      ✨ new version: reload
    </button>
  )
}
