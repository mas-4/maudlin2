// What the workbench works out from the index: motifs by id, what rests on each, the motifs each claim is in, the views
import { useMemo } from 'react'
import { client, useJSON } from '../lib/queries'
import type { Entry, WBState } from './types'

export const SOURCE: Record<string, string> = { narrative: 'online', 'focus-group': 'focus group', shows: 'radio & podcasts' }
export const MAX_OPEN = 8
export const COLORS = 6

export interface Model {
  data: WBState
  by: Record<string, Entry>
  kids: Record<string, string[]>
  inClaim: Map<string, Entry[]> // claim text -> the motifs it's in
}

export function useWorkbench() {
  const q = useJSON<WBState>('/workbench.json')
  const model = useMemo<Model | null>(() => (q.data ? build(q.data) : null), [q.data])
  return { ...q, model }
}

export function build(data: WBState): Model {
  const by: Record<string, Entry> = {}
  const kids: Record<string, string[]> = {}
  const inClaim = new Map<string, Entry[]>()
  for (const e of data.entries) {
    by[e.id] = e
    for (const p of e.parents) (kids[p] ??= []).push(e.id)
    for (const c of e.claims) {
      const list = inClaim.get(c.claim)
      if (list) list.push(e)
      else inClaim.set(c.claim, [e])
    }
  }
  return { data, by, kids, inClaim }
}

export const motifsOf = (m: Model, claim: string): Entry[] => m.inClaim.get(claim) ?? []
export const isSingle = (m: Model, e: Entry) =>
  e.claims.length === 1 && !e.stands_alone && !e.parents.length && !(m.kids[e.id] ?? []).length
export const isEmpty = (m: Model, e: Entry) => !e.claims.length && !(m.kids[e.id] ?? []).length
export const noteState = (e: Entry) => (!e.note ? 'none' : ['model', 'claude'].includes(e.note_by ?? '') ? 'draft' : 'yours')
export const newCount = (e: Entry) => e.claims.filter((c) => c.new).length
export const groupName = (m: Model, id: string) => m.data.groups.find((g) => g.id === id)?.name ?? id

export const VIEWS: [string, string, (m: Model, e: Entry) => boolean][] = [
  ['all', '🗂️ all', () => true],
  ['singles', '1️⃣ singles', isSingle],
  ['nonote', '📝 no note', (_m, e) => noteState(e) === 'none'],
  ['drafts', '🗒️ draft notes', (_m, e) => noteState(e) === 'draft'],
  ['model', '🤖 model-made', (_m, e) => !e.curated && e.done !== 'done'], // made and named by the model, not reviewed yet
  ['todo', '⏳ not done', (_m, e) => e.done !== 'done'],
  ['new', '🆕 new claims', (_m, e) => e.done === 'new'],
  ['unchecked', '❔ unchecked', (_m, e) => e.claims.some((c) => !c.checked)],
  ['nogenre', '🎭 no genre', (_m, e) => !e.facets?.genre],
  ['empty', '🫙 empty', isEmpty],
]

export const SORTS: Record<string, (a: Entry, b: Entry) => number> = {
  size: (a, b) => b.claims.length - a.claims.length || a.name.localeCompare(b.name),
  az: (a, b) => a.name.localeCompare(b.name),
  new: (a, b) => (b.first_seen ?? '').localeCompare(a.first_seen ?? '') || b.id.localeCompare(a.id),
  old: (a, b) => (a.first_seen ?? '').localeCompare(b.first_seen ?? '') || a.id.localeCompare(b.id),
}

/** A motif matches every word of a search over its id, name and note */
export function matches(e: Entry, words: string[]) {
  if (!words.length) return true
  const hay = (e.id + ' ' + e.name + ' ' + (e.note ?? '')).toLowerCase()
  return words.every((w) => hay.includes(w))
}
export const words = (q: string) => q.toLowerCase().split(/\s+/).filter(Boolean)

/** A group's or genre's colour, as on the maps (app/site/static/motif-map-layout.js): by its place A to Z */
export const GROUP_COLORS = ['#ff4fa3', '#3a86ff', '#ff6b1a', '#8a5cff', '#00a896', '#e0a800']
export const GENRE_COLORS = ['#ff4fa3', '#00c2a8', '#ffc400', '#3a86ff', '#ff6b1a', '#8a5cff', '#2bb673', '#e0102e', '#a0522d',
  '#00a6d6', '#c2185b', '#6b8e23', '#ff8fab', '#5c6bc0']
export const groupColor = (k: number) => GROUP_COLORS[Math.max(0, k) % GROUP_COLORS.length]
export const genreColor = (genres: string[], v: string | null | undefined) =>
  GENRE_COLORS[Math.max(0, genres.indexOf(v ?? '')) % GENRE_COLORS.length]

export const claimLink = (claim: string) => `/ui/workbench?claim=${encodeURIComponent(claim)}`
export const motifLink = (id: string) => `/ui/workbench?motif=${encodeURIComponent(id)}`

/** The index as last fetched, outside React (the drag engine and the actions read it when they run) */
let lastData: WBState | undefined
let lastModel: Model | null = null
export function currentModel(): Model | null {
  const d = client.getQueryData<WBState>(['/workbench.json', {}])
  if (d !== lastData) {
    lastData = d
    lastModel = d ? build(d) : null
  }
  return lastModel
}
