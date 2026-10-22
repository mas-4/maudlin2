// Where a claim came from (/claim-detail.json): the fact-check, the posts that told it, the shows and their
// transcripts, the Focus Group passage; and the same as plain text for 📋 copy. A motif as plain text too.
import { useJSON } from '../lib/queries'
import { clock } from './bits'
import { currentModel, motifsOf, newCount, SOURCE, type Model } from './model'
import { copyText } from './ops'
import type { Entry } from './types'

interface Telling { show: string; lean?: string; title?: string; date?: string; url?: string; speaker?: string; at?: number; claim?: string; quote?: string;
  context?: { before: string; quote: string; after: string } }
export interface ClaimDetail {
  kind?: string; split_from?: string; title?: string; url?: string; context?: { before: string; quote: string; after: string }; quote?: string
  side?: string; people?: number; tellings?: Telling[]; all_posts?: { text: string; n: number; reply?: boolean; source?: string }[]
  examples?: string[]; posts?: number; summary?: string; label?: Record<string, string>; piece?: string; model_words?: string | string[]
}

// Who said it on the show (app/analysis/show_claims.py SPEAKERS), said plainly (Oct 22: "clip" was a faint word at the
// end of the line, and a right-wing clip The Young Turks played read as theirs)
const SPEAKER: Record<string, string> = {
  host: '🎙️ the show’s own hosts', guest: '🎤 a guest the hosts interview', caller: '📞 a listener calling in',
  clip: '▶️ a clip the show played: someone else’s words, not the hosts’ (shows often play a clip to answer it)',
}

export function useDetail(claim: string | undefined) {
  return useJSON<ClaimDetail>('/claim-detail.json', { claim }, { enabled: !!claim })
}

export function Detail({ claim }: { claim: string }) {
  const { data: x, isLoading, error } = useDetail(claim)
  if (isLoading) return <div className="detail">⏳</div>
  if (error || !x) return <div className="detail">😬 couldn’t load it</div>
  const lab = x.label ?? {}
  const shows = new Set((x.tellings ?? []).map((t) => t.show)).size
  const words = ([] as string[]).concat(x.model_words ?? []).filter((m) => m && m !== claim)
  return (
    <div className="detail">
      <div>
        <button className="mini copy" onClick={() => void copyText(detailText(x, claim))} title="copy the claim, where it came from and every post">📋 copy</button>
        <b>{x.kind}</b>
      </div>
      {x.split_from && <div className="faint">✂️ split from: “{x.split_from}”</div>}
      {x.title && <div>{x.url ? <a href={x.url} target="_blank" rel="noopener">{x.title}</a> : x.title}</div>}
      {x.context ? (
        <div className="transcript">🗣️ {x.context.before}<mark>{x.context.quote}</mark>{x.context.after}{x.side && <span className="faint"> · the voter: {x.side}</span>}</div>
      ) : x.quote ? <div>🗣️ “{x.quote}”{x.side ? ' · ' + x.side : ''}</div> : null}
      {x.people ? <div>🧶 told by {x.people} people</div> : null}
      {(x.tellings ?? []).length > 0 && (
        <div>
          🎙️ told {x.tellings!.length} time{x.tellings!.length === 1 ? '' : 's'} on {shows} show{shows === 1 ? '' : 's'}
          {x.tellings!.map((t, i) => (
            <div className="telling" key={i}>
              <b>{t.show}</b>{t.lean && <span className="faint"> (the show: {t.lean})</span>} ·{' '}
              {t.url ? <a href={t.url} target="_blank" rel="noopener">{t.title || 'the episode'}</a> : t.title || 'an episode'}{' '}
              <span className="faint">{t.date}{t.at != null ? ` · the part from ${clock(t.at)}` : ''}</span>
              {t.speaker && <div className={'speaker ' + t.speaker}>{SPEAKER[t.speaker] ?? t.speaker}</div>}
              {t.claim && t.claim !== claim && <div className="faint">as read there: “{t.claim}”</div>}
              {t.context ? <div className="transcript">🗣️ {t.context.before}<mark>{t.context.quote}</mark>{t.context.after}</div>
                : t.quote ? <div>🗣️ “{t.quote}”</div> : null}
            </div>
          ))}
        </div>
      )}
      {(x.all_posts ?? []).length > 0 ? (
        <details className="posts" open>
          <summary>💬 all {x.all_posts!.reduce((n, p) => n + p.n, 0)} posts still kept ({x.all_posts!.length} different)</summary>
          {x.all_posts!.map((p, i) => (
            <q key={i}>{p.text}{p.n > 1 && <b className="faint"> ×{p.n}</b>}{p.reply && <span className="faint"> ↩ reply</span>}{p.source === 'mastodon' && <span className="faint"> 🐘</span>}</q>
          ))}
        </details>
      ) : (
        <div>
          {(x.examples ?? []).map((t, i) => <q key={i}>{t}</q>)}
          {(x.posts ?? 0) > (x.examples ?? []).length && <span className="faint">{(x.examples ?? []).length} of {x.posts} posts: the report kept only a sample</span>}
        </div>
      )}
      {x.summary && <div>{x.summary}</div>}
      {lab.context && <div>📰 {lab.context}</div>}
      {lab['claim from the piece'] && lab['claim from the piece'] !== claim && (
        <div><span className="faint">as the piece tells it:</span> “{lab['claim from the piece']}”</div>
      )}
      {x.piece && <details className="posts"><summary>📄 the piece's opening</summary><div className="piece">{x.piece}</div></details>}
      {words.length > 0 && <div>the model's words: {words.map((m) => '“' + m + '”').join(' · ')}</div>}
    </div>
  )
}

/** Where a claim came from as plain text: the claim, its source, every telling and post, its motifs with their notes */
export function detailText(x: ClaimDetail, claim: string) {
  const m = currentModel()
  const posts = (x.all_posts ?? []).length ? x.all_posts!.map((p) => `- ${p.text}${p.n > 1 ? ` (×${p.n})` : ''}`) : (x.examples ?? []).map((t) => `- ${t}`)
  const ms = m ? motifsOf(m, claim) : []
  const words = ([] as string[]).concat(x.model_words ?? []).filter((w) => w && w !== claim)
  return [
    `Claim: ${claim}`,
    x.kind ? `Source: ${x.kind}${x.title ? ', ' + x.title : ''}${x.url ? ' ' + x.url : ''}` : '',
    x.context ? `Transcript: ${x.context.before}${x.context.quote}${x.context.after}${x.side ? ` (the voter: ${x.side})` : ''}` : x.quote ? `Quote: “${x.quote}”${x.side ? ' · ' + x.side : ''}` : '',
    x.people ? `Told by ${x.people} people` : '',
    (x.tellings ?? []).length ? `Told on the shows (${x.tellings!.length}):\n` + x.tellings!.map((t) => `- ${t.show}${t.lean ? ' (' + t.lean + ')' : ''}, ${t.title || 'an episode'} ${t.date || ''}`
      + `${t.at != null ? ', the part from ' + clock(t.at) : ''}${t.speaker ? ', ' + t.speaker : ''}${t.url ? ' ' + t.url : ''}`
      + (t.claim && t.claim !== claim ? `\n  As read there: ${t.claim}` : '')
      + (t.context ? `\n  Transcript: ${t.context.before}${t.context.quote}${t.context.after}` : t.quote ? `\n  Quote: “${t.quote}”` : '')).join('\n') : '',
    ms.length ? `Motifs (${ms.length}):\n` + ms.map((e) => `- ${e.name} (${e.id})${e.note ? ': ' + e.note : ': no note yet'}`).join('\n') : 'Motifs: none yet',
    x.summary ?? '',
    x.label?.context ? `What the piece shows: ${x.label.context}` : '',
    x.label?.['claim from the piece'] && x.label['claim from the piece'] !== claim ? `As the piece tells it: ${x.label['claim from the piece']}` : '',
    x.piece ? `The piece's opening:\n${x.piece}` : '',
    words.length ? `The model's words: ${words.map((w) => '“' + w + '”').join(' · ')}` : '',
    posts.length ? `Posts (${posts.length}):\n${posts.join('\n')}` : '',
  ].filter(Boolean).join('\n')
}

/** Every motif sharing claims with this one, and how many */
export function sharedWith(m: Model, e: Entry): [string, number][] {
  const shared: Record<string, number> = {}
  for (const c of e.claims) for (const o of motifsOf(m, c.claim)) if (o.id !== e.id) shared[o.id] = (shared[o.id] ?? 0) + 1
  return Object.entries(shared).sort((a, b) => b[1] - a[1])
}

/** A motif as plain text, for its 📋 copy: as the panel shows it, the motifs it's linked to with their notes */
export function motifText(m: Model, e: Entry) {
  const named = (id: string) => { const o = m.by[id]; return o ? `- ${o.name} (${id})${o.note ? ': ' + o.note : ': no note yet'}` : '' }
  const list = (label: string, ids: string[], note?: (id: string) => string) => ids.length
    ? `${label} (${ids.length}):\n` + ids.map((id) => named(id) + (note?.(id) ? ` [related: ${note(id)}]` : '')).filter(Boolean).join('\n') : `${label}: none`
  const shared = sharedWith(m, e)
  const groups = (e.groups ?? []).map((g) => m.data.groups.find((x) => x.id === g)?.name ?? g)
  return [
    `Motif: ${e.name} (${e.id})`,
    [`${e.claims.length} claim${e.claims.length === 1 ? '' : 's'}`, e.done === 'done' ? 'done' : e.done === 'new' ? `done, ${newCount(e)} new since` : 'not done',
      e.curated ? 'made by hand' : 'made by the model', e.first_seen ? 'since ' + e.first_seen.slice(0, 10) : ''].filter(Boolean).join(' · '),
    `Note: ${e.note || 'none yet'}`,
    e.not_this ? `Not this: ${e.not_this}` : '',
    e.told ? `Told on ${e.told.events} occasion${e.told.events === 1 ? '' : 's'} (${e.attested ? 'attested' : 'placed'}), ${(e.told.span ?? []).join(' to ')}` : '',
    `Groups: ${groups.join(', ') || 'none'}`,
    `Genre: ${e.facets?.genre || 'none'}`,
    list('Rests on', e.parents),
    list('Rest on it', m.kids[e.id] ?? []),
    list('Related', e.related, (id) => e.related_notes?.[id] ?? ''),
    shared.length ? `Shares claims with (${shared.length}): ` + shared.map(([o, n]) => `${m.by[o]?.name ?? o} (${n})`).join(', ') : '',
    `Claims (${e.claims.length}):\n` + e.claims.map((c) => `- ${c.checked === 'yes' ? '✓ ' : ''}${c.claim} [#${c.id}, ${SOURCE[c.source] || c.source || 'unknown'}]`).join('\n'),
  ].filter(Boolean).join('\n')
}
