import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Nav } from './components/Nav'
import { PAGES } from './lib/routes'
import { Boundary } from './components/Boundary'
import { Feedback } from './components/Feedback'
import { Workbench } from './workbench/Workbench'
import { Dashboard } from './pages/dashboard/Dashboard'
import { Experiments } from './pages/experiments/Experiments'
import { Flow } from './pages/flow/Flow'
import { Labels } from './pages/labels/Labels'
import { Live } from './pages/live/Live'
import { MotifMap } from './pages/map/Map'
import { Names } from './pages/names/Names'

// Each page, by its path
const PAGE: Record<string, () => ReactNode> = {
  '/workbench': () => <Workbench />,
  '/map': () => <MotifMap />,
  '/dashboard': () => <Dashboard />,
  '/experiments': () => <Experiments />,
  '/flow': () => <Flow />,
  '/live': () => <Live />,
  '/names': () => <Names />,
  '/labels': () => <Labels />,
}

export function App() {
  return (
    <>
      <Nav />
      <Routes>
        <Route path="/" element={<Navigate to="/workbench" replace />} />
        {PAGES.map((p) => (
          <Route key={p.path} path={`${p.path}/*`} element={<Boundary key={p.path}>{PAGE[p.path]()}</Boundary>} />
        ))}
        <Route path="*" element={<Navigate to="/workbench" replace />} />
      </Routes>
      <Feedback />
    </>
  )
}
