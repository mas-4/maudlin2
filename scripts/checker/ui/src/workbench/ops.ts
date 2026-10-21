// What the workbench does, shared by the tree, the panels, the inbox and the drag menus
import { ask, sure, toast } from '../components/Feedback'
import { client } from '../lib/queries'
import { act, batch } from './act'
import { currentModel, MAX_OPEN, motifsOf } from './model'
import { getWB, mark, setWB } from './store'
import type { Action, WBState } from './types'

const name = (id: string) => currentModel()?.by[id]?.name ?? id

// ---------- opening motifs ----------
/** Open a motif in the outlined panel, or beside the others (⧉, Shift/Ctrl-click); one already open is just shown */
export function openMotif(id: string, beside = false) {
  const m = currentModel()
  if (!m?.by[id]) return
  const s = getWB()
  const open = [...s.open]
  let active = s.active
  const at = open.indexOf(id)
  if (at >= 0) active = at
  else if (beside || !open.length) {
    open.push(id)
    if (open.length > MAX_OPEN) open.shift()
    active = open.length - 1
  } else {
    active = Math.min(active, open.length - 1)
    open[active] = id
  }
  setWB({ open, active, sel: {}, selLast: {} })
  requestAnimationFrame(() =>
    document.querySelector(`.panel[data-panel="${active}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }),
  )
}

export function closePanel(i: number) {
  const s = getWB()
  const open = s.open.filter((_, k) => k !== i)
  setWB({ open, active: s.active >= i && s.active > 0 ? s.active - 1 : s.active, sel: {}, selLast: {} })
}

/** A motif made with claims, then opened beside the ones open, to work on */
export async function makeNew(nameOf: string, claims: Record<string, unknown>[]) {
  const before = new Set(currentModel()?.data.entries.map((e) => e.id))
  if (!(await act({ action: 'new_with', name: nameOf, claims }, `✨ made “${nameOf}”`))) return false
  const made = client.getQueryData<WBState>(['/workbench.json', {}])?.entries.find((e) => !before.has(e.id))
  if (made) openMotif(made.id, true)
  return true
}

/** A new motif with nothing in it yet, opened */
export async function addMotif(anchor?: Element | null) {
  const n = await ask('Name the new motif', '', { anchor })
  if (!n) return
  const before = new Set(currentModel()?.data.entries.map((e) => e.id))
  if (await act({ action: 'add', name: n }, `✨ made “${n}”`)) {
    const made = client.getQueryData<WBState>(['/workbench.json', {}])?.entries.find((e) => !before.has(e.id))
    if (made) openMotif(made.id)
  }
}

/** A new group with these motifs in it, named in a card by the drop (one undo step) */
export async function newGroupOf(anchor: Element | null, ids: string[]) {
  const n = await ask(`Name the new group (${ids.length} motifs in it)`, '', { anchor })
  if (!n) return false
  await act({ action: 'group_new', name: n, ids }, `📁 new group ${n}, with ${ids.length} in it`)
  return true
}

// ---------- claims ----------
/** A claim put on hold or taken off it: the queues that list it are read again */
export function holdClaim(claim: string, on: boolean) {
  const from = getWB().tab === 'sure' ? { from: 'sure' } : {} // held from ✅ sure: the tab's tally counts it as needing you
  return act({ action: on ? 'hold' : 'unhold', claim, ...from }, on ? '⏸ on hold: in ⏸ held' : '▶ off hold: back in the queues', ['judge', 'held'])
}

/** The quick lists' decisions as one undoable step: [['claim|motif', 'yes' or 'out']] */
export function quickDecide(pairs: [string, 'yes' | 'out'][], done: string, extra?: Record<string, unknown>, more: Action[] = []) {
  const steps: Action[] = pairs.map(([k, answer]) => {
    const i = k.lastIndexOf('|')
    const claim = k.slice(0, i), id = k.slice(i + 1)
    mark('decided', k)
    return answer === 'yes' ? { action: 'check', claim, id, answer: 'yes' } : { action: 'unfile', claim, id }
  })
  steps.push(...more)
  setWB({ checkHere: null })
  return batch(steps, done, extra, ['judge', 'held'])
}

/** Open a claim in 🔍 claim; from a list, the list and where you were in it are kept for ← back */
export function openClaim(claim: string, extra: { src?: string; ref?: string } = {}) {
  const s = getWB()
  const inbox = document.querySelector('.inbox-scroll')
  if (s.tab !== 'claim') {
    history.pushState({ wb: 'claim' }, '')
    setWB({ back: { tab: s.tab, scroll: inbox?.scrollTop ?? 0 } })
  }
  setWB({ claim: { claim, ...extra }, tab: 'claim', claimQ: '' })
}

export function goBack() {
  const b = getWB().back
  if (!b) return
  setWB({ back: null, tab: b.tab })
  requestAnimationFrame(() => {
    const inbox = document.querySelector('.inbox-scroll')
    if (inbox) inbox.scrollTop = b.scroll
  })
}
addEventListener('popstate', () => {
  if (getWB().back) goBack()
})

/** A claim pinned in the claims to judge, now under other words */
export function renamed(old: string, text: string) {
  const s = getWB()
  if (s.checkHere?.claim === old) setWB({ checkHere: { ...s.checkHere, claim: text } })
  if (s.claim?.claim === old) setWB({ claim: { ...s.claim, claim: text } })
}

/** What the 🔍 claim's own buttons do: file it, check it, take it out, a new motif with it, reword it */
export async function claimAction(kind: string, id = '', anchor?: Element | null) {
  const m = currentModel(), c = getWB().claim
  if (!m || !c) return
  const ins = motifsOf(m, c.claim), first = ins[0]
  const rec = first?.claims.find((x) => x.claim === c.claim)
  const src = rec?.source || c.src || '', ref = rec?.ref || c.ref || ''
  const fileHere = (to: string): Action => first ? { action: 'also', claim: c.claim, source: first.id, target: to }
    : { action: 'file', claim: c.claim, id: to, source: src, ref }
  if (kind === 'check' || kind === 'unfile') mark('decided', c.claim + '|' + id) // off the claims to judge's doubts too
  if (kind === 'check') return act({ action: 'check', claim: c.claim, id, answer: 'yes' }, '✓ checked')
  if (kind === 'unfile') return act({ action: 'unfile', claim: c.claim, id }, `✕ out of “${name(id)}”`)
  if (kind === 'add') return act(fileHere(id), `＋ filed in “${name(id)}”`)
  const asNew = { claim: c.claim, source: first?.id ?? '', src, ref, mode: 'also' }
  if (kind === 'newnamed') {
    const n = getWB().claimQ.trim()
    if (!n) return
    setWB({ claimQ: '' })
    return makeNew(n, [asNew])
  }
  if (kind === 'new') {
    const n = await ask('Name the new motif', getWB().claimQ.trim() || c.claim.slice(0, 80), { anchor })
    return n && makeNew(n, [asNew])
  }
  if (kind === 'nomotif') {
    return (await sure('No motif: take it out of every motif, for good?', 'yes, do it', anchor)) && act({ action: 'no_motif', claim: c.claim }, '∅ no motif')
  }
}

/** A claim reworded (our summary, never the source's words); everything that pinned it follows */
export async function correctClaim(old: string, text: string) {
  if (!text || text === old) return
  if (await act({ action: 'correct', claim: old, text }, '✎ corrected')) renamed(old, text)
}

/** A claim split by hand: one new claim per line, each one side's assertion in its own voice; the original stays as the
 * telling and the new ones are filed at the next hourly run */
export async function splitByHand(claim: string, anchor?: Element | null) {
  const text = await ask('Split it: one claim per line, each one side’s assertion in its own voice', '', { multiline: true, anchor })
  const children = (text ?? '').split('\n').map((x) => x.trim()).filter(Boolean)
  if (children.length) return act({ action: 'split', claim, children }, `✂️ split into ${children.length}: filed at the next hourly run`)
}

export function copyText(text: string) {
  // the clipboard API only works on https or localhost (the checker is opened over the LAN too) and can be refused:
  // then the old way, a hidden text box selected and copied
  const old = () => {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok ? Promise.resolve() : Promise.reject(new Error('copy refused'))
  }
  const p = navigator.clipboard && window.isSecureContext ? navigator.clipboard.writeText(text).catch(old) : old()
  return p.then(() => toast('📋 copied'), () => toast('😬 couldn’t copy', true))
}

/** Open an inbox tab; its list is read fresh */
export function setTab(tab: string) {
  setWB({ back: null, tab })
  void client.invalidateQueries({ queryKey: ['/workbench-queue.json', { kind: tab }] })
}
