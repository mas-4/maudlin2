// What GET /flow.json sends (app/analysis/flow.py) and what the page works out from it: the rows shown under the
// filters, each story's first telling, the lag histogram, the hub motifs
import { genreColor as paletteColor } from '../../workbench/model'

export type Source = 'posts' | 'fact-check' | 'shows' | 'focus group'

export interface Filing {
  date: string // the day it was told, YYYY-MM-DD
  motif: string
  source: Source
  claim: string
  checked: boolean
  plain: boolean // its motif is a watch list (plain reporting, like Straight news): the baseline
  tie: 'same event' | 'same issue'
  lag: number | null // days from the story's first day in the news
}

export interface Story {
  id: number
  label: string
  first: string | null // ISO minutes
  last: string | null
  motifs: number // motifs it was told as, plain reporting left out
  filings: Filing[]
}

export interface FlowMotif { name: string; genre: string; stories: number; plain: boolean }

export interface FlowData {
  stories: Story[]
  motifs: Record<string, FlowMotif>
  genres: string[]
  filings: number
  lags: number[]
  made: string
}

/** A story under the filters, with the filings that pass them */
export interface Row extends Story { fs: Filing[] }

export type Sort = 'first' | 'motifs' | 'lag'

export interface Filters { q: string; sort: Sort; plain: boolean; sources: Set<Source> }

/** Each source kind: its mark on the chart, the box that hides it, and a word for the tooltip */
export const SOURCES: { key: Source; mark: string; label: string }[] = [
  { key: 'posts', mark: '●', label: 'people online' },
  { key: 'fact-check', mark: '■', label: 'fact-checks' },
  { key: 'shows', mark: '▲', label: 'shows' },
  { key: 'focus group', mark: '◆', label: 'focus group' },
]

/** A motif's genre colour, as on the maps; grey for a motif with no genre yet */
export const genreColor = (genres: string[], g: string | null | undefined) => (g ? paletteColor(genres, g) : '#bbb')

/** A day as noon local time, so a dot sits in the middle of its day's column */
export const day = (s: string | null | undefined) => (s ? new Date(s.slice(0, 10) + 'T12:00') : null)

/** Days from the news to a story's first telling, plain reporting left out */
export function firstLag(s: Story): number | null {
  const ls = s.filings.filter((f) => !f.plain && f.lag !== null).map((f) => f.lag as number)
  return ls.length ? Math.min(...ls) : null
}

/** The stories shown: filings filtered by source and plainness, stories by the search, sorted; with a motif followed,
 *  the stories that fed it first, in the order they were told, and the rest after as they were */
export function shown(d: FlowData, f: Filters, picked: string | null): Row[] {
  const q = f.q.trim().toLowerCase()
  const keep = (x: Filing) => f.sources.has(x.source) && (f.plain || !x.plain)
  let rows: Row[] = d.stories.map((s) => ({ ...s, fs: s.filings.filter(keep) })).filter((s) => s.fs.length)
  if (q) rows = rows.filter((s) => s.label.toLowerCase().includes(q) || s.fs.some((x) => d.motifs[x.motif]?.name.toLowerCase().includes(q)))
  rows.sort(f.sort === 'motifs' ? (a, b) => b.motifs - a.motifs
    : f.sort === 'lag' ? (a, b) => (firstLag(b) ?? -1) - (firstLag(a) ?? -1)
      : (a, b) => (a.first ?? '').localeCompare(b.first ?? ''))
  if (picked) {
    const at = (s: Row) => s.fs.find((x) => x.motif === picked)?.date || '9999'
    rows.sort((a, b) => (at(a) < at(b) ? -1 : at(a) > at(b) ? 1 : 0))
  }
  return rows
}

/** The top cards' numbers: stories told, motifs, the first-telling lags in nine bins (≤0, 1…7, 8+) and their median */
export function summary(d: FlowData) {
  const told = d.stories.filter((s) => s.motifs)
  const firsts = told.map(firstLag).filter((x): x is number => x !== null)
  const bins = [...Array(9)].map((_, i) => firsts.filter((x) => (i === 8 ? x >= 8 : i === 0 ? x <= 0 : x === i)).length)
  const sorted = [...firsts].sort((a, b) => a - b)
  const hubs = Object.entries(d.motifs).filter(([, m]) => !m.plain).sort((a, b) => b[1].stories - a[1].stories).slice(0, 8)
  return {
    told: told.length,
    motifs: Object.values(d.motifs).filter((m) => !m.plain).length,
    bins,
    median: sorted.length ? sorted[Math.floor(sorted.length / 2)] : null,
    hubs,
  }
}

export const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`
