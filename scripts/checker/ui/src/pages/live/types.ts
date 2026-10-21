// What GET /live.json sends (app/analysis/trace_view.py): the stream (stages, events, counts, examples, the glossary),
// a search's claims, and one claim's journey through the filing pipeline

export interface Stage { id: string; emoji: string; name: string; what: string }

/** One thing that happened to a claim at one stage: t its time, s the stage, k the claim's key, c its words */
export interface LiveEvent { t: string; s: string; k: string; c: string; line: string; kept?: boolean; sure?: boolean }

export interface Counts {
  hours: string[] // the hour labels of the last day, oldest first
  per_hour: Record<string, number[]>
  last_hour: Record<string, number>
  day: Record<string, number>
}

/** A claim worth opening */
export interface Pick { k: string; c: string; t?: string; note?: string }

/** A signal's short name and what it means */
export type Gloss = [string, string]

export interface Stream {
  error?: string
  now: string
  events: LiveEvent[]
  counts: Counts
  traced_since: string | null
  stages?: Stage[] // the first fetch only, as are the examples and the glossary
  examples?: Record<string, Pick[]>
  glossary?: Record<string, Gloss>
}

export interface Found { error?: string; found?: Pick[] }

export interface Source {
  kind?: string; source?: string; title?: string; url?: string; published?: string; summary?: string; made?: string
  people?: number; posts?: number; quote?: string; side?: string; examples?: string[]; piece?: string; context?: string
  tellings?: { show?: string; quote?: string; speaker?: string; date?: string; url?: string }[]
  label?: { genre?: string; motif?: string; context?: string; side?: string }
  articles?: string[]; error?: string
}

export interface WrittenEvent { t: string; posts?: number; authors?: number; variety?: number; keys?: string[]; shows?: string[]; story?: number }

export interface Row {
  id: string; why?: string | null; rank?: number | null; score?: number | null; picked: boolean; verdict?: boolean | null
  x?: number[]; z?: number[]; push?: number[]
}

export interface Shortlist {
  t: string; traced: boolean; rows: Row[]
  method?: string; features?: string[]; coef?: number[]; bias?: number; of?: number
  next?: { id: string; rank: number; score?: number }[] | null
  shown?: string[]; seeds?: string[]; refile?: string | null; source?: string | null; next_motif?: number | null
}

export interface Picked {
  t?: string; picked?: string[] | null; new?: string[] | null; reason?: string | null; new_reason?: string | null
  filed?: string[] | null; made?: string[] | null; outcome?: string | null; was?: string | null; why?: string | null
}

export interface Push { f: string; v: number; w: number; c: number }
export interface Filing { id: string; fit: number | null; z: number | null; bias: number | null; pushes: Push[] }
export interface Scoring { t: string; model?: string; sure_at?: number | null; confirmed?: boolean; filings: Filing[] }

export interface Now {
  id: string; fit: number | null; model?: string | null; checked?: string | null; date?: string | null
  refiled?: { at: string; was: string } | null; story?: number | null; story_tie?: string | null; carrying?: string[] | null
  variants: number; split_from?: string | null; yours: boolean
}

export interface Decision {
  t: string; by: string; k: string; c: string; id?: string; kept?: boolean | null; act: string; fit?: number | null
  sure_at?: number | null; sure?: boolean | null; batch?: string | null; why?: string; name?: string
  to?: string | string[]; from?: string
}

export interface MotifInfo {
  name: string; genre?: string | null; size?: number; yours?: boolean; note?: string
  told?: { events?: number; sources?: string[]; span?: string[] } | null
}

export interface Journey {
  error?: string
  claim: { k: string; id6: string; c: string; words: string[]; keys: string[] }
  logged_source: string | null
  written: { traced: WrittenEvent[]; source: Source }
  shaped: { shape: string | null; layers: Record<string, string> | null; traced: boolean }
  passes: { shortlist: Shortlist; picked: Picked | null }[]
  scored: { traced: Scoring[]; now: Now[]; alternatives: { id: string; fit: number }[]; sure_at: number | null }
  decided: Decision[]
  split: {
    proposed: { split?: boolean; reason?: string; triggers?: string[] }[]
    children?: { k: string; c: string }[]; at?: string; by?: string; why?: string; was_in?: string[]
    from?: { k: string; c: string }
  }
  motifs: Record<string, MotifInfo>
  stories: Record<string, { label: string }>
  glossary: Record<string, Gloss>
  traced: boolean
  traced_since: string | null
}
