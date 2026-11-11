# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Roof outline, ridge and beams above the cut, dotted in plan.

After DIN 1356-1 edges above the cut plane are drawn dotted. In a floor plan that
is the roof of the storey above (outline with the overhang, all slabs of one roof
united, and the ridge), roofs of the own storey entirely above the cut (a carport),
and downstand and upstand beams. Which ones and where comes from plan.roofs.

Text in, text out. No bpy.
"""
from . import svg

STROKE = 0.35            # mm; with round caps the dots are about 0.55 mm
DOTS = "0.2, 1.0"        # mm
GROUP_ID = "btk-dach"


def group(outlines, ridges):
    """The SVG group: outlines (rings of sheet points) and ridges (segments), dotted."""
    d = []
    for ring in outlines:
        d.append("M" + " L".join("%.4f,%.4f" % tuple(p) for p in ring) + " Z")
    for a, b in ridges:
        d.append("M%.4f,%.4f L%.4f,%.4f" % (a[0], a[1], b[0], b[1]))
    if not d:
        return ""
    style = "fill:none;stroke:black;stroke-width:%g;stroke-linecap:round;stroke-dasharray:%s" % (STROKE, DOTS)
    return ('<g id="%s" class="btk-dach" style="fill:none">\n<path style="%s" d="%s"/>\n</g>'
            % (GROUP_ID, style, " ".join(d)))


def insert(svg_text, group_text):
    """Our group from an earlier run out, the new one (if any) before </svg>."""
    spans = svg.outer_groups(svg_text, lambda h: 'id="%s"' % GROUP_ID in h)
    # with the newline insert() put after it
    spans = [(a, e + 1) if svg_text[e:e + 1] == "\n" else (a, e) for a, e in spans]
    text = svg.remove_spans(svg_text, spans)
    if not group_text:
        return text
    k = text.rfind("</svg>")
    return text[:k] + group_text + "\n" + text[k:]


def apply(svg_text, roofs):
    """(text, report). roofs from plan.roofs (None: nothing to draw)."""
    if not roofs:
        return insert(svg_text, ""), []
    return insert(svg_text, group(roofs["outlines"], roofs["ridges"])), [roofs["message"]]
