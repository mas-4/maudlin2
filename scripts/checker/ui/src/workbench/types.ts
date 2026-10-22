// The workbench's data, as scripts/validate.py's workbench_state() and workbench_queue() send it

export interface Claim {
  claim: string
  id: string // 6-hex, the claim's short id
  source: string
  ref?: string
  checked?: 'yes' | 'unsure' | 'no' | null
  new?: boolean
  variants?: string[]
  carrying?: string[]
}

export interface Entry {
  id: string
  name: string
  note?: string
  note_by?: string
  not_this?: string
  parents: string[]
  related: string[]
  related_notes?: Record<string, string>
  groups?: string[]
  facets?: { genre?: string }
  by_model?: { genre?: string; groups?: string[] }
  done?: 'done' | 'new' | null
  curated?: boolean
  first_seen?: string
  told?: { events: number; span?: string[] }
  attested?: boolean
  stands_alone?: boolean
  watch?: boolean
  carrying?: [string, number][]
  claims: Claim[]
}

export interface Group { id: string; name: string; note?: string }

export interface Confidence {
  sure_at: number
  auc: number
  at_sure: { precision: number }
  out_at: number
  at_out?: { removed?: number }
  tally?: { day: string; clean: number; needed: number }[]
}

export interface WBState {
  entries: Entry[]
  groups: Group[]
  facets: { genre?: string[] }
  facet_notes?: { genre?: Record<string, string> }
  to_check: number
  second_look: number
  held?: string[]
  proposals?: number
  splits?: number
  tellings?: number
  tellings_of?: Record<string, number>
  not_same: [string, string][]
  confidence?: Confidence | null
  version?: number // the index's version this state was read at (validate.workbench_state)
}

export interface JudgeItem {
  claim: string
  source: string
  reasons: { kind: 'unchecked' | 'doubted'; id: string; fit?: number; refiled?: { was: string; at: string } }[]
  fits: Record<string, number>
  unsure: string[]
  better: unknown[]
}

export interface Proposal {
  id: string
  kind: string
  args: Record<string, any>
  reason?: string
  fit?: number | null
  judge?: { score: number; reason?: string } | null
  unlikely?: boolean
  do: Action
}

export interface SplitProposal {
  id: string
  args: { claim: string; posts?: number; triggers?: Record<string, string> }
  filings: { id: string; name: string }[]
  children: { claim: string; names?: string[]; posts: number; texts?: string[] }[]
  reason?: string
}

export interface TellingMotif {
  id: string
  name: string
  note?: string
  claims: number
  tellings: { key: string; name: string; note: string; claims: string[] }[]
}

export interface ClaimHit { claim: string; source: string; ref?: string; motifs: { id: string }[]; score?: number; id?: string }

/** A claim being carried in a drag, and where it was dragged from */
export interface Carried { claim: string; source: string; src: string; ref: string }
export type DragItem =
  | { kind: 'claim'; claims: Carried[] }
  | { kind: 'motif'; id: string }
  | { kind: 'motifs'; ids: string[]; group?: string }

/** A choice offered when something is dropped */
export interface Zone { label: string; say?: string; run: () => unknown }

/** Any action the checker takes (app/analysis/motif_actions.py) */
export type Action = { action: string; [field: string]: unknown }
