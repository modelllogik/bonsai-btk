# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Outlines of cut areas: rings from loose edges, drawing order, joints and build-ups.

- **Rings from loose edges.** A plain Blender mesh cut by Bonsai comes out as loose
  two-point paths, not as an area, so it gets no fill and no hatching. The edges are
  chained into rings as a fallback; an element with a hole keeps its hole.
- **Structural layers last.** Where two layers share an edge, the one drawn later
  covers half the line of the earlier one. Structural layers (heavier line in the
  style) are therefore moved to the end of each run of sibling layers, and
  waterproofing bands after them.
- **No joint between elements of the same material.** Cut areas of the same
  material are united; only the outline of the union is drawn. Walls of the same
  masonry meeting at a corner are hatched through without a line between them,
  while a joint between different materials stays.
- **Build-ups as one area.** From 1:100, floor, ceiling and roof build-ups are drawn
  as one white area with one outline, and thin claddings (plaster, membranes) are
  left out; otherwise their lines merge into black bars. Per element the
  ``EPset_BTK_Hatching.Layers`` switch overrides this in any scale (model.py).

Text in, text out; shapely is used for the area operations (it comes with Bonsai).
No bpy here.
"""
import math
import re

from . import style, svg

RING_TOLERANCE = 1e-3      # mm on paper: closer points are the same node
STRAIGHT_TOLERANCE = 1e-3  # mm: an intermediate point closer to the line is dropped
MAX_EDGES = 20000          # emergency brake against degenerate drawings

OUTLINE_CLASS = "din-umriss"   # outline built from loose edges
JOINT_CLASS = "din-fuge"       # outline of a union of the same material
BUILD_UP_CLASS = "din-aufbau"  # build-up as one area

BUILD_UP_FROM = 100        # scale denominator from which build-ups are one area
BUILD_UP_STROKE = 0.25     # mm, outline of a build-up area
BUILD_UP_GAP = 0.03        # mm on paper: smaller gaps between build-up parts are closed

ROLE_OMIT = "weg"          # left out (membranes, plaster claddings)
ROLE_BUILD_UP = "aufbau"   # part of a build-up
ROLE_INSULATION = "daemmung"  # joins a build-up it touches
ROLE_FORCED = "aufbau!"    # switch off: one area in every scale

_RE_PATH_D = re.compile(r'<path\b[^>]*\bd="([^"]*)"')
_RE_JOINT_GROUP = re.compile(r'<g class="[^"]*\b%s\b[^"]*"[^>]*>.*?</g>' % JOINT_CLASS, re.S)


def remove_joint_groups(svg_text):
    """The text without earlier joint outlines, so that a step can run again."""
    return _RE_JOINT_GROUP.sub("", svg_text)


# ------------------------------------------------------------------ rings from loose edges

class _Nodes:
    """Snap points to a grid of the tolerance, so that equal corners get one number."""

    def __init__(self, tolerance):
        self.tolerance = tolerance
        self.cells = {}
        self.points = []

    def number(self, p):
        x, y = p
        t = self.tolerance
        i, j = int(math.floor(x / t)), int(math.floor(y / t))
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for n in self.cells.get((i + di, j + dj), ()):
                    qx, qy = self.points[n]
                    if abs(qx - x) <= t and abs(qy - y) <= t:
                        return n
        n = len(self.points)
        self.points.append((x, y))
        self.cells.setdefault((i, j), []).append(n)
        return n


def area(points):
    """Unsigned area of a closed polyline (shoelace formula)."""
    p = points[:-1] if len(points) > 1 and points[0] == points[-1] else points
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def has_ring(polylines, tolerance=RING_TOLERANCE):
    """True if one of the polylines is already closed; then nothing is chained."""
    for line in polylines:
        if len(line) >= 3:
            (x0, y0), (x1, y1) = line[0], line[-1]
            if abs(x0 - x1) <= tolerance and abs(y0 - y1) <= tolerance:
                return True
    return False


def _merge_straight(ring, tolerance=STRAIGHT_TOLERANCE):
    """Drop intermediate points on a straight line (ring with first point == last).
    Bonsai puts such points where other edges join."""
    if len(ring) < 5:
        return ring
    p = ring[:-1]
    keep = []
    n = len(p)
    for i in range(n):
        a, b, c = p[(i - 1) % n], p[i], p[(i + 1) % n]
        ax, ay = c[0] - a[0], c[1] - a[1]
        length = math.hypot(ax, ay)
        if length < 1e-12:
            keep.append(b)
            continue
        if abs(ax * (a[1] - b[1]) - ay * (a[0] - b[0])) / length > tolerance:
            keep.append(b)
    if len(keep) < 3:
        return ring
    return keep + [keep[0]]


def _canonical_ring(ring):
    """Start at the smallest point and run in the smaller direction, so that the text
    of a ring does not depend on where chaining began (same geometry, same clip id)."""
    p = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else list(ring)
    if len(p) < 3:
        return ring
    i = min(range(len(p)), key=lambda k: p[k])
    forward = p[i:] + p[:i]
    backward = [forward[0]] + list(reversed(forward[1:]))
    best = forward if forward <= backward else backward
    return best + [best[0]]


def _direction(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def rings_from_edges(polylines, tolerance=RING_TOLERANCE, straight=True):
    """(rings, report). Each ring is a point list with first point == last.

    The edges of all polylines are chained at shared end points. Duplicate edges are
    dropped, dead ends cut off; at a crossing the straightest continuation is taken.
    Separate rings stay separate, so a hole stays a hole (outline_group joins them
    with fill-rule evenodd)."""
    nodes = _Nodes(tolerance)
    edges = set()
    for line in polylines:
        for i in range(len(line) - 1):
            a = nodes.number(line[i])
            b = nodes.number(line[i + 1])
            if a == b:
                continue
            edges.add((min(a, b), max(a, b)))
            if len(edges) > MAX_EDGES:
                return [], ["too many edges (>%d), not chained" % MAX_EDGES]

    report = []
    neighbours = {}
    for edge in edges:
        neighbours.setdefault(edge[0], set()).add(edge)
        neighbours.setdefault(edge[1], set()).add(edge)

    pending = [k for k, e in neighbours.items() if len(e) == 1]
    cut = 0
    while pending:
        k = pending.pop()
        if len(neighbours.get(k, ())) != 1:
            continue
        edge = next(iter(neighbours[k]))
        edges.discard(edge)
        cut += 1
        for m in edge:
            neighbours[m].discard(edge)
            if len(neighbours[m]) == 1:
                pending.append(m)
    if cut:
        report.append("%d loose edge(s) without connection left out" % cut)

    rings = []
    unused = set(edges)
    while unused:
        start = min(unused)
        unused.discard(start)
        a, b = start
        path = [a, b]
        while path[-1] != a and len(path) <= len(edges) + 2:
            here, before = path[-1], path[-2]
            candidates = [(e[0] if e[1] == here else e[1], e)
                          for e in neighbours.get(here, ()) if e in unused]
            if not candidates:
                break
            if len(candidates) == 1:
                following, edge = candidates[0]
            else:
                incoming = _direction(nodes.points[before], nodes.points[here])
                best = None
                for n, e in sorted(candidates):
                    outgoing = _direction(nodes.points[here], nodes.points[n])
                    turn = abs(math.atan2(math.sin(outgoing - incoming), math.cos(outgoing - incoming)))
                    if best is None or turn < best[0]:
                        best = (turn, n, e)
                _, following, edge = best
            unused.discard(edge)
            path.append(following)
        if path[-1] == a and len(path) >= 4:
            points = [nodes.points[n] for n in path]
            if straight:
                points = _merge_straight(points)
            rings.append(_canonical_ring(points))
        else:
            report.append("open chain of %d point(s) dropped" % len(path))

    rings.sort(key=lambda r: (-area(r), r[0]))
    if rings:
        report.insert(0, "%d ring(s) chained from %d edge(s)" % (len(rings), len(edges)))
    return rings, report


def _point_in_ring(p, ring):
    x, y = p
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > y) != (y2 > y):
            if x1 + (y - y1) * (x2 - x1) / (y2 - y1) > x:
                inside = not inside
    return inside


def sort_rings(rings):
    """(areas, holes): a ring inside an odd number of other rings is a hole, the same
    rule by which fill-rule evenodd fills."""
    areas, holes = [], []
    for i, r in enumerate(rings):
        depth = sum(1 for j, s in enumerate(rings) if j != i and _point_in_ring(r[0], s))
        (holes if depth % 2 else areas).append(r)
    return areas, holes


def _with_sign(ring, positive=True):
    p = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return list(reversed(ring)) if (s > 0) != positive else list(ring)


def orient_rings(areas, holes):
    """Areas and holes in opposite directions, so that a hole comes from the winding
    alone. Inkscape loses clip-rule evenodd on PDF export, and printing goes through
    Inkscape."""
    return [_with_sign(r, True) for r in areas] + [_with_sign(r, False) for r in holes]


def d(points):
    """Path data of one polyline, four decimals."""
    return " ".join(("M" if i == 0 else "L") + "%.4f,%.4f" % p for i, p in enumerate(points))


def outline_group(rings):
    """All rings in ONE path: with fill-rule evenodd a hole stays open. The group
    takes fill and category from the element; its own line is off, the edges of the
    element still draw the outline."""
    return ('<g class="%s"><path d="%s" style="fill-rule:evenodd; stroke:none"/></g>'
            % (OUTLINE_CLASS, " ".join(d(r) for r in rings)))


def _ring_paths(geometry):
    rings = []
    for poly in getattr(geometry, "geoms", [geometry]):
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        rings.append(list(poly.exterior.coords))
        rings += [list(r.coords) for r in poly.interiors]
    return " ".join("M" + " L".join("%.4f,%.4f" % (x, y) for x, y in r[:-1]) + " Z" for r in rings)


def _areas_of_group(content):
    """Shapely areas from the closed subpaths of a group (rings from loose edges as
    a fallback)."""
    from shapely.geometry import Polygon
    polylines = []
    for path in _RE_PATH_D.findall(content):
        polylines += svg.subpaths(path)
    if not polylines:
        return []
    if has_ring(polylines):
        rings = [p for p in polylines if len(p) >= 4 and p[0] == p[-1]]
    else:
        rings, _ = rings_from_edges(polylines)
    result = None
    for r in rings:
        if len(r) < 3:
            continue
        p = Polygon(r)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty:
            continue
        result = p if result is None else result.symmetric_difference(p)
    return [] if result is None or result.is_empty else [result]


# ------------------------------------------------------------------ drawing order

def structural_last(svg_text):
    """(text, number of reordered runs). In each run of directly adjacent cut groups
    with a category, structural layers move after the others and waterproofing bands
    after those. The sort is stable, so a second run changes nothing."""
    css = svg.style_text(svg_text) or svg_text
    heavy = style.structural_categories(css)
    band = style.band_categories(svg_text)
    if not heavy and not band:
        return svg_text, 0

    def rank(category):
        if category in band:
            return 2
        return 1 if category in heavy else 0

    layers = []
    for head_start, head_end, content_end in svg.groups(svg_text):
        head = svg_text[head_start:head_end]
        if not svg.has_class(head, "cut"):
            continue
        category = style.category_of(head)
        if category is None:
            continue
        layers.append((head_start, svg.group_end(svg_text, head_end, content_end), category))
    if len(layers) < 2:
        return svg_text, 0
    layers.sort()

    runs, run = [], [layers[0]]
    for entry in layers[1:]:
        if svg_text[run[-1][1]:entry[0]].strip() == "":
            run.append(entry)
        else:
            runs.append(run)
            run = [entry]
    runs.append(run)

    text, count = svg_text, 0
    for run in sorted(runs, key=lambda r: -r[0][0]):
        if len(run) < 2:
            continue
        order = sorted(range(len(run)), key=lambda i: rank(run[i][2]))
        if order == list(range(len(run))):
            continue
        pieces = [text[a:e] for a, e, _ in run]
        between = [text[run[i][1]:run[i + 1][0]] for i in range(len(run) - 1)]
        built = pieces[order[0]]
        for i in range(1, len(run)):
            built += between[i - 1] + pieces[order[i]]
        text = text[:run[0][0]] + built + text[run[-1][1]:]
        count += 1
    return text, count


# ------------------------------------------------------------------ joints of the same material

def merge_joints(svg_text):
    """(text, number of outlines). Cut areas of the same material (layer:
    layer-material-X, otherwise material-X) are united. The single outlines, also the
    overall outline of a layered element, get stroke:none; the outline of the union
    comes with the same classes, so with the same line weight from the style, as a
    group din-fuge at the end of the drawing. A second run gives the same result."""
    try:
        import shapely
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
    except ImportError:
        return svg_text, 0
    text = remove_joint_groups(svg_text)
    all_groups = svg.groups(text)
    cut_groups = []
    for head_start, head_end, content_end in all_groups:
        names = svg.classes(text[head_start:head_end])
        if "cut" in names and JOINT_CLASS not in names and BUILD_UP_CLASS not in names:
            cut_groups.append((head_start, head_end, content_end, names))
    if not cut_groups:
        return text, 0
    layered = {c for _, _, _, names in cut_groups if "IfcMaterialLayer" in names
               for c in names if c.startswith("material-")}
    areas, silent = {}, []
    for head_start, head_end, content_end, names in cut_groups:
        layer = [c for c in names if c.startswith("layer-material-") and not c.startswith(style.CATEGORY_CLASS)]
        material = [c for c in names if c.startswith("material-")]
        if layer:
            key = layer[0]
        elif material and material[0] in layered:
            key = None                      # overall outline: the layers draw it
        elif material:
            key = material[0]
        else:
            continue
        direct_end = text.find("<g", head_end, content_end)
        if direct_end < 0:
            direct_end = content_end
        silent.append((head_end, direct_end))
        if key is None:
            continue
        result = None
        for path in _RE_PATH_D.findall(text[head_end:direct_end]):
            for points in svg.subpaths(path):
                if len(points) < 3:
                    continue
                p = Polygon(points)
                if not p.is_valid:
                    p = p.buffer(0)
                if p.is_empty:
                    continue
                result = p if result is None else result.symmetric_difference(p)
        if result is not None and not result.is_empty:
            areas.setdefault(key, [names, []])[1].append(result)
    new = []
    for key in sorted(areas):
        names, parts = areas[key]
        united = unary_union([shapely.set_precision(p, 0.001) for p in parts])
        path = _ring_paths(united)
        if not path:
            continue
        classes = [c for c in names if not svg.is_global_id(c)] + [JOINT_CLASS]
        new.append('<g class="%s" style="fill:none"><path style="fill:none" d="%s"/></g>'
                   % (" ".join(classes), path))
    first = cut_groups[0][0]
    parents = [g for g in all_groups if g[0] < first and g[2] > first]
    insert = max(parents)[2] if parents else cut_groups[-1][2]
    for start, end in sorted(silent, key=lambda x: -x[0]):
        part = re.sub(r"<path(?![^>]*\bstyle=)", '<path style="stroke:none"', text[start:end])
        text = text[:start] + part + text[end:]
        if start < insert:
            insert += len(part) - (end - start)
    text = text[:insert] + "".join(new) + text[insert:]
    return text, len(new)


# ------------------------------------------------------------------ build-ups as one area

def simplify_build_ups(svg_text, roles, denominator=None):
    """(text, groups left out, groups united). roles = {GlobalId: role} (model.py).

    Below BUILD_UP_FROM only elements switched to one area are united. A second run
    finds no parts any more and changes nothing."""
    if denominator is None:
        denominator = svg.scale_denominator(svg_text) or 0.0
    roles = roles or {}
    if denominator < BUILD_UP_FROM:
        roles = {g: ROLE_BUILD_UP for g, r in roles.items() if r == ROLE_FORCED}
    else:
        roles = {g: (ROLE_BUILD_UP if r == ROLE_FORCED else r) for g, r in roles.items()}
    if not roles:
        return svg_text, 0, 0
    try:
        import shapely
        from shapely.ops import unary_union
    except ImportError:
        return svg_text, 0, 0
    elevation = "target-view-ELEVATIONVIEW" in svg_text   # the plinth line stays in elevations
    omit, parts = [], {}
    for head_start, head_end, content_end in svg.groups(svg_text):
        head = svg_text[head_start:head_end]
        names = svg.classes(head)
        if not names or not ({"cut", "projection"} & set(names)) or BUILD_UP_CLASS in names:
            continue
        guid = svg.global_id(head)
        role = roles.get(guid)
        if role is None:
            continue
        end = svg.group_end(svg_text, head_end, content_end)
        if role == ROLE_OMIT:
            if not elevation:
                omit.append((head_start, end))
        elif "cut" in names:
            parts.setdefault(guid, []).append(
                (head_start, end, _areas_of_group(svg_text[head_end:content_end]), role))
    core = [a for entries in parts.values() for _, _, areas, r in entries if r == ROLE_BUILD_UP for a in areas]
    core_union = unary_union(core) if core else None
    take, areas = [], []
    for guid, entries in parts.items():
        role = entries[0][3]
        own = [a for _, _, aa, _ in entries for a in aa]
        if role == ROLE_INSULATION:
            if core_union is None or not own or unary_union(own).distance(core_union) > BUILD_UP_GAP:
                continue
        take += [(a, e) for a, e, _, _ in entries]
        areas += own
    new_group = ""
    if areas:
        g = BUILD_UP_GAP
        united = unary_union([shapely.set_precision(a, 0.001) for a in areas])
        united = united.buffer(g, join_style=2).buffer(-g, join_style=2)
        new_group = ('<g class="cut %s"><path style="fill:white; fill-rule:evenodd; stroke:black; '
                     'stroke-width:%g" d="%s"/></g>' % (BUILD_UP_CLASS, BUILD_UP_STROKE, _ring_paths(united)))
    spans = []
    for a, e in sorted(set(omit + take)):
        if spans and a < spans[-1][1]:
            continue
        spans.append((a, e))
    if not spans:
        return svg_text, 0, 0
    insert_at = min(a for a, _ in take) if take else None
    text = svg_text
    for a, e in reversed(spans):
        text = text[:a] + ("\x00" if a == insert_at else "") + text[e:]
    return text.replace("\x00", new_group), len(omit), len(take)
