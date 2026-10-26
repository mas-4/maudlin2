"""Every change to the motif index, by name: the checker's pages and the MCP server send an action ({"action": name,
...fields}) and apply() checks its fields and carries it out (Oct 21, Fable's architecture review: the checker had
grown 61 `if act ==` branches over three functions, and the only list of the actions was the MCP tool's docstring).

ACTIONS is the table: each name, the fields it needs and what kind each must be, and the verb it runs. A few
actions are more than one verb and stay as code in apply(): a batch of steps, a proposal approved or rejected, a
claim's split, a telling made a motif, and a new motif made from claims dropped on it.

Field kinds, checked before anything runs:
  motif  the id of a live motif (not merged away)
  group  the id of a group
  text   a string with something in it
  str    a string, maybe empty (clears a note)
  words  a string or a list of strings (the carrying words)
  facet  a facet the index sorts by (genre)"""
from collections.abc import Callable

from app.analysis import motif_index as mi

ON = lambda d, k: d.get(k, True) is not False  # noqa: E731 - a switch that's on unless sent false


class _Context:
    """The index as an action sees it, read once when first needed (inside a batch: the batch's copy)"""

    def __init__(self):
        self._index = None

    @property
    def index(self) -> dict:
        if self._index is None:
            self._index = mi.load()
        return self._index

    @property
    def live(self) -> set[str]:
        return {e['id'] for e in mi.live(self.index)}

    @property
    def groups(self) -> dict:
        return self.index.get('groups', {})


def _fits(kind: str, value, cx: _Context) -> bool:
    if kind == 'motif':
        return value in cx.live
    if kind == 'group':
        return value in cx.groups
    if kind == 'text':
        return isinstance(value, str) and bool(value.strip())
    if kind == 'str':
        return isinstance(value, str)
    if kind == 'words':
        return isinstance(value, (str, list))
    if kind == 'facet':
        return value in mi.FACETS
    raise KeyError(kind)


def _group_new(d: dict, cx: _Context):
    """A new group, with a first motif in it if one is given, or a proposed family's (one undo step)"""
    live = cx.live
    gid = mi.group_add(d['name'])
    for eid in [d.get('id')] + list(d.get('ids') or []):
        if eid in live:
            mi.group_member(eid, gid)


def _not_same(d: dict, cx: _Context):
    if d['a'] == d['b']:
        raise ValueError('not the same: two motifs')
    mi.not_same(d['a'], d['b'])


def _facet_rename(d: dict, cx: _Context):
    if not (isinstance(d.get('to'), str) and d['to'].strip()):
        raise ValueError('facet_rename: the new name')
    mi.facet_rename(d['facet'], d['value'], d['to'])


def _check(d: dict, cx: _Context):
    if d.get('answer') not in ('yes', 'no', 'unsure'):
        raise ValueError('a check is yes, no or unsure')
    mi.check(d.get('claim', ''), d.get('id', ''), d['answer'])


def _new_with(d: dict, cx: _Context):
    """A new motif made from claims dropped on it: each moved or copied from its motif, or filed by hand. With no
    claims at all, a proposed motif kept as a seed, its claims not fitting (Oct 12)"""
    name, claims = d.get('name'), d.get('claims')
    if not (isinstance(name, str) and name.strip() and isinstance(claims, list) and (claims or d.get('proposed'))):
        raise ValueError('new_with: a name and claims')
    live = cx.live
    eid = mi.add(name)
    for c in claims:
        text, source = (c.get('claim') or '').strip(), c.get('source')
        if not text:
            continue
        if source in live and c.get('mode') == 'move':
            mi.move(text, source, eid)
        elif source in live:
            mi.also_file(text, source, eid)
        else:
            mi.file_by_hand({'claim': text, 'source': c.get('src', ''), 'ref': c.get('ref', '')}, eid)
    if (d.get('note') or '').strip():  # a 💡 proposed motif comes with its note and genre
        mi.set_note(eid, d['note'])
    if d.get('genre'):
        mi.set_facet(eid, 'genre', d['genre'])


# name: ({field: kind}, run(data, context)). Fields not named here are optional and read by the verb.
ACTIONS: dict[str, tuple[dict[str, str], Callable[[dict, _Context], object]]] = {
    # claims and their motifs
    'move': ({'claim': 'text', 'source': 'motif', 'target': 'motif'},
             lambda d, cx: mi.move(d['claim'], d['source'], d['target'])),
    'also': ({'claim': 'text', 'source': 'motif', 'target': 'motif'},
             lambda d, cx: mi.also_file(d['claim'], d['source'], d['target'])),
    'move_new': ({'claim': 'text', 'source': 'motif', 'name': 'text'},
                 lambda d, cx: mi.move(d['claim'], d['source'], mi.add(d['name']))),
    'also_new': ({'claim': 'text', 'source': 'motif', 'name': 'text'},
                 lambda d, cx: mi.also_file(d['claim'], d['source'], mi.add(d['name']))),
    'file': ({'claim': 'text', 'id': 'motif'},
             lambda d, cx: mi.file_by_hand({'claim': d['claim'].strip(), 'source': d.get('source', ''),
                                            'ref': d.get('ref', '')}, d['id'])),
    'unfile': ({'claim': 'text', 'id': 'motif'}, lambda d, cx: mi.unfile(d['claim'], d['id'])),
    'reject': ({'claim': 'text', 'id': 'motif'}, lambda d, cx: mi.reject(d['claim'], d['id'])),
    'check': ({}, _check),
    'no_motif': ({'claim': 'text'}, lambda d, cx: mi.no_motif(d['claim'])),
    # filed by mistake, not a verdict: out of every motif with nothing the models read as "not this motif" (Oct 25: a
    # regrouping of the show claims filed duplicates of claims already filed, in new words)
    'withdraw': ({'claim': 'text'}, lambda d, cx: mi.withdraw(d['claim'])),
    'hold': ({'claim': 'text'}, lambda d, cx: mi.hold(d['claim'], True)),  # kept aside to look at later; no verdict
    'unhold': ({'claim': 'text'}, lambda d, cx: mi.hold(d['claim'], False)),
    'correct': ({'claim': 'text', 'text': 'text'}, lambda d, cx: mi.correct_claim(d['claim'], d['text'])),
    'same_claim': ({'variant': 'text', 'canonical': 'text'},  # one claim told two ways: the variant folds in
                   lambda d, cx: mi.same_claim(d['variant'].strip(), d['canonical'].strip())),
    'carrying': ({'claim': 'text', 'id': 'motif', 'text': 'words'},  # the tellers' words that carry it, per filing
                 lambda d, cx: mi.set_carrying(d['claim'], d['id'], d['text'])),
    # motifs
    'add': ({'name': 'text'}, lambda d, cx: mi.add(d['name'])),
    'new_with': ({}, _new_with),
    'rename': ({'id': 'motif', 'name': 'text'}, lambda d, cx: mi.rename(d['id'], d['name'])),
    'merge': ({'source': 'motif', 'target': 'motif'}, lambda d, cx: mi.merge(d['source'], d['target'])),
    'delete': ({'id': 'motif'}, lambda d, cx: mi.delete(d['id'])),
    'note': ({'id': 'motif', 'note': 'str'}, lambda d, cx: mi.set_note(d['id'], d['note'])),
    'keep_note': ({'id': 'motif'}, lambda d, cx: mi.keep_note(d['id'])),
    'not_this': ({'id': 'motif', 'text': 'str'}, lambda d, cx: mi.set_not_this(d['id'], d['text'])),
    'done': ({'id': 'motif'}, lambda d, cx: mi.mark_done(d['id'], bool(d.get('done', True)))),
    'reset_done': ({}, lambda d, cx: mi.reset_done()),
    'stands_alone': ({'id': 'motif'}, lambda d, cx: mi.stands_alone(d['id'], ON(d, 'alone'))),
    'watch': ({'id': 'motif'}, lambda d, cx: mi.set_watch(d['id'], ON(d, 'on'))),  # a sink for plain reports (Straight news)
    # links between motifs
    'parent': ({'id': 'motif', 'parent': 'motif'}, lambda d, cx: mi.set_parent(d['id'], d['parent'], ON(d, 'on'))),
    'relate': ({'a': 'motif', 'b': 'motif'},
               lambda d, cx: mi.relate(d['a'], d['b'], True, d['note'] if isinstance(d.get('note'), str) else None)),
    'unrelate': ({'a': 'motif', 'b': 'motif'},
                 lambda d, cx: mi.relate(d['a'], d['b'], False, d['note'] if isinstance(d.get('note'), str) else None)),
    'not_same': ({'a': 'motif', 'b': 'motif'}, _not_same),
    # groups
    'group_add': ({'name': 'text'}, lambda d, cx: mi.group_add(d['name'])),
    'group_new': ({'name': 'text'}, _group_new),
    'group_rename': ({'group': 'group', 'name': 'text'}, lambda d, cx: mi.group_rename(d['group'], d['name'])),
    'group_note': ({'group': 'group'}, lambda d, cx: mi.group_note(d['group'], d.get('note') or '')),
    'group_delete': ({'group': 'group'}, lambda d, cx: mi.group_delete(d['group'])),
    'group_assign': ({'id': 'motif'}, lambda d, cx: mi.group_assign(d['id'], d.get('group') or None)),
    'group_member': ({'id': 'motif', 'group': 'group'},
                     lambda d, cx: mi.group_member(d['id'], d['group'], ON(d, 'on'))),
    # genres (the one facet)
    'facet': ({'id': 'motif', 'facet': 'str'}, lambda d, cx: mi.set_facet(d['id'], d['facet'], d.get('value') or None)),
    'facet_value': ({'facet': 'str', 'value': 'text'}, lambda d, cx: mi.add_facet_value(d['facet'], d['value'])),
    'facet_rename': ({'facet': 'facet', 'value': 'text'}, _facet_rename),
    'facet_remove': ({'facet': 'facet', 'value': 'text'}, lambda d, cx: mi.facet_remove(d['facet'], d['value'])),
    'facet_note': ({'facet': 'str', 'value': 'str'},
                   lambda d, cx: mi.facet_note(d['facet'], d['value'], d.get('note') or '')),
}
# Carried out by apply() itself, not by one verb
COMPOUND = ('batch', 'telling', 'telling_reject', 'split', 'split_reject', 'proposal_reject')


def names() -> list[str]:
    """Every action apply() takes"""
    return sorted(ACTIONS) + list(COMPOUND)


def _with_made(x, made: list[str]):
    """A batch step with "$1", "$2"… replaced by the motifs the batch's earlier steps made"""
    if isinstance(x, dict):
        return {k: _with_made(v, made) for k, v in x.items()}
    if isinstance(x, list):
        return [_with_made(v, made) for v in x]
    if isinstance(x, str) and x[:1] == '$' and x[1:].isdigit():
        if not 0 < int(x[1:]) <= len(made):
            raise ValueError(f'{x}: no motif made that early in the batch')
        return made[int(x[1:]) - 1]
    return x


def apply(data: dict, on_check: Callable[[dict], None] | None = None):
    """Carry out one action; raises ValueError on an unknown action or a missing or wrong field. `on_check` is called
    with each check once it's made (the checker records the person's answers). A step may add to `data` what the log
    should keep (a telling's new id, the motifs a split claim left)."""
    act = data.get('action')
    if act in ('telling', 'telling_reject'):  # 🧩 a flabby motif's telling made a motif of its own (tellings.py)
        from app.analysis import tellings
        if act == 'telling_reject':
            tellings.reject(data.get('key'))
        else:
            claims = [c for c in data.get('claims') or [] if isinstance(c, str)]
            data['id'] = tellings.make(data.get('parent', ''), data.get('name', ''), claims, data.get('note') or '',
                                       data.get('move', True) is not False, data.get('key'))
        return
    if act in ('split', 'split_reject'):  # the claim organizer's (claim_organizer.py), or a person's own split: its own
        from app.analysis import claim_organizer as co  # action, never read as "not this motif"
        why = data['why'].strip() if isinstance(data.get('why'), str) and data['why'].strip() else None
        if act == 'split_reject':
            co.reject_split(data.get('proposal', ''), why)
        else:  # the children file at the next hourly run (refile_pending), into the claims to judge
            done = co.apply_split(data.get('proposal') or None, data.get('children'), why,
                                  claim=None if data.get('proposal') else data.get('claim'), refile=False)
            data['ids'] = done.get('ids', [])  # the motifs the claim left, for the log
        return
    if data.get('proposal'):  # a proposal approved (its own action, carried out as usual) or rejected
        from app.analysis import motif_proposals as mp
        if act != 'proposal_reject':
            apply({**{k: v for k, v in data.items() if k != 'proposal'}, 'proposed': True}, on_check)
        mp.decide(data['proposal'], 'rejected' if act == 'proposal_reject' else 'approved',
                  data['why'] if isinstance(data.get('why'), str) else None,
                  None if act == 'proposal_reject' else {k: v for k, v in data.items() if k not in ('proposal', 'why')})
        return
    if act == 'batch':
        steps = data.get('steps')
        if not isinstance(steps, list) or not steps or any(not isinstance(x, dict) or x.get('action') == 'batch' for x in steps):
            raise ValueError('a batch is a list of actions')
        made = []  # motifs made by earlier steps: later steps name them "$1", "$2"… (Oct 9, for the MCP)
        with mi.batched():  # the index saved once at the end, not once a step (Oct 19: 29 steps took over a minute)
            for n, step in enumerate(steps):
                steps[n] = step = _with_made(step, made)  # the real ids, so the log has them
                had = set(mi.load()['entries'])
                try:
                    apply(step, on_check)
                except (ValueError, KeyError) as e:
                    e.done = steps[:n]  # the steps that ran stay done: the caller logs them
                    raise
                made += sorted(set(mi.load()['entries']) - had)
        return
    if act not in ACTIONS:
        raise ValueError(f'unknown action: {act!r}')
    fields, run = ACTIONS[act]
    cx = _Context()
    wrong = [f'{k} ({kind})' for k, kind in fields.items() if not _fits(kind, data.get(k), cx)]
    if wrong:
        raise ValueError(f"{act}: missing or wrong {', '.join(wrong)}")
    run(data, cx)
    if act == 'check' and on_check is not None:
        on_check(data)
