// The checker's React app (Oct 21). Built into dist/, which is committed: production serves it as files, with no build
// step. `npm run dev` serves it with hot reload and sends the API to a checker on CHECKER (default 127.0.0.1:8799): run a
// second scripts/validate.py --port 8799 for that, never the live one on 8766, whose undo stack is the person's.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const checker = process.env.CHECKER ?? 'http://127.0.0.1:8799'
const api = ['/workbench', '/motif-board', '/motif-verdict', '/verdict', '/critique', '/checkpoint', '/undo', '/entities',
  '/experiment-verdict', '/motif-export', '/checker/static']

export default defineConfig({
  base: '/ui/',
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 900 },
  server: {
    proxy: Object.fromEntries([...api.map((p) => [p, checker]), ['^/[a-z-]+\\.json', checker]]),
  },
})
