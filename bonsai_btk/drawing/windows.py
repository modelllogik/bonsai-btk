# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows and doors drawn fine, the glass as one line.

Bonsai builds the glass of a window 10 mm thick (ifcopenshell.api.geometry
add_window_representation, glass_thickness = 0.01). At 1:50 that gives two parallel
lines 0.2 mm apart, which together with 0.25 mm strokes print as one black bar.
Here every line of a window or door group gets the narrow weight, and each such
pair of lines becomes one line in the middle.

Text in, text out. No bpy here.
"""
import re

from . import hatching, outline, svg

WINDOW_STROKE = 0.13     # mm, narrow line weight
PANE_CLASS = "din-scheibe"  # the pane as one line; hatching.apply leaves it out
GLASS_THICKNESS_M = 0.01  # m, fixed in Bonsai

_RE_PATH_TAG = re.compile(r"<path\b[^>]*?/?>")
_RE_STYLE = re.compile(r'\bstyle="([^"]*)"')
_RE_SEGMENT = re.compile(r"^\s*M\s*(-?[\d.]+)[ ,](-?[\d.]+)\s*L\s*(-?[\d.]+)[ ,](-?[\d.]+)\s*$")


def _lines(pieces):
    """pieces: [(start, end, x1, y1, x2, y2)] -> [(axis, position, from, to, [piece index])].
    Axis-parallel pieces on one line that touch or overlap are joined."""
    raw = {}
    for i, (_, _, x1, y1, x2, y2) in enumerate(pieces):
        if abs(x1 - x2) < 1e-3:
            key = ("v", round(x1, 2))
            a, b = sorted((y1, y2))
        elif abs(y1 - y2) < 1e-3:
            key = ("h", round(y1, 2))
            a, b = sorted((x1, x2))
        else:
            continue
        raw.setdefault(key, []).append((a, b, i))
    result = []
    for key, intervals in raw.items():
        intervals.sort(key=lambda z: (z[0], z[1]))
        current = None
        for a, b, i in intervals:
            if current and a <= current[1] + 0.02:
                current[1] = max(current[1], b)
                current[2].append(i)
            else:
                if current:
                    result.append((key[0], key[1], current[0], current[1], current[2]))
                current = [a, b, [i]]
        if current:
            result.append((key[0], key[1], current[0], current[1], current[2]))
    return result


def fine(svg_text, denominator=None):
    """(text, panes as one line, window and door groups). A second run changes nothing."""
    if denominator is None:
        denominator = svg.scale_denominator(svg_text)
    glass = GLASS_THICKNESS_M * 1000.0 / float(denominator or 100)
    line_style = "fill:none; stroke:black; stroke-width:%g" % WINDOW_STROKE
    all_groups = svg.groups(svg_text)
    chosen = []
    for head_start, head_end, content_end in all_groups:
        names = set(svg.classes(svg_text[head_start:head_end]))
        if {"IfcWindow", "IfcDoor"} & names and {"cut", "projection"} & names:
            chosen.append((head_start, head_end, content_end))
    chosen = [c for c in chosen if not any(o[1] <= c[0] and c[2] <= o[2] and o != c for o in chosen)]
    own = [(a, e) for a, _, e in all_groups
           if re.search(r'class="(%s|%s)"' % (hatching.SIGN_CLASS, outline.OUTLINE_CLASS), svg_text[a:a + 120])]
    changes, panes = [], 0
    for _, head_end, content_end in chosen:
        pieces, paths = [], []
        for m in _RE_PATH_TAG.finditer(svg_text, head_end, content_end):
            if any(a <= m.start() < e for a, e in own):
                continue
            tag = m.group(0)
            st = _RE_STYLE.search(tag)
            if st and "stroke:none" in st.group(1).replace(" ", ""):
                continue
            paths.append((m.start(), m.end(), tag))
            dm = re.search(r'\bd="([^"]*)"', tag)
            s = _RE_SEGMENT.match(dm.group(1)) if dm else None
            if s and not (st and "stroke-width" in st.group(1)):
                pieces.append((m.start(), m.end()) + tuple(float(v) for v in s.groups()))
        lines = [ln for ln in _lines(pieces) if ln[3] - ln[2] > 3.0]
        gone, new = set(), []
        for i, a in enumerate(lines):
            for j, b in enumerate(lines):
                if j <= i or a[0] != b[0] or set(a[4]) & gone or set(b[4]) & gone:
                    continue
                if (abs(abs(a[1] - b[1]) - glass) < 0.03 and abs(a[2] - b[2]) < 0.1
                        and abs(a[3] - b[3]) < 0.1):
                    gone |= set(a[4]) | set(b[4])
                    mid, start, end = (a[1] + b[1]) / 2.0, max(a[2], b[2]), min(a[3], b[3])
                    points = (mid, start, mid, end) if a[0] == "v" else (start, mid, end, mid)
                    new.append('<path class="%s" style="%s" d="M%.4f,%.4f L%.4f,%.4f"/>'
                               % ((PANE_CLASS, line_style) + points))
                    panes += 1
        gone_spans = {(pieces[i][0], pieces[i][1]) for i in gone}
        for start, end, tag in paths:
            if (start, end) in gone_spans:
                # kept but not drawn: the hatching used these edges for the outline of
                # the frame, and a second run must find them again
                st = _RE_STYLE.search(tag)
                if st:
                    hidden = tag.replace(st.group(0), 'style="%s; stroke:none"' % st.group(1).rstrip("; "))
                else:
                    hidden = tag.replace("<path", '<path style="stroke:none"', 1)
                changes.append((start, end, hidden))
                continue
            st = _RE_STYLE.search(tag)
            if st and "stroke-width" in st.group(1):
                continue
            if st:
                replacement = tag.replace(st.group(0), 'style="%s; stroke-width:%g"'
                                          % (st.group(1).rstrip("; "), WINDOW_STROKE))
            else:
                replacement = tag.replace("<path", '<path style="stroke-width:%g"' % WINDOW_STROKE, 1)
            changes.append((start, end, replacement))
        if new:
            changes.append((content_end, content_end, "".join(new)))
    text = svg_text
    for start, end, replacement in sorted(changes, key=lambda z: (-z[0], -z[1])):
        text = text[:start] + replacement + text[end:]
    return text, panes, len(chosen)
