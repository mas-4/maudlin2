// 🧰 The motif workbench: every motif page's work in one window. The motifs as a tree (left), the open motifs
// (middle), an inbox of decisions (right), the shelf of groups and genres above, and drag-and-drop between them all
import { useEffect, useRef, type PointerEvent as RPE } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DragLayer } from './DragLayer'
import { HoverCard } from './bits'
import { Inbox } from './Inbox'
import { currentModel, useWorkbench } from './model'
import { openMotif } from './ops'
import { Panels } from './Panels'
import { Shelf } from './Shelf'
import { setWB, useWB } from './store'
import { TopBar } from './TopBar'
import type { JudgeItem } from './types'
import { Tree } from './Tree'
import { WhyBar } from './tabs/Proposals'
import { onUndo } from '../lib/undo'
import { client, useJSON } from '../lib/queries'
import './workbench.css'

export function Workbench() {
  const { model, error } = useWorkbench()
  const cols = useWB((s) => s.cols)
  const main = useRef<HTMLElement>(null)
  const [params, setParams] = useSearchParams()
  // Others' changes (the hourly run filing claims, the worker): the index's version, read every 30 s, against the one
  // this state was read at. Ahead of it, the state and the claims to judge are read again; the card on screen stays
  // (Oct 22: the claims to judge were read once and never again while the tab stayed open)
  const iv = useJSON<{ version: number }>('/index-version.json', undefined, { refetchInterval: 30_000, staleTime: 0 })
  const have = model?.data.version
  useEffect(() => {
    if (iv.data && have !== undefined && iv.data.version > have) {
      void client.invalidateQueries({ queryKey: ['/workbench.json'] })
      void client.invalidateQueries({ queryKey: ['/workbench-queue.json', { kind: 'judge' }] })
    }
  }, [iv.data, have])
  // an undo takes decisions back: the filings it left unticked are waiting again, and so are the doubted ones it
  // un-confirmed (still ticked, but in the claims to judge again: Oct 24, a ✓ on a doubted filing undone stayed
  // hidden), so off this session's decided set (the old workbench kept them hidden until a reload)
  useEffect(() => onUndo(() => {
    const m = currentModel()
    if (!m) return
    const open = new Set(m.data.entries.flatMap((e) => e.claims.filter((c) => !c.checked).map((c) => c.claim + '|' + e.id)))
    for (const x of client.getQueryData<JudgeItem[]>(['/workbench-queue.json', { kind: 'judge' }]) ?? [])
      for (const r of x.reasons) if (r.kind === 'doubted') open.add(x.claim + '|' + r.id)
    setWB((s) => ({ decided: s.decided.filter((k) => !open.has(k)) }))
  }), [])
  // opened from a link (↗, a middle click): the claim or motif it names
  useEffect(() => {
    if (!model) return
    const motif = params.get('motif'), claim = params.get('claim')
    if (motif && model.by[motif]) openMotif(motif)
    if (claim) setWB({ claim: { claim }, tab: 'claim' })
    if (motif || claim) setParams({}, { replace: true })
  }, [model, params, setParams])
  useEffect(() => { // the page is the whole window: the panes scroll, not the page
    document.body.classList.add('wb-page')
    return () => document.body.classList.remove('wb-page')
  }, [])
  // adjustable columns: drag the bars between the panes; the widths are remembered, capped to the window
  const resize = (side: 'left' | 'right') => (ev: RPE<HTMLDivElement>) => {
    ev.preventDefault()
    const bar = ev.currentTarget, start = ev.clientX, box = main.current!.getBoundingClientRect()
    const was = { left: main.current!.querySelector('.tree-pane')!.getBoundingClientRect().width, right: main.current!.querySelector('.inbox-pane')!.getBoundingClientRect().width }
    try { bar.setPointerCapture(ev.pointerId) } catch { /* a synthetic or ended pointer */ }
    document.body.classList.add('resizing')
    const move = (e: PointerEvent) => {
      const dx = e.clientX - start, max = box.width * 0.6
      setWB({ cols: side === 'left' ? { ...was, left: Math.min(max, Math.max(180, was.left + dx)) } : { ...was, right: Math.min(max, Math.max(240, was.right - dx)) } })
    }
    const done = () => { bar.removeEventListener('pointermove', move); document.body.classList.remove('resizing') }
    bar.addEventListener('pointermove', move)
    bar.addEventListener('pointerup', done, { once: true })
    bar.addEventListener('lostpointercapture', done, { once: true })
  }
  const style = cols ? { ['--left' as string]: `min(${cols.left}px, 35vw)`, ['--right' as string]: `min(${cols.right}px, 45vw)` } : undefined
  return (
    <div className="wb">
      <TopBar />
      <Shelf />
      {error && !model && <p className="faint">😬 couldn’t load the index: {(error as Error).message}</p>}
      <main className="wb-main" ref={main} style={style}>
        <Tree />
        <div className="colbar" title="drag to resize (double-click: back to the default)" onPointerDown={resize('left')} onDoubleClick={() => setWB({ cols: null })} />
        <Panels />
        <div className="colbar" title="drag to resize (double-click: back to the default)" onPointerDown={resize('right')} onDoubleClick={() => setWB({ cols: null })} />
        <Inbox />
      </main>
      <DragLayer />
      <HoverCard />
      <WhyBar />
    </div>
  )
}
