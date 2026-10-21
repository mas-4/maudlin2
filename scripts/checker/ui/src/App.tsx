import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Nav } from './components/Nav'
import { NotPorted } from './components/NotPorted'
import { PAGES } from './lib/routes'

// Each ported page, by its path; the rest show where the old page is
const PORTED: Record<string, () => ReactNode> = {}

export function App() {
  return (
    <>
      <Nav />
      <Routes>
        <Route path="/" element={<Navigate to="/workbench" replace />} />
        {PAGES.map((p) => (
          <Route key={p.path} path={`${p.path}/*`} element={PORTED[p.path] ? PORTED[p.path]() : <NotPorted page={p} />} />
        ))}
        <Route path="*" element={<Navigate to="/workbench" replace />} />
      </Routes>
    </>
  )
}
