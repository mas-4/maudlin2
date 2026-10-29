"""The outlet map's shape (Oct 29): soft shading behind the coverage view's dots shows the shape the outlets make
(on Oct 29 an arrow: a shaft of business and wire outlets forking into a left prong and a right one)."""
from app.site import page_outlet_map as om


def test_the_shading_follows_the_dots_and_leaves_the_gaps():
    # two clumps far apart: shading round each, none in the gap between them
    pts = [(100 + d, 100 + d) for d in (0, 4, 8)] + [(600 + d, 400 + d) for d in (0, 4, 8)]
    svg = om.density_svg(pts, 760, 560)
    assert svg.startswith('<g class="omap-shape"') and 'omap-shape-0' in svg
    outer = [p for p in svg.split('<path ')[1:] if 'omap-shape-0' in p]
    assert len(outer) == 2  # one outline round each clump
    assert om.density_svg(pts[:2], 760, 560) == ''  # too few dots to have a shape


def test_only_the_coverage_view_gets_a_shape():
    outlets = {f'O{i}': {'x': (i % 5) / 4 - 0.5, 'y': (i // 5) / 3 - 0.5, 'wire': i / 15, 'heat': (15 - i) / 15,
                         'is_wire': False, 'lean': None, 'type': None} for i in range(15)}
    svg = om.map_svg(outlets)
    coverage, style = svg.split('data-view="style"')
    assert 'omap-shape' in coverage and 'omap-shape' not in style
