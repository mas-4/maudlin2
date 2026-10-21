// Drag and drop with pointer events: a mouse drags after 6px, a touch after a 350ms hold (moving 8px first is a
// scroll). Hovering a drop target opens its choices beside the pointer; the way from the pointer to the menu keeps it
// open, so crossing other targets on the way doesn't swap it. Letting go on a choice runs it; on the target itself, its
// only choice runs, or the menu stays pinned to click. The pane under the pointer scrolls near its edges. Esc cancels.
// Sources carry data-drag (motif, group, claim), targets data-drop (motif, claim, sameclaim, group, facet, newmotif,
// nomotif, trash), as the old workbench did, so the choices (zones.ts) read the same attributes.
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { itemOf, label, zones, zoneText } from './zones'
import type { DragItem, Zone } from './types'

// whether a motif is being carried (the tree shows its tray of groups for it)
let carrying: DragItem | null = null
const listeners = new Set<() => void>()
export function useCarrying() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => carrying,
  )
}
function setCarrying(v: DragItem | null) {
  carrying = v
  listeners.forEach((l) => l())
}

let lastDragEnd = 0
/** A click right after a drag ended is the drag's own let-go, not a click */
export const justDragged = () => Date.now() - lastDragEnd < 250

interface Menu { list: Zone[]; target: HTMLElement; pinned: boolean; x: number; y: number; from: { x: number; y: number } }

export function DragLayer() {
  const ghost = useRef<HTMLDivElement>(null)
  const menuEl = useRef<HTMLDivElement>(null)
  const [menu, setMenu] = useState<Menu | null>(null)
  const menuRef = useRef<Menu | null>(null)
  menuRef.current = menu

  useEffect(() => {
    type Drag = { h: HTMLElement; x: number; y: number; on: boolean; touch: boolean; timer?: number; id: number; item?: DragItem | null;
      scroll: number; scroller?: Element | null }
    let drag: Drag | null = null
    const show = (m: Menu | null) => {
      menuRef.current = m
      setMenu(m)
    }
    const clearTargets = () => document.querySelectorAll('.dz-target').forEach((x) => x.classList.remove('dz-target'))
    const onTheWay = (x: number, y: number) => {
      const m = menuRef.current, el = menuEl.current
      if (!m || !el) return false
      const r = el.getBoundingClientRect(), pad = 14
      return x >= Math.min(r.left, m.from.x) - pad && x <= Math.max(r.right, m.from.x) + pad
        && y >= Math.min(r.top, m.from.y) - pad && y <= Math.max(r.bottom, m.from.y) + pad
    }
    const start = (ev: PointerEvent) => {
      if (!drag) return
      drag.item = itemOf(drag.h)
      if (!drag.item) { drag = null; return } // an empty group: nothing to carry
      drag.on = true
      document.body.classList.add('dragging')
      ghost.current!.hidden = false
      ghost.current!.textContent = label(drag.item)
      setCarrying(drag.item)
      move(ev)
    }
    const move = (ev: PointerEvent) => {
      if (!drag?.item) return
      ghost.current!.style.left = ev.clientX - 12 + 'px' // below-left of the pointer (the choices pop up to its right)
      ghost.current!.style.top = ev.clientY + 14 + 'px'
      const el = document.elementFromPoint(ev.clientX, ev.clientY)
      document.querySelectorAll('.dz-zone.hot').forEach((z) => z.classList.remove('hot'))
      const z = el?.closest('.dz-zone')
      const m = menuRef.current
      if (z) z.classList.add('hot')
      else if (!onTheWay(ev.clientX, ev.clientY) || (el && el.closest('[data-drop]') === m?.target)) {
        const t = el?.closest<HTMLElement>('[data-drop]')
        if (t && t !== m?.target) {
          clearTargets()
          const list = zones(drag.item, t)
          if (list.length) {
            t.classList.add('dz-target')
            show({ list, target: t, pinned: false, ...place(ev.clientX, ev.clientY), from: { x: ev.clientX, y: ev.clientY } })
          } else show(null)
        } else if (!t && !el?.closest('.dz-menu')) {
          clearTargets()
          show(null)
        }
      }
      const sc = el?.closest('[data-scroll]')
      drag.scroll = 0
      if (sc) {
        const r = sc.getBoundingClientRect()
        drag.scroll = ev.clientY < r.top + 50 ? -1 : ev.clientY > r.bottom - 50 ? 1 : 0
        drag.scroller = sc
      }
    }
    const end = (ev: PointerEvent | KeyboardEvent, cancel: boolean) => {
      if (!drag) return
      clearTimeout(drag.timer)
      const was = drag
      drag = null
      document.body.classList.remove('dragging')
      ghost.current!.hidden = true
      setCarrying(null)
      clearTargets()
      if (!was.on) return
      lastDragEnd = Date.now()
      if (cancel || !('clientX' in ev)) { show(null); return }
      const el = document.elementFromPoint(ev.clientX, ev.clientY)
      const m = menuRef.current
      const z = el?.closest<HTMLElement>('.dz-zone')
      if (z && m) {
        const run = m.list[+z.dataset.zone!]
        show(null)
        void run?.run()
        return
      }
      const t = el?.closest('[data-drop]')
      if (t && m && t === m.target) {
        if (m.list.length === 1) {
          show(null)
          void m.list[0].run()
          return
        }
        show({ ...m, pinned: true, ...place(ev.clientX, ev.clientY), from: { x: ev.clientX, y: ev.clientY } }) // let go on the target: the choices stay up
        return
      }
      show(null)
    }
    const down = (ev: PointerEvent) => {
      if (ev.button !== 0 || menuRef.current?.pinned) return
      const t = ev.target as HTMLElement
      const h = t.closest<HTMLElement>('[data-drag]')
      if (!h || t.closest('button, input, textarea, select, a, dialog, .dz-menu')) return
      drag = { h, x: ev.clientX, y: ev.clientY, on: false, touch: ev.pointerType === 'touch', id: ev.pointerId, scroll: 0 }
      if (drag.touch) drag.timer = window.setTimeout(() => { if (drag && !drag.on) start(ev) }, 350)
    }
    const pmove = (ev: PointerEvent) => {
      if (!drag || ev.pointerId !== drag.id) return
      if (!drag.on) {
        const far = Math.hypot(ev.clientX - drag.x, ev.clientY - drag.y)
        if (drag.touch) {
          if (far > 8) { clearTimeout(drag.timer); drag = null }
          return
        }
        if (far < 6) return
        start(ev)
        if (!drag) return
      }
      ev.preventDefault()
      move(ev)
    }
    const tmove = (ev: TouchEvent) => { if (drag?.on) ev.preventDefault() }
    const up = (ev: PointerEvent) => end(ev, false)
    const cancel = (ev: PointerEvent) => end(ev, true)
    const key = (ev: KeyboardEvent) => {
      if (ev.key !== 'Escape') return
      if (drag) end(ev, true)
      show(null)
    }
    const clickAway = (ev: MouseEvent) => {
      if (justDragged()) { // the click a browser fires at the end of any drag: the drag's own let-go, swallowed
        ev.preventDefault()
        ev.stopPropagation()
        return
      }
      if (menuRef.current?.pinned && !(ev.target as Element).closest('.dz-menu')) show(null)
    }
    const tick = window.setInterval(() => {
      if (drag?.on && drag.scroll && drag.scroller) drag.scroller.scrollTop += drag.scroll * 14
    }, 30)
    document.addEventListener('pointerdown', down)
    document.addEventListener('pointermove', pmove, { passive: false })
    document.addEventListener('touchmove', tmove, { passive: false })
    document.addEventListener('pointerup', up)
    document.addEventListener('pointercancel', cancel)
    document.addEventListener('keydown', key)
    document.addEventListener('click', clickAway, true)
    return () => {
      clearInterval(tick)
      document.removeEventListener('pointerdown', down)
      document.removeEventListener('pointermove', pmove)
      document.removeEventListener('touchmove', tmove)
      document.removeEventListener('pointerup', up)
      document.removeEventListener('pointercancel', cancel)
      document.removeEventListener('keydown', key)
      document.removeEventListener('click', clickAway, true)
    }
  }, [])

  // the menu beside the pointer, moved left of it near the window's right edge (measured once drawn)
  useEffect(() => {
    const el = menuEl.current
    if (!el || !menu) return
    const r = el.getBoundingClientRect()
    let x = menu.from.x + 16, y = menu.from.y - 14
    if (x + r.width > innerWidth - 8) x = Math.max(8, menu.from.x - r.width - 16)
    if (y + r.height > innerHeight - 8) y = Math.max(8, innerHeight - r.height - 8)
    el.style.left = x + 'px'
    el.style.top = y + 'px'
  }, [menu])

  return (
    <>
      <div ref={ghost} className="ghost" hidden />
      {menu && (
        <div ref={menuEl} className="dz-menu" style={{ left: menu.x, top: menu.y }}>
          <div className="dz-title">{menu.pinned ? 'drop it as…' : 'let go on a choice'}</div>
          {menu.list.map((z, k) => (
            <button key={k} className="dz-zone" data-zone={k} title={z.label}
              onClick={() => { if (!menu.pinned) return; setMenu(null); void z.run() }}>
              {zoneText(z)}
            </button>
          ))}
          {menu.pinned && <button className="dz-zone dz-cancel" onClick={() => setMenu(null)}>cancel</button>}
        </div>
      )}
    </>
  )
}

const place = (x: number, y: number) => ({ x: x + 16, y: y - 14 })
