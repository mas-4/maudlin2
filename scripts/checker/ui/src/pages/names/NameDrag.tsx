// Dragging one subject onto another on the names page, the workbench's way (src/workbench/DragLayer.tsx) on a smaller
// scale: a mouse drags after 6px, a touch after a 350ms hold (moving 8px first is a scroll). Hovering a subject opens
// its choices beside the pointer, each saying in full what it does; the way from the pointer to the menu keeps it open,
// so crossing other subjects on the way doesn't swap it. Letting go on a choice runs it; on the subject itself, its
// only choice runs, or the menu stays pinned to click. The window scrolls near its top and bottom edges. Esc cancels.
// Sources carry data-nm-drag (a subject's name line, or one of its other names), targets data-nm-drop (a subject's
// card), so the workbench's engine, keyed on data-drag and data-drop, never picks them up.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

/** What is carried: a subject (by its name line), or one of a subject's other names */
export interface NameItem { name: string; alias: boolean; of: string }
export interface Choice { label: string; say: string; run: () => unknown }

interface Menu { list: Choice[]; target: HTMLElement; pinned: boolean; from: { x: number; y: number } }

function itemOf(h: HTMLElement): NameItem | null {
  const name = h.dataset.name, of = h.dataset.of
  return name && of ? { name, of, alias: h.dataset.alias === '1' } : null
}

export function NameDrag({ choices }: { choices: (item: NameItem, target: string) => Choice[] }) {
  const ghost = useRef<HTMLDivElement>(null)
  const menuEl = useRef<HTMLDivElement>(null)
  const [menu, setMenu] = useState<Menu | null>(null)
  const menuRef = useRef<Menu | null>(null)
  const choicesRef = useRef(choices)
  useEffect(() => {
    choicesRef.current = choices
  }, [choices])

  useEffect(() => {
    type Drag = { h: HTMLElement; x: number; y: number; on: boolean; touch: boolean; id: number; timer?: number; item?: NameItem | null; scroll: number }
    let drag: Drag | null = null
    let lastEnd = 0
    const show = (m: Menu | null) => {
      menuRef.current = m
      setMenu(m)
    }
    const clearTarget = () => document.querySelectorAll('.nm-target').forEach((x) => x.classList.remove('nm-target'))
    const onTheWay = (x: number, y: number) => {
      const m = menuRef.current, el = menuEl.current
      if (!m || !el) return false
      const r = el.getBoundingClientRect(), pad = 14
      return x >= Math.min(r.left, m.from.x) - pad && x <= Math.max(r.right, m.from.x) + pad
        && y >= Math.min(r.top, m.from.y) - pad && y <= Math.max(r.bottom, m.from.y) + pad
    }
    const move = (ev: PointerEvent) => {
      if (!drag?.item) return
      ghost.current!.style.left = ev.clientX - 12 + 'px' // below-left of the pointer (the choices open to its right)
      ghost.current!.style.top = ev.clientY + 14 + 'px'
      const el = document.elementFromPoint(ev.clientX, ev.clientY)
      document.querySelectorAll('.nm-zone.hot').forEach((z) => z.classList.remove('hot'))
      const z = el?.closest('.nm-zone')
      const m = menuRef.current
      if (z) z.classList.add('hot')
      else if (!onTheWay(ev.clientX, ev.clientY) || (el && el.closest('[data-nm-drop]') === m?.target)) {
        const t = el?.closest<HTMLElement>('[data-nm-drop]')
        if (t && t !== m?.target) {
          clearTarget()
          const list = choicesRef.current(drag.item, t.dataset.name ?? '')
          if (list.length) {
            t.classList.add('nm-target')
            show({ list, target: t, pinned: false, from: { x: ev.clientX, y: ev.clientY } })
          } else show(null)
        } else if (!t && !el?.closest('.nm-menu')) {
          clearTarget()
          show(null)
        }
      }
      drag.scroll = ev.clientY < 50 ? -1 : ev.clientY > innerHeight - 50 ? 1 : 0
    }
    const start = (ev: PointerEvent) => {
      if (!drag) return
      drag.item = itemOf(drag.h)
      if (!drag.item) {
        drag = null
        return
      }
      drag.on = true
      document.body.classList.add('nm-dragging')
      ghost.current!.hidden = false
      ghost.current!.textContent = '🗣️ ' + drag.item.name
      move(ev)
    }
    const end = (ev: PointerEvent | KeyboardEvent, cancel: boolean) => {
      if (!drag) return
      clearTimeout(drag.timer)
      const was = drag
      drag = null
      document.body.classList.remove('nm-dragging')
      ghost.current!.hidden = true
      clearTarget()
      if (!was.on) return
      lastEnd = Date.now()
      if (cancel || !('clientX' in ev)) {
        show(null)
        return
      }
      const el = document.elementFromPoint(ev.clientX, ev.clientY)
      const m = menuRef.current
      const z = el?.closest<HTMLElement>('.nm-zone')
      if (z && m) {
        const choice = m.list[+z.dataset.zone!]
        show(null)
        void choice?.run()
        return
      }
      if (m && el?.closest('[data-nm-drop]') === m.target) {
        if (m.list.length === 1) {
          show(null)
          void m.list[0].run()
          return
        }
        show({ ...m, pinned: true, from: { x: ev.clientX, y: ev.clientY } }) // let go on the subject: the choices stay up
        return
      }
      show(null)
    }
    const down = (ev: PointerEvent) => {
      if (ev.button !== 0 || menuRef.current?.pinned) return
      const t = ev.target as HTMLElement
      const h = t.closest<HTMLElement>('[data-nm-drag]')
      if (!h || t.closest('button, input, textarea, select, a, .nm-menu')) return
      drag = { h, x: ev.clientX, y: ev.clientY, on: false, touch: ev.pointerType === 'touch', id: ev.pointerId, scroll: 0 }
      if (drag.touch) drag.timer = window.setTimeout(() => { if (drag && !drag.on) start(ev) }, 350)
    }
    const pmove = (ev: PointerEvent) => {
      if (!drag || ev.pointerId !== drag.id) return
      if (!drag.on) {
        const far = Math.hypot(ev.clientX - drag.x, ev.clientY - drag.y)
        if (drag.touch) {
          if (far > 8) {
            clearTimeout(drag.timer)
            drag = null
          }
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
    const click = (ev: MouseEvent) => {
      if (Date.now() - lastEnd < 250) { // the click a browser fires at the end of any drag: the drag's own let-go
        ev.preventDefault()
        ev.stopPropagation()
        return
      }
      if (menuRef.current?.pinned && !(ev.target as Element).closest('.nm-menu')) show(null)
    }
    const tick = window.setInterval(() => {
      if (drag?.on && drag.scroll) window.scrollBy(0, drag.scroll * 14)
    }, 30)
    document.addEventListener('pointerdown', down)
    document.addEventListener('pointermove', pmove, { passive: false })
    document.addEventListener('touchmove', tmove, { passive: false })
    document.addEventListener('pointerup', up)
    document.addEventListener('pointercancel', cancel)
    document.addEventListener('keydown', key)
    document.addEventListener('click', click, true)
    return () => {
      clearInterval(tick)
      document.body.classList.remove('nm-dragging')
      document.removeEventListener('pointerdown', down)
      document.removeEventListener('pointermove', pmove)
      document.removeEventListener('touchmove', tmove)
      document.removeEventListener('pointerup', up)
      document.removeEventListener('pointercancel', cancel)
      document.removeEventListener('keydown', key)
      document.removeEventListener('click', click, true)
    }
  }, [])

  // the menu beside the pointer, moved left of it near the window's right edge (measured once drawn)
  useLayoutEffect(() => {
    const el = menuEl.current
    if (!el || !menu) return
    el.style.left = '0px' // measured at its own width: squeezed against the edge it measures narrow
    el.style.top = '0px'
    const r = el.getBoundingClientRect()
    let x = menu.from.x + 16, y = menu.from.y - 14
    if (x + r.width > innerWidth - 8) x = Math.max(8, menu.from.x - r.width - 16)
    if (y + r.height > innerHeight - 8) y = Math.max(8, innerHeight - r.height - 8)
    el.style.left = x + 'px'
    el.style.top = y + 'px'
  }, [menu])

  const close = () => {
    menuRef.current = null
    setMenu(null)
  }
  return (
    <>
      <div ref={ghost} className="nm-ghost" hidden />
      {menu && (
        <div ref={menuEl} className="nm-menu" style={{ left: menu.from.x + 16, top: menu.from.y - 14 }}>
          <div className="nm-menu-title">{menu.pinned ? 'drop it as…' : 'let go on a choice'}</div>
          {menu.list.map((z, k) => (
            <button key={k} className="nm-zone" data-zone={k} title={z.label}
              onClick={() => {
                if (!menu.pinned) return
                close()
                void z.run()
              }}>
              <b>{z.label}</b>
              <span>{z.say}</span>
            </button>
          ))}
          {menu.pinned && <button className="nm-zone nm-cancel" onClick={close}>cancel</button>}
        </div>
      )}
    </>
  )
}
