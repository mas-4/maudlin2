// Numbers and times as the live page writes them, and a signal's value in words
import type { Gloss } from './types'

export const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v * 100)}%`)
export const num = (v: number | null | undefined, d = 3) => (v == null ? '–' : (+v).toFixed(d))
export const signed = (v: number | null | undefined, d = 2) => (v == null ? '–' : (v > 0 ? '+' : '') + (+v).toFixed(d))
export const hhmm = (t?: string | null) => (t || '').slice(11, 16)
export const when = (t?: string | null) => (t ? `${t.slice(5, 10)} ${t.slice(11, 16)}` : '')
export const sigmoid = (v: number) => 1 / (1 + Math.exp(-v))

/** A signal's value in words: the reranker's and the judge's are log-odds, read as the chance of yes; the rank and
 * size are stored as log(1 + n) */
export function val(f: string, v: number | null | undefined): string {
  if (v == null) return '–'
  if (f === 'rerank' || f === 'judge') return `${pct(sigmoid(v))} yes`
  if (f === 'rank') return `#${Math.round(Math.expm1(v)) + 1}`
  if (f === 'size') return `${Math.round(Math.expm1(v))} claims`
  if (f.startsWith('from ')) return v ? 'yes' : 'no'
  return num(v)
}

/** A grid cell's colour: teal up, coral down, as strong as the value is against its scale */
export function cellColor(v: number | null | undefined, scale: number): string {
  if (v == null) return '#f3f3f3'
  const a = Math.min(1, Math.abs(v) / scale)
  return v >= 0 ? `rgba(0,194,168,${a})` : `rgba(255,107,107,${a})`
}

/** The glossary lookup a journey reads: the stream's, else the journey's own, else the signal's code name */
export type GlossOf = (f: string) => Gloss

export const KIND_LABEL: Record<string, string> = {
  recent: '🆕 recent', kept: '✓ kept', 'taken out': '✕ taken out', 'not on its shortlist': '🙈 moved to one not shortlisted',
  'new motif': '🌱 new motif made', 'passed as sure': '🎯 passed as sure', refiled: '♻️ refiled', split: '✂️ split',
}

/** A hex id typed in the search box opens that claim's journey on Enter */
export const HEX_ID = /^#?[0-9a-f]{6,16}$/

export const plural = (n: number, one: string, many = one + 's') => (n === 1 ? one : many)
