"""The person's corrections of the model's drafts, as records: the draft, what the person said was wrong, and what they
made of it. Fable (Oct 12): the loop of proposal, critique, correction and approval is the best teaching material the
project has (the Brothers Grimm's only win was showing the model the person's corrections of its own drafts) and also
the trail of the person's authorship (a name or note they rewrote is theirs; a draft only approved is the machine's).

Three sources, read, never written here:

    proposals        a proposal decided with the person's words (`why`, from the checker's "what was wrong?" or with
                     the decision) or carried out other than proposed (`final`)
    the log's why    any checker action sent with a `why` (the MCP passes the person's words along with the change)
    rewritten drafts a note action over a drafted note, or a rename of a motif the model made: draft and final, no why

    critiques()      every record, oldest first: {'at', 'kind', 'draft', 'why', 'final', 'by'}"""
from app.analysis import curation_db, motif_index as mi, motif_proposals as mp


def from_proposals() -> list[dict]:
    out = []
    for p in mp.load().values():
        if p.get('status') in ('approved', 'rejected') and (p.get('why') or p.get('final')):
            out.append({'at': p.get('decided') or p.get('made', ''), 'kind': f"proposal {p['kind']} {p['status']}",
                        'draft': {'args': p.get('args'), 'reason': p.get('reason')}, 'why': p.get('why', ''),
                        'final': p.get('final'), 'by': 'person'})
    return out


def from_log() -> list[dict]:
    out = []
    for row in curation_db.actions():
        a, before = row['action'], row['before'] or {}
        if a.get('action') == 'critique':  # the proposal's own record has it
            continue
        batch = a.get('action') == 'batch'
        for n, s in enumerate((a.get('steps') if batch else [a]) or []):
            if not isinstance(s, dict):
                continue
            # what the motif was before: a batch's first step, or any step since each got its own context (Oct 12)
            ctx = (before.get('steps') or [])[n] if batch and before.get('steps') else before if n == 0 else {}
            was = ctx.get('id') if isinstance((ctx or {}).get('id'), dict) else {}
            if was and was.get('id') != s.get('id'):
                was = {}
            draft = None
            if s.get('action') == 'note' and was.get('note_by') in mi.DRAFTS and was.get('note') != s.get('note'):
                draft = {'note': was.get('note')}
            elif s.get('action') == 'rename' and was.get('by') == 'model' and was.get('name') != s.get('name'):
                draft = {'name': was.get('name')}
            why = s.get('why') or a.get('why') or ''
            if draft or why:
                out.append({'at': row['at'], 'kind': s.get('action', ''), 'draft': draft or was or None, 'why': why,
                            'final': {k: v for k, v in s.items() if k != 'why'}, 'by': row['by'] or 'person'})
    return out


def critiques() -> list[dict]:
    return sorted(from_proposals() + from_log(), key=lambda r: r['at'])
