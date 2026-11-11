# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stairs in plan after DIN 1356-1.

Bonsai offers a walking line as a manual annotation (STAIR_ARROW: circle, arrow,
the fixed text "UP"); the flight itself is drawn as a cut slab. Here, in every
plan, Bonsai's groups of each IfcStairFlight are replaced by a group computed from
the model (plan.flights). The rule follows the cut plane of the plan, not the flight:

- nosings and flight edges as seen edges (0.25); steps below the cut plane drawn,
  above it dashed (ground floor: the lower part drawn; upper floor: the whole flight
  below, seen from above, drawn)
- where the flight is cut: an inclined cut line at the first step above the cut
  plane, drawn twice 5 cm apart; between the two lines the flight stays empty
- the walking line (narrow) on the middle of the flight: a circle at the start, an
  arrow at the end, the arrow always pointing up; dashed above the cut line
- the note "17 Stg. 17,65/26" (risers, rise/going in cm) only where the flight starts
  (at most 2 m below the cut plane), beside the flight on the side with fewer lines
- no step numbers

Straight flights. Text in, text out; the flight data come from plan.flights. No bpy.
"""
import math
import re
from xml.sax.saxutils import quoteattr

from . import svg

EDGE = 0.25              # mm, seen edges (as .projection)
NARROW = 0.13            # mm, walking line
DASH = "2, 1"            # mm
CIRCLE_R = 1.0           # mm, circle at the start
ARROW_LENGTH = 2.5       # mm
ARROW_HALF_WIDTH = 1.0   # mm
TEXT_SIZE = 3.49         # px = mm on the sheet, 2.5 mm cap height
CUT_STEPS = 2.0          # the cut line spans this many goings along the flight
CUT_DOUBLE = 0.05        # m, distance of the second cut line
NOTE_GAP = 2.0           # mm between the flight edge and the middle of the text, plus half its height

GROUP_CLASS = "btk-treppe"
NOTE_CLASS = "btk-treppe-angabe"

_RE_NUMBER_PAIR = re.compile(r"(-?\d+(?:\.\d+)?)[ ,](-?\d+(?:\.\d+)?)")


def cut(flight):
    """(u, span) of the inclined cut line, or None if the flight is not cut. The cut
    plane is z = 0."""
    above = [t for t in flight["treads"] if t[0] > 0]
    below = [t for t in flight["treads"] if t[0] <= 0]
    if not above or not below:
        return None
    u = above[0][1]
    span = min(CUT_STEPS * flight["going"], max(flight["end_u"] - u, 1e-3))
    return u, span


def _split(a, b, border):
    """Split segment a-b (uv) at the cut line border(v) -> u. (below, above)."""
    def f(p):
        return p[0] - border(p[1])
    fa, fb = f(a), f(b)
    if fa <= 0 and fb <= 0:
        return [(a, b)], []
    if fa >= 0 and fb >= 0:
        return [], [(a, b)]
    t = fa / (fa - fb)
    m = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return ([(a, m)], [(m, b)]) if fa < 0 else ([(m, b)], [(a, m)])


def lines(flight):
    """Segments in uv: dict(drawn, dashed, walk_drawn, walk_dashed, cut)."""
    vmin, vmax = flight["vmin"], flight["vmax"]
    c = cut(flight)
    if c is None:
        all_above = all(t[0] > 0 for t in flight["treads"])

        def border(v):
            return -1e9 if all_above else 1e9
    else:
        u_cut, span = c

        def border(v):
            return u_cut + span * (v - vmin) / (vmax - vmin)
    edges = [((t[1], vmin), (t[1], vmax)) for t in flight["treads"]]
    edges.append(((flight["end_u"], vmin), (flight["end_u"], vmax)))
    edges.append(((flight["start_u"], vmin), (flight["end_u"], vmin)))
    edges.append(((flight["start_u"], vmax), (flight["end_u"], vmax)))
    gap = CUT_DOUBLE if c is not None else 0.0

    def border2(v):
        return border(v) + gap

    def divide(a, b):
        """Drawn below the first line, dashed above the second, free between."""
        under, rest = _split(a, b, border)
        over = []
        for p, q in rest:
            _, oo = _split(p, q, border2)
            over += oo
        return under, over
    drawn, dashed = [], []
    for a, b in edges:
        u, o = divide(a, b)
        drawn += u
        dashed += o
    vm = (vmin + vmax) / 2
    walk_drawn, walk_dashed = divide((flight["start_u"], vm), (flight["end_u"], vm))
    cut_lines = None
    if c is not None:
        cut_lines = [((c[0], vmin), (c[0] + c[1], vmax)),
                     ((c[0] + gap, vmin), (c[0] + c[1] + gap, vmax))]
    return dict(drawn=drawn, dashed=dashed, walk_drawn=walk_drawn, walk_dashed=walk_dashed, cut=cut_lines)


def _to_sheet(flight, width, height, sk):
    def f(p):
        x = flight["o"][0] + p[0] * flight["eu"][0] + p[1] * flight["ev"][0]
        y = flight["o"][1] + p[0] * flight["eu"][1] + p[1] * flight["ev"][1]
        return ((width / 2 + x) * sk, (height / 2 - y) * sk)
    return f


def _d(segments, f):
    parts = []
    for a, b in segments:
        pa, pb = f(a), f(b)
        parts.append("M%.4f,%.4f L%.4f,%.4f" % (pa[0], pa[1], pb[0], pb[1]))
    return " ".join(parts)


def occupied_points(svg_text, step=0.5):
    """Points (mm) of all paths of the drawing, long segments sampled every step mm."""
    points = []
    for d in re.findall(r'\sd="([^"]+)"', svg_text):
        pairs = [(float(a), float(b)) for a, b in _RE_NUMBER_PAIR.findall(d)]
        for i, p in enumerate(pairs):
            points.append(p)
            if i and "L" in d:
                q = pairs[i - 1]
                n = int(math.hypot(p[0] - q[0], p[1] - q[1]) / step)
                for k in range(1, n):
                    t = k / n
                    points.append((q[0] + t * (p[0] - q[0]), q[1] + t * (p[1] - q[1])))
    return points


def note_position(flight, f, sk, um, text, occupied):
    """Middle of the note (sheet mm) beside the flight, on the side where fewer drawn
    points fall into the text box."""
    length_m = 0.55 * TEXT_SIZE * len(text) / sk
    height_m = 1.2 * TEXT_SIZE / sk
    offset = (NOTE_GAP + 0.6 * TEXT_SIZE) / sk
    best = None
    for side, edge in ((1, flight["vmax"]), (-1, flight["vmin"])):
        v = edge + side * offset
        corners = [f((um + du * length_m / 2, v + dv * height_m / 2))
                   for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        x0, x1 = min(c[0] for c in corners), max(c[0] for c in corners)
        y0, y1 = min(c[1] for c in corners), max(c[1] for c in corners)
        n = sum(1 for x, y in occupied if x0 <= x <= x1 and y0 <= y <= y1)
        if best is None or n < best[0]:
            best = (n, f((um, v)))
    return best[1]


def group(guid, name, flight, width, height, sk, note=None, occupied=None):
    """The SVG group of one flight."""
    f = _to_sheet(flight, width, height, sk)
    li = lines(flight)
    parts = ['<g id="%s-%s" class="%s" ifc:guid="%s" ifc:name=%s style="fill:none">'
             % (GROUP_CLASS, guid, GROUP_CLASS, guid, quoteattr(name))]

    def path(segments, stroke, dash=None):
        if not segments:
            return
        style = "fill:none;stroke:black;stroke-width:%g;stroke-linecap:butt" % stroke
        if dash:
            style += ";stroke-dasharray:%s" % dash
        parts.append('<path style="%s" d="%s"/>' % (style, _d(segments, f)))
    path(li["drawn"], EDGE)
    path(li["dashed"], EDGE, DASH)
    if li["cut"]:
        path(li["cut"], EDGE)
    vm = (flight["vmin"] + flight["vmax"]) / 2
    centre = f((flight["start_u"], vm))
    r_m = CIRCLE_R / sk
    walk = [((max(a[0], flight["start_u"] + r_m), a[1]), b) for a, b in li["walk_drawn"]
            if b[0] > flight["start_u"] + r_m]
    path(walk, NARROW)
    path(li["walk_dashed"], NARROW, DASH)
    parts.append('<circle cx="%.4f" cy="%.4f" r="%g" style="fill:none;stroke:black;stroke-width:%g"/>'
                 % (centre[0], centre[1], CIRCLE_R, NARROW))
    tip = (flight["end_u"], vm)
    al, aw = ARROW_LENGTH / sk, ARROW_HALF_WIDTH / sk
    path([((tip[0] - al, vm + aw), tip), (tip, (tip[0] - al, vm - aw))], NARROW)
    if note:
        end = flight["end_u"] if li["cut"] is None else li["cut"][0][0][0]
        um = (flight["start_u"] + end) / 2
        p0, p1 = f((um, vm)), f((um + 1.0, vm))
        w = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        if w >= 90 or w < -90:           # readable from below or from the right
            w -= 180 if w > 0 else -180
        q = note_position(flight, f, sk, um, note, occupied or [])
        parts.append('<text x="%.4f" y="%.4f" transform="rotate(%.3f %.4f %.4f)" '
                     'style="font-size:%gpx;text-anchor:middle;dominant-baseline:middle" class="%s">%s</text>'
                     % (q[0], q[1], w, q[0], q[1], TEXT_SIZE, NOTE_CLASS, note))
    parts.append("</g>")
    return "\n".join(parts)


def replace(svg_text, new_groups):
    """(text, number removed). Bonsai's groups of the flights (and our own from an
    earlier run) out, the new groups before </svg>. new_groups: {GlobalId: text}."""
    def remove(head):
        if 'class="%s"' % GROUP_CLASS in head:
            return True
        if "IfcStairFlight" not in head:
            return False
        if "guid" not in head:          # joint outline (outline.merge_joints) has no GlobalId
            return True
        return any(g in head for g in new_groups)
    spans = svg.outer_groups(svg_text, remove)
    # our own groups go with the newline replace() put after each of them
    spans = [(a, e + 1) if 'class="%s"' % GROUP_CLASS in svg_text[a:a + 200] and svg_text[e:e + 1] == "\n"
             else (a, e) for a, e in spans]
    text = svg.remove_spans(svg_text, spans)
    k = text.rfind("</svg>")
    return text[:k] + "\n".join(new_groups.values()) + "\n" + text[k:], len(spans)


def apply(svg_text, flights, frame):
    """(text, report). flights from plan.flights, frame = dict(width, height, scale)."""
    if not flights:
        return svg_text, []
    width, height, sk = frame["width"], frame["height"], frame["scale"]
    without, _ = replace(svg_text, {f["guid"]: "" for f in flights})
    occupied = occupied_points(without)
    new, report = {}, []
    for item in flights:
        flight = item["flight"]
        new[item["guid"]] = group(item["guid"], item["name"], flight, width, height, sk, item["note"], occupied)
        c = cut(flight)
        if c:
            where = "cut at step %d" % (1 + [t[1] for t in flight["treads"]].index(c[0]))
        else:
            where = "entirely below the cut plane" if flight["treads"][-1][0] <= 0 else "entirely above"
        report.append("%s: %d steps, %s%s" % (item["name"] or item["guid"], len(flight["treads"]), where,
                                              ", note " + item["note"] if item["note"] else ""))
    text, removed = replace(svg_text, new)
    report.append("%d group(s) of Bonsai replaced" % removed)
    return text, report
