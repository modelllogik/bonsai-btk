# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Legend and north arrow on the sheet.

Bonsai builds a sheet from its layout file (``layouts/<sheet>.svg``): title block,
drawings, view titles. A German plan also carries a legend of the hatchings and,
with a floor plan, a north arrow. Both are written here as groups into the layout
file, before Bonsai builds the sheet, so they come onto the sheet like everything
else and can be moved there.

- **Legend:** one entry per material category that is cut in one of the drawings
  of the sheet, in the order of the style. The box shows the same hatching as the
  drawing (line patterns as real lines, the timber cross, the waterproofing band).
  The text comes from the comment in the style rule: ``/* Legende: Mauerwerk */``
  or, as in din.css, ``/* legend: Mauerwerk - masonry */`` (the part before " - ").
  With sill heights on the sheet a sentence below says what they refer to.
- **North arrow:** on sheets with a plan view.

An existing legend or north arrow keeps its position; a new one is placed beside
the title block (legend) or at the top right (north arrow). The texts on the sheet
are German, as the plans are.

Text in, text out. No bpy.
"""
import re

from . import hatching, style, svg

LEGEND_TITLE = "Legende"
SILL_NOTE = "Alle Brüstungshöhen beziehen sich auf OKFFB."
TITLE_CAP_MM, ENTRY_CAP_MM = 5.0, 3.5      # cap heights
BOX_W, BOX_H, ROW, GAP = 10.0, 5.0, 7.0, 3.0
TITLEBLOCK_W, TITLEBLOCK_H, MARGIN, SPACING = 180.0, 55.0, 5.0, 8.0
TITLEBLOCK_BASELINE = 50.0                 # last text line of the title block, mm below its top
FONT = "font-family: Arial, 'Liberation Sans', Helvetica, sans-serif; fill: black; stroke: none"
ARIAL_CAP = 0.716                          # font-size = cap height / 0.716

NORTH_W, NORTH_H, NORTH_CX, NORTH_CY = 15.0, 22.5, 7.5, 14.5   # frame and circle centre in it
NORTH_MARGIN = 15.0                        # default: from the top and right edge of the sheet

_RE_LEGEND = re.compile(r'<g\b(?=[^>]*\bdata-type="din-legende")[^>]*>\s*<g\b[^>]*>.*?</g>\s*</g>', re.S)
_RE_NORTH = re.compile(r'<g\b(?=[^>]*\bdata-type="din-nordpfeil")[^>]*>\s*<g\b[^>]*>.*?</g>\s*</g>', re.S)
_RE_RULE = re.compile(r"\.cut(?:\.\w+)*\.layer-material-category-([A-Za-z0-9]+)(?:\.\w+)*\s*\{([^}]*)\}")
_RE_FILL = re.compile(r"(?<![-\w])fill:\s*([^;]+);")
_RE_BLOCK = re.compile(r"([^{}]+)\{([^}]*)\}")
_RE_PROFILE_SELECTOR = re.compile(r"^\.cut\.materialCategory-([A-Za-z0-9]+)$")
PROFILE_CLASS = "materialCategory-"   # the class Bonsai writes for EPset_Drawing.Metadata = material.Category
_RE_NAME = re.compile(r"/\*\s*(?:Legende|legend):\s*(.*?)\s*\*/")
_RE_DRAWING_GROUP = re.compile(r'<g\b(?=[^>]*\bdata-type="drawing")[^>]*>')
_RE_PATTERN_HEAD = re.compile(r"<pattern\b[^>]*>")


def _mm(text):
    return float(re.sub(r"[a-z]+$", "", text or "0"))


def _num(v):
    """As Bonsai writes numbers: decimal point, no needless digits."""
    return repr(float(round(v, 4)))


def _escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def legend_name(rule_body, category):
    """Legend text from the comment of a style rule; the German part of 'X - english'."""
    m = _RE_NAME.search(rule_body)
    if not m:
        return category
    return m.group(1).split(" - ")[0].strip()


# ------------------------------------------------------------------ layout

def layout_drawings(layout_text):
    """[dict(id, guid)] of the drawings placed on a layout (data-id, data-drawing)."""
    result = []
    for m in _RE_DRAWING_GROUP.finditer(layout_text):
        result.append(dict(id=svg.attribute(m.group(0), "data-id"), guid=svg.attribute(m.group(0), "data-drawing")))
    return result


def has_sills(drawing_texts):
    return any("data-din-brh=" in t for t in drawing_texts)


# ------------------------------------------------------------------ legend

def legend_entries(drawings):
    """drawings = [(reference id on the sheet, SVG text of the drawing)].

    ([(category, text, fill, sign, pattern text)], report). Only categories cut in one
    of the drawings, in the order of the style rules. The fill gets the id prefix the
    sheet builder gives the drawing's definitions (d<reference id>-).

    The box shows the category as it is drawn: a category that is cut as a profile (an
    element without layers, class materialCategory-X) takes the fill of a rule
    .cut.materialCategory-X if the style has one (din.css 4b: steel and metal profiles
    black), also when the category occurs as a layer as well; otherwise the fill of the
    layer rule."""
    info, order, used, profiles, profile_fill = {}, [], set(), set(), {}
    for ref, text in drawings:
        css = "".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S))
        for block in _RE_BLOCK.finditer(re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
            fill = _RE_FILL.search(block.group(2))
            for selector in block.group(1).split(","):
                m = _RE_PROFILE_SELECTOR.match(selector.strip())
                if m and fill and m.group(1) not in profile_fill:
                    profile_fill[m.group(1)] = fill.group(1).strip()
        defs = text[:text.find("</defs>")]
        patterns = style.read_patterns(defs)
        for m in _RE_RULE.finditer(css):
            category = m.group(1)
            if category in info:
                continue
            fill = _RE_FILL.search(m.group(2))
            raw = fill.group(1).strip() if fill else "none"
            pid = re.search(r"url\(#([^)]+)\)", raw)
            pattern = patterns.get(pid.group(1)) if pid else None
            sign = pattern.sign if pattern else ""
            text_of_pattern = pattern.text if pattern else ""
            info[category] = (legend_name(m.group(2), category), raw.replace("url(#", "url(#d%s-" % ref),
                              sign, text_of_pattern)
            order.append(category)
        body = text[text.find("</defs>"):]
        for names in re.findall(r'<g\b[^>]*\sclass="([^"]*)"', body):
            k = names.split()
            if "cut" in k:
                used.update(c[len(style.CATEGORY_CLASS):] for c in k if c.startswith(style.CATEGORY_CLASS))
                profiles.update(c[len(PROFILE_CLASS):] for c in k if c.startswith(PROFILE_CLASS))
    report = ["category %s has no style rule, not in the legend" % k for k in sorted(used - set(info))]
    entries = []
    for k in order:
        if k not in used:
            continue
        name, fill, sign, pattern_text = info[k]
        if k in profiles and k in profile_fill and not profile_fill[k].startswith("url("):
            fill, sign, pattern_text = profile_fill[k], "", ""
            report.append("category %s: box as the profile is drawn (%s)" % (k, fill))
        entries.append((k, name, fill, sign, pattern_text))
    return entries, report


def _legend_size(entries, notes):
    title_px, entry_px = TITLE_CAP_MM / ARIAL_CAP, ENTRY_CAP_MM / ARIAL_CAP
    width = max([len(LEGEND_TITLE) * 0.56 * title_px] +
                [BOX_W + GAP + len(n) * 0.56 * entry_px for _, n, _, _, _ in entries])
    height = TITLE_CAP_MM + GAP + len(entries) * ROW - (ROW - BOX_H)
    if notes:
        width = max([width] + [len(s) * 0.56 * entry_px for s in notes])
        height += len(notes) * ROW
    return width, height


def legend_group(entries, notes, x, y):
    """The legend group with its top left corner at (x, y) mm on the sheet."""
    title_px, entry_px = TITLE_CAP_MM / ARIAL_CAP, ENTRY_CAP_MM / ARIAL_CAP
    width, height = _legend_size(entries, notes)
    parts = ['<g data-type="din-legende" data-x="%s" data-y="%s" data-breite="%s" data-hoehe="%s">'
             % (_num(x), _num(y), _num(width), _num(height)),
             '<g transform="translate(%s,%s)">' % (_num(x), _num(y)),
             '<text x="0" y="%s" style="%s; font-size: %.2fpx">%s</text>'
             % (_num(TITLE_CAP_MM), FONT, title_px, LEGEND_TITLE)]
    zy = TITLE_CAP_MM + GAP
    for _, name, fill, sign, pattern_text in entries:
        # a line pattern as real lines in the box, clipped by computation (no clipPath:
        # a second group in the legend would break finding it again)
        lines = []
        if pattern_text and not sign:
            families = style.line_families(pattern_text)
            if families is not None:
                fam, background = families
                patterns = list(style.read_patterns(pattern_text).values())
                base = (patterns[0].base_angle if patterns else None) or 0.0
                lines = hatching.lines_in_rectangle(fam, base, 0.0, zy, BOX_W, BOX_H)
                if lines:
                    fill = background or "white"
        parts.append('<path d="M 0 %s h %s v %s h %s Z" style="fill: %s; stroke: black; stroke-width: 0.25; '
                     'stroke-linejoin: miter" />' % (_num(zy), _num(BOX_W), _num(BOX_H), _num(-BOX_W), fill))
        parts += lines
        if sign == style.SIGN_CROSS:
            parts.append('<path d="M 0 %s L %s %s M %s %s L 0 %s" style="fill: none; stroke: black; stroke-width: %s" />'
                         % (_num(zy), _num(BOX_W), _num(zy + BOX_H), _num(BOX_W), _num(zy), _num(zy + BOX_H),
                            _num(hatching.CROSS_STROKE)))
        elif sign == style.SIGN_CENTRE_LINE:
            middle = zy + BOX_H / 2
            offset = (hatching.BAND_WIDTH - hatching.BAND_EDGE) / 2
            for side in (-offset, offset):
                parts.append('<path d="M 0 %s H %s" style="fill: none; stroke: black; stroke-width: %s" />'
                             % (_num(middle + side), _num(BOX_W), _num(hatching.BAND_EDGE)))
            parts.append('<path d="M 0 %s H %s" style="fill: none; stroke: black; stroke-width: %s; '
                         'stroke-linecap: butt; stroke-dasharray: %s %s" />'
                         % (_num(middle), _num(BOX_W), _num(hatching.BAND_WIDTH),
                            _num(hatching.BAND_DASH), _num(hatching.BAND_GAP)))
        parts.append('<text x="%s" y="%s" style="%s; font-size: %.2fpx">%s</text>'
                     % (_num(BOX_W + GAP), _num(zy + (BOX_H + ENTRY_CAP_MM) / 2), FONT, entry_px, _escape(name)))
        zy += ROW
    for sentence in notes:
        parts.append('<text data-din-hinweis="1" x="0" y="%s" style="%s; font-size: %.2fpx">%s</text>'
                     % (_num(zy + BOX_H / 2 + ENTRY_CAP_MM / 2), FONT, entry_px, _escape(sentence)))
        zy += ROW
    return "".join(parts) + "</g></g>"


def place_legend(layout_text, entries, notes=()):
    """(layout text, report). Without entries an existing legend is removed."""
    old = _RE_LEGEND.search(layout_text)
    if not entries:
        if old:
            return layout_text[:old.start()] + layout_text[old.end():], ["no cut categories, legend removed"]
        return layout_text, ["no cut categories, no legend"]
    width, height = _legend_size(entries, notes)
    if old:
        x, y = _mm(svg.attribute(old.group(0), "data-x")), _mm(svg.attribute(old.group(0), "data-y"))
        where = "position from the layout"
    else:
        root = re.search(r"<svg\b[^>]*>", layout_text).group(0)
        w, h = _mm(svg.attribute(root, "width")), _mm(svg.attribute(root, "height"))
        x = w - MARGIN - TITLEBLOCK_W - SPACING - width
        last_baseline = height - BOX_H + (BOX_H + ENTRY_CAP_MM) / 2
        y = h - MARGIN - TITLEBLOCK_H + TITLEBLOCK_BASELINE - last_baseline   # level with the last title block line
        where = "left of the title block"
        if x < 25.0:   # title block over the whole width (A4 portrait): above it, right-aligned
            x, y = w - MARGIN - 3.0 - width, h - MARGIN - TITLEBLOCK_H - SPACING - height
            where = "above the title block"
        x, y = round(x, 1), round(y, 2)
    group = legend_group(entries, notes, x, y)
    if old:
        text = layout_text[:old.start()] + group + layout_text[old.end():]
    else:
        end = layout_text.rfind("</svg>")
        text = layout_text[:end] + group + layout_text[end:]
    return text, ["%d entries (%s), %s x %s / y %s"
                  % (len(entries), ", ".join(n for _, n, _, _, _ in entries), where, _num(x), _num(y))]


# ------------------------------------------------------------------ north arrow

def north_arrow_content():
    """Circle 15 mm filled white, a cross, the north half as a 1.5 mm bar that ends
    below the circle line; N 3.5 mm above. Origin at the centre of the circle."""
    s = "stroke: black; stroke-width: 0.25"
    return ('<circle r="7.5" style="fill: white; stroke: none" />'
            '<path d="M -0.75 0 L -0.75 -7.4624 A 7.5 7.5 0 0 1 0.75 -7.4624 L 0.75 0 Z" style="fill: black; stroke: none" />'
            '<path d="M -7.5 0 H 7.5 M 0 0 V 7.5" style="fill: none; %s" />'
            '<circle r="7.5" style="fill: none; %s" />'
            '<text x="0" y="-9.5" text-anchor="middle" style="%s; font-size: %.2fpx">N</text>'
            % (s, s, FONT, ENTRY_CAP_MM / ARIAL_CAP))


def place_north_arrow(layout_text, needed, angle=0.0):
    """(layout text, report). angle: degrees clockwise. Without a plan on the sheet an
    existing north arrow is removed."""
    old = _RE_NORTH.search(layout_text)
    if not needed:
        if old:
            return layout_text[:old.start()] + layout_text[old.end():], ["no plan on the sheet, removed"]
        return layout_text, []
    if old:
        x, y = _mm(svg.attribute(old.group(0), "data-x")), _mm(svg.attribute(old.group(0), "data-y"))
        where = "position from the layout"
    else:
        root = re.search(r"<svg\b[^>]*>", layout_text).group(0)
        x, y = round(_mm(svg.attribute(root, "width")) - NORTH_MARGIN - NORTH_W, 1), NORTH_MARGIN
        where = "top right"
    group = ('<g data-type="din-nordpfeil" data-x="%s" data-y="%s" data-breite="%s" data-hoehe="%s">'
             '<g transform="translate(%s,%s) rotate(%s)">%s</g></g>'
             % (_num(x), _num(y), _num(NORTH_W), _num(NORTH_H), _num(x + NORTH_CX), _num(y + NORTH_CY),
                _num(angle), north_arrow_content()))
    if old:
        text = layout_text[:old.start()] + group + layout_text[old.end():]
    else:
        end = layout_text.rfind("</svg>")
        text = layout_text[:end] + group + layout_text[end:]
    return text, ["%s x %s / y %s" % (where, _num(x), _num(y))]
