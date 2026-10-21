// The checker's toast (after each change, with ↶ undo) and its in-page ask and confirm cards, in place of the
// browser's prompt and confirm: shown beside what was pressed, Enter saves, Shift+Enter a new line, Esc or a click
// elsewhere cancels.
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { undo } from '../lib/undo'

interface ToastState { text: string; bad: boolean; withUndo: boolean; n: number }
interface AskState {
  kind: 'ask' | 'sure'
  label: string
  value: string
  multiline: boolean
  empty: boolean
  ok: string
  rect: DOMRect | null
  resolve: (v: string | null) => void
}

let toastState: ToastState | null = null
let askState: AskState | null = null
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())
const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => listeners.delete(l)
}

let toastTimer: number | undefined
export function toast(text: string, bad = false, withUndo = false) {
  toastState = { text, bad, withUndo, n: (toastState?.n ?? 0) + 1 }
  emit()
  clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toastState = null
    emit()
  }, bad ? 7000 : 4500)
}

// The element last pressed: an ask with no anchor of its own opens beside it
let lastPressed: Element | null = null
document.addEventListener('pointerdown', (ev) => {
  const t = ev.target as Element | null
  if (t && !t.closest('.ask-card')) lastPressed = t
}, true)

function open(state: Omit<AskState, 'resolve' | 'rect'>, anchor?: Element | null): Promise<string | null> {
  askState?.resolve(null)
  const a = [anchor, lastPressed].find((x) => x && x.isConnected) ?? null
  return new Promise((resolve) => {
    askState = { ...state, rect: a ? a.getBoundingClientRect() : null, resolve }
    emit()
  })
}

/** A line of text asked for in place. Empty gives null, unless `empty` (then '' can be saved: a description cleared) */
export function ask(label: string, value = '', opts: { multiline?: boolean; empty?: boolean; anchor?: Element | null } = {}) {
  return open({ kind: 'ask', label, value, multiline: !!opts.multiline, empty: !!opts.empty, ok: '💾 save' }, opts.anchor)
}

/** Yes or no, asked in place */
export function sure(text: string, ok = 'yes, do it', anchor?: Element | null): Promise<boolean> {
  return open({ kind: 'sure', label: text, value: '', multiline: false, empty: false, ok }, anchor).then((v) => v !== null)
}

function close(value: string | null) {
  const a = askState
  askState = null
  emit()
  a?.resolve(value)
}

export function Feedback() {
  const t = useSyncExternalStore(subscribe, () => toastState)
  const a = useSyncExternalStore(subscribe, () => askState)
  return (
    <>
      {t && (
        <div className={'toast' + (t.bad ? ' bad' : '')} key={t.n} role="status">
          {t.text}
          {t.withUndo && (
            <button className="mini" onClick={() => void undo()}>
              ↶ undo
            </button>
          )}
        </div>
      )}
      {a && <AskCard a={a} />}
    </>
  )
}

function AskCard({ a }: { a: AskState }) {
  const ref = useRef<HTMLFormElement>(null)
  const field = useRef<HTMLInputElement & HTMLTextAreaElement>(null)
  const [value, setValue] = useState(a.value)
  const [pos, setPos] = useState<{ left: number; top: number }>({ left: -9999, top: -9999 })
  useLayoutEffect(() => {
    const m = ref.current!.getBoundingClientRect()
    const r = a.rect ?? { left: innerWidth / 2 - 180, top: innerHeight / 3, bottom: innerHeight / 3 }
    let y = r.bottom + 6
    if (y + m.height > innerHeight - 8) y = Math.max(8, r.top - m.height - 6)
    setPos({ left: Math.max(8, Math.min(r.left, innerWidth - m.width - 8)), top: y })
    if (field.current) {
      field.current.focus()
      field.current.select()
    } else ref.current!.querySelector('button')?.focus()
  }, [a])
  useEffect(() => {
    const away = (ev: PointerEvent) => {
      if (ref.current && !ref.current.contains(ev.target as Node)) close(null)
    }
    document.addEventListener('pointerdown', away, true)
    return () => document.removeEventListener('pointerdown', away, true)
  }, [])
  const submit = () => {
    if (a.kind === 'sure') return close('yes')
    const v = value.trim()
    close(v || (a.empty ? '' : null))
  }
  return (
    <form
      ref={ref}
      className="ask-card"
      style={pos}
      onSubmit={(ev) => {
        ev.preventDefault()
        submit()
      }}
      onKeyDown={(ev) => {
        if (ev.key === 'Escape') {
          ev.preventDefault()
          close(null)
        }
        if (ev.key === 'Enter' && !ev.shiftKey && (ev.target as HTMLElement).tagName === 'TEXTAREA') {
          ev.preventDefault()
          submit()
        }
      }}
    >
      {a.kind === 'ask' ? <label>{a.label}</label> : <p>{a.label}</p>}
      {a.kind === 'ask' &&
        (a.multiline ? (
          <textarea ref={field} rows={3} value={value} onChange={(e) => setValue(e.target.value)} />
        ) : (
          <input ref={field} type="text" value={value} onChange={(e) => setValue(e.target.value)} />
        ))}
      <div className="ask-btns">
        <button className={'btn ' + (a.kind === 'ask' ? 'yes' : 'no')} type="submit">
          {a.ok}
        </button>
        <button className="btn" type="button" onClick={() => close(null)}>
          cancel
        </button>
        {a.kind === 'ask' && <span className="faint">Enter saves · Esc cancels</span>}
      </div>
    </form>
  )
}
