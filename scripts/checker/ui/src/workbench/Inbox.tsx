// The right pane: the inbox of decisions, a tab each, with what waits in it
import { useWorkbench, isEmpty, isSingle } from './model'
import { useJudging } from './judge'
import { setTab } from './ops'
import { useWB } from './store'
import { ClaimView, JudgeTab } from './tabs/ClaimView'
import { EmptyTab, FindTab, HeldTab, PairsTab, QuickTab, SinglesTab, TodayTab, UnfiledTab } from './tabs/Lists'
import { ProposalsTab, SplitsTab, TellingsTab } from './tabs/Proposals'
import { StatsTab } from './tabs/Stats'

// Five tabs, each with its parts (Oct 22: fifteen tabs in three rows were too many to scan, and took 106 px a laptop
// couldn't spare). A part is still its own tab underneath (the store's tab, setTab), so links and keys into one work
// as before; a tab opens on the part last used in it
const GROUPS: { key: string; label: string; parts: [string, string][] }[] = [
  { key: 'judge', label: '🎯 judge', parts: [['judge', '🎯 claims to judge'], ['sure', '✅ sure'], ['misfits', '🚫 misfits'], ['held', '⏸ held']] },
  { key: 'shape', label: '✨ shape', parts: [['today', '✨ to shape'], ['proposals', '💡 proposals'], ['splits', '✂️ splits'], ['tellings', '🧩 tellings']] },
  { key: 'tidy', label: '🧹 tidy', parts: [['pairs', '🔗 pairs'], ['singles', '1️⃣ singles'], ['empty', '🫙 empty'], ['claims', '📥 unfiled']] },
  { key: 'find', label: '🔎 find', parts: [['find', '🔎 claims'], ['claim', '🔍 claim']] },
  { key: 'stats', label: '📊 stats', parts: [['stats', '📊 stats']] },
]
const groupOf = (tab: string) => GROUPS.find((g) => g.parts.some(([k]) => k === tab)) ?? GROUPS[0]

export function Inbox() {
  const { model: m } = useWorkbench()
  const tab = useWB((s) => s.tab)
  const lastPart = useWB((s) => s.lastPart)
  const claim = useWB((s) => s.claim)
  const j = useJudging()
  if (!m) return <section className="pane inbox-pane" />
  const d = m.data
  const group = groupOf(tab)
  const counts: Record<string, number | undefined> = {
    judge: j ? j.items.length : d.to_check + d.second_look, sure: j?.sure.length, misfits: j?.out.length, held: (d.held ?? []).length,
    proposals: d.proposals, splits: d.splits, tellings: d.tellings,
    singles: d.entries.filter((e) => isSingle(m, e)).length, empty: d.entries.filter((e) => isEmpty(m, e)).length,
  }
  return (
    <section className="pane inbox-pane" aria-label="Inbox">
      <div className="pane-head">
        <div className="tabs" role="tablist">
          {GROUPS.map((g) => {
            const n = g.key === 'judge' ? counts.judge : g.parts.reduce<number | undefined>((t, [k]) => counts[k] === undefined ? t : (t ?? 0) + counts[k]!, undefined)
            return <button key={g.key} role="tab" className={'tab' + (group.key === g.key ? ' on' : '')}
              onClick={() => setTab(g.key === group.key ? tab : (lastPart[g.key] ?? g.parts[0][0]))}>{g.label}{n !== undefined && <> <i>{n}</i></>}</button>
          })}
        </div>
        {group.parts.length > 1 && (
          <div className="parts" role="tablist">
            {group.parts.map(([k, label]) => <button key={k} role="tab" className={'part' + (tab === k ? ' on' : '')} onClick={() => setTab(k)}>{label}{counts[k] !== undefined && <> <i>{counts[k]}</i></>}</button>)}
          </div>
        )}
      </div>
      <div className="scroll inbox-scroll" data-scroll>
        {tab === 'stats' ? <StatsTab />
          : tab === 'judge' ? <JudgeTab j={j} />
            : tab === 'sure' ? <QuickTab kind="sure" j={j} />
              : tab === 'misfits' ? <QuickTab kind="out" j={j} />
                : tab === 'held' ? <HeldTab />
                  : tab === 'today' ? <TodayTab />
                    : tab === 'find' ? <FindTab />
                      : tab === 'claim' ? <ClaimView claim={claim} j={j} />
                        : tab === 'pairs' ? <PairsTab />
                          : tab === 'singles' ? <SinglesTab />
                            : tab === 'proposals' ? <ProposalsTab />
                              : tab === 'splits' ? <SplitsTab />
                                : tab === 'tellings' ? <TellingsTab />
                                  : tab === 'claims' ? <UnfiledTab />
                                    : tab === 'empty' ? <EmptyTab /> : null}
      </div>
    </section>
  )
}
