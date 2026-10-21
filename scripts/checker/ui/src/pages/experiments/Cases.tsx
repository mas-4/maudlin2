// 🔍 Case by case: the items an experiment was tested on, what happened to each, sorted into kinds (failures first).
// Where the person judges them (Pandora's tellings, Ptah's pairs, Sinbad's stories, Rip Van Winkle's filings) each row
// has verdict buttons; pressing the one already chosen clears it. The blind set, to judge first, is marked.
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { postJSON } from '../../lib/api'
import { useJSON } from '../../lib/queries'
import { toast } from '../../components/Feedback'
import type { CaseRow, Cases, Cell } from './types'

const PANDORA: [string, string][] = [['motif', '✅ worth a motif'], ['already', '♻️ already one'], ['not', '✕ not a telling']]
const isLink = (x: Cell) => typeof x === 'string' && /^https?:\/\//.test(x)

export function CasesPane({ code }: { code: string }) {
  const qc = useQueryClient()
  const params = { code }
  const { data: c, error, isLoading } = useJSON<Cases>('/experiment-cases.json', params)
  const [kind, setKind] = useState<string | null>(null)
  // rows judged since the filter was chosen stay in view, though their kind has changed, so a slip can be undone
  const [kept, setKept] = useState<Set<string>>(() => new Set())
  const [saving, setSaving] = useState<string | null>(null) // `${key}|${value}` while it saves

  if (isLoading) return <div className="ex-loading">⏳ fetching the cases…</div>
  if (error || !c) return <div className="ex-empty">😬 The cases didn't load: {error?.message ?? 'no answer'}</div>

  const choices = c.choices ?? PANDORA
  const total = c.summary.reduce((n, [, k]) => n + k, 0)
  const rows = c.rows.filter((r) => !kind || r.kind === kind || (r.key !== undefined && kept.has(r.key)))
  const blind = c.rows.some((r) => r.blind)
  const pickKind = (k: string | null) => {
    setKind(k)
    setKept(new Set())
  }

  const judge = async (row: CaseRow, value: string) => {
    if (row.key === undefined) return
    if (saving) return toast('⏳ still saving…')
    const key = row.key
    const verdict = row.verdict === value ? null : value
    setSaving(`${key}|${value}`)
    try {
      await postJSON('/experiment-verdict', { code, key, verdict })
      // the same key can stand on two rows (two random groups of a motif may share a name): both take the verdict
      qc.setQueryData<Cases>(['/experiment-cases.json', params], (old) =>
        old && { ...old, rows: old.rows.map((r) => (r.key === key ? { ...r, verdict } : r)) })
      setKept((s) => new Set(s).add(key))
      void qc.invalidateQueries({ queryKey: ['/experiment-cases.json', params] }) // the kinds' counts move
      toast(verdict ? `💾 ${choices.find(([v]) => v === verdict)?.[1] ?? verdict} · press it again to clear` : '🧽 verdict cleared')
    } catch (e) {
      toast(`😬 not saved: ${(e as Error).message}`, true)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div>
      {c.note && <p className="ex-note">{c.note}</p>}
      {blind && <p className="faint">🙈 Rows edged in yellow are the blind set: judge those first.</p>}
      <div className="ex-kinds" role="group" aria-label="filter by kind">
        <button className={'ex-kind' + (kind ? '' : ' on')} onClick={() => pickKind(null)}>
          all <b>{total}</b>
        </button>
        {c.summary.map(([k, n]) => (
          <button key={k} className={'ex-kind' + (k === 'ok' ? ' ok' : '') + (k === kind ? ' on' : '')} onClick={() => pickKind(k === kind ? null : k)}>
            {k} <b>{n}</b> <span className="ex-bar" style={{ width: Math.round((60 * n) / Math.max(1, total)) }} />
          </button>
        ))}
      </div>
      {rows.length ? (
        <>
          {rows.length < c.rows.length && <div className="faint">showing {rows.length} of {c.rows.length}</div>}
          <div className="ex-cases">
            <table>
              <thead>
                <tr>
                  {c.judge && <th>your verdict</th>}
                  {c.columns.map((h, j) => <th key={j}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, n) => (
                  <tr key={n} className={(r.kind === 'ok' ? 'ex-k-ok' : 'ex-k-bad') + (r.blind ? ' ex-blind' : '')}>
                    {c.judge && (
                      <td className="ex-verdict">
                        {r.key !== undefined &&
                          choices.map(([v, label]) => (
                            <button
                              key={v}
                              className={(r.verdict === v ? 'on' : '') + (saving === `${r.key}|${v}` ? ' busy' : '')}
                              aria-pressed={r.verdict === v}
                              title={r.verdict === v ? 'press again to clear' : undefined}
                              onClick={() => void judge(r, v)}
                            >
                              {label}
                            </button>
                          ))}
                      </td>
                    )}
                    {r.cells.map((x, j) => (
                      <td key={j}>
                        {isLink(x) ? (
                          <a href={String(x)} target="_blank" rel="noopener noreferrer">scan ↗</a>
                        ) : (
                          String(x ?? '')
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="ex-empty">🦗 Nothing here yet.</div>
      )}
    </div>
  )
}
