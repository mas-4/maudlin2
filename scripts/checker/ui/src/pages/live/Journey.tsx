// One claim's journey through the filing pipeline, a card a stage down a dotted road: how it was written, its shape
// and layers, each filing pass (the shortlist's signals as a grid of motifs × signals, then the filing model's pick),
// the confidence model's fit and what pushed it, the person's verdicts, a split, and where it went downstream
import type { ReactNode } from 'react'
import { claimLink, motifLink } from '../../workbench/model'
import { cellColor, num, pct, plural, signed, val, when, type GlossOf } from './format'
import type { Journey as J, Push, Shortlist } from './types'

export type GridMode = 'push' | 'z'

interface Props {
  J: J
  gl: GlossOf
  glossary: Record<string, [string, string]>
  mode: GridMode
  setMode: (m: GridMode) => void
  onOpen: (k: string) => void
  onClose: () => void
}

type Verdicts = Record<string, boolean>
const verdictOf = (J: J): Verdicts => {
  const v: Verdicts = {}
  for (const d of J.decided) if (d.id && d.kept != null) v[d.id] = d.kept
  return v
}
const vcls = (v: boolean | null | undefined) => (v === true ? 'kept' : v === false ? 'out' : '')
const nameOf = (J: J, id: string) => J.motifs[id]?.name || id

/** A motif: its name, linked to it in the workbench */
function M({ J, id, cls = '', pre = '' }: { J: J; id: string; cls?: string; pre?: string }) {
  const g = J.motifs[id]?.genre
  return (
    <a className={`lv-chip ${cls}`} href={motifLink(id)} title={`${id}${g ? ' · ' + g : ''} · open it in the workbench`}>
      {pre}{nameOf(J, id)}
    </a>
  )
}

/** A run of motifs, a space between each */
function Ms({ J, ids, cls }: { J: J; ids: string[]; cls?: (id: string) => string }) {
  return <>{ids.map((id, i) => <span key={id + i}>{i > 0 && ' '}<M J={J} id={id} cls={cls?.(id)} /></span>)}</>
}

function Step({ emoji, title, at, badge, children }: { emoji: string; title: string; at?: string; badge?: ReactNode; children: ReactNode }) {
  return (
    <div className="lv-step">
      <div className="lv-dot" aria-hidden="true">{emoji}</div>
      <div className="lv-card">
        <h3>{title}<small>{at || ''}</small>{badge}</h3>
        {children}
      </div>
    </div>
  )
}

const Traced = ({ yes }: { yes: boolean }) =>
  yes ? <span className="lv-badge traced">traced</span> : <span className="lv-badge rebuilt">rebuilt from the logs</span>

const Missing = ({ children }: { children: ReactNode }) => <div className="lv-missing">{children}</div>
const Quote = ({ children }: { children: ReactNode }) => <div className="lv-quote">{children}</div>

function Written({ J }: { J: J }) {
  const src = J.written.source || {}, tr = J.written.traced || []
  const kind = src.kind || ''
  let body: ReactNode
  if (kind.startsWith('folklore (')) {
    body = <Missing>Its report is gone{J.logged_source ? `; it came from ${J.logged_source === 'narrative' ? 'what people post' : J.logged_source}` : ''}.</Missing>
  } else if (kind === 'folklore') {
    body = (
      <>
        <p>From what people post: <b>{src.people ?? '?'} people</b> in <b>{src.posts ?? '?'} posts</b> that say one thing, written up as one claim by the filing model{src.made ? ` (the report of ${when(src.made)})` : ''}.</p>
        {src.examples && <><p className="faint">a few of the posts:</p>{src.examples.map((x, i) => <Quote key={i}>{x}</Quote>)}</>}
        {src.articles && <p className="faint">links they share: {src.articles.join(' · ')}</p>}
      </>
    )
  } else if (kind === 'fact-check') {
    body = (
      <>
        <p>From a fact-check: <a href={src.url} target="_blank" rel="noopener">{src.title || src.url}</a> <span className="faint">{src.source || ''} · {src.published || ''}</span></p>
        {src.summary && <Quote>{src.summary}</Quote>}
        {src.piece && <details><summary>the piece's opening</summary><p className="faint">{src.piece}</p></details>}
      </>
    )
  } else if (kind === 'focus-group') {
    body = (
      <>
        <p>From the Focus Group: <a href={src.url} target="_blank" rel="noopener">{src.title || 'the episode'}</a> <span className="faint">{src.published || ''}{src.side ? ' · ' + src.side : ''}</span></p>
        {src.quote && <Quote>“{src.quote}”</Quote>}
        {src.context && <details><summary>around the quote</summary><p className="faint">{src.context}</p></details>}
      </>
    )
  } else if (kind.startsWith('radio')) {
    body = (
      <>
        <p>Told on two or more shows:</p>
        {(src.tellings || []).map((t, i) => (
          <Quote key={i}>“{t.quote}” <span className="faint">{t.show || ''}{t.speaker ? ', ' + t.speaker : ''}{t.date ? ' · ' + t.date : ''}</span></Quote>
        ))}
      </>
    )
  } else if (src.error) {
    body = <Missing>Where it came from couldn't be read: {src.error}</Missing>
  } else {
    body = <Missing>Where it came from isn't known{J.logged_source ? `; its source was ${J.logged_source}` : ''}.</Missing>
  }
  return (
    <Step emoji="✍️" title="the claim is written" at={tr.length ? when(tr[0].t) : ''} badge={<Traced yes={tr.length > 0} />}>
      {body}
      {src.label && (src.label.genre || src.label.motif) && (
        <p className="faint">read as: {src.label.genre || ''}{src.label.motif ? ` · “${src.label.motif}”` : ''}</p>
      )}
      {J.claim.words.length > 0 && <p className="faint">✏️ reworded by you from: {J.claim.words.map((w) => `“${w}”`).join(', ')}</p>}
      {tr.length > 0 && (
        <p className="faint">
          {tr.map((e, i) => (
            <span key={i}>
              {i > 0 && <br />}
              written {when(e.t)}
              {e.posts ? ` from ${e.posts} posts by ${e.authors} people (wording ${Math.round(100 * (e.variety || 0))}% varied${e.keys ? `, ${e.keys.length} post keys kept` : ''})` : ''}
              {e.shows ? ' on ' + e.shows.join(', ') : ''}
              {e.story ? ` · tied to story #${e.story}` : ''}
            </span>
          ))}
        </p>
      )}
    </Step>
  )
}

const LAYERS: [string, string][] = [['character', '🧍'], ['plot', '📜'], ['theory', '🕸️'], ['argument', '⚖️'], ['value', '💎']]

function Shaped({ J }: { J: J }) {
  const sh = J.shaped
  if (!sh.shape && !sh.layers) {
    return (
      <Step emoji="🧩" title="its shape and layers">
        <Missing>No shape or layers asked yet: the filing model asks them when it files the claim.</Missing>
      </Step>
    )
  }
  const ls = sh.layers || {}
  return (
    <Step emoji="🧩" title="its shape and layers" badge={<Traced yes={sh.traced} />}>
      {sh.shape && (
        <>
          <p className="faint">the bare shape of its story, in the filing model's words (no names, places or dates):</p>
          <div className="lv-shape">{sh.shape}</div>
        </>
      )}
      {sh.layers && (
        <>
          <p className="faint">layer by layer (each layer is matched against every motif's note: "best layer" and "its genre's layer" in the grid):</p>
          <div className="lv-layers">
            {LAYERS.map(([l, emo]) => {
              const t = ls[l] || 'none'
              const none = /^none\.?$/i.test(t.trim())
              return (
                <span key={l} className="lv-layer">
                  <span>{emo} <b>{l}</b></span>
                  <span className={none ? 'none' : ''}>{none ? 'none' : t}</span>
                </span>
              )
            })}
          </div>
        </>
      )}
    </Step>
  )
}

/** The shortlist as a grid of neurons: a row a motif, a column a signal, each cell coloured by its push on the score
 * (or by the signal itself, in spreads from the usual), and each signal's learned weight as a bar above */
function Grid({ J, sl, vd, gl, mode, setMode }: { J: J; sl: Shortlist; vd: Verdicts; gl: GlossOf; mode: GridMode; setMode: (m: GridMode) => void }) {
  const fs = sl.features ?? [], coef = sl.coef ?? []
  const scale = mode === 'push' ? 1.5 : 2.5
  const wmax = Math.max(...coef.map(Math.abs), 1e-9)
  return (
    <>
      <div className="lv-legend">
        <span>colour:</span>
        <button className={'lv-chip' + (mode === 'push' ? ' on' : '')} onClick={() => setMode('push')}>its push on the score</button>
        <button className={'lv-chip' + (mode === 'z' ? ' on' : '')} onClick={() => setMode('z')}>the signal itself</button>
        <span><span className="lv-ramp" /> down … up</span>
        <span>⭐ the filing model picked it · ✓ you kept it · ✕ you took it out · hover a cell for its numbers</span>
      </div>
      <div className="lv-gridwrap">
        <table className="lv-neurons">
          <thead>
            <tr>
              <th />
              <th className="faint">score</th>
              {fs.map((f) => <th key={f} className="f"><div title={`${f}: ${gl(f)[1]}`}>{gl(f)[0]}</div></th>)}
            </tr>
            <tr className="w">
              <td className="m faint">weight →</td>
              <td />
              {coef.map((w, i) => (
                <td key={i} title={`${fs[i]}: weight ${signed(w, 3)} (on the signal's spread)`}>
                  <div className="lv-wbar" style={{ height: Math.max(2, (26 * Math.abs(w)) / wmax), background: w >= 0 ? 'var(--teal)' : 'var(--coral)' }} />
                </td>
              ))}
            </tr>
          </thead>
          <tbody>
            {sl.rows.map((r) => {
              const v = vd[r.id]
              const cls = `${r.picked ? 'picked ' : ''}${vcls(v)}`
              const label = (
                <td className="m" title={`${nameOf(J, r.id)} (${r.id})${r.rank != null ? `, #${r.rank + 1} of ${sl.of}` : ''}`}>
                  {r.picked ? '⭐' : ''}{v === true ? '✓' : v === false ? '✕' : ''}{' '}
                  {r.rank != null && <span className="faint">#{r.rank + 1} </span>}
                  <a href={motifLink(r.id)}>{nameOf(J, r.id)}</a>
                  {r.why === 'tree' && <span className="lv-badge" title="shown because it rests on, or is rested on by, a top motif">family</span>}
                  {r.why === 'seed' && <span className="lv-badge" title="a seed: your motif with no claims yet, offered by likeness to its name and note">seed</span>}
                </td>
              )
              if (!r.x) {
                return (
                  <tr key={r.id} className={cls}>
                    {label}<td /><td colSpan={fs.length} className="faint">no signals: it has no claims yet</td>
                  </tr>
                )
              }
              return (
                <tr key={r.id} className={cls}>
                  {label}
                  <td className="sc">{num(r.score, 2)}</td>
                  {fs.map((f, i) => {
                    const shown = mode === 'push' ? r.push?.[i] : r.z?.[i]
                    return (
                      <td key={f} className="cell" style={{ background: cellColor(shown, scale) }}
                        title={`${gl(f)[0]} for ${nameOf(J, r.id)}: ${val(f, r.x![i])} (${signed(r.z?.[i])} spreads from the usual) × weight ${signed(coef[i], 3)} = ${signed(r.push?.[i])} on its score`} />
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

function Passes({ J, gl, mode, setMode }: { J: J; gl: GlossOf; mode: GridMode; setMode: (m: GridMode) => void }) {
  const vd = verdictOf(J)
  if (!J.passes.length) {
    return (
      <Step emoji="🔦" title="the shortlist">
        <Missing>No filing of this claim on record: it was filed before the shortlist log began (Oct 12), or not filed yet.</Missing>
      </Step>
    )
  }
  return (
    <>
      {J.passes.map((p, n) => {
        const sl = p.shortlist, pk = p.picked || {}
        const refile = sl.refile ? ` · ♻️ refiling (${sl.refile})` : ''
        // a motif made after this pass couldn't have been on its shortlist
        const existed = (id: string) => {
          const m = /^M(\d+)$/.exec(id)
          return !sl.next_motif || (!!m && +m[1] < sl.next_motif)
        }
        const missed = Object.entries(vd).filter(([id, k]) => k === true && existed(id) && !sl.rows.some((r) => r.id === id) && !(pk.made || []).includes(id)).map(([id]) => id)
        const picked = pk.picked || []
        return (
          <div key={n}>
            <Step emoji="🔦" title="the shortlist" at={when(sl.t) + refile} badge={<Traced yes={sl.traced} />}>
              {sl.traced && sl.features ? (
                <>
                  <p>
                    {sl.of} motifs scored by {sl.method === 'learned' ? 'the learned weights over every signal' : 'the plain weights'}; these {sl.rows.length} shown to the filing model, best first.
                    Each row a motif, each column a signal: <b>green pushed it up the list, red down</b>.
                  </p>
                  <Grid J={J} sl={sl} vd={vd} gl={gl} mode={mode} setMode={setMode} />
                  {sl.next && sl.next.length > 0 && (
                    <p className="faint">
                      next in line, not shown:{' '}
                      {sl.next.map((x) => <span key={x.id}><M J={J} id={x.id} cls={vcls(vd[x.id])} /> <span className="faint">#{x.rank + 1}</span> </span>)}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <p>{sl.rows.length} motifs shown to the filing model{sl.seeds && sl.seeds.length ? ` (${sl.seeds.length} of them seeds)` : ''}, best first:</p>
                  <p>{sl.rows.map((r) => <span key={r.id}><M J={J} id={r.id} cls={vcls(r.verdict)} pre={r.picked ? '⭐ ' : ''} /> </span>)}</p>
                  <Missing>
                    The signals behind this shortlist weren't recorded: it was drawn before tracing began{J.traced_since ? ` (${J.traced_since})` : ''}. Claims filed from now on show every signal for every motif.
                  </Missing>
                </>
              )}
              {missed.length > 0 && (
                <p>
                  🙈 you put it in <Ms J={J} ids={missed} cls={() => 'kept'} />, {missed.length === 1 ? 'which was' : 'which were'} not on this shortlist
                  {sl.next ? ' (' + missed.map((id) => { const x = sl.next!.find((y) => y.id === id); return x ? `#${x.rank + 1}` : 'further down' }).join(', ') + ')' : ''}.
                </p>
              )}
            </Step>
            <Step emoji="🤖" title="the filing model picks" at={when(pk.t)} badge={<Traced yes={sl.traced} />}>
              {picked.length ? <p>picked: <Ms J={J} ids={picked} cls={(id) => 'picked ' + vcls(vd[id])} /></p> : <p>none of them fits clearly.</p>}
              {pk.reason && <Quote>🤖 {pk.reason}</Quote>}
              {pk.new && pk.new.length > 0 && (
                <p>
                  it named a new motif: <b>{pk.new.join(', ')}</b>
                  {pk.made && pk.made.length ? <> → made <Ms J={J} ids={pk.made} /></>
                    : pk.filed && pk.filed.length && !picked.length ? <> → matched <Ms J={J} ids={pk.filed} /></> : null}
                </p>
              )}
              {pk.new_reason && <Quote>🤖 {pk.new_reason}</Quote>}
              {pk.was && (
                <p className="faint">
                  it was: {pk.was}
                  {pk.filed && pk.filed.length ? <>; now filed, unchecked, in <Ms J={J} ids={pk.filed} /></> : '; nothing new filed'}
                </p>
              )}
              {!pk.reason && !sl.traced && <Missing>Its reason wasn't kept before tracing began.</Missing>}
            </Step>
          </div>
        )
      })}
    </>
  )
}

/** A fit as a bar, with the sure line dashed across it */
function FitBar({ fit, sure }: { fit: number | null; sure: number | null | undefined }) {
  return (
    <div className="lv-fitbar" title={`fit ${pct(fit)}${sure ? ', sure from ' + pct(sure) : ''}`}>
      <i style={{ width: `${Math.round(100 * (fit || 0))}%` }} />
      {sure ? <span className="sure" style={{ left: `${Math.round(100 * sure)}%` }} title={`the sure line: ${pct(sure)}`} /> : null}
    </div>
  )
}

function PushLine({ p, dir, gl }: { p: Push; dir: 'up' | 'down'; gl: GlossOf }) {
  const g = gl(p.f)
  return (
    <div className={`lv-push ${dir}`}>
      <span className="v">{signed(p.c)}</span>
      <span><b title={p.f}>{g[0]}</b> <span className="faint">{val(p.f, p.v)} · {g[1]}</span></span>
    </div>
  )
}

function Scored({ J, gl }: { J: J; gl: GlossOf }) {
  const sc = J.scored, vd = verdictOf(J)
  const last = sc.traced[sc.traced.length - 1]
  let body: ReactNode
  if (last) {
    const first = last.filings[0]
    body = (
      <>
        <p>
          The confidence model weighs {first ? first.pushes.length : ''} signals, each value × its weight, plus a bias of {signed(first?.bias)}; the sum through a sigmoid is the fit.
          {last.sure_at ? ` Past ${pct(last.sure_at)} (the dashed line) a filing counts as sure.` : ''}
        </p>
        {last.filings.map((f) => {
          const up = f.pushes.filter((p) => p.c > 0).slice(0, 4), down = f.pushes.filter((p) => p.c < 0).slice(0, 4)
          return (
            <div className="lv-fit" key={f.id}>
              <b><M J={J} id={f.id} cls={vcls(vd[f.id])} /> {pct(f.fit)}</b> <span className="faint">(sum {signed(f.z)})</span>
              <FitBar fit={f.fit} sure={last.sure_at} />
              <div className="lv-pushes">
                <div>
                  <h4>⬆️ pushed up by</h4>
                  {up.length ? up.map((p) => <PushLine key={p.f} p={p} dir="up" gl={gl} />) : <p className="faint">nothing</p>}
                </div>
                <div>
                  <h4>⬇️ pulled down by</h4>
                  {down.length ? down.map((p) => <PushLine key={p.f} p={p} dir="down" gl={gl} />) : <p className="faint">nothing</p>}
                </div>
              </div>
              <details>
                <summary>every signal</summary>
                <table className="lv-all">
                  <tbody>
                    {f.pushes.map((p) => (
                      <tr key={p.f}><td>{gl(p.f)[0]}</td><td>{val(p.f, p.v)}</td><td>× {signed(p.w, 3)}</td><td><b>{signed(p.c)}</b></td></tr>
                    ))}
                    <tr><td>bias</td><td /><td /><td><b>{signed(f.bias)}</b></td></tr>
                  </tbody>
                </table>
              </details>
            </div>
          )
        })}
        {sc.traced.length > 1 && <p className="faint">scored {sc.traced.length} times; the latest shown (model of {when(last.model)}).</p>}
      </>
    )
  } else if (sc.now.length) {
    body = (
      <>
        <p>Its fits now:</p>
        {sc.now.map((x) => (
          <div className="lv-fit" key={x.id}>
            <b><M J={J} id={x.id} cls={vcls(vd[x.id])} /> {x.fit == null ? 'no fit' : pct(x.fit)}</b>{' '}
            <span className="faint">{x.yours ? '' : '(a motif not yours yet: not scored)'}{x.model ? ' model of ' + when(x.model) : ''}</span>
            {x.fit != null && <FitBar fit={x.fit} sure={sc.sure_at} />}
          </div>
        ))}
        <Missing>What pushed these fits up or down wasn't recorded before tracing began{J.traced_since ? ` (${J.traced_since})` : ''}.</Missing>
      </>
    )
  } else body = <Missing>No fit: it is in no motif of yours now.</Missing>
  return (
    <Step emoji="🎯" title="the confidence model" at={last ? when(last.t) : ''} badge={<Traced yes={!!last} />}>
      {body}
      {sc.alternatives.length > 0 && (
        <p>💡 where it might belong instead: {sc.alternatives.map((a) => <span key={a.id}><M J={J} id={a.id} cls={vcls(vd[a.id])} /> {pct(a.fit)} </span>)}</p>
      )}
    </Step>
  )
}

const VERB: Record<string, string> = {
  'moved out': '↪ moved out of', 'moved in': '↪ moved into', added: '➕ added to', 'into a new motif': '🌱 put in a new motif',
  'filed by hand': '✋ filed by hand in', unfile: '✕ taken out of', reject: '✕ rejected from', 'not this motif': '✕ not',
  'tells no story': '🚫 tells no story', reworded: '✏️ reworded', split: '✂️ split', 'carrying words': '🗣️ carrying words in',
}

function Decided({ J }: { J: J }) {
  if (!J.decided.length) {
    const now = J.scored.now
    return (
      <Step emoji="🧑" title="your verdict">
        <p className="faint">{now.length ? <>Not decided yet: waiting in <Ms J={J} ids={now.map((x) => x.id)} /></> : 'No verdict on record.'}</p>
      </Step>
    )
  }
  return (
    <Step emoji="🧑" title="your verdict" badge={<span className="lv-badge traced">curation log</span>}>
      {J.decided.map((d, i) => {
        const verb = d.act === 'check' ? (d.kept ? '✓ kept in' : d.kept === false ? '✕ taken out of' : '🤷 not sure of') : VERB[d.act] ?? d.act
        return (
          <div className="lv-dec" key={i}>
            <span className="faint">{when(d.t)} · {d.by === 'person' ? 'you' : d.by.split(',')[0]}</span>
            <br />
            {verb} {d.id ? <M J={J} id={d.id} cls={vcls(d.kept)} /> : d.name ? <b>{d.name}</b> : null}{' '}
            {d.fit != null && (
              <span className="faint">
                · its fit then {pct(d.fit)}{d.sure ? ' · 🎯 passed as sure' : d.sure_at && d.fit >= d.sure_at ? ' (past the sure line)' : ''}
              </span>
            )}
            {d.to && d.act === 'reworded' && <><br />→ “{String(d.to)}”</>}
            {d.to && d.act === 'carrying words' && <><br />{([] as string[]).concat(d.to).join(' · ')}</>}
            {d.why && <Quote>{d.why}</Quote>}
            {d.batch && <span className="faint">{d.batch}</span>}
          </div>
        )
      })}
    </Step>
  )
}

function Split({ J, onOpen }: { J: J; onOpen: (k: string) => void }) {
  const sp = J.split
  const proposed = sp.proposed || []
  if (!proposed.length && !sp.children && !sp.from) return null
  return (
    <Step emoji="✂️" title="split">
      {proposed.map((p, i) => (
        <p key={i}>
          🤖 the organizer read its posts: {p.split ? 'they tell different things' : 'one telling'}{p.reason ? ` (${p.reason})` : ''}
          {p.triggers && <><br /><span className="faint">asked because: {p.triggers.join(', ')}</span></>}
        </p>
      ))}
      {sp.children && (
        <>
          <p>✂️ split {sp.by === 'model' ? 'as the organizer drafted it' : 'in your words'}{sp.at ? ' on ' + when(sp.at) : ''} into:</p>
          {sp.children.map((c) => (
            <button key={c.k} className="lv-quote lv-claimlink" onClick={() => onOpen(c.k)} title="follow this claim">
              {c.c} <span className="faint">#{c.k.slice(0, 6)} →</span>
            </button>
          ))}
          {sp.why && <Quote>{sp.why}</Quote>}
        </>
      )}
      {sp.from && (
        <p>
          ✂️ split from{' '}
          <button className="lv-claimlink lv-inline" onClick={() => onOpen(sp.from!.k)} title="follow the claim it was split from">
            <b>“{sp.from.c}”</b> <span className="faint">#{sp.from.k.slice(0, 6)} →</span>
          </button>
        </p>
      )}
    </Step>
  )
}

function Downstream({ J }: { J: J }) {
  const now = J.scored.now
  if (!now.length) return null
  return (
    <Step emoji="🌊" title="downstream">
      {now.map((x) => {
        const m = J.motifs[x.id] || { name: x.id }, t = m.told || {}
        const story = x.story != null
          ? J.stories[x.story] ? `📰 about the story “${J.stories[x.story].label}” (${x.story_tie || 'tied'})` : `📰 story #${x.story} (${x.story_tie || 'tied'})`
          : ''
        return (
          <div className="lv-dec" key={x.id}>
            <M J={J} id={x.id} cls={x.checked === 'yes' ? 'kept' : ''} />{' '}
            <span className="faint">
              {m.genre || 'no genre'} · {m.size} claims
              {t.events ? ` · told on ${t.events} ${plural(t.events, 'occasion')} (${(t.sources || []).join(', ')}${t.span && t.span.length ? ', ' + t.span.join(' to ') : ''})` : ''}
            </span>
            {story && <><br />{story}</>}
            {x.carrying && x.carrying.length > 0 && <><br />🗣️ carrying words: {x.carrying.map((w) => `“${w}”`).join(', ')}</>}
            {x.variants > 0 && <><br /><span className="faint">{x.variants} other {plural(x.variants, 'wording')} folded in</span></>}
            {x.refiled && <><br /><span className="faint">♻️ refiled {x.refiled.at} (was {x.refiled.was})</span></>}
          </div>
        )
      })}
    </Step>
  )
}

function Glossary({ glossary }: { glossary: Record<string, [string, string]> }) {
  return (
    <details className="lv-card lv-glossary">
      <summary><b>📖 what the signals mean</b></summary>
      <dl>
        {Object.entries(glossary).map(([f, g]) => (
          <div key={f}>
            <dt>{g[0]} <span className="faint">({f})</span></dt>
            <dd>{g[1]}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}

export function Journey({ J, gl, glossary, mode, setMode, onOpen, onClose }: Props) {
  return (
    <>
      <div className="lv-card lv-jhead">
        <button className="lv-close" title="close" aria-label="close the journey" onClick={onClose}>✕</button>
        <p className="faint">
          🧭 the journey of claim #{J.claim.id6}{' '}
          {J.traced ? <span className="lv-badge traced">traced</span> : <span className="lv-badge rebuilt">from before tracing: rebuilt from the logs</span>}
        </p>
        <h2>“{J.claim.c || "(its words aren't known)"}”</h2>
        <p className="faint">
          {J.claim.c ? <a href={claimLink(J.claim.c)}>🧰 work on it in the workbench</a> : <>search #{J.claim.id6} in the workbench to work on it</>}
          {' · '}<a href={`#claim=${J.claim.k}`}>🔗 link to this journey</a>
        </p>
      </div>
      <div className="lv-steps">
        <Written J={J} />
        <Shaped J={J} />
        <Passes J={J} gl={gl} mode={mode} setMode={setMode} />
        <Scored J={J} gl={gl} />
        <Decided J={J} />
        <Split J={J} onOpen={onOpen} />
        <Downstream J={J} />
      </div>
      <Glossary glossary={glossary} />
    </>
  )
}
