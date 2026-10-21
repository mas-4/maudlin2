// 📊 The catalog's numbers, now and day by day, and how good the machine is (/workbench-metrics.json)
import { useJSON } from '../../lib/queries'

type Day = Record<string, any> & { day: string; shape?: Record<string, number> }
interface Metrics {
  now: Record<string, number>
  days: Day[]
  models?: Record<string, any>[]
  health?: { at: string; problems?: { outlet?: string; feed?: string; problem: string }[] } | null
}

export function StatsTab() {
  const { data: m, error } = useJSON<Metrics>('/workbench-metrics.json')
  if (error) return <p className="faint">😬 {(error as Error).message}</p>
  if (!m) return <p className="faint">⏳</p>
  const n = m.now, days = m.days, h = m.health, hp = h?.problems ?? []
  const shaped = days.filter((d) => d.shape)
  const tile = (emoji: string, big: string | number, small: string, color: string) => (
    <li style={{ ['--sticker' as string]: color }}><span className="sticker-emoji">{emoji}</span><b>{big}</b><span>{small}</span></li>
  )
  return (
    <div className="stats-tab">
      {h && <div className={'health' + (hp.length ? ' sick' : '')}><b>🩺 {hp.length ? `${hp.length} feed${hp.length === 1 ? '' : 's'} or outlet${hp.length === 1 ? '' : 's'} not coming in` : 'every outlet and regular feed coming in'}</b>{' '}
        <span className="faint">checked {h.at.slice(0, 16).replace('T', ' ')} UTC</span>
        {hp.map((p, i) => <div key={i}>· {p.outlet || p.feed}: {p.problem}</div>)}</div>}
      <h3>📊 the catalog now</h3>
      <ul className="stat-tiles">
        {tile('🧩', n.motifs, 'motifs', '#00c2a8')}{tile('💬', n.claims, `claims (${n.filings} filings, ${n.per_motif} a motif)`, '#3a86ff')}
        {tile('1️⃣', n.singles + '%', 'single-claim motifs', '#ffc400')}{tile('🌳', n.in_tree + '%', 'resting on another, or rested on', '#8a5cff')}
        {tile('🎭', n.with_genre + '%', 'with a genre', '#ff6b1a')}{tile('✅', n.done + '%', 'done by you', '#7fd97a')}
        {tile('📝', n.your_notes + '%', 'with your note', '#ff4fa3')}{tile('☑️', n.checked + '%', 'of filings checked', '#a9a9b8')}
        {tile('∅', n.no_motif, 'claims with no motif', '#e2e2ea')}{tile('≡', n.variants, 'claims folded in as the same', '#ece4ff')}
      </ul>
      <Bars days={days} title="✨ new motifs a day" keys={['new_motifs']} colors={['#00c2a8']} note="the model makes most; a merge doesn't take one back" />
      <Bars days={days} title="🤖 how the model filed claims" keys={['filed_matched', 'filed_new', 'filed_none']} colors={['#3a86ff', '#ffc400', '#c9c9d4']} note="counted from Oct 6: into motifs already there, into a new one, or none" />
      <Bars days={days} title="✋ your changes a day" keys={['actions']} colors={['#ff4fa3']} note="merges, moves, links, notes, checks… in the curation log" />
      <Bars days={days} title="☑️ your checks" keys={['checks_yes', 'checks_no', 'checks_unsure']} colors={['#7fd97a', '#ff6b6b', '#c9c9d4']} />
      <Machine models={m.models ?? []} sure={days.filter((d) => d.shape && d.shape.sure_share != null)} />
      {shaped.length > 0 && <div className="stat"><h3>🧱 the shape, day by day</h3>
        <table className="shape"><thead><tr><th />{shaped.map((d) => <th key={d.day}>{d.day.slice(5)}</th>)}</tr></thead>
          <tbody>{([['singles', 'single-claim'], ['two_plus', '2+ claims'], ['in_tree', 'in the tree'], ['with_genre', 'with a genre'], ['done', 'done'], ['your_notes', 'your notes']] as const).map(([k, label]) => (
            <tr key={k}><td>{label}</td>{shaped.map((d) => <td key={d.day}>{d.shape![k]}%</td>)}</tr>))}</tbody></table>
        <p className="faint">a snapshot after each filing run, from Oct 6</p></div>}
    </div>
  )
}

/** One bar a day (stacked when there are parts), the day under it */
function Bars({ days, title, keys, colors, note }: { days: Day[]; title: string; keys: string[]; colors: string[]; note?: string }) {
  const totals = days.map((d) => keys.reduce((t, k) => t + (d[k] || 0), 0))
  const peak = Math.max(1, ...totals)
  if (!totals.some(Boolean)) return null
  return (
    <div className="stat"><h3>{title}</h3>
      <div className="daybars">{days.map((d, i) => (
        <div key={d.day} className="daybar" title={`${d.day}: ${keys.map((k) => `${k.replace(/_/g, ' ')} ${d[k] || 0}`).join(', ')}`}>
          <div className="stack" style={{ height: `${Math.round(100 * totals[i] / peak)}%` }}>{keys.map((k, j) => d[k] ? <span key={k} style={{ flex: d[k], background: colors[j] }} /> : null)}</div>
          <i>{totals[i] || ''}</i><small>{d.day.slice(5)}</small></div>))}</div>
      {(keys.length > 1 || note) && <p className="faint">{keys.length > 1 && keys.map((k, j) => <span key={k}>{j > 0 && ' · '}<span className="key" style={{ background: colors[j] }} />{k.replace(/^\w+_/, '').replace(/_/g, ' ')}</span>)}{keys.length > 1 && note ? ' · ' : ''}{note}</p>}
    </div>
  )
}

/** 🤖 how good the machine is, day by day: the models' tests on checks they didn't learn from */
function Machine({ models, sure }: { models: Record<string, any>[]; sure: Day[] }) {
  if (!models.length) return null
  const pct = (v: number | null) => (v == null ? '–' : `${Math.round(v * 1000) / 10}%`)
  const bySure = Object.fromEntries(sure.map((d) => [d.day, d.shape]))
  const row = (label: string, title: string, cell: (d: Record<string, any>) => string) => (
    <tr><td title={title}>{label}</td>{models.map((d) => <td key={d.day}>{cell(d)}</td>)}</tr>
  )
  return (
    <div className="stat"><h3>🤖 how good the machine is</h3>
      <table className="shape"><thead><tr><th />{models.map((d) => <th key={d.day}>{d.day.slice(5)}</th>)}</tr></thead><tbody>
        {row('🎯 right when sure', 'of the filings the confidence model calls sure, how many you kept: tested on checks it never learned from', (d) => pct(d.right_when_sure))}
        {row('📏 the sure line', 'the fit a filing needs to count as sure: lower means more pass as sure', (d) => (d.sure_at == null ? '–' : `${Math.round(d.sure_at * 100)}%`))}
        {row('⚖️ AUC', 'how often the confidence model scores a filing you kept above one you took out: 0.5 a coin toss, 1 perfect', (d) => (d.auc == null ? '–' : d.auc.toFixed(3)))}
        {row('🔎 right motif in the top 12', 'how often the motif you chose is among the 12 the shortlist shows the judge', (d) => pct(d.top12))}
        {row("🫶 the day's filings sure", "of the day's filings in your motifs, how many the model of the day put past the sure line: as this climbs and right-when-sure holds, you have less to look at and correct (from Oct 11)", (d) => (bySure[d.day] ? `${bySure[d.day]!.sure_share}%` : '–'))}
      </tbody></table>
      <p className="faint">the day's last test of each model, held out from its training; from Oct 8</p></div>
  )
}
