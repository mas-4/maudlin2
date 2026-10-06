"""Charts for the story pages, drawn as inline SVG (no script, so hundreds of pages cost nothing to load): who carried
the story and when, with its moments on TV, the radio and online beneath; and how many front pages carried it over
time, by lean. Times in, naive UTC; labels out, Eastern."""
from datetime import datetime, timedelta as td
from html import escape

import pytz

from app.site.graphing import bias_colors, bias_ink

EASTERN = pytz.timezone('US/Eastern')
LABEL_W = 120  # the outlet names' column
ROW_H = 18
WIDTH = 760
MAX_ROWS = 40  # outlets shown; the rest are counted
LEAN_GROUPS = [('left', '#3b4cc0', lambda b: b is not None and b < 0),
               ('center', '#a9a9b8', lambda b: b == 0),
               ('right', '#b40426', lambda b: b is not None and b > 0),
               ('not rated', '#e2e2ea', lambda b: b is None)]
DASHED = 'stroke-dasharray="3 2" '
STEPS = (1, 2, 3, 6, 12, 24, 48)  # hours between ticks


def _local(t: datetime) -> datetime:
    return pytz.UTC.localize(t).astimezone(EASTERN)


def ticks(t0: datetime, t1: datetime, most: int = 7) -> list[tuple[datetime, str]]:
    """Whole Eastern hours between t0 and t1 a few hours apart (at most `most`), labeled '8 AM', or 'Oct 6' at
    midnight and on the first tick"""
    hours = max((t1 - t0).total_seconds() / 3600, 1)
    step = next((s for s in STEPS if hours / s <= most), STEPS[-1])
    local = _local(t0).replace(minute=0, second=0, microsecond=0) + td(hours=1)
    while local.hour % step:
        local += td(hours=1)
    out, first = [], True
    while True:
        t = local.astimezone(pytz.UTC).replace(tzinfo=None)
        if t > t1:
            break
        label = local.strftime('%b %-d') if local.hour == 0 else local.strftime('%-I %p')
        if first and local.hour:
            label = local.strftime('%b %-d, %-I %p')
        out.append((t, label))
        first = False
        local = EASTERN.normalize(local + td(hours=step))
    return out


class Axis:
    def __init__(self, t0: datetime, t1: datetime, x0: float, x1: float):
        self.t0, self.x0, self.x1 = t0, x0, x1
        self.span = max((t1 - t0).total_seconds(), 60)
        self.t1 = t1

    def x(self, t: datetime) -> float:
        f = (min(max(t, self.t0), self.t1) - self.t0).total_seconds() / self.span
        return self.x0 + (self.x1 - self.x0) * f


def _grid(axis: Axis, top: float, bottom: float) -> list[str]:
    parts = []
    for t, label in ticks(axis.t0, axis.t1):
        x = axis.x(t)
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" class="sc-grid"/>'
                     f'<text x="{x:.1f}" y="{bottom + 13}" class="sc-tick" text-anchor="middle">{escape(label)}</text>')
    return parts


def span_of(story: dict, extra: list[datetime] = ()) -> tuple[datetime, datetime]:
    """From its first headline (no more than a day before the story began, and at least an hour before) to its last
    moment anywhere (no more than two days past its last front page)"""
    firsts = [h['first'] for h in story['headlines'] if h['first']]
    t0 = max(min(firsts + [story['first'] - td(hours=1)]), story['first'] - td(days=1))
    t1 = max([story['last']] + [t for t in extra if t and t <= story['last'] + td(days=2)])
    return t0, max(t1, t0 + td(hours=2))


def timeline(story: dict, outlets: list[dict], tv_spots: list[dict], radio: list[dict], retold: datetime | None,
             channel_ink: dict) -> str | None:
    """Who carried it and when: a row per outlet in the order they picked it up, a bar for each of its headlines from
    first to last seen (lean colors), and beneath, a lane each for TV captions, radio newscasts and the day people were
    found retelling it"""
    heads = [h for h in story['headlines'] if h['first']]
    if not heads:
        return None
    radio_at = [r['at'].astimezone(pytz.UTC).replace(tzinfo=None) for r in radio]
    t0, t1 = span_of(story, [s['at'] for s in tv_spots] + radio_at + [retold])
    by = {}
    for h in sorted(heads, key=lambda h: h['first']):
        by.setdefault(h['outlet'], []).append(h)
    order = sorted(by, key=lambda o: by[o][0]['first'])
    shown, more = order[:MAX_ROWS], len(order) - MAX_ROWS
    lanes = [(name, kind) for name, kind in (('📺 TV', 'tv'), ('📻 radio', 'radio'), ('🧶 online', 'online'))
             if {'tv': tv_spots, 'radio': radio_at, 'online': retold}[kind]]
    top = 6
    rows_end = top + ROW_H * len(shown) + (ROW_H if more > 0 else 0)
    lanes_top = rows_end + (8 if lanes else 0)
    bottom = lanes_top + ROW_H * len(lanes)
    axis = Axis(t0, t1, LABEL_W, WIDTH - 10)
    parts = _grid(axis, top - 4, bottom + 2)
    bias = {h['outlet']: h['bias'] for h in outlets}
    short = {h['outlet']: h.get('short') for h in outlets}
    for i, o in enumerate(shown):
        y = top + i * ROW_H
        b = bias.get(o)
        fill = bias_colors[int(b) + 3] if b is not None else '#ffffff'
        ink = bias_ink[int(b) + 3] if b is not None else '#1f1f2e'
        name = short.get(o) or o
        name = name if len(name) <= 20 else name[:19] + '…'
        parts.append(f'<text x="{LABEL_W - 6}" y="{y + 13}" class="sc-label" text-anchor="end">{escape(name)}'
                     f'<title>{escape(o)}</title></text>')
        for n, h in enumerate(by[o]):
            x0 = axis.x(max(h['first'], t0))
            x1 = max(axis.x(h['last'] or h['first']), x0 + 4)
            when = _local(h['first']).strftime('%b %-d, %-I:%M %p')
            parts.append(f'<rect x="{x0:.1f}" y="{y + 3}" width="{x1 - x0:.1f}" height="{ROW_H - 6}" rx="4" '
                         f'fill="{fill}" stroke="#1f1f2e" stroke-width="{1.5 if b is None else 0.8}" '
                         f'{DASHED if b is None else ""}>'
                         f'<title>{escape(o)}, {when} ET: {escape(h["title"])}</title></rect>')
            if n:  # a new headline: reworded, or a follow-up
                parts.append(f'<circle cx="{x0:.1f}" cy="{y + ROW_H / 2}" r="2.6" fill="{ink}" stroke="#1f1f2e" '
                             f'stroke-width="0.6"/>')
    if more > 0:
        parts.append(f'<text x="{LABEL_W - 6}" y="{top + len(shown) * ROW_H + 13}" class="sc-label sc-more" '
                     f'text-anchor="end">and {more} more</text>')
    for j, (name, kind) in enumerate(lanes):
        y = lanes_top + j * ROW_H
        parts.append(f'<text x="{LABEL_W - 6}" y="{y + 13}" class="sc-label" text-anchor="end">{name}</text>'
                     f'<line x1="{LABEL_W}" y1="{y + ROW_H / 2}" x2="{WIDTH - 10}" y2="{y + ROW_H / 2}" class="sc-lane"/>')
        if kind == 'tv':
            for s in tv_spots:
                x = axis.x(s['at'])
                w = max(2.0, (axis.x(s['at'] + td(seconds=s['seconds'])) - x))
                parts.append(f'<rect x="{x:.1f}" y="{y + 3}" width="{w:.1f}" height="{ROW_H - 6}" '
                             f'fill="{channel_ink.get(s["channel"], "#888")}" opacity="0.85">'
                             f'<title>{escape(s["name"])}, {_local(s["at"]).strftime("%-I:%M %p")} ET: '
                             f'{escape(s["text"])}</title></rect>')
        elif kind == 'radio':
            for r, at in zip(radio, radio_at):
                x = axis.x(at)
                parts.append(f'<circle cx="{x:.1f}" cy="{y + ROW_H / 2}" r="{6 if r["place"] == 1 else 4}" '
                             f'fill="#e8463c" stroke="#1f1f2e" stroke-width="0.8"><title>{escape(r["show"])}, '
                             f'{escape(r["when"])} ET: {"the lead" if r["place"] == 1 else "story %d of %d" % (r["place"], r["of"])}'
                             f'</title></circle>')
        else:
            x = axis.x(retold)
            parts.append(f'<text x="{x:.1f}" y="{y + 14}" text-anchor="middle" class="sc-emoji">🧶'
                         f'<title>found retold online (the day\'s report)</title></text>')
    height = bottom + 20
    return (f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" class="story-chart" '
            f'aria-label="Which outlets carried it and when, with TV, radio and online beneath">{"".join(parts)}</svg>')


def by_lean(story: dict, outlets: list[dict], height: int = 120) -> dict | None:
    """Front pages carrying it at each hourly run, stacked by the outlets' lean: an SVG and the peak"""
    times = sorted({s['at'] for s in story['snapshots']})
    if len(times) < 2:
        return None
    bias = {h['outlet']: h['bias'] for h in outlets}
    spans = {}
    for h in story['headlines']:
        if h['first']:
            spans.setdefault(h['outlet'], []).append((h['first'], h['last'] or h['first']))
    counts = []
    for t in times:
        on = [o for o, ss in spans.items() if any(a - td(minutes=30) <= t <= b + td(minutes=30) for a, b in ss)]
        counts.append([sum(test(bias.get(o)) for o in on) for _, _, test in LEAN_GROUPS])
    peak = max(sum(c) for c in counts) or 1
    t0, t1 = times[0], times[-1]
    axis = Axis(t0, t1, 30, WIDTH - 10)
    top, bottom = 8, height - 20

    def y(v):
        return bottom - (bottom - top) * v / peak
    parts = _grid(axis, top, bottom)
    for v in sorted({peak, round(peak / 2)} - {0}):
        parts.append(f'<line x1="30" y1="{y(v):.1f}" x2="{WIDTH - 10}" y2="{y(v):.1f}" class="sc-grid"/>'
                     f'<text x="24" y="{y(v) + 4:.1f}" class="sc-tick" text-anchor="end">{v}</text>')
    below = [0] * len(times)
    for g, (name, color, _) in enumerate(LEAN_GROUPS):
        above = [b + c[g] for b, c in zip(below, counts)]
        if any(c[g] for c in counts):
            pts = [f'{axis.x(t):.1f},{y(v):.1f}' for t, v in zip(times, above)]
            back = [f'{axis.x(t):.1f},{y(v):.1f}' for t, v in reversed(list(zip(times, below)))]
            parts.append(f'<polygon points="{" ".join(pts + back)}" fill="{color}" stroke="#1f1f2e" '
                         f'stroke-width="0.6"><title>{name}</title></polygon>')
        below = above
    parts.append(f'<line x1="30" y1="{bottom}" x2="{WIDTH - 10}" y2="{bottom}" stroke="#1f1f2e" stroke-width="1"/>')
    svg = (f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" class="story-chart" '
           f'aria-label="Front pages carrying it over time by lean, peak {peak}">{"".join(parts)}</svg>')
    legend = [{'name': name, 'color': color} for g, (name, color, _) in enumerate(LEAN_GROUPS)
              if any(c[g] for c in counts)]
    return {'svg': svg, 'peak': peak, 'from': _local(t0).strftime('%b %-d, %-I %p'),
            'to': _local(t1).strftime('%b %-d, %-I %p'), 'legend': legend}


PART_COLORS = ['#ff4fa3', '#00c2a8', '#ffc400', '#3a86ff', '#ff6b1a', '#8a5cff']  # the front page's pops, in turn


def saga_lanes(parts: list[dict], tv_spots: list[dict], radio: list[dict], retold: list, channel_ink: dict) -> str | None:
    """A saga's parts in the order they broke: a row each, a bar from first to last seen on the front pages, in the
    part's color, and beneath, its TV captions, radio newscasts and retellings, each in the color of its part.
    `parts`: [{'story', 'label', 'first', 'last', 'outlets'}]; spots and newscasts carry 'story'; retold: [(when, story)]"""
    if not parts:
        return None
    color = {p['story']: PART_COLORS[i % len(PART_COLORS)] for i, p in enumerate(parts)}
    radio_at = [(r['at'].astimezone(pytz.UTC).replace(tzinfo=None), r) for r in radio]
    t0 = min(p['first'] for p in parts) - td(hours=1)
    t1 = max([p['last'] for p in parts] + [s['at'] for s in tv_spots] + [a for a, _ in radio_at] + [w for w, _ in retold if w])
    t1 = max(t1, t0 + td(hours=3))
    lanes = [(n, k) for n, k in (('📺 TV', 'tv'), ('📻 radio', 'radio'), ('🧶 online', 'online'))
             if {'tv': tv_spots, 'radio': radio_at, 'online': retold}[k]]
    top, label_w = 6, 210
    rows_end = top + ROW_H * len(parts)
    lanes_top = rows_end + (8 if lanes else 0)
    bottom = lanes_top + ROW_H * len(lanes)
    axis = Axis(t0, t1, label_w, WIDTH - 10)
    out = _grid(axis, top - 4, bottom + 2)
    for i, p in enumerate(parts):
        y = top + i * ROW_H
        name = p['label'] if len(p['label']) <= 34 else p['label'][:33] + '…'
        x0, x1 = axis.x(p['first']), axis.x(p['last'])
        out.append(f'<text x="{label_w - 6}" y="{y + 13}" class="sc-label" text-anchor="end">{i + 1}. {escape(name)}'
                   f'<title>{escape(p["label"])}</title></text>'
                   f'<rect x="{x0:.1f}" y="{y + 3}" width="{max(4.0, x1 - x0):.1f}" height="{ROW_H - 6}" rx="4" '
                   f'fill="{color[p["story"]]}" stroke="#1f1f2e" stroke-width="0.8"><title>{escape(p["label"])}: '
                   f'{_local(p["first"]).strftime("%b %-d, %-I %p")} to {_local(p["last"]).strftime("%b %-d, %-I %p")} ET'
                   f'{", " + str(p["outlets"]) + " outlets" if p.get("outlets") else ""}</title></rect>')
    for j, (name, kind) in enumerate(lanes):
        y = lanes_top + j * ROW_H
        out.append(f'<text x="{label_w - 6}" y="{y + 13}" class="sc-label" text-anchor="end">{name}</text>'
                   f'<line x1="{label_w}" y1="{y + ROW_H / 2}" x2="{WIDTH - 10}" y2="{y + ROW_H / 2}" class="sc-lane"/>')
        if kind == 'tv':
            for s in tv_spots:
                x = axis.x(s['at'])
                w = max(2.0, axis.x(s['at'] + td(seconds=s['seconds'])) - x)
                out.append(f'<rect x="{x:.1f}" y="{y + 3}" width="{w:.1f}" height="{ROW_H - 6}" '
                           f'fill="{color.get(s["story"], channel_ink.get(s["channel"], "#888"))}" stroke="#1f1f2e" stroke-width="0.4">'
                           f'<title>{escape(s["name"])}, {_local(s["at"]).strftime("%b %-d, %-I:%M %p")} ET: {escape(s["text"])}</title></rect>')
        elif kind == 'radio':
            for at, r in radio_at:
                out.append(f'<circle cx="{axis.x(at):.1f}" cy="{y + ROW_H / 2}" r="{6 if r["place"] == 1 else 4}" '
                           f'fill="{color.get(r["story"], "#e8463c")}" stroke="#1f1f2e" stroke-width="0.8"><title>'
                           f'{escape(r["show"])}, {escape(r["when"])} ET</title></circle>')
        else:
            for when, story in retold:
                if when:
                    out.append(f'<text x="{axis.x(when):.1f}" y="{y + 14}" text-anchor="middle" class="sc-emoji">🧶'
                               f'<title>retold online (the day\'s report)</title></text>')
    height = bottom + 20
    return (f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" class="story-chart" '
            f'aria-label="The saga\'s parts over time, with TV, radio and online beneath">{"".join(out)}</svg>')


def saga_coverage(parts: list[dict], height: int = 140) -> dict | None:
    """Front pages carrying each part at each hourly run, stacked by part in its color: an SVG and the peak.
    `parts` carry 'snapshots': [{'at', 'outlets'}]"""
    times = sorted({s['at'] for p in parts for s in p.get('snapshots', [])})
    if len(times) < 2:
        return None
    counts = []
    for p in parts:
        snap = {s['at']: s['outlets'] for s in p.get('snapshots', [])}
        counts.append([snap.get(t, 0) for t in times])
    totals = [sum(c[i] for c in counts) for i in range(len(times))]
    peak = max(totals) or 1
    axis = Axis(times[0], times[-1], 30, WIDTH - 10)
    top, bottom = 8, height - 20

    def y(v):
        return bottom - (bottom - top) * v / peak
    out = _grid(axis, top, bottom)
    for v in sorted({peak, round(peak / 2)} - {0}):
        out.append(f'<line x1="30" y1="{y(v):.1f}" x2="{WIDTH - 10}" y2="{y(v):.1f}" class="sc-grid"/>'
                   f'<text x="24" y="{y(v) + 4:.1f}" class="sc-tick" text-anchor="end">{v}</text>')
    below = [0] * len(times)
    for i, (p, c) in enumerate(zip(parts, counts)):
        above = [b + n for b, n in zip(below, c)]
        if any(c):
            pts = [f'{axis.x(t):.1f},{y(v):.1f}' for t, v in zip(times, above)]
            back = [f'{axis.x(t):.1f},{y(v):.1f}' for t, v in reversed(list(zip(times, below)))]
            out.append(f'<polygon points="{" ".join(pts + back)}" fill="{PART_COLORS[i % len(PART_COLORS)]}" '
                       f'stroke="#1f1f2e" stroke-width="0.6"><title>{escape(p["label"])}</title></polygon>')
        below = above
    out.append(f'<line x1="30" y1="{bottom}" x2="{WIDTH - 10}" y2="{bottom}" stroke="#1f1f2e" stroke-width="1"/>')
    return {'svg': f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" role="img" class="story-chart" '
                   f'aria-label="Front pages carrying each part over time, peak {peak}">{"".join(out)}</svg>',
            'peak': peak, 'from': _local(times[0]).strftime('%b %-d, %-I %p'), 'to': _local(times[-1]).strftime('%b %-d, %-I %p')}
