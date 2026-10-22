// The checker's browser tests (Oct 22, the person: "go ahead and add playwright"): a real browser clicks, presses and
// drags through the React app as the person would, on a fresh copy of the data (sandbox.py), never the live checker.
// Run with `npm run e2e` (it builds the app first): the copy is made, a checker started on it at port 8798, the tests
// run one at a time (they change the copy), and the checker stops after.
import { defineConfig } from '@playwright/test'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ROOT = join(import.meta.dirname, '..', '..', '..')
const PY = join(ROOT, '.venv', 'bin', 'python')
const COPY = join(tmpdir(), 'maudlin-e2e-sandbox')
const PORT = 8798

export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  workers: 1, // one checker on one copy of the data, which the tests change: one at a time
  reporter: [['list']],
  use: { baseURL: `http://127.0.0.1:${PORT}`, viewport: { width: 1366, height: 768 } }, // a laptop's screen
  webServer: {
    command: `${PY} ${join(ROOT, 'scripts', 'checker', 'ui', 'sandbox.py')} ${COPY} && MAUDLIN_DATA=${COPY} MAUDLIN_TRACE=off ${PY} ${join(ROOT, 'scripts', 'validate.py')} --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/version.json`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
