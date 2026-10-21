// How groups sit on the map and how a group is drawn, ported from app/site/static/motif-map-layout.js (the site's map
// still loads that file). Keep the two in step, so a group sits and looks the same on both maps; the colours are
// model.ts's GROUP_COLORS and GENRE_COLORS, the same lists.
import * as d3 from 'd3'

export interface Placed { id: string; x?: number; y?: number; vx?: number; vy?: number }

export const BLOB_GAP = 180 // members further apart than this aren't joined in their group's blob
export const GROUP_PULL = 0.9 // how hard a group's motifs are drawn to its home (links pull them toward their neighbours elsewhere)
export const CROSSING = 0.2 // a link from a motif in a group to one outside all its groups pulls this much as hard

/** Whether a link joins a grouped motif to one outside all its groups (groupsOf: a node's shown groups) */
export const crossing = <N>(groupsOf: (n: N) => string[]) => (l: { source: N | string | number; target: N | string | number }) => {
  const a = groupsOf(l.source as N), b = groupsOf(l.target as N)
  return (a.length > 0 || b.length > 0) && !a.some((g) => b.includes(g))
}

/** Each group has a home of its own, spaced evenly on a ring around the middle, and its motifs are drawn there; a motif
 * in two groups settles between their homes, one in none stays free in the middle. A motif not in a group is kept `room`
 * off that group's members, so it never sits inside the group's blob. Each step only looks at the motifs inside a
 * group's reach (its members' box, widened by the largest gap): checking every motif against every member of every
 * group took seconds a layout with 453 motifs (Oct 9) */
export function groupForce<N extends Placed>(nodes: N[], groups: (string | number)[], groupsOf: (n: N) => (string | number)[],
  r: (n: N) => number, W: number, H: number, room = 30) {
  const homes = new Map<string | number, [number, number]>(), ring = 0.42 * Math.min(W, H)
  groups.forEach((g, k) => {
    const t = 2 * Math.PI * k / Math.max(1, groups.length) - Math.PI / 2
    homes.set(g, [W / 2 + 1.5 * ring * Math.cos(t), H / 2 + ring * Math.sin(t)])
  })
  const mine = new Map(nodes.map((n) => [n, new Set(groupsOf(n))]))
  const members = groups.map((g) => [g, nodes.filter((n) => mine.get(n)!.has(g))] as const).filter(([, ms]) => ms.length)
  return (alpha: number) => {
    const rad = new Map(nodes.map((n) => [n, r(n)]))
    const most = d3.max(nodes, (n) => rad.get(n)!) ?? 0
    members.forEach(([g, ms]) => {
      const reach = (d3.max(ms, (m) => rad.get(m)!) ?? 0) + most + room
      const x0 = d3.min(ms, (m) => m.x!)! - reach, x1 = d3.max(ms, (m) => m.x!)! + reach
      const y0 = d3.min(ms, (m) => m.y!)! - reach, y1 = d3.max(ms, (m) => m.y!)! + reach
      nodes.forEach((n) => {
        if (n.x! < x0 || n.x! > x1 || n.y! < y0 || n.y! > y1 || mine.get(n)!.has(g)) return
        ms.forEach((m) => {
          const dx = n.x! - m.x!, dy = n.y! - m.y!, d = Math.hypot(dx, dy) || 1, gap = rad.get(m)! + rad.get(n)! + room
          if (d < gap) {
            const f = (gap - d) / d * 0.5 * alpha
            n.vx! += dx * f
            n.vy! += dy * f
          }
        })
      })
    })
    nodes.forEach((n) => {
      const hs = [...mine.get(n)!].map((g) => homes.get(g)).filter((h): h is [number, number] => !!h)
      if (!hs.length) return
      const tx = d3.mean(hs, (h) => h[0])!, ty = d3.mean(hs, (h) => h[1])!
      n.vx! += (tx - n.x!) * GROUP_PULL * alpha
      n.vy! += (ty - n.y!) * GROUP_PULL * alpha
    })
  }
}

/** A group as a blob hugging its members (a bubble set): a bubble round each, joined by bands along the shortest links
 * between them (a minimum spanning tree), a band longer than BLOB_GAP cut, so a far-off member is an island of its own.
 * groups: a selection of one <g> per group, each holding a <g> for the blob and a <text> for its name */
export function drawBlobs<G, N extends Placed>(groups: d3.Selection<SVGGElement, G, SVGGElement, unknown>, members: (g: G) => N[], pad: (n: N) => number) {
  groups.each(function (g) {
    const ms = members(g), edges: [N, N][] = []
    if (ms.length > 1) {
      const inTree = new Set([0]), best: [number, number][] = ms.map((n) => [Math.hypot(n.x! - ms[0].x!, n.y! - ms[0].y!), 0])
      while (inTree.size < ms.length) {
        let k = -1
        ms.forEach((_, i) => { if (!inTree.has(i) && (k < 0 || best[i][0] < best[k][0])) k = i })
        inTree.add(k)
        if (best[k][0] <= BLOB_GAP) edges.push([ms[best[k][1]], ms[k]])
        ms.forEach((n, i) => {
          if (inTree.has(i)) return
          const d = Math.hypot(n.x! - ms[k].x!, n.y! - ms[k].y!)
          if (d < best[i][0]) best[i] = [d, k]
        })
      }
    }
    const blob = d3.select(this).select<SVGGElement>('g')
    blob.selectAll<SVGCircleElement, N>('circle').data(ms, (n) => n.id).join('circle')
      .attr('cx', (n) => n.x!).attr('cy', (n) => n.y!).attr('r', pad)
    blob.selectAll<SVGLineElement, [N, N]>('line').data(edges).join('line')
      .attr('x1', (e) => e[0].x!).attr('y1', (e) => e[0].y!).attr('x2', (e) => e[1].x!).attr('y2', (e) => e[1].y!)
      .attr('stroke-width', (e) => 1.6 * Math.min(pad(e[0]), pad(e[1]))).attr('stroke-linecap', 'round')
    d3.select(this).select('text').attr('x', ms.length ? d3.mean(ms, (n) => n.x!)! : -9999)
      .attr('y', ms.length ? d3.min(ms, (n) => n.y! - pad(n))! - 6 : -9999)
  })
}
