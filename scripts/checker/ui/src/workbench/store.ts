// The workbench's own state in this browser tab: what's open, the views picked, selections and this session's
// decisions. The settings are kept in localStorage under the same keys as the old workbench ('wb-…'), so what was open
// there opens here.
import { useSyncExternalStore } from 'react'

const KEEP = ['open', 'view', 'sort', 'tab', 'folded', 'groupby', 'quickper', 'cols', 'shelf', 'similarOpen'] as const

function read<T>(k: string, d: T): T {
  try {
    const v = localStorage.getItem('wb-' + k)
    return v === null ? d : (JSON.parse(v) as T)
  } catch {
    return d
  }
}
function write(k: string, v: unknown) {
  try {
    localStorage.setItem('wb-' + k, JSON.stringify(v))
  } catch {
    // a private window
  }
}

export interface Shelf { kind: 'group' | 'genre'; id: string }
export interface WB {
  open: string[]
  active: number
  view: string
  sort: string
  groupby: 'group' | 'genre' | 'none'
  tab: string
  folded: string[]
  quickper: number
  cols: { left: number; right: number } | null
  shelf: number | null // the shelf's height
  shelfFilter: Shelf | null
  q: string
  msel: string[]
  mlast: string | null
  sel: Record<string, string[]> // per open motif: its selected claims
  selLast: Record<string, number | null>
  claim: { claim: string; src?: string; ref?: string } | null // the claim in 🔍 claim
  back: { tab: string; scroll: number } | null
  claimQ: string
  similarOpen: boolean // ≡ claims like this one, unfolded (kept: whoever opens it wants it each time)
  findQ: string
  unfiledQ: string
  tellingsFor: string | null
  // the claims to judge: where you are
  checkAt: number
  checkHere: { claim: string; source: string } | null
  checkBack: string | null
  checkTrail: string[]
  checkForward: string[]
  quickPage: Record<string, number>
  // this session's decisions, hidden at once
  decided: string[]
  rejected: string[]
  quickSkip: string[]
  unticked: string[]
  outTicked: string[]
}

const legacyTab = (t: string) => ({ check: 'judge', unchecked: 'judge', second: 'judge' } as Record<string, string>)[t] ?? t

let state: WB = {
  open: read<string[]>('open', []),
  active: 0,
  view: read('view', 'all'),
  sort: read('sort', 'size'),
  groupby: read('groupby', 'group'),
  tab: legacyTab(read('tab', 'judge')),
  folded: read<string[]>('folded', []),
  quickper: read('quickper', 25),
  cols: read('cols', null),
  shelf: read('shelf', null),
  shelfFilter: null,
  q: '',
  msel: [],
  mlast: null,
  sel: {},
  selLast: {},
  claim: null,
  back: null,
  claimQ: '',
  similarOpen: read('similarOpen', false),
  findQ: '',
  unfiledQ: '',
  tellingsFor: null,
  checkAt: 0,
  checkHere: null,
  checkBack: null,
  checkTrail: [],
  checkForward: [],
  quickPage: {},
  decided: [],
  rejected: [],
  quickSkip: [],
  unticked: [],
  outTicked: [],
}
const listeners = new Set<() => void>()

export function getWB(): WB {
  return state
}

export function setWB(change: Partial<WB> | ((s: WB) => Partial<WB>)) {
  const part = typeof change === 'function' ? change(state) : change
  state = { ...state, ...part }
  for (const k of KEEP) if (k in part) write(k, state[k])
  listeners.forEach((l) => l())
}

export function useWB<T>(pick: (s: WB) => T): T {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => pick(state),
  )
}

/** Add to or take from one of the session's sets of keys */
export function mark(set: 'decided' | 'rejected' | 'quickSkip' | 'unticked' | 'outTicked', key: string, on = true) {
  setWB((s) => {
    const has = s[set].includes(key)
    if (on === has) return {}
    return { [set]: on ? [...s[set], key] : s[set].filter((k) => k !== key) } as Partial<WB>
  })
}
