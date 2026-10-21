// The right pane: the inbox of decisions, a tab each, with what waits in it
import { useWorkbench, isEmpty, isSingle } from './model'
import { useJudging } from './judge'
import { setTab } from './ops'
import { useWB } from './store'
import { ClaimView, JudgeTab } from './tabs/ClaimView'
import { EmptyTab, FindTab, HeldTab, PairsTab, QuickTab, SinglesTab, TodayTab, UnfiledTab } from './tabs/Lists'
import { ProposalsTab, SplitsTab, TellingsTab } from './tabs/Proposals'
import { StatsTab } from './tabs/Stats'

const TABS: [string, string][] = [['stats', '📊'], ['judge', '🎯 claims to judge'], ['sure', '✅ sure'], ['misfits', '🚫 misfits'], ['held', '⏸ held'], ['today', '✨ to shape'],
  ['find', '🔎 claims'], ['claim', '🔍 claim'], ['pairs', '🔗 pairs'], ['singles', '1️⃣ singles'], ['proposals', '💡 proposals'], ['splits', '✂️ splits'],
  ['tellings', '🧩 tellings'], ['claims', '📥 unfiled'], ['empty', '🫙 empty']]

export function Inbox() {
  const { model: m } = useWorkbench()
  const tab = useWB((s) => s.tab)
  const claim = useWB((s) => s.claim)
  const j = useJudging()
  if (!m) return <section className="pane inbox-pane" />
  const d = m.data
  const counts: Record<string, number | undefined> = {
    judge: j ? j.items.length : d.to_check + d.second_look, sure: j?.sure.length, misfits: j?.out.length, held: (d.held ?? []).length,
    proposals: d.proposals, splits: d.splits, tellings: d.tellings,
    singles: d.entries.filter((e) => isSingle(m, e)).length, empty: d.entries.filter((e) => isEmpty(m, e)).length,
  }
  return (
    <section className="pane inbox-pane" aria-label="Inbox">
      <div className="pane-head"><div className="tabs" role="tablist">
        {TABS.map(([k, label]) => <button key={k} role="tab" className={'tab' + (tab === k ? ' on' : '')} onClick={() => setTab(k)}>{label}{counts[k] !== undefined && <> <i>{counts[k]}</i></>}</button>)}
      </div></div>
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
