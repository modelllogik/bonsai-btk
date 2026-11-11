# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hatching as real lines, turned with the element.

Bonsai fills a cut area with an SVG pattern that is fixed to the sheet. Two things
go wrong with that on paper:

1. **The hatching does not follow the element.** On an inclined wall it runs across
   the wall. Here the angle of each cut area is taken from its longest edge and the
   hatching turned with it::

       target angle = base angle of the pattern + (element angle mod 90) + extra

   "mod 90" leaves horizontal and vertical elements as they were. A pattern can say
   otherwise (``data-din-bezug``, see style.py), and the extra angle comes from the
   model (``EPset_BTK_Hatching.Rotation``, button *Rotate Hatching*).
2. **A pattern fill is rasterised when printed.** A PDF tiling pattern is rendered
   once and repeated: the rounding of a 0.10 mm line repeats in every tile, and the
   diagonal restarts at each tile border. Line patterns are therefore written as real
   paths, clipped to the cut area. The lines are read from the <pattern> itself, so
   the pattern stays the one source, also for the legend. Dot patterns (gravel,
   plaster) do not suffer from tiling and stay a pattern fill, turned as a copy.

Instead of an area pattern a category can have a sign per section: a diagonal cross
for timber (only for short sections, not in windows and doors) or a band on the
middle of a waterproofing layer.

Elements without a layer set (columns, beams, railings) get no category class from
Bonsai. add_categories() adds it from the model, together with the class Bonsai
writes for ``EPset_Drawing.Metadata = material.Category``; in din.css that class
fills steel and metal profiles black (rule 4b), while a steel layer stays outlined.

Text in, text out. No bpy here.
"""
import hashlib
import math
import re

from . import outline, style, svg

TURN = 180.0               # a line pattern repeats after 180 degrees
ELEMENT_MOD = 90.0         # horizontal and vertical elements stay as they are

SIGN_CLASS = "din-zeichen"     # group of a drawn sign (cross, band)
LINES_CLASS = "din-schraffur"  # group of real hatching lines

CROSS_STROKE = 0.10        # mm on paper, as fine as the hatching
CROSS_RATIO = 4.0          # a cross only on short sections: length at most 4 x thickness
NO_CROSS = ("IfcWindow", "IfcDoor")   # frames and sashes are too small for a cross
BAND_WIDTH = 0.7           # mm, width of the waterproofing band
BAND_DASH = 3.0            # mm
BAND_GAP = 1.5             # mm
BAND_EDGE = 0.10           # mm, the two fine lines at the edges of the band

MATERIAL_CATEGORY_CLASS = "materialCategory-"   # as Bonsai writes it from EPset_Drawing.Metadata

_RE_PATH_D = re.compile(r'<path\b[^>]*\bd="([^"]*)"')
_RE_SIGN_GROUP = re.compile(r'<g class="%s"[^>]*>.*?</g>' % SIGN_CLASS, re.S)
_RE_LINES_GROUP = re.compile(r'<g class="%s"[^>]*>.*?</g>' % LINES_CLASS, re.S)
_RE_OUTLINE_GROUP = re.compile(r'<g class="%s"[^>]*>.*?</g>' % outline.OUTLINE_CLASS, re.S)
_RE_CLIP_ID = re.compile(r'<clipPath\b[^>]*\bid="([^"]+)"')
# the pane line of windows.fine lies in the cut group of a window or door; it is no
# edge of the area (windows.PANE_CLASS, not imported to keep the modules independent)
_RE_PANE_PATH = re.compile(r'<path class="din-scheibe"[^>]*/>')


# ------------------------------------------------------------------ angles

def target_angle(base, element_angle, reference, extra):
    """Angle of the hatching in degrees, 0 to under 180.

    base           base angle of the pattern (None = 0)
    element_angle  angle of the cut area
    reference      data-din-bezug: "bauteil" = full element angle, "blatt" = fixed to
                   the sheet, otherwise element angle mod 90
    extra          EPset_BTK_Hatching.Rotation; it also acts on "blatt", as an explicit
                   choice on the element
    """
    b = 0.0 if base is None else base
    if reference == style.REFERENCE_SHEET:
        share = 0.0
    else:
        share = element_angle % (TURN if reference == style.REFERENCE_ELEMENT else ELEMENT_MOD)
    return (b + share + extra) % TURN


def pattern_copy_id(base_id, angle):
    return "%s-w%s" % (base_id, ("%g" % round(angle, 1)).replace(".", "p").replace("-", "m"))


def turned_pattern(text, new_id, angle):
    """A copy of a <pattern> with a new id and patternTransform rotate(angle)."""
    end = text.find(">") + 1
    head, rest = text[:end], text[end:]
    head = re.sub(r'\bid="[^"]*"', 'id="%s"' % new_id, head, count=1)
    transform = 'patternTransform="rotate(%g 0 0)"' % round(angle, 1)
    if 'patternTransform="' in head:
        head = re.sub(r'patternTransform="[^"]*"', transform, head, count=1)
    else:
        head = head[:-1].rstrip() + " " + transform + ">"
    return head + rest


# ------------------------------------------------------------------ lines

def _line_style(family, offset=None):
    text = ("fill:none; stroke:%s; stroke-width:%g; stroke-linecap:butt" % (family.colour, family.width))
    if family.length < family.period - 1e-9:
        text += "; stroke-dasharray:%g %g" % (family.length, family.period - family.length)
        if offset:
            text += "; stroke-dashoffset:%g" % offset
    return text


def _to_pattern(points, c, s):
    return [(x * c + y * s, -x * s + y * c) for x, y in points]


def _family_lines(family, x0, x1, y0, y1):
    """Start and end points of the lines of one family in pattern coordinates. Along
    the line every line starts on a dash start, so all lines of a family share one
    path and one dash offset."""
    if family.axis == "v":
        umin, umax, vmin, vmax = x0, x1, y0, y1
    else:
        umin, umax, vmin, vmax = y0, y1, x0, x1
    spacing, period = family.spacing, family.period
    va = family.start + math.floor((vmin - family.start) / period) * period
    ve = family.start + math.ceil((vmax - family.start) / period) * period
    if ve <= va:
        ve = va + period
    result = []
    k = int(math.floor((umin - family.offset) / spacing))
    k_end = int(math.ceil((umax - family.offset) / spacing))
    while k <= k_end:
        u = family.offset + k * spacing
        result.append(((u, va), (u, ve)) if family.axis == "v" else ((va, u), (ve, u)))
        k += 1
    return result


def line_paths(families, angle, points):
    """<path> elements with the lines of a pattern over a point cloud, on the sheet.
    The grid sits at the origin of the drawing like a <pattern>, so the lines run on
    across the pieces of a wall split by openings."""
    if not points:
        return []
    r = math.radians(angle)
    c, s = math.cos(r), math.sin(r)
    local = _to_pattern(points, c, s)
    xs = [p[0] for p in local]
    ys = [p[1] for p in local]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    result = []
    for family in families:
        pieces = []
        for a, e in _family_lines(family, x0, x1, y0, y1):
            pieces.append("M%.4f,%.4f L%.4f,%.4f" % (a[0] * c - a[1] * s, a[0] * s + a[1] * c,
                                                    e[0] * c - e[1] * s, e[0] * s + e[1] * c))
        if pieces:
            result.append('<path d="%s" style="%s"/>' % (" ".join(pieces), _line_style(family)))
    return result


def _clip_segment(a, e, x, y, w, h):
    """Liang-Barsky: (t0, t1) of the piece from a to e inside the rectangle, or None."""
    dx, dy = e[0] - a[0], e[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x), (dx, x + w - a[0]), (-dy, a[1] - y), (dy, y + h - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return None
            if r < t1:
                t1 = r
    return None if t1 - t0 < 1e-9 else (t0, t1)


def lines_in_rectangle(families, angle, x, y, w, h):
    """The same lines clipped by computation to an axis-parallel rectangle, with the
    dash offset per line: for the legend box, where no clipPath is wanted."""
    r = math.radians(angle)
    c, s = math.cos(r), math.sin(r)
    local = _to_pattern([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], c, s)
    xs = [p[0] for p in local]
    ys = [p[1] for p in local]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    result = []
    for family in families:
        full = []
        for a, e in _family_lines(family, x0, x1, y0, y1):
            pa = (a[0] * c - a[1] * s, a[0] * s + a[1] * c)
            pe = (e[0] * c - e[1] * s, e[0] * s + e[1] * c)
            t = _clip_segment(pa, pe, x, y, w, h)
            if t is None:
                continue
            t0, t1 = t
            length = math.hypot(pe[0] - pa[0], pe[1] - pa[1])
            qa = (pa[0] + (pe[0] - pa[0]) * t0, pa[1] + (pe[1] - pa[1]) * t0)
            qe = (pa[0] + (pe[0] - pa[0]) * t1, pa[1] + (pe[1] - pa[1]) * t1)
            path = "M%.4f,%.4f L%.4f,%.4f" % (qa[0], qa[1], qe[0], qe[1])
            if family.length < family.period - 1e-9:
                result.append('<path d="%s" style="%s" />'
                              % (path, _line_style(family, (t0 * length) % family.period)))
            else:
                full.append(path)
        if full:
            result.append('<path d="%s" style="%s" />' % (" ".join(full), _line_style(family)))
    return result


def _clip_key(paths):
    """Stable id part from the geometry: same area, same clip id, nothing doubled."""
    return hashlib.sha1("|".join(paths).encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ signs

def _element_rectangle(points, angle):
    """Corners of the bounding rectangle aligned with the element, with length (along
    the element) and thickness."""
    r = math.radians(angle)
    c, s = math.cos(r), math.sin(r)
    turned = [(x * c + y * s, -x * s + y * c) for x, y in points]
    xs = [p[0] for p in turned]
    ys = [p[1] for p in turned]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    back = [(x * c - y * s, x * s + y * c) for x, y in corners]
    return back, x1 - x0, y1 - y0


def _fills_rectangle(points, length, thickness):
    """Does the area fill its element rectangle (within 1 %)? Then the sign needs no
    clip. The area is compared, not the number of points: Bonsai puts extra points
    where other edges join."""
    target = length * thickness
    if target <= 0:
        return False
    return abs(outline.area(points) - target) <= 0.01 * target


def _centre_line(points, angle):
    corners, length, thickness = _element_rectangle(points, angle)
    p0, p1, p2, p3 = corners
    a = ((p0[0] + p3[0]) / 2.0, (p0[1] + p3[1]) / 2.0)
    e = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    return a, e, length, thickness


def _offset_lines(points, angle, v):
    a, e, _, _ = _centre_line(points, angle)
    length = math.hypot(e[0] - a[0], e[1] - a[1])
    if length < 1e-9:
        return []
    nx, ny = -(e[1] - a[1]) / length, (e[0] - a[0]) / length
    return [outline.d([(a[0] + nx * s, a[1] + ny * s), (e[0] + nx * s, e[1] + ny * s)]) for s in (+v, -v)]


def sign_group(sign, polylines, angle, clip_id, force_clip=False):
    """(group text, clip needed, number of areas too long for a cross). The group is
    empty if there is nothing to draw. force_clip: for an element with a hole, so
    the sign does not run across the hole."""
    pieces, clip_lines, skipped = [], [], 0
    for points in polylines:
        if sign == style.SIGN_CROSS:
            corners, length, thickness = _element_rectangle(points, angle)
            if min(length, thickness) < 0.05:
                continue
            if length > CROSS_RATIO * thickness:
                skipped += 1
                continue
            p0, p1, p2, p3 = corners
            for path in (outline.d([p0, p2]), outline.d([p1, p3])):
                pieces.append('<path d="%s" style="fill:none; stroke:black; stroke-width:%g"/>'
                              % (path, CROSS_STROKE))
        elif sign == style.SIGN_CENTRE_LINE:
            a, e, length, thickness = _centre_line(points, angle)
            if length < 0.05:
                continue
            path = outline.d([a, e])
            # A white ground in the full band width first: the band replaces what lies
            # in its strip; otherwise neighbouring layer lines show in the gaps.
            pieces.append('<path d="%s" style="fill:none; stroke:white; stroke-width:%g; '
                          'stroke-linecap:butt"/>' % (path, BAND_WIDTH))
            for edge in _offset_lines(points, angle, (BAND_WIDTH - BAND_EDGE) / 2.0):
                pieces.append('<path d="%s" style="fill:none; stroke:black; stroke-width:%g; '
                              'stroke-linecap:butt"/>' % (edge, BAND_EDGE))
            pieces.append('<path d="%s" style="fill:none; stroke:black; stroke-width:%g; '
                          'stroke-linecap:butt; stroke-dasharray:%g %g"/>'
                          % (path, BAND_WIDTH, BAND_DASH, BAND_GAP))
        else:
            continue
        if not _fills_rectangle(points, length, thickness):
            clip_lines.append(points)
    if not pieces:
        return "", False, skipped
    clip = bool(clip_lines) or force_clip
    clip_style = ' style="clip-path:url(#%s)"' % clip_id if clip else ""
    return '<g class="%s"%s>%s</g>' % (SIGN_CLASS, clip_style, "".join(pieces)), clip, skipped


# ------------------------------------------------------------------ categories from the model

def add_categories(svg_text, categories, material_category_class=True):
    """(text, number). Add the category class to cut groups without a layer set.

    Bonsai writes layer-material-category-X only per layer, so columns, beams and
    profiles stay without hatching and line weight. categories = {GlobalId: category}
    from the model. With material_category_class the class materialCategory-X is
    added as well, the class Bonsai writes for EPset_Drawing.Metadata =
    material.Category; din.css fills steel and metal profiles black through it.
    A group that has a category already is left alone."""
    if not categories:
        return svg_text, 0
    changes = []
    for head_start, head_end, _ in svg.groups(svg_text):
        head = svg_text[head_start:head_end]
        names = svg.classes(head)
        if "cut" not in names or any(n.startswith(style.CATEGORY_CLASS) for n in names):
            continue
        guid = None
        for n in names:
            if svg.is_global_id(n):
                guid = n
        if guid is None:
            ids = svg.global_ids(head)
            guid = ids[0] if ids else None
        if guid is None or guid not in categories:
            continue
        category = svg.canonical_class(categories[guid])
        if not category:
            continue
        new = svg.add_class(head, style.CATEGORY_CLASS + category)
        if material_category_class:
            new = svg.add_class(new, MATERIAL_CATEGORY_CLASS + category)
        changes.append((head_start, head_end, new))
    return svg.replace_spans(svg_text, changes), len(changes)


# ------------------------------------------------------------------ the step

def apply(svg_text, rotations=None, categories=None, material_category_class=True):
    """(text, report). Hatching, signs and pattern copies for every cut group with a
    category; then structural layers last.

    rotations   {GlobalId: degrees} from EPset_BTK_Hatching.Rotation
    categories  {GlobalId: category} for elements without a layer set
    """
    rotations = rotations or {}
    report = []
    svg_text, added = add_categories(svg_text, categories or {}, material_category_class)
    if added:
        report.append("%d group(s) without layers: category added" % added)
    css = svg.style_text(svg_text) or svg_text
    category_patterns = style.category_patterns(css)
    patterns = style.read_patterns(svg_text)
    existing_ids = set(_RE_CLIP_ID.findall(svg_text))
    families_of = {}
    new_patterns, new_clips, changes = {}, {}, []
    signs = lines = turned = 0

    for head_start, head_end, content_end in svg.groups(svg_text):
        head = svg_text[head_start:head_end]
        names = svg.classes(head)
        if "cut" not in names:
            continue
        category, guid = None, None
        for n in names:
            if n.startswith(style.CATEGORY_CLASS):
                category = n[len(style.CATEGORY_CLASS):]
            elif svg.is_global_id(n):
                guid = n
        if guid is None:
            ids = svg.global_ids(head)
            guid = ids[0] if ids else None
        if not category:
            continue
        content = svg_text[head_end:content_end]
        # our own groups out: they would change the element angle on a second run
        clean = _RE_OUTLINE_GROUP.sub("", _RE_LINES_GROUP.sub("", _RE_SIGN_GROUP.sub("", content)))
        panes = "".join(_RE_PANE_PATH.findall(clean))   # stay at the end, as windows.fine put them
        clean = _RE_PANE_PATH.sub("", clean)
        paths = _RE_PATH_D.findall(clean)

        ring_group, clip_paths, holes = "", paths, 0
        raw = [p for path in paths for p in svg.subpaths(path)]
        if paths and not outline.has_ring(raw):
            rings, ring_report = outline.rings_from_edges(raw)
            if rings:
                areas, hole_rings = outline.sort_rings(rings)
                holes = len(hole_rings)
                ordered = outline.orient_rings(areas, hole_rings)
                ring_group = outline.outline_group(ordered)
                # ONE clip path with all rings: several paths in a clipPath are united
                clip_paths = [" ".join(outline.d(r) for r in ordered)]
                paths = [outline.d(r) for r in areas] or clip_paths
                report.append("%s %s: %s%s" % (category, guid, "; ".join(ring_report),
                                               ", %d hole(s)" % holes if holes else ""))
        clip_rule = ' style="clip-rule:evenodd"' if ring_group else ""

        pid = category_patterns.get(category)
        if not pid or pid not in patterns:
            # a flat fill from the style (steel, insulation) only needs an area
            if ring_group and ring_group + clean + panes != content:
                changes.append((head_end, content_end, ring_group + clean + panes))
            continue
        pattern = patterns[pid]
        angle = svg.longest_edge_angle(paths)
        if angle is None:
            continue
        extra = float(rotations.get(guid, 0.0))

        if pattern.sign == style.SIGN_CROSS and set(NO_CROSS) & set(names):
            if ring_group + clean + panes != content:
                changes.append((head_end, content_end, ring_group + clean + panes))
            report.append("%s %s: no timber cross in windows and doors" % (category, guid))
            continue
        if pattern.sign:
            polylines = [p for path in paths for p in svg.subpaths(path)]
            clip_id = "%s-clip-%s" % (SIGN_CLASS, _clip_key(clip_paths))
            group, clip, too_long = sign_group(pattern.sign, polylines, angle, clip_id, force_clip=bool(holes))
            new_content = ring_group + clean + group + panes
            if new_content != content:
                changes.append((head_end, content_end, new_content))
            if clip and clip_id not in existing_ids and clip_id not in new_clips:
                new_clips[clip_id] = '<clipPath id="%s">%s</clipPath>' % (
                    clip_id, "".join('<path d="%s"%s/>' % (p, clip_rule) for p in clip_paths))
            if group:
                signs += 1
                report.append("%s %s: %s, element %.1f degrees%s%s"
                              % (category, guid, pattern.sign, angle, " with clip" if clip else "",
                                 ", %d area(s) too long" % too_long if too_long else ""))
            else:
                report.append("%s %s: no %s, area longer than %g x thickness"
                              % (category, guid, pattern.sign, CROSS_RATIO))
            continue

        if pid not in families_of:
            families_of[pid] = style.line_families(pattern.text)
        families = families_of[pid]

        if families is not None:
            line_families, background = families
            target = target_angle(pattern.base_angle, angle, pattern.reference, extra)
            points = [p for path in paths for line in svg.subpaths(path) for p in line]
            pieces = line_paths(line_families, target, points)
            clip_id = "%s-clip-%s" % (LINES_CLASS, _clip_key(clip_paths))
            group = ('<g class="%s" style="clip-path:url(#%s)">%s</g>'
                     % (LINES_CLASS, clip_id, "".join(pieces))) if pieces else ""
            new_content = ring_group + clean + group + panes   # ON TOP of the area
            if new_content != content:
                changes.append((head_end, content_end, new_content))
            # cut area opaque white: edges of the view below must not show through,
            # such as the joint of two walls of the same material
            new_head = svg.set_style(head, "fill", background or "white")
            if new_head != head:
                changes.append((head_start, head_end, new_head))
            if pieces and clip_id not in existing_ids and clip_id not in new_clips:
                new_clips[clip_id] = '<clipPath id="%s">%s</clipPath>' % (
                    clip_id, "".join('<path d="%s"%s/>' % (p, clip_rule) for p in clip_paths))
            if pieces:
                lines += 1
            report.append("%s %s: element %.1f degrees, extra %g, %d line family(ies) at %g degrees, %d lines"
                          % (category, guid, angle, extra, len(pieces), round(target, 1),
                             sum(x.count("M") for x in pieces)))
            continue

        if pattern.base_angle is None:        # dot pattern or flat fill: not turned
            if ring_group and ring_group + clean + panes != content:
                changes.append((head_end, content_end, ring_group + clean + panes))
            continue
        target = target_angle(pattern.base_angle, angle, pattern.reference, extra)
        if ring_group and ring_group + clean + panes != content:
            changes.append((head_end, content_end, ring_group + clean + panes))
        if abs(target - (pattern.base_angle % TURN)) < 0.05:
            continue
        nid = pattern_copy_id(pid, target)
        if nid not in new_patterns and nid not in patterns:
            new_patterns[nid] = turned_pattern(pattern.text, nid, target)
        new_head = svg.set_style(head, "fill", "url(#%s)" % nid)
        if new_head != head:
            changes.append((head_start, head_end, new_head))
            turned += 1

    text = svg.replace_spans(svg_text, changes)
    extra_defs = list(new_patterns.values()) + list(new_clips.values())
    if extra_defs:
        i = text.find("<defs>")
        if i < 0:
            report.append("no <defs> found, nothing changed")
            return svg_text, report
        i += len("<defs>")
        text = text[:i] + "\n" + "\n".join(extra_defs) + text[i:]
    text, reordered = outline.structural_last(text)
    if reordered:
        report.append("%d run(s) reordered: structural layers and bands last" % reordered)
    report.append("%d area(s) with real lines, %d with a turned pattern, %d pattern copies, %d signs, %d clips"
                  % (lines, turned, len(new_patterns), signs, len(new_clips)))
    return text, report
