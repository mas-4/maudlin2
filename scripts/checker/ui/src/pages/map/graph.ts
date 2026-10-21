// The map itself: the motifs as dots in a D3 force layout, drawn straight into the page's <svg> (React draws the bar,
// the list, the cards and the desk around it). Ported from the old map (scripts/checker/templates/map.html). The page
// hands it the index and its settings with update(); it redraws only when the dots or lines change, and otherwise just
// marks what's picked, found or faded. Positions are kept for each way of laying out (by structure, by claims), so a
// redraw or a mode switch puts every dot back where it was.
import * as d3 from 'd3'
import { genreColor, groupColor as colorAt, type Model } from '../../workbench/model'
import type { Entry } from '../../workbench/types'
import { CROSSING, crossing, drawBlobs, groupForce } from './layout'

/** 🧲 claims (app/analysis/claim_map.py): the motifs by their claims alone, and the clusters found there */
export interface ClaimMap {
  nodes: Record<string, number> // motif -> its cluster
  clusters: { id: number; size: number; label: string; names: string[] }[]
  links: { source: string; target: string; kind: 'shared' | 'alike'; n?: number; w?: number }[]
}

export interface MapOpts {
  showKind: boolean // the rests-on lines
  related: 'focus' | 'all' | 'none' // related lines: the picked one's, all, none
  sharedMin: number // grey lines between motifs sharing at least this many claims (0: none)
  onlyLinked: boolean
  claimMode: boolean
  bubble: boolean
  tree: boolean
  hiddenGroups: Set<string>
  pickedGenre: string | null
  pickedCluster: number | null
  term: string // the search, lower case
  msel: string[] // the motifs selected
  desk: boolean // the desk is open on the right
}

export interface Hooks {
  onFocus: (id: string | null) => void
  onCount: (text: string) => void
  onToggle: (id: string) => void // Ctrl/⌘/Shift-click on a dot
  onBox: (ids: string[]) => void // Shift-drag a box
  onClearSel: () => void
}

type Kind = 'kind' | 'related' | 'shared' | 'alike'
interface Node extends d3.SimulationNodeDatum { id: string; e: Entry; deg: number }
interface Link extends d3.SimulationLinkDatum<Node> { kind: Kind; n?: number; w?: number }
interface Group { id: string; name: string }
type XY = { x: number; y: number }

const R = (n: Node) => 5 + 3 * Math.sqrt(n.e.claims.length) // a dot's size: its claims
const sid = (x: string | number | Node) => (typeof x === 'object' ? x.id : String(x))
/** A cluster's colour: golden-angle hues, so 27 clusters get 27 colours */
export const clusterColor = (k: number) => d3.hsl((k * 137.508) % 360, 0.62, k % 2 ? 0.62 : 0.5).formatHex()
const genreOf = (e: Entry) => e.facets?.genre ?? ''

export class MapGraph {
  private svg: d3.Selection<SVGSVGElement, unknown, null, undefined>
  private root: d3.Selection<SVGGElement, unknown, null, undefined> | null = null
  private zoomer = d3.zoom<SVGSVGElement, unknown>()
  private sim: d3.Simulation<Node, Link> | null = null
  private nodes: Node[] = []
  private links: Link[] = []
  private keptStructure = new Map<string, XY>()
  private keptClaims = new Map<string, XY>()
  private gathered = new Map<string, XY>() // id -> where it was before it was gathered round the picked one
  private openGroups = new Set<string>() // 🫧 the groups opened
  private focus: string | null = null
  private hover: string | null = null
  private near: Set<string> | null = null
  private m: Model | null = null
  private cm: ClaimMap | null = null
  private o: MapOpts | null = null
  private key = ''
  private lt = 0
  private timers = new Set<number>()
  private boxed = false

  constructor(private el: SVGSVGElement, private box: HTMLElement, private hooks: Hooks) {
    this.svg = d3.select(el)
    // scroll zooms; dragging the background pans (not a dot: that's the drag engine's, nor with Shift: a box)
    this.zoomer.scaleExtent([0.15, 5])
      .filter((ev: Event & { ctrlKey?: boolean; shiftKey?: boolean; button?: number }) =>
        ev.type === 'wheel' || (!(ev.target as Element).closest('.mm-node') && !ev.ctrlKey && !ev.shiftKey && !ev.button))
      .on('zoom', (ev: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        this.root?.attr('transform', ev.transform.toString())
        clearTimeout(this.lt)
        this.lt = window.setTimeout(() => this.placeLabels(), 120)
      })
    this.svg.call(this.zoomer)
    // a click on the background lets the picked one go, and the selection (unless Shift is held)
    this.svg.on('click', (ev: MouseEvent) => {
      if (this.boxed) { this.boxed = false; return }
      if ((ev.target as Element).closest('.mm-node, .mm-bubble')) return
      this.pick(null)
      if (!ev.shiftKey) this.hooks.onClearSel()
    })
    // Shift-drag across the background: a box, and every dot in it selected (added to what's selected)
    let sel: { x: number; y: number; to?: [number, number]; el: d3.Selection<SVGRectElement, unknown, null, undefined> } | null = null
    this.svg.on('pointerdown.box', (ev: PointerEvent) => {
      if (!ev.shiftKey || ev.button || (ev.target as Element).closest('.mm-node') || !this.root) return
      const [x, y] = d3.pointer(ev, this.root.node())
      sel = { x, y, el: this.root.append('rect').attr('class', 'mm-box').attr('x', x).attr('y', y) }
      try { el.setPointerCapture(ev.pointerId) } catch { /* an ended pointer */ }
    }).on('pointermove.box', (ev: PointerEvent) => {
      if (!sel || !this.root) return
      const [x, y] = d3.pointer(ev, this.root.node())
      sel.el.attr('x', Math.min(x, sel.x)).attr('y', Math.min(y, sel.y)).attr('width', Math.abs(x - sel.x)).attr('height', Math.abs(y - sel.y))
      sel.to = [x, y]
    }).on('pointerup.box', () => {
      if (!sel) return
      if (sel.to) {
        const [x0, x1] = [sel.x, sel.to[0]].sort((a, b) => a - b), [y0, y1] = [sel.y, sel.to[1]].sort((a, b) => a - b)
        this.hooks.onBox(this.nodes.filter((n) => n.x! >= x0 && n.x! <= x1 && n.y! >= y0 && n.y! <= y1 && this.visible(n)).map((n) => n.id))
        this.boxed = true
      }
      sel.el.remove()
      sel = null
    })
  }

  destroy() {
    this.sim?.stop()
    this.timers.forEach(clearTimeout)
    clearTimeout(this.lt)
    this.svg.on('.zoom', null).on('click', null).on('.box', null)
    this.svg.selectAll('*').remove()
  }

  private later(fn: () => void, ms: number) {
    const t = window.setTimeout(() => { this.timers.delete(t); fn() }, ms)
    this.timers.add(t)
  }

  private get kept() { return this.o?.claimMode ? this.keptClaims : this.keptStructure }
  private size() { return { W: this.box.clientWidth, H: this.box.clientHeight } }
  /** How much of the map's right side the details box and the desk cover (wide windows only) */
  private cover() {
    const { W } = this.size()
    if (W <= 1000) return 0
    return (this.focus ? 380 : 0) + (this.o?.desk ? 372 : 0)
  }
  private visible(n: Node) {
    const g = this.svg.select<SVGGElement>(`.mm-node[data-id="${n.id}"]`).node()
    return !!g && getComputedStyle(g).display !== 'none'
  }
  private shownGroups = (n: Node) => (n.e.groups ?? []).filter((g) => !this.o!.hiddenGroups.has(g))
  private groupColor(gid: string) { return colorAt(this.m!.data.groups.findIndex((g) => g.id === gid)) }

  /** The index and the settings, after any change: a redraw if the dots or lines change, otherwise just the marks */
  update(m: Model, cm: ClaimMap | null, o: MapOpts) {
    if (o.claimMode && !cm) return // 🧲 waits for its map
    const prev = this.o
    const key = JSON.stringify([o.showKind, o.related === 'none', o.sharedMin, o.onlyLinked, o.claimMode, o.bubble, [...o.hiddenGroups].sort()])
    const fresh = m !== this.m || (o.claimMode && cm !== this.cm)
    this.m = m
    this.cm = cm
    this.o = o
    if (prev?.bubble && !o.bubble) this.openGroups.clear()
    if (!prev || fresh || key !== this.key) {
      this.key = key
      this.draw()
      if (o.claimMode && !prev?.claimMode && !this.keptClaims.size) this.later(() => this.fit(), 4000) // and again once it settles
      return
    }
    if (prev.tree !== o.tree) {
      if (this.focus) this.scatter()
      if (o.tree) this.layTree()
      else this.leaveTree()
    }
    this.marks()
  }

  /** The window changed size: laid out again for it */
  resized() { if (this.m && this.o) this.draw() }

  private buildLinks(): Link[] {
    const m = this.m!, o = this.o!, out: Link[] = []
    const es = m.data.entries
    if (o.showKind) es.forEach((e) => e.parents.forEach((p) => { if (m.by[p]) out.push({ source: e.id, target: p, kind: 'kind' }) }))
    if (o.related !== 'none') { // drawn per the setting (CSS); they still shape the layout
      const seen = new Set<string>()
      es.forEach((e) => e.related.forEach((r) => {
        const k = [e.id, r].sort().join()
        if (m.by[r] && !seen.has(k)) { seen.add(k); out.push({ source: e.id, target: r, kind: 'related' }) }
      }))
    }
    if (o.sharedMin) { // every pair of motifs holding the same claims, not already linked
      const count = new Map<string, number>()
      m.inClaim.forEach((holders) => {
        const ids = [...new Set(holders.map((e) => e.id))].sort()
        for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
          const k = ids[i] + ',' + ids[j]
          count.set(k, (count.get(k) ?? 0) + 1)
        }
      })
      const linked = new Set(out.map((l) => [sid(l.source!), sid(l.target!)].sort().join()))
      count.forEach((n, k) => {
        if (linked.has(k) || n < o.sharedMin) return
        const [a, b] = k.split(',')
        out.push({ source: a, target: b, kind: 'shared', n })
      })
    }
    return out
  }

  private draw() {
    const m = this.m!, o = this.o!, cm = o.claimMode ? this.cm : null
    this.sim?.stop()
    this.gathered.clear()
    const kept = this.kept
    const raw: Link[] = cm ? cm.links.filter((l) => m.by[l.source] && m.by[l.target]).map((l) => ({ ...l })) : this.buildLinks()
    const deg = new Map<string, number>()
    raw.forEach((l) => [sid(l.source!), sid(l.target!)].forEach((x) => deg.set(x, (deg.get(x) ?? 0) + 1)))
    const only = o.onlyLinked
    this.nodes = m.data.entries.filter((e) => cm
      ? e.id in cm.nodes && (!only || deg.get(e.id) || e.id === this.focus)
      : !only || deg.get(e.id) || e.id === this.focus || (e.groups ?? []).some((g) => !o.hiddenGroups.has(g)))
      .map((e) => Object.assign({ id: e.id, e, deg: deg.get(e.id) ?? 0 }, kept.get(e.id) ?? {}))
    const ids = new Set(this.nodes.map((n) => n.id))
    this.links = raw.filter((l) => ids.has(sid(l.source!)) && ids.has(sid(l.target!)))
    const nKind = (k: Kind) => this.links.filter((l) => l.kind === k).length
    this.hooks.onCount(cm
      ? `${this.nodes.length} motifs by their claims · ${cm.clusters.length} clusters · ${nKind('shared')} told together · ${nKind('alike')} alike`
      : `${this.nodes.length} motifs · ${nKind('kind')} rests on · ${nKind('related')} related · ${nKind('shared')} sharing claims`)
    const apart = (l: Link) => !!cm && cm.nodes[sid(l.source!)] !== cm.nodes[sid(l.target!)] // between two clusters
    const { W, H } = this.size()
    this.svg.selectAll('*').remove()
    this.svg.append('defs').append('marker').attr('id', 'mm-arrow').attr('viewBox', '0 -5 10 10').attr('refX', 10)
      .attr('markerWidth', 7).attr('markerHeight', 7).attr('orient', 'auto')
      .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#0a8f7e')
    const root = this.svg.append('g')
    this.root = root
    root.attr('transform', d3.zoomTransform(this.el).toString()) // a redraw keeps the view where it was
    // Groups: a soft area around each group's motifs, with its name (drawn first, under everything)
    const shown: Group[] = cm ? [] : m.data.groups.filter((g) => !o.hiddenGroups.has(g.id))
    const members = (g: Group) => this.nodes.filter((n) => (n.e.groups ?? []).includes(g.id))
    const hulls = root.append('g').selectAll<SVGGElement, Group>('g').data(shown, (g) => g.id).join('g')
    hulls.append('g').attr('class', 'mm-blob').attr('fill', (g) => this.groupColor(g.id)).attr('stroke', (g) => this.groupColor(g.id))
    hulls.append('text').attr('class', 'mm-glabel').attr('fill', (g) => this.groupColor(g.id)).attr('text-anchor', 'middle').text((g) => '📁 ' + g.name)
    const drawHulls = () => drawBlobs(hulls, members, (n: Node) => R(n) + 14)
    // 🫧 a closed group drawn as one bubble at the centre of its motifs (they keep their places, hidden); drop a motif on
    // it to put it in the group, click it to open it
    const bubbles = root.append('g').selectAll<SVGGElement, Group>('g').data(o.bubble ? shown : [], (g) => g.id).join('g')
      .attr('class', (g) => 'mm-bubble' + (this.openGroups.has(g.id) ? ' open' : '')).attr('data-drop', 'group').attr('data-g', (g) => g.id)
    bubbles.append('circle').attr('r', (g) => 18 + 9 * Math.sqrt(members(g).length)).attr('fill', (g) => this.groupColor(g.id))
      .attr('fill-opacity', 0.28).attr('stroke', (g) => this.groupColor(g.id))
    bubbles.append('text').attr('text-anchor', 'middle').attr('dy', 4).text((g) => `📁 ${g.name} · ${members(g).length}`)
    bubbles.append('title').text((g) => this.openGroups.has(g.id) ? `${g.name}: click to close` : `${g.name}: click to open (${members(g).map((n) => n.e.name).join(', ')})`)
    bubbles.on('click', (ev: MouseEvent, g) => {
      ev.stopPropagation()
      const opening = !this.openGroups.has(g.id)
      if (opening) this.openGroups.add(g.id)
      else this.openGroups.delete(g.id)
      this.draw()
      if (opening) this.later(() => this.fitTo(new Set(members(g).map((n) => n.id))), 60) // to the group just opened
    })
    const placeBubbles = () => bubbles.attr('transform', (g) => {
      const ms = members(g)
      if (!ms.length) return 'translate(-9999,-9999)'
      return `translate(${d3.mean(ms, (n) => n.x!)},${d3.mean(ms, (n) => n.y!)})`
    })
    const link = root.append('g').selectAll<SVGLineElement, Link>('line').data(this.links).join('line')
      .attr('class', (l) => `mm-link k-${l.kind}` + (apart(l) ? ' apart' : ''))
      .attr('stroke-width', (l) => (l.kind === 'shared' ? Math.min(1 + (l.n ?? 1), 6) : null))
      .attr('marker-end', (l) => (l.kind === 'kind' ? 'url(#mm-arrow)' : null))
    link.append('title').text((l) => l.kind === 'alike' ? `their claims read alike (${l.w})` : l.kind === 'shared' ? `${l.n} claim${l.n === 1 ? '' : 's'} in both`
      : l.kind === 'kind' ? 'rests on' : 'related')
    // a dot: dragged by the one drag engine (data-drag), and a drop target for motifs and claims (data-drop)
    const node = root.append('g').selectAll<SVGGElement, Node>('g').data(this.nodes, (n) => n.id).join('g')
      .attr('class', 'mm-node').attr('data-drag', 'motif').attr('data-drop', 'motif').attr('data-id', (n) => n.id)
    // fill: its genre (white for none); outline: its place in the rests-on links (thick: others rest on it; dashed: it
    // rests on another; both: in the middle of a chain)
    const genres = m.data.facets.genre ?? []
    node.classed('broad', (n) => (m.kids[n.id] ?? []).length > 0).classed('sub', (n) => n.e.parents.length > 0)
    node.append('circle').attr('r', R).attr('fill', (n) => cm ? clusterColor(cm.nodes[n.id]) : genreOf(n.e) ? genreColor(genres, genreOf(n.e)) : '#fff')
    node.append('text').attr('x', (n) => R(n) + 3).attr('y', 4).text((n) => n.e.name) // which show: placeLabels()
    node.append('title').text((n) => `${n.e.name} (${n.e.claims.length} claim${n.e.claims.length === 1 ? '' : 's'})${n.e.note ? '\n' + n.e.note : ''}`)
    node.on('click', (ev: MouseEvent, n) => {
      ev.stopPropagation()
      if (ev.ctrlKey || ev.metaKey || ev.shiftKey) return this.hooks.onToggle(n.id)
      this.pick(n.id, true)
    })
    // pointing at a dot: its related lines and its neighbours' names, without picking it
    node.on('mouseenter', (_ev, n) => { this.hover = n.id; this.markNear() }).on('mouseleave', () => { this.hover = null; this.markNear() })

    const crosses = crossing(this.shownGroups)
    const sim = d3.forceSimulation<Node, Link>(this.nodes)
      .force('link', d3.forceLink<Node, Link>(this.links).id((n) => n.id)
        .distance((l) => l.kind === 'kind' ? 55 : l.kind === 'related' ? 90 : l.kind === 'alike' ? 60 + 220 * (1 - (l.w ?? 0)) : cm ? 70 : 120)
        .strength((l) => cm && apart(l) ? 0.05 : l.kind === 'alike' ? 0.5 * (l.w ?? 0) : l.kind === 'shared' ? (cm ? Math.min(0.2 + 0.15 * (l.n ?? 1), 0.8) : 0.15)
          : 0.6 * (crosses(l as { source: Node; target: Node }) ? CROSSING : 1)))
      .force('charge', d3.forceManyBody().strength(-160)).force('center', d3.forceCenter(W / 2, H / 2))
      .force('collide', d3.forceCollide<Node>().radius((n) => R(n) + 4)).force('x', d3.forceX(W / 2).strength(0.03)).force('y', d3.forceY(H / 2).strength(0.04))
      // groups apart: each drawn to a home of its own, non-members kept off its members; in 🧲 the clusters, as groups
      .force('group', cm
        ? groupForce(this.nodes, cm.clusters.filter((c) => c.size > 1).map((c) => c.id), (n) => [cm.nodes[n.id]], R, W, H)
        : groupForce(this.nodes, shown.map((g) => g.id), this.shownGroups, R, W, H))
      .on('tick', () => {
        drawHulls()
        placeBubbles()
        link.each(function (l) { // arrows end at the circle's edge
          const s = l.source as Node, t = l.target as Node
          const dx = t.x! - s.x!, dy = t.y! - s.y!, d = Math.hypot(dx, dy) || 1, cut = l.kind === 'kind' ? R(t) + 2 : 0
          d3.select(this).attr('x1', s.x!).attr('y1', s.y!).attr('x2', t.x! - dx / d * cut).attr('y2', t.y! - dy / d * cut)
        })
        node.attr('transform', (n) => `translate(${n.x},${n.y})`)
        // a gathered one goes back where it was; so does the tree
        if (!this.o!.tree) this.nodes.forEach((n) => { if (!this.gathered.has(n.id)) kept.set(n.id, { x: n.x!, y: n.y! }) })
      })
    this.sim = sim
    if (kept.size) sim.alpha(0.3)
    else sim.on('end.fit', () => { sim.on('end.fit', null); this.fit() })
    sim.on('end.labels', () => this.placeLabels())
    if (o.bubble) { // a motif shows when one of its groups is open, or it's in none; links only between shown ones
      const hidden = (n: Node) => this.shownGroups(n).length > 0 && !this.shownGroups(n).some((g) => this.openGroups.has(g))
      node.classed('in-bubble', hidden)
      // an open group's motifs named and the rest dimmed, so its members stand out among the ungrouped ones
      const mate = (n: Node) => this.shownGroups(n).some((g) => this.openGroups.has(g))
      node.classed('bubble-mate', mate).classed('bubble-dim', (n) => this.openGroups.size > 0 && !mate(n))
      link.classed('in-bubble', (l) => hidden(l.source as Node) || hidden(l.target as Node))
      hulls.style('display', (g) => (this.openGroups.has(g.id) ? null : 'none'))
    }
    if (o.tree) this.layTree()
    // the picked one, after a change: still picked, its neighbourhood gathered again (the view stays where it is)
    if (this.focus && !m.by[this.focus]) this.pick(null)
    else if (this.focus && !o.tree) this.gather(this.focus)
    this.marks()
  }

  private marks() {
    const o = this.o!, cm = this.cm
    this.el.classList.toggle('related-focus', o.related === 'focus')
    this.el.classList.toggle('claim-mode', o.claimMode)
    this.el.classList.toggle('tree-mode', o.tree)
    const sel = new Set(o.msel)
    this.svg.selectAll<SVGGElement, Node>('.mm-node')
      .classed('gdim', (n) => o.pickedGenre !== null && genreOf(n.e) !== o.pickedGenre)
      .classed('cdim', (n) => o.claimMode && !!cm && o.pickedCluster !== null && cm.nodes[n.id] !== o.pickedCluster)
      .classed('msel', (n) => sel.has(n.id))
    this.applyFocus()
  }

  // ---------- 🌳 the tree ----------
  // The rests-on links laid out top down. Rows by depth (a motif one row below the deepest motif it rests on), each row
  // ordered by where its neighbours are (barycentres, down and up a few times) so lines cross less; each family (a
  // connected set) side by side, packed on shelves. The same dots, pinned there; toggled off they go back where they were
  private layTree() {
    const by = this.m!.by
    const on = new Set(this.nodes.map((n) => n.id))
    const ups = (id: string) => (by[id]?.parents ?? []).filter((p) => on.has(p))
    const downs = new Map<string, string[]>()
    this.nodes.forEach((n) => ups(n.id).forEach((p) => { if (!downs.has(p)) downs.set(p, []); downs.get(p)!.push(n.id) }))
    const inTree = new Set(this.nodes.filter((n) => ups(n.id).length || downs.has(n.id)).map((n) => n.id))
    const depth = new Map<string, number>()
    const deep = (id: string, seen = new Set<string>()): number => { // the longest way up to a motif resting on nothing
      if (depth.has(id)) return depth.get(id)!
      if (seen.has(id)) return 0
      seen.add(id)
      const d = Math.max(-1, ...ups(id).map((p) => deep(p, seen))) + 1
      depth.set(id, d)
      return d
    }
    inTree.forEach((id) => deep(id))
    // families: the connected sets, biggest first
    const family = new Map<string, number>()
    let fam = 0
    inTree.forEach((id) => {
      if (family.has(id)) return
      const todo = [id]
      while (todo.length) {
        const x = todo.pop()!
        if (family.has(x)) continue
        family.set(x, fam)
        todo.push(...ups(x), ...(downs.get(x) ?? []))
      }
      fam++
    })
    const fams = [...Array(fam).keys()].map((f) => [...inTree].filter((id) => family.get(id) === f)).sort((a, b) => b.length - a.length)
    const DX = 175, DY = 120, SHELF = 2600 // families packed on shelves this wide, biggest first, like words in lines
    let x0 = 0, y0 = 0, shelfH = 0
    const pos = new Map<string, XY>()
    fams.forEach((members) => {
      const rows: string[][] = []
      members.forEach((id) => { const d = depth.get(id)!; (rows[d] ??= []).push(id) })
      rows.forEach((row) => row.sort((a, b) => by[a].name.localeCompare(by[b].name)))
      const at = new Map<string, number>()
      rows.forEach((row) => row.forEach((id, i) => at.set(id, i)))
      const mean = (ids: string[]) => (ids.length ? ids.reduce((t, i) => t + at.get(i)!, 0) / ids.length : null)
      for (let pass = 0; pass < 6; pass++) { // down by what each rests on, up by what rests on each
        const order = pass % 2 ? [...rows.keys()].reverse() : [...rows.keys()]
        order.forEach((d) => {
          const row = rows[d]
          if (!row) return
          const key = new Map(row.map((id) => [id, mean(pass % 2 ? (downs.get(id) ?? []).filter((x) => family.get(x) === family.get(id)) : ups(id)) ?? at.get(id)!]))
          row.sort((a, b) => key.get(a)! - key.get(b)!)
          row.forEach((id, i) => at.set(id, i))
        })
      }
      const width = Math.max(...rows.filter(Boolean).map((r) => r.length))
      if (x0 && x0 + width * DX > SHELF) { x0 = 0; y0 += shelfH + DY; shelfH = 0 } // a new shelf
      rows.forEach((row, d) => row?.forEach((id, i) => pos.set(id, { x: x0 + (i + (width - row.length) / 2) * DX, y: y0 + d * DY })))
      x0 += (width + 1) * DX
      shelfH = Math.max(shelfH, (rows.length - 1) * DY)
    })
    this.nodes.forEach((n) => {
      const p = pos.get(n.id)
      n.fx = p ? p.x : null
      n.fy = p ? p.y : null
    })
    this.svg.selectAll<SVGGElement, Node>('.mm-node').classed('tree-off', (n) => !pos.has(n.id))
    this.svg.selectAll<SVGLineElement, Link>('.mm-link').classed('tree-off', (l) => !(pos.has(sid(l.source!)) && pos.has(sid(l.target!))))
    this.sim?.alpha(0.3).restart()
    this.later(() => this.fitTo(new Set(pos.keys()), 0.15), 50) // the whole tree: as far out as it takes
  }

  private leaveTree() {
    this.nodes.forEach((n) => {
      const k = this.kept.get(n.id)
      n.fx = null
      n.fy = null
      if (k) { n.x = k.x; n.y = k.y }
    })
    this.svg.selectAll('.tree-off').classed('tree-off', false)
    this.sim?.alpha(0.2).restart()
    this.later(() => this.fit(), 400)
  }

  // ---------- names, focus, neighbourhoods ----------
  /** Names where they fit: the most telling first (claims, others resting on it), each kept only if it overlaps none
   * already placed, on screen; the picked one's neighbourhood, search hits and the dot pointed at always named (CSS) */
  private placeLabels() {
    if (!this.m) return
    const t = d3.zoomTransform(this.el), { W, H } = this.size()
    const kids = this.m.kids
    const prio = (n: Node) => n.e.claims.length * 2 + ((kids[n.id] ?? []).length ? 4 : 0) + (n.e.parents.length ? 1 : 0)
    const placed: { x0: number; x1: number; y0: number; y1: number }[] = []
    const fits = (b: (typeof placed)[0]) => !placed.some((p) => b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0)
    const shown = new Set<string>()
    for (const n of [...this.nodes].sort((a, b) => prio(b) - prio(a))) {
      if (n.x === undefined) continue
      const rad = R(n) * t.k, x = n.x * t.k + t.x, y = n.y! * t.k + t.y
      const b = { x0: x + rad, x1: x + rad + n.e.name.length * 6.1 * t.k + 4, y0: y - 8 * t.k, y1: y + 6 * t.k }
      if (b.x1 < 0 || b.x0 > W || b.y1 < 0 || b.y0 > H) continue // off screen
      if (fits(b)) { placed.push(b); shown.add(n.id) }
    }
    this.svg.selectAll<SVGTextElement, Node>('.mm-node text').classed('lbl-off', (n) => !shown.has(n.id))
  }

  /** A motif's neighbourhood: what it rests on and what rests on it, two steps along those; its related motifs, one */
  private neighbourhood(id: string) {
    const s = new Set([id]), m = this.m!
    if (this.o!.claimMode) {
      this.links.forEach((l) => { if (sid(l.source!) === id) s.add(sid(l.target!)); if (sid(l.target!) === id) s.add(sid(l.source!)) })
      return s
    }
    let edge = [id]
    for (let step = 0; step < 2; step++) {
      const next: string[] = []
      edge.forEach((x) => [...(m.by[x]?.parents ?? []), ...(m.kids[x] ?? [])].forEach((y) => { if (!s.has(y)) { s.add(y); next.push(y) } }))
      edge = next
    }
    ;(m.by[id]?.related ?? []).forEach((r) => s.add(r))
    return s
  }

  /** Related lines drawn for the motif picked or pointed at (with "the picked one's"), and the names around it */
  private markNear() {
    const at = new Set([this.focus, this.hover].filter(Boolean) as string[])
    this.svg.selectAll<SVGLineElement, Link>('.mm-link').classed('near', (l) => at.has(sid(l.source!)) || at.has(sid(l.target!)))
    const around = this.hover ? this.neighbourhood(this.hover) : new Set<string>()
    this.svg.selectAll<SVGGElement, Node>('.mm-node').classed('near-focus', (n) => around.has(n.id) || !!(this.focus && this.near?.has(n.id)))
  }

  private applyFocus() {
    const term = this.o?.term ?? ''
    this.near = this.focus ? this.neighbourhood(this.focus) : null // picked: its neighbourhood stays, the rest fades almost away
    const near = this.near
    this.el.classList.toggle('focusing', !!this.focus)
    this.svg.selectAll<SVGGElement, Node>('.mm-node').classed('far', (n) => (near ? !near.has(n.id) : false))
      .classed('hit', (n) => (!!term && n.e.name.toLowerCase().includes(term)) || n.id === this.focus)
    this.svg.selectAll<SVGLineElement, Link>('.mm-link').classed('far', (l) => (near ? !(near.has(sid(l.source!)) && near.has(sid(l.target!))) : false))
    this.markNear()
    this.placeLabels()
  }

  /** Picked: its neighbourhood gathered round it as a small diagram (what it rests on above, what rests on it below,
   * related to the sides; a second step further out), the rest left where it was, faded; let go, they spring back */
  private gather(id: string) {
    this.scatter()
    const m = this.m!, c = this.nodes.find((n) => n.id === id)
    if (!c || c.x === undefined) return
    const e = m.by[id], kidsOf = (x: string) => m.kids[x] ?? []
    const up1 = e.parents.filter((p) => m.by[p]), down1 = kidsOf(id)
    const up2 = [...new Set(up1.flatMap((p) => m.by[p].parents))].filter((x) => x !== id && !up1.includes(x))
    const down2 = [...new Set(down1.flatMap(kidsOf))].filter((x) => x !== id && !down1.includes(x))
    const rel = e.related.filter((r) => m.by[r] && !up1.includes(r) && !down1.includes(r))
    const ROW = 5 // at most this many side by side; more go in further rows
    const byId = new Map(this.nodes.map((n) => [n.id, n]))
    const place = (ids: string[], dy: number, spread: number) => ids.forEach((x, i) => {
      const n = byId.get(x)
      if (!n || this.gathered.has(x)) return
      this.gathered.set(x, { x: n.x!, y: n.y! })
      const row = Math.floor(i / ROW), inRow = Math.min(ROW, ids.length - row * ROW), col = i % ROW
      n.fx = c.x! + (col - (inRow - 1) / 2) * spread
      n.fy = c.y! + dy + Math.sign(dy) * row * 60
    })
    this.gathered.set(id, { x: c.x, y: c.y! })
    c.fx = c.x
    c.fy = c.y
    const rows = (ids: string[]) => Math.max(0, Math.ceil(ids.length / ROW) - 1) * 60
    place(up1, -120, 140)
    place(up2, -230 - rows(up1), 125)
    place(down1, 120, 140)
    place(down2, 230 + rows(down1), 125)
    rel.forEach((x, i) => { // the related ones in a column each side
      const n = byId.get(x)
      if (!n || this.gathered.has(x)) return
      this.gathered.set(x, { x: n.x!, y: n.y! })
      const side = i % 2 ? 1 : -1, row = Math.floor(i / 2)
      n.fx = c.x! + side * 260
      n.fy = c.y! + (row - (Math.ceil(rel.length / 2) - 1) / 2) * 60
    })
    this.sim?.alpha(0.25).restart()
  }

  private scatter() { // the gathered ones back where they were
    if (!this.gathered.size) return
    const byId = new Map(this.nodes.map((n) => [n.id, n]))
    this.gathered.forEach((was, id) => {
      const n = byId.get(id)
      if (n) { n.fx = null; n.fy = null; n.x = was.x; n.y = was.y }
    })
    this.gathered.clear()
    this.sim?.alpha(0.15).restart()
  }

  /** Pick a motif (null: let it go). `zoom`: the view goes to its neighbourhood */
  pick(id: string | null, zoom = false) {
    if (id && !this.m?.by[id]) id = null
    this.focus = id
    if (id && !this.o?.tree) this.gather(id)
    else this.scatter() // in the tree the neighbourhood is already in place: just picked out
    this.applyFocus()
    this.hooks.onFocus(id)
    if (id && (zoom || this.gathered.size) && this.near) this.fitTo(this.near) // leaving room for the details box (cover())
  }

  /** Go to a motif: picked, and the view on it. One not on the map (no links, with "only linked" on) is put there first */
  center(id: string, again = false) {
    const n = this.nodes.find((x) => x.id === id)
    this.pick(id)
    if (!n) {
      if (!again && this.m?.by[id]) { this.draw(); this.later(() => this.center(id, true), 500) }
      return
    }
    const { W, H } = this.size(), w = W - this.cover()
    this.svg.transition().duration(500).call(this.zoomer.transform, d3.zoomIdentity.translate(w / 2 - n.x! * 1.3, H / 2 - n.y! * 1.3).scale(1.3))
  }

  /** The first motif whose name has the search in it, gone to */
  findFirst(term: string) {
    const t = term.trim().toLowerCase()
    const n = t && this.nodes.find((x) => x.e.name.toLowerCase().includes(t))
    if (n) this.center(n.id)
  }

  /** The given motifs in view, left of the details box, zoomed out no further than `least` */
  private fitTo(ids: Set<string>, least = 0.4) {
    const ns = this.nodes.filter((n) => ids.has(n.id) && n.x !== undefined)
    if (!ns.length) return
    const { W: full, H } = this.size(), W = full - this.cover()
    // where they're going (a gathered one is pinned there), not where they are mid-move
    const xs = ns.map((n) => n.fx ?? n.x!), ys = ns.map((n) => n.fy ?? n.y!)
    const x0 = Math.min(...xs) - 60, x1 = Math.max(...xs) + 180, y0 = Math.min(...ys) - 50, y1 = Math.max(...ys) + 50
    const k = Math.max(least, Math.min(2.2, 0.9 * Math.min(W / (x1 - x0), H / (y1 - y0))))
    this.svg.transition().duration(500).call(this.zoomer.transform, d3.zoomIdentity.translate(W / 2 - k * (x0 + x1) / 2, H / 2 - k * (y0 + y1) / 2).scale(k))
  }

  /** The whole map in view */
  fit() {
    if (!this.nodes.length) return
    const xs = this.nodes.map((n) => n.x!), ys = this.nodes.map((n) => n.y!), { W, H } = this.size()
    const x0 = Math.min(...xs) - 40, x1 = Math.max(...xs) + 140, y0 = Math.min(...ys) - 30, y1 = Math.max(...ys) + 30
    const k = Math.min(2, 0.95 * Math.min(W / (x1 - x0), H / (y1 - y0)))
    this.svg.transition().duration(600).call(this.zoomer.transform, d3.zoomIdentity.translate(W / 2 - k * (x0 + x1) / 2, H / 2 - k * (y0 + y1) / 2).scale(k))
  }
}
