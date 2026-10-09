// The motif maps' shared layout and colors: the site's map (motif-map.html) and the checker's (scripts/checker/templates/
// map.html, which gets this file from /checker/static/) both load it, so how groups sit, how a group is drawn and what
// color a group or genre is stay the same on both. Each page keeps its own dots, cards and controls. Needs d3.
window.MotifMap = (function () {
    // A group's color by its place among all groups A to Z, a genre's by its place among all genres A to Z (the
    // workbench shelf's order), so a group or genre is one color on every page
    const GROUP_COLORS = ['#ff4fa3', '#3a86ff', '#ff6b1a', '#8a5cff', '#00a896', '#e0a800'];
    const GENRE_COLORS = ['#ff4fa3', '#00c2a8', '#ffc400', '#3a86ff', '#ff6b1a', '#8a5cff', '#2bb673', '#e0102e', '#a0522d',
                          '#00a6d6', '#c2185b', '#6b8e23', '#ff8fab', '#5c6bc0'];
    const groupColor = (k) => GROUP_COLORS[Math.max(0, k) % GROUP_COLORS.length];
    const genreColor = (genres, v) => GENRE_COLORS[Math.max(0, genres.indexOf(v)) % GENRE_COLORS.length];

    const BLOB_GAP = 180;  // members further apart than this aren't joined in their group's blob
    const GROUP_PULL = 0.9;  // how hard a group's motifs are drawn to its home (links pull them toward their neighbours elsewhere)
    const CROSSING = 0.2;  // a link from a motif in a group to one outside all its groups pulls this much as hard

    // Whether a link joins a grouped motif to one outside all its groups (groupsOf: a node's shown groups)
    const crossing = (groupsOf) => (l) => {
        const a = groupsOf(l.source), b = groupsOf(l.target);
        return (a.length || b.length) && !a.some((g) => b.includes(g));
    };

    // Each group has a home of its own, spaced evenly on a ring around the middle, and its motifs are drawn there; a
    // motif in two groups settles between their homes, one in none stays free in the middle. Pulling each group to its
    // own center and pushing groups apart lost to the links (every pair of 8 groups still overlapped, Oct 7). A motif
    // not in a group is kept `room` off that group's members, so it never sits inside the group's blob.
    // groups: the shown groups' ids; groupsOf(n): a node's groups among them; r(n): a dot's radius
    // Each step only looks at the motifs inside a group's reach (its members' box, widened by the largest gap): checking
    // every motif against every member of every group took 10 ms a step with 453 motifs, seconds for a layout (Oct 9)
    function groupForce(nodes, groups, groupsOf, r, W, H, room = 30) {
        const homes = new Map(), ring = 0.42 * Math.min(W, H);
        groups.forEach((g, k) => {
            const t = 2 * Math.PI * k / Math.max(1, groups.length) - Math.PI / 2;
            homes.set(g, [W / 2 + 1.5 * ring * Math.cos(t), H / 2 + ring * Math.sin(t)]);
        });
        const mine = new Map(nodes.map((n) => [n, new Set(groupsOf(n))]));
        const members = groups.map((g) => [g, nodes.filter((n) => mine.get(n).has(g))]).filter(([, ms]) => ms.length);
        return (alpha) => {
            const rad = new Map(nodes.map((n) => [n, r(n)]));  // read each step: the dot-size slider changes them
            const most = d3.max(nodes, (n) => rad.get(n)) || 0;
            members.forEach(([g, ms]) => {
                const reach = d3.max(ms, (m) => rad.get(m)) + most + room;
                const x0 = d3.min(ms, (m) => m.x) - reach, x1 = d3.max(ms, (m) => m.x) + reach;
                const y0 = d3.min(ms, (m) => m.y) - reach, y1 = d3.max(ms, (m) => m.y) + reach;
                nodes.forEach((n) => {
                    if (n.x < x0 || n.x > x1 || n.y < y0 || n.y > y1 || mine.get(n).has(g)) return;
                    ms.forEach((m) => {
                        const dx = n.x - m.x, dy = n.y - m.y, d = Math.hypot(dx, dy) || 1, gap = rad.get(m) + rad.get(n) + room;
                        if (d < gap) { const f = (gap - d) / d * 0.5 * alpha; n.vx += dx * f; n.vy += dy * f; }
                    });
                });
            });
            nodes.forEach((n) => {
                const hs = [...mine.get(n)].map((g) => homes.get(g)).filter(Boolean);
                if (!hs.length) return;
                const tx = d3.mean(hs, (h) => h[0]), ty = d3.mean(hs, (h) => h[1]);
                n.vx += (tx - n.x) * GROUP_PULL * alpha; n.vy += (ty - n.y) * GROUP_PULL * alpha;
            });
        };
    }

    // A group as a blob hugging its members (a bubble set): a bubble round each, joined by bands along the shortest
    // links between them (a minimum spanning tree), a band longer than BLOB_GAP cut, so a far-off member is an island
    // of its own. Until Oct 7 a convex hull round all of them took in every motif in between (non-members looked like
    // members). groups: a selection of one <g> per group, each holding a <g> for the blob and a <text> for its name;
    // the blob is drawn in layers, each `grow` wider (an outline under a fill), styled by their class
    function drawBlobs(groups, members, pad, layers = [{cls: '', grow: 0}]) {
        groups.each(function (g) {
            const ms = members(g), edges = [];
            if (ms.length > 1) {
                const inTree = new Set([0]), best = ms.map((n) => [Math.hypot(n.x - ms[0].x, n.y - ms[0].y), 0]);
                while (inTree.size < ms.length) {
                    let k = -1;
                    ms.forEach((_, i) => { if (!inTree.has(i) && (k < 0 || best[i][0] < best[k][0])) k = i; });
                    inTree.add(k);
                    if (best[k][0] <= BLOB_GAP) edges.push([ms[best[k][1]], ms[k]]);
                    ms.forEach((n, i) => { if (!inTree.has(i)) { const d = Math.hypot(n.x - ms[k].x, n.y - ms[k].y); if (d < best[i][0]) best[i] = [d, k]; } });
                }
            }
            const blob = d3.select(this).select('g');
            blob.selectAll(':scope > g').data(layers).join('g').attr('class', (l) => l.cls).each(function (l) {
                const layer = d3.select(this);
                layer.selectAll('circle').data(ms, (n) => n.id).join('circle').attr('cx', (n) => n.x).attr('cy', (n) => n.y).attr('r', (n) => pad(n) + l.grow);
                layer.selectAll('line').data(edges).join('line').attr('x1', (e) => e[0].x).attr('y1', (e) => e[0].y).attr('x2', (e) => e[1].x).attr('y2', (e) => e[1].y)
                    .attr('stroke-width', (e) => 1.6 * Math.min(pad(e[0]), pad(e[1])) + 2 * l.grow).attr('stroke-linecap', 'round');
            });
            d3.select(this).select('text').attr('x', ms.length ? d3.mean(ms, (n) => n.x) : -9999)
                .attr('y', ms.length ? d3.min(ms, (n) => n.y - pad(n)) - 6 - d3.max(layers, (l) => l.grow) : -9999);
        });
    }

    return {GROUP_COLORS, GENRE_COLORS, groupColor, genreColor, BLOB_GAP, GROUP_PULL, CROSSING, crossing, groupForce, drawBlobs};
})();
