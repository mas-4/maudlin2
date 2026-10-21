// The shapes the experiments page reads, from scripts/experiments/lab.py (served by scripts/validate.py)

export interface ResultLine { at: string; line: string }

/** One experiment in the catalog: shown by its folklore figure, picked by its code (the URL hash) */
export interface Experiment {
  code: string
  figure: string
  why: string
  family: string
  question: string
  status: string
  result: string
  script: string
  lines: ResultLine[] // the last 12 result lines, oldest first
  cases: boolean // has a case-by-case record
  paper: boolean // has a paper in ~/maudlin-data/papers
}

/** A step on the GPU queue */
export interface QueueStep { id: number; step: string; status: string; tries: number; started: string | null; finished: string | null }

/** One of Ma'at's weekly weighings of the judge against the same fixed decisions */
export interface Weighing {
  at: string
  set?: string
  filings: number
  kept?: number
  auc: number | null
  sure_at?: number
  'right when sure': number | null
  'kept that pass': number | null
  'trained on'?: number
  judge?: string
}

/** A story production cut (or kept whole) at a seam, with the judge's answer */
export interface Seam { cut: boolean; one_event: boolean[]; reason: string; a: string[]; b: string[] }

export interface Overview { experiments: Experiment[]; queue: QueueStep[]; maat: Weighing[]; seams: Seam[] }

/** A paper and the pipeline paper (the pipeline comes only with a paper) */
export interface Paper { text: string; file: string | null; pipeline?: string }

export type Cell = string | number | boolean | null

/** One item an experiment was tested on: its kind ('ok' or the failure), and for judged ones the key and verdict */
export interface CaseRow { kind: string; cells: Cell[]; key?: string; verdict?: string | null; blind?: boolean }

export interface Cases {
  summary: [string, number][]
  columns: string[]
  rows: CaseRow[]
  note: string
  judge?: string | boolean // the person gives verdicts on these rows
  choices?: [string, string][] // [value, label]; Pandora's three when absent
}
