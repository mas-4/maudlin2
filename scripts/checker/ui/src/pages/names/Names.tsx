// 👥 names (#165): one name per subject for the front page's "mentioned:" filters. Suggested merges first (a name
// inside another), then every subject with the other names that point to it, searchable and sortable. Each change is
// POST /entities (merge, not_same, unmerge; a rename is a merge into the typed name), undoable, and the page fetches
// /entities.json again after. A subject's name line, or one of its other names, drags onto another subject.
import { memo, useCallback, useDeferredValue, useMemo, useRef, useState } from 'react'
import { useJSON, useWrite } from '../../lib/queries'
import { ask, sure, toast } from '../../components/Feedback'
import { NameDrag, type Choice, type NameItem } from './NameDrag'
import './names.css'

interface Subject { name: string; stories: number; names: string[] }
interface Pair { a: string; b: string; a_stories: number; b_stories: number }
interface NamesData { pairs: Pair[]; name_count: number; subjects: Subject[] }
type Body = { action: 'merge'; source: string; target: string } | { action: 'not_same'; a: string; b: string } | { action: 'unmerge'; name: string }
/** One change: what to post, what the toast says after, and the pressed button's key (it shows ⏳ meanwhile) */
type Act = (body: Body, said: string, key?: string) => Promise<void>

const SORTS = {
  most: { label: 'most stories', by: (a: Subject, b: Subject) => b.stories - a.stories || a.name.localeCompare(b.name) },
  fewest: { label: 'fewest stories', by: (a: Subject, b: Subject) => a.stories - b.stories || a.name.localeCompare(b.name) },
  az: { label: 'A–Z', by: (a: Subject, b: Subject) => a.name.localeCompare(b.name) },
  za: { label: 'Z–A', by: (a: Subject, b: Subject) => b.name.localeCompare(a.name) },
  aliases: { label: 'most other names', by: (a: Subject, b: Subject) => b.names.length - a.names.length || b.stories - a.stories },
}
type Sort = keyof typeof SORTS

const q = (x: string) => `“${x}”`
const stories = (n: number) => `${n} stor${n === 1 ? 'y' : 'ies'}`

// The sort is remembered in this browser; storage may be off (a private window), and then it isn't
function savedSort(): Sort {
  try {
    const s = localStorage.getItem('nm-sort')
    if (s && s in SORTS) return s as Sort
  } catch { /* no storage */ }
  return 'most'
}

export function Names() {
  const data = useJSON<NamesData>('/entities.json')
  const { mutateAsync } = useWrite<Body>('/entities')
  const [busy, setBusy] = useState<string | null>(null)
  const busyRef = useRef<string | null>(null)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<Sort>(savedSort)
  const query = useDeferredValue(search.trim().toLowerCase())

  const act: Act = useCallback(async (body, said, key = 'drag') => {
    if (busyRef.current) {
      toast('⏳ still saving…')
      return
    }
    busyRef.current = key
    setBusy(key)
    document.body.classList.add('acting')
    try {
      await mutateAsync(body)
      toast(said, false, true)
    } catch (e) {
      toast('Couldn’t save: ' + (e as Error).message, true)
    } finally {
      busyRef.current = null
      setBusy(null)
      document.body.classList.remove('acting')
    }
  }, [mutateAsync])

  // what letting go of a subject, or one of its other names, on another subject can mean (as the old page offered)
  const choices = useCallback((i: NameItem, other: string): Choice[] => {
    if (!other || other === i.of) return []
    if (i.alias)
      return [{ label: '⇢ a name for this one', say: `${q(i.name)} now names ${q(other)} (no longer ${q(i.of)}).`,
        run: () => act({ action: 'merge', source: i.name, target: other }, `⇢ ${q(i.name)} now names ${q(other)}`) }]
    return [
      { label: '⤵ another name for it', say: `${q(i.name)} is another name for ${q(other)}: its stories and names go under ${q(other)}.`,
        run: () => act({ action: 'merge', source: i.name, target: other }, `⤵ ${q(i.name)} is now another name for ${q(other)}`) },
      { label: '⤴ it is another name for this', say: `${q(other)} is another name for ${q(i.name)}: its stories and names go under ${q(i.name)}.`,
        run: () => act({ action: 'merge', source: other, target: i.name }, `⤴ ${q(other)} is now another name for ${q(i.name)}`) },
      { label: '✗ different subjects', say: `${q(i.name)} and ${q(other)} are kept apart (never suggested as one).`,
        run: () => act({ action: 'not_same', a: i.name, b: other }, `✗ ${q(i.name)} and ${q(other)} kept apart`) },
    ]
  }, [act])

  const subjects = data.data?.subjects
  const known = useMemo(() => new Set((subjects ?? []).map((s) => s.name.toLowerCase())), [subjects])
  const shown = useMemo(() => {
    const list = (subjects ?? []).filter((s) => !query || (s.name + ' ' + s.names.join(' ')).toLowerCase().includes(query))
    return list.sort(SORTS[sort].by)
  }, [subjects, query, sort])

  // ⤵ another name for…: asked in place. A name no subject has yet makes it a rename, so that is asked first
  const mergeInto = useCallback(async (source: string, anchor: Element) => {
    const target = await ask(`${q(source)} is another name for which subject?`, '', { anchor })
    if (!target || target === source) return
    if (!known.has(target.toLowerCase()) && !(await sure(`No subject is called ${q(target)} yet: rename ${q(source)} to it?`, '✎ rename it', anchor)))
      return
    await act({ action: 'merge', source, target }, `⤵ ${q(source)} is now another name for ${q(target)}`, 'into:' + source)
  }, [act, known])

  if (data.isPending) return <main className="page nm-page"><p className="empty">⏳ loading the names…</p></main>
  if (data.isError) return <main className="page nm-page"><p className="empty">😵 Couldn’t load the names: {data.error.message}</p></main>
  const d = data.data

  return (
    <main className="page nm-page">
      <section className="card nm-intro">
        <h1>👥 Names</h1>
        <p>
          The people, places and groups the local model names in each story, for the “mentioned:” filters on the front
          page: {d.subjects.length} subjects under {d.name_count} names. Give each subject one name: merge names for the
          same subject, rename a subject, or keep two apart. Or drag: a subject by its name line (⠿) onto another
          subject, or one of its other names onto the subject it belongs to. Changes go live with the next site build.
        </p>
      </section>

      <h2 className="nm-head">🤝 Suggested merges</h2>
      {d.pairs.length ? d.pairs.map((p) => <PairCard key={p.a + '|' + p.b} p={p} busy={busy} act={act} />)
        : <p className="nm-none">🌱 No suggestions right now: no name sits inside another that isn’t already one subject or kept apart.</p>}

      <h2 className="nm-head">🗣️ Every subject</h2>
      <div className="nm-tools">
        <input type="search" placeholder="🔍 search names" value={search} onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') setSearch('') }} />
        <select value={sort} aria-label="sort" onChange={(e) => {
          const s = e.target.value as Sort
          setSort(s)
          try { localStorage.setItem('nm-sort', s) } catch { /* no storage */ }
        }}>
          {Object.entries(SORTS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
        </select>
        <span className="faint">{query ? `${shown.length} of ${d.subjects.length} shown` : `${d.subjects.length} subjects`}</span>
      </div>
      {shown.length ? shown.map((s) => <SubjectCard key={s.name} s={s} busy={busyIn(busy, s)} act={act} mergeInto={mergeInto} />)
        : <p className="nm-none">🤷 No subject goes by {q(search.trim())}.</p>}
      <NameDrag choices={choices} />
    </main>
  )
}

/** The pressed button's key if it is on this subject's card (so only that card redraws) */
function busyIn(busy: string | null, s: Subject) {
  if (!busy) return null
  const [kind, ...rest] = busy.split(':'), name = rest.join(':')
  return (kind === 'alias' ? s.names.includes(name) : name === s.name) ? busy : null
}

function PairCard({ p, busy, act }: { p: Pair; busy: string | null; act: Act }) {
  const key = (k: string) => `${k}:${p.a}|${p.b}`
  const cls = (k: string) => 'btn' + (busy === key(k) ? ' busy' : '')
  return (
    <section className="card nm-pair">
      <p className="nm-said">one name inside the other</p>
      <div className="nm-two">
        <div><b>{p.a}</b> <span className="nm-said">{stories(p.a_stories)}</span></div>
        <div><b>{p.b}</b> <span className="nm-said">{stories(p.b_stories)}</span></div>
      </div>
      <div className="nm-row">
        <button className={cls('ab')} onClick={() => act({ action: 'merge', source: p.a, target: p.b }, `⤵ ${q(p.a)} is now another name for ${q(p.b)}`, key('ab'))}>
          ⤵ {q(p.a)} is {q(p.b)}
        </button>
        <button className={cls('ba')} onClick={() => act({ action: 'merge', source: p.b, target: p.a }, `⤵ ${q(p.b)} is now another name for ${q(p.a)}`, key('ba'))}>
          ⤵ {q(p.b)} is {q(p.a)}
        </button>
        <button className={cls('apart')} onClick={() => act({ action: 'not_same', a: p.a, b: p.b }, `✗ ${q(p.a)} and ${q(p.b)} kept apart`, key('apart'))}>
          ✗ different subjects
        </button>
      </div>
    </section>
  )
}

// One subject's card, redrawn only when its own data or its pressed button changes (there are well over a thousand)
const SubjectCard = memo(function SubjectCard({ s, busy, act, mergeInto }: {
  s: Subject; busy: string | null; act: Act; mergeInto: (source: string, anchor: Element) => Promise<void>
}) {
  const field = useRef<HTMLInputElement>(null)
  const rename = () => {
    const target = field.current?.value.trim() ?? ''
    if (!target || target === s.name) {
      toast('✎ type the new name first')
      field.current?.focus()
      return
    }
    void act({ action: 'merge', source: s.name, target }, `✎ ${q(s.name)} is now ${q(target)}`, 'rename:' + s.name)
  }
  const cls = (k: string) => (busy === k ? ' busy' : '')
  return (
    <section className="card nm-subject" data-nm-drop="" data-name={s.name}>
      <p className="nm-grip" data-nm-drag="" data-name={s.name} data-of={s.name} title="drag onto another subject">
        <span aria-hidden="true">⠿ </span>{s.name} · {stories(s.stories)}
      </p>
      <div className="nm-row">
        <input ref={field} className="nm-name" defaultValue={s.name} aria-label={`new name for ${s.name}`}
          onKeyDown={(e) => { if (e.key === 'Enter') rename() }} />
        <button className={'btn' + cls('rename:' + s.name)} onClick={rename}>✎ rename</button>
        <button className={'btn' + cls('into:' + s.name)} onClick={(e) => void mergeInto(s.name, e.currentTarget)}>⤵ another name for…</button>
      </div>
      {s.names.length > 0 && (
        <p className="nm-said nm-aliases">
          also named:{' '}
          {s.names.map((n) => (
            <span key={n} className="nm-alias-wrap">
              <span className="nm-alias" data-nm-drag="" data-alias="1" data-name={n} data-of={s.name}
                title="drag onto another subject to move just this name">{n}</span>
              <button className={'mini' + cls('alias:' + n)} title={`${q(n)} isn’t ${q(s.name)}: give it back its own subject`}
                onClick={() => act({ action: 'unmerge', name: n }, `✗ ${q(n)} no longer names ${q(s.name)}`, 'alias:' + n)}>✗ not this</button>
            </span>
          ))}
        </p>
      )}
    </section>
  )
})
