"""The motif index, exported: for reading, for a spreadsheet, for another tool, or for linking to other catalogs.

- json: every motif with its name, note, genre, group, parents, related motifs and claims (each claim's source, side,
  date and the other ways it was told)
- csv: one row per claim in a motif (a claim in two motifs is two rows), for a spreadsheet
- md: a readable catalog, by group then name
- ttl: SKOS in Turtle, each motif a skos:Concept at its address on the site (motifs.html#M004), its parents
  skos:broader, related motifs skos:related, groups skos:Collections, claims skos:example: ready for the ~Oct 12
  mapping to prior catalogs (docs/motif-catalogs.md) as skos:closeMatch links

`scope` is 'verified' (what the site shows: motifs a person marked done, with the claims they held then, and only a
person's notes) or 'all' (every live motif, every claim, draft notes marked as drafts)."""
import csv
import io
import json
from datetime import date

from app.analysis import motif_index as mi

FORMATS = {'json': 'application/json', 'csv': 'text/csv', 'md': 'text/markdown', 'ttl': 'text/turtle'}
SCOPES = ('verified', 'all')


def motifs(scope: str = 'verified', index: dict | None = None) -> list[dict]:
    """The motifs in `scope`, plain dicts, ordered by group name then motif name"""
    if scope not in SCOPES:
        raise ValueError(f'scope is one of {SCOPES}')
    index = index or mi.load()
    groups = {gid: g['name'] for gid, g in index.get('groups', {}).items()}
    shown = [e for e in mi.live(index) if scope == 'all' or mi.public(e)]
    ids = {e['id'] for e in shown}
    out = []
    for e in shown:
        claims = mi.public_claims(e) if scope == 'verified' else e['claims']
        if scope == 'verified':
            note, drafted = mi.public_note(e), False
        else:
            note, drafted = e.get('note', ''), e.get('note_by') in mi.DRAFTS
        out.append({
            'id': e['id'], 'name': e['name'], 'note': note, **({'note_is_draft': True} if note and drafted else {}),
            'genre': (e.get('facets') or {}).get('genre'),
            'groups': [groups[g] for g in mi.groups_of(e) if g in groups],
            'parents': [p for p in mi.parents_of(e) if p in ids],
            'related': sorted({x for pair in index.get('related', []) if e['id'] in pair for x in pair
                               if x != e['id'] and x in ids}),
            'verified': mi.is_done(e) or False, 'first_seen': e.get('first_seen', ''), 'last_seen': e.get('last_seen', ''),
            'claims': [{'id': mi.key(c['claim'])[:6], 'claim': mi.corrected(c['claim'], index), 'source': c.get('source', ''),
                        'side': c.get('side', ''), 'date': c.get('date', ''), 'ref': c.get('ref', ''),
                        **({'checked': c['checked']} if scope == 'all' and c.get('checked') else {}),
                        **({'also_told': [v['claim'] for v in c['variants']]} if c.get('variants') else {})}
                       for c in claims]})
    out.sort(key=lambda m: m['name'].lower())
    return out


def as_json(found: list[dict], scope: str) -> str:
    return json.dumps({'title': 'BND Motif Index', 'source': 'https://bignews.day/motifs.html', 'scope': scope,
                       'exported': date.today().isoformat(), 'motifs': found}, indent=1, ensure_ascii=False)


def as_csv(found: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['motif', 'name', 'genre', 'groups', 'parents', 'note', 'claim_id', 'claim', 'source', 'side', 'date',
                'also_told'])
    for m in found:
        for c in m['claims'] or [{}]:  # a motif without claims still gets its row
            w.writerow([m['id'], m['name'], m['genre'] or '', ' | '.join(m['groups']), ' '.join(m['parents']), m['note'],
                        c.get('id', ''), c.get('claim', ''), c.get('source', ''), c.get('side', ''), c.get('date', ''),
                        ' | '.join(c.get('also_told', []))])
    return out.getvalue()


def as_markdown(found: list[dict], scope: str) -> str:
    names = {m['id']: m['name'] for m in found}
    lines = ['# 🧩 BND Motif Index', '',
             f"{len(found)} motifs ({'verified by a person' if scope == 'verified' else 'all, verified or not'}), "
             f"{sum(len(m['claims']) for m in found)} claims; exported {date.today().isoformat()} from bignews.day. "
             "Licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/), with credit to bignews.day; "
             "commercial use needs our permission.", '']
    # By group, a motif in several groups under each, then the ungrouped
    sections = sorted({g for m in found for g in m['groups']}, key=str.lower)
    for section in sections + [None]:
        inside = [m for m in found if (section in m['groups'] if section else not m['groups'])]
        if not inside:
            continue
        lines += [f"## {section or 'Ungrouped'}", '']
        for m in inside:
            lines += entry_md(m, names, scope)
    return '\n'.join(lines)


def entry_md(m: dict, names: dict, scope: str) -> list[str]:
    """One motif in the readable catalog"""
    lines = []
    tags = [f"genre: {m['genre']}"] if m['genre'] else []
    tags += [f"rests on: {', '.join(names[p] for p in m['parents'])}"] if m['parents'] else []
    tags += [f"related: {', '.join(names[r] for r in m['related'])}"] if m['related'] else []
    tags += ['not yet verified'] if scope == 'all' and not m['verified'] else []
    lines += [f"### {m['name']} ({m['id']})", '']
    if m['note']:
        lines += [f"{m['note']}{' *(draft)*' if m.get('note_is_draft') else ''}", '']
    if tags:
        lines += [f"*{' · '.join(tags)}*", '']
    for c in m['claims']:
        where = ', '.join(x for x in (c['side'], c['source'], c['date']) if x)
        lines.append(f"- {c['claim']}" + (f" ({where})" if where else ''))
        lines += [f"  - also told: {v}" for v in c.get('also_told', [])]
    lines.append('')
    return lines


def _lit(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '') + '"@en'


def as_turtle(found: list[dict], scope: str) -> str:
    lines = ['@prefix skos: <http://www.w3.org/2004/02/skos/core#> .',
             '@prefix dct: <http://purl.org/dc/terms/> .',
             '@prefix bnd: <https://bignews.day/motifs.html#> .', '',
             'bnd:index a skos:ConceptScheme ;',
             f'    skos:prefLabel {_lit("BND Motif Index")} ;',
             f'    dct:description {_lit(f"Recurring rumor and narrative shapes in US political talk, built bottom-up on bignews.day ({scope} motifs).")} ;',
             '    dct:license <https://creativecommons.org/licenses/by-nc-sa/4.0/> ;',
             f'    dct:modified "{date.today().isoformat()}"']
    tops = [f"bnd:{m['id']}" for m in found if not m['parents']]
    lines[-1] += (' ;\n    skos:hasTopConcept ' + ', '.join(tops) if tops else '') + ' .'
    lines.append('')
    for m in found:
        props = ['a skos:Concept', 'skos:inScheme bnd:index', f"skos:prefLabel {_lit(m['name'])}",
                 f"skos:notation \"{m['id']}\""]
        if m['note']:
            props.append(f"skos:scopeNote {_lit(m['note'])}")
        if m['genre']:
            props.append(f"dct:type {_lit(m['genre'])}")
        if m['parents']:
            props.append('skos:broader ' + ', '.join(f'bnd:{p}' for p in m['parents']))
        if m['related']:
            props.append('skos:related ' + ', '.join(f'bnd:{r}' for r in m['related']))
        if m['first_seen']:
            props.append(f"dct:created \"{m['first_seen']}\"")
        for c in m['claims']:
            props.append(f"skos:example {_lit(c['claim'])}")
        lines += [f"bnd:{m['id']} " + ' ;\n    '.join(props) + ' .', '']
    groups = {}
    for m in found:
        for g in m['groups']:
            groups.setdefault(g, []).append(m['id'])
    for i, (name, members) in enumerate(sorted(groups.items()), 1):
        lines += [f'bnd:group-{i} a skos:Collection ;', f'    skos:prefLabel {_lit(name)} ;',
                  '    skos:member ' + ', '.join(f'bnd:{x}' for x in members) + ' .', '']
    return '\n'.join(lines)


def export(fmt: str = 'json', scope: str = 'verified') -> tuple[str, str, str]:
    """(text, media type, file name)"""
    if fmt not in FORMATS:
        raise ValueError(f'format is one of {sorted(FORMATS)}')
    found = motifs(scope)
    text = {'json': lambda: as_json(found, scope), 'csv': lambda: as_csv(found),
            'md': lambda: as_markdown(found, scope), 'ttl': lambda: as_turtle(found, scope)}[fmt]()
    return text, FORMATS[fmt], f'bnd-motifs-{scope}-{date.today().isoformat()}.{fmt}'
