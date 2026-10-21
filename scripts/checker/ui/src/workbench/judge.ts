// The claims to judge, read once for the three tabs that use them (🎯 claims to judge, ✅ sure, 🚫 misfits): each
// filing's fit (the chance you keep it, learned from your own checks), the ones never passed as sure, the doubted
// ones, and why each claim is here. The lists hide this session's decisions at once, without fetching again.
import { useMemo } from 'react'
import { useJSON } from '../lib/queries'
import { motifsOf, useWorkbench, type Model } from './model'
import { useWB } from './store'
import type { JudgeItem } from './types'

/** A queue of the inbox (/workbench-queue.json?kind=…), read when its tab opens and kept until then */
export function useQueue<T>(kind: string, enabled = true) {
  return useJSON<T>('/workbench-queue.json', { kind }, { enabled, staleTime: Infinity, refetchOnWindowFocus: false })
}

export interface Judging {
  list: JudgeItem[]
  fits: Record<string, number>
  unsure: Set<string>
  doubted: Set<string>
  why: Record<string, JudgeItem>
  waiting: (claim: string) => string[]
  doubts: (claim: string, id: string) => boolean
  items: JudgeItem[] // with something still waiting
  sure: { claim: string; ids: string[]; at: number }[]
  out: { claim: string; ids: string[]; at: number }[]
}

export function useJudging(): Judging | null {
  const { model } = useWorkbench()
  const q = useQueue<JudgeItem[]>('judge')
  const decided = useWB((s) => s.decided)
  const quickSkip = useWB((s) => s.quickSkip)
  return useMemo(() => (model && q.data ? judging(model, q.data, new Set(decided), new Set(quickSkip)) : null), [model, q.data, decided, quickSkip])
}

function judging(m: Model, list: JudgeItem[], decided: Set<string>, skip: Set<string>): Judging {
  const fits: Record<string, number> = {}, unsure = new Set<string>(), doubted = new Set<string>(), why: Record<string, JudgeItem> = {}
  for (const x of list) {
    for (const [id, f] of Object.entries(x.fits)) fits[x.claim + '|' + id] = f
    x.unsure.forEach((id) => unsure.add(x.claim + '|' + id))
    x.reasons.filter((r) => r.kind === 'doubted').forEach((r) => doubted.add(x.claim + '|' + r.id))
    why[x.claim] = x
  }
  const doubts = (claim: string, id: string) => doubted.has(claim + '|' + id) && !decided.has(claim + '|' + id)
  // A claim's filings still waiting for you: the ones nobody has checked, and the ones you confirmed that the model
  // now doubts (until you say again that they fit, or take them out)
  // (a filing answered in this session stops waiting at once, before the server's answer redraws the index)
  const waiting = (claim: string) => motifsOf(m, claim).filter((e) => (e.claims.some((c) => c.claim === claim && !c.checked) && !decided.has(claim + '|' + e.id))
    || doubts(claim, e.id)).map((e) => e.id)
  const items = list.filter((x) => waiting(x.claim).length)
  // The quick tabs (Oct 18): ✅ sure, claims whose every waiting filing is past the sure line (passing a row finishes
  // the claim); 🚫 misfits, filings under the likely-out line, none ticked (the model is never sure of a no). Filings the
  // model can't be sure of, and ones you confirmed that it now doubts, are in neither: those want the card
  const conf = m.data.confidence
  const sure: Judging['sure'] = [], out: Judging['out'] = []
  if (conf) {
    for (const x of items) {
      const left = waiting(x.claim)
      const fit = (id: string) => fits[x.claim + '|' + id]
      const plain = (id: string) => fit(id) != null && !doubts(x.claim, id) && !unsure.has(x.claim + '|' + id) && !skip.has(x.claim + '|' + id)
      if (left.every((id) => plain(id) && fit(id) >= conf.sure_at)) sure.push({ claim: x.claim, ids: left, at: Math.min(...left.map(fit)) })
      const low = left.filter((id) => plain(id) && fit(id) < conf.out_at)
      if (low.length) out.push({ claim: x.claim, ids: low, at: Math.min(...low.map(fit)) })
    }
    sure.sort((a, b) => b.at - a.at) // the surest first
    out.sort((a, b) => a.at - b.at) // the least likely first
  }
  return { list, fits, unsure, doubted, why, waiting, doubts, items, sure, out }
}

/** Why a claim is in the claims to judge, in a line */
export function whyHere(m: Model, j: Judging, claim: string) {
  const x = j.why[claim]
  if (!x) return ''
  const fresh = x.reasons.filter((r) => r.kind === 'unchecked'), torn = fresh.filter((r) => r.fit != null && r.fit >= 0.2 && r.fit <= 0.8)
  const doubted = x.reasons.filter((r) => r.kind === 'doubted')
  // filed again by the watch list (Charybdis): what it was, and since when
  const refiled = fresh.filter((r) => r.refiled).map((r) => `♻️ refiled into ${m.by[r.id] ? '“' + m.by[r.id].name + '”' : r.id}: was ${r.refiled!.was === 'watched motif' ? 'plain news' : 'in no motif'} until ${new Date(r.refiled!.at + 'T12:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`)
  return [...refiled, fresh.length ? `🤖 ${fresh.length} new filing${fresh.length === 1 ? '' : 's'}${torn.length ? ` (the model torn on ${torn.length})` : ''}` : '',
    doubted.length ? `🧐 ${doubted.length} you confirmed that the model now doubts` : ''].filter(Boolean).join(' · ')
}
