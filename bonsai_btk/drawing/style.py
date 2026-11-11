# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading the drawing style: hatch patterns, material categories, line weights.

The style is the one source. The post-processing keeps no list of categories,
patterns or line weights of its own; it reads them from the CSS and the patterns
embedded in each drawing. Whoever adds a category to the style (one line in
din.css of native-ifc-template, perhaps a pattern in din-patterns.svg) gets
hatching, drawing order and legend without touching this code.

What is read:

- **Patterns** (``<pattern id="din-…">``): the base angle from patternTransform and
  two data attributes on the pattern itself. Their values are part of the published
  style format and stay as they are:

  ``data-din-bezug="bauteil"``
      turn fully with the element (wood-based panels: lines across the panel)
  ``data-din-bezug="blatt"``
      do not turn with the element (soil, which has no direction)
  ``data-din-zeichen="kreuz"``
      a diagonal cross per section instead of an area pattern (timber)
  ``data-din-zeichen="mittellinie"``
      a band drawn on the middle of the layer (waterproofing)

- **Category rules**: ``.cut.layer-material-category-X { fill: url(#…);
  stroke-width: … }``. Bonsai writes the category of a layer material as that
  class (IfcMaterial.Category, letters and digits only).
- **Base rule** for layers: ``.cut.IfcMaterialLayer { stroke-width: … }``.
  Categories drawn heavier than the base rule are structural (masonry, concrete,
  timber, steel); they are drawn last so that their outline lies on top.

No bpy here.
"""
import re
from collections import namedtuple

from . import svg

REFERENCE_ELEMENT = "bauteil"
REFERENCE_SHEET = "blatt"
SIGN_CROSS = "kreuz"
SIGN_CENTRE_LINE = "mittellinie"

CATEGORY_CLASS = "layer-material-category-"

Pattern = namedtuple("Pattern", "text base_angle reference sign")
Pattern.__doc__ = """A hatch pattern of the style.

text        the whole <pattern> element
base_angle  rotation from patternTransform in degrees, or None
reference   value of data-din-bezug, or ""
sign        value of data-din-zeichen, or ""
"""

LineFamily = namedtuple("LineFamily", "axis offset spacing start length period width colour")
LineFamily.__doc__ = """One family of parallel lines of a tiled line pattern.

axis     "v" (vertical in pattern coordinates) or "h"
offset   position across the lines, 0 to under spacing
spacing  distance between the lines (tile width or height)
start    start of the dash along the line, 0 to under period
length   dash length; equal to period for a continuous line
period   repeat along the line
width    stroke width in mm on paper
colour   stroke colour
"""

_RE_PATTERN = re.compile(r'<pattern\b[^>]*\bid="([^"]+)".*?</pattern>', re.S)
_RE_ROTATE = re.compile(r"rotate\(\s*(-?[\d.]+)")
_RE_REFERENCE = re.compile(r'\bdata-din-bezug="([^"]*)"')
_RE_SIGN = re.compile(r'\bdata-din-zeichen="([^"]*)"')
_RE_CHILD = re.compile(r"<(line|rect|circle|ellipse|path|polyline|polygon|use|image|text)\b([^>]*?)/?>")
_RE_COMMENT = re.compile(r"<!--.*?-->", re.S)
# On a sheet Bonsai appends .d<drawing id> to every class, hence optional.
_RE_BASE_RULE = re.compile(r"(?<![\w.$-])\.cut\.IfcMaterialLayer(?:\.d\d+)?\s*\{([^{}]*)\}")
# The selector may carry further classes (.IfcMaterialLayer, .d<id>) on either side.
_RE_CATEGORY_RULE = re.compile(r"\.cut(?:\.[\w-]+)*\.layer-material-category-(\w+)(?:\.[\w-]+)*\s*\{([^{}]*)\}")
_RE_ANY_CATEGORY_RULE = re.compile(r"\.layer-material-category-([A-Za-z0-9]+)[^{]*\{([^}]*)\}")
_RE_FILL_URL = re.compile(r"fill:\s*url\(#([^)]+)\)")
_RE_STROKE_WIDTH = re.compile(r"stroke-width\s*:\s*([\d.]+)")


# ------------------------------------------------------------------ patterns

def read_patterns(svg_text):
    """{pattern id: Pattern} of all <pattern> elements in the text."""
    result = {}
    for m in _RE_PATTERN.finditer(svg_text):
        text = m.group(0)
        head = text[: text.find(">") + 1]
        base = None
        transform = svg.attribute(head, "patternTransform")
        if transform:
            r = _RE_ROTATE.search(transform)
            if r:
                base = float(r.group(1))
        ref = _RE_REFERENCE.search(head)
        sign = _RE_SIGN.search(head)
        result[m.group(1)] = Pattern(text, base, ref.group(1) if ref else "", sign.group(1) if sign else "")
    return result


def _number(attrs, name, default=None):
    value = svg.attribute(" " + attrs, name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _property(attrs, name, default=""):
    """Value from the style attribute or from a presentation attribute of that name."""
    for prop, value in svg.style_declarations(attrs):
        if prop == name:
            return value
    value = svg.attribute(" " + attrs, name)
    return value.strip() if value is not None else default


def line_families(pattern_text):
    """(families, background fill) of a LINE pattern, or None for other patterns.

    A line pattern has only axis-parallel <line> elements and at most one <rect>
    that fills the whole tile (background). Dots, circles or inclined lines make it
    something else; such patterns stay a pattern fill. Two lines that describe the
    same family are counted once (a family split in two pieces to fit the tile).
    """
    end = pattern_text.find(">") + 1
    head = pattern_text[:end]
    width = _number(head, "width")
    height = _number(head, "height")
    if not width or not height:
        return None
    close = pattern_text.rfind("</pattern>")
    body = _RE_COMMENT.sub("", pattern_text[end:close if close > 0 else len(pattern_text)])
    background = ""
    raw = []
    for m in _RE_CHILD.finditer(body):
        tag, attrs = m.group(1), m.group(2)
        if tag == "rect":
            x = _number(attrs, "x", 0.0) or 0.0
            y = _number(attrs, "y", 0.0) or 0.0
            w = _number(attrs, "width")
            h = _number(attrs, "height")
            if w is None or h is None:
                return None
            if abs(x) > 1e-9 or abs(y) > 1e-9 or w < width - 1e-9 or h < height - 1e-9:
                return None
            background = _property(attrs, "fill", "")
            continue
        if tag != "line":
            return None
        x1 = _number(attrs, "x1", 0.0) or 0.0
        y1 = _number(attrs, "y1", 0.0) or 0.0
        x2 = _number(attrs, "x2", 0.0) or 0.0
        y2 = _number(attrs, "y2", 0.0) or 0.0
        colour = _property(attrs, "stroke", "black") or "black"
        try:
            stroke = float(_property(attrs, "stroke-width", "1") or 1.0)
        except ValueError:
            stroke = 1.0
        if abs(x1 - x2) < 1e-9:
            raw.append(("v", x1, min(y1, y2), abs(y2 - y1), stroke, colour))
        elif abs(y1 - y2) < 1e-9:
            raw.append(("h", y1, min(x1, x2), abs(x2 - x1), stroke, colour))
        else:
            return None
    if not raw:
        return None
    families, seen = [], set()
    for axis, offset, start, length, stroke, colour in raw:
        spacing = width if axis == "v" else height
        period = height if axis == "v" else width
        if length >= period - 1e-9:
            start, length = 0.0, period
        key = (axis, round(offset % spacing, 4), round(start % period, 4),
               round(min(length, period), 4), round(stroke, 4), colour)
        if key in seen:
            continue
        seen.add(key)
        families.append(LineFamily(axis, offset % spacing, spacing, start % period,
                                   min(length, period), period, stroke, colour))
    return families, background


# ------------------------------------------------------------------ categories

def category_patterns(css_text):
    """{category: pattern id} of the category rules that fill with a pattern.
    A later rule for the same category wins, as in CSS."""
    result = {}
    for m in _RE_ANY_CATEGORY_RULE.finditer(css_text):
        url = _RE_FILL_URL.search(m.group(2))
        if url:
            result[m.group(1)] = url.group(1)
    return result


def base_layer_width(css_text):
    """stroke-width of the base rule .cut.IfcMaterialLayer, or None. The last rule
    with a width wins."""
    width = None
    for m in _RE_BASE_RULE.finditer(css_text):
        w = _RE_STROKE_WIDTH.search(m.group(1))
        if w:
            width = float(w.group(1))
    return width


def category_widths(css_text):
    """{category: stroke-width} of the cut category rules that set a width."""
    result = {}
    for m in _RE_CATEGORY_RULE.finditer(css_text):
        w = _RE_STROKE_WIDTH.search(m.group(2))
        if w:
            result[m.group(1)] = float(w.group(1))
    return result


def structural_categories(css_text):
    """Categories drawn heavier than the base rule: structural layers. They are
    drawn last, so that their outline covers the thinner one of a neighbour. Empty
    if the style has no base rule."""
    base = base_layer_width(css_text)
    if base is None:
        return set()
    return {cat for cat, w in category_widths(css_text).items() if w > base + 1e-9}


def band_categories(svg_text):
    """Categories whose pattern carries a band on the middle of the layer
    (data-din-zeichen="mittellinie"), today the waterproofing. A membrane is thinner
    on paper than its own band, so these layers are drawn after all others."""
    patterns = read_patterns(svg_text)
    css = svg.style_text(svg_text) or svg_text
    return {cat for cat, pid in category_patterns(css).items()
            if pid in patterns and patterns[pid].sign == SIGN_CENTRE_LINE}


def category_of(head):
    """Material category of a cut group from its classes, or None."""
    for name in svg.classes(head):
        if name.startswith(CATEGORY_CLASS):
            return name[len(CATEGORY_CLASS):]
    return None
