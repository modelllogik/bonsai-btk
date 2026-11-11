# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading and editing the SVG text of a Bonsai drawing.

The post-processing works on the SVG as text, not on a parsed tree: Bonsai and the
sheet builder write it in a regular form, and editing the text keeps everything
that is not touched byte for byte as it was. This module collects what every step
needs:

- groups: find <g> elements with their content, also nested and empty ones
- classes and attributes of a group head, the GlobalId of the element
- path data: subpaths as point lists, and back
- the drawing scale

Where Bonsai stores what (Bonsai 0.9.1):

- The GlobalId of an element is a class of its group when Bonsai writes the group
  itself (elements with a layer set, such as walls), and an attribute ``ifc:guid``
  when the IfcOpenShell serialiser writes it (beams, windows). On a sheet the
  namespace prefix can differ (``ns3:guid``), so any prefix is accepted.
- On a sheet every class gets the drawing's suffix class ``d<id>`` in addition.
- Cut areas are paths of M/L/Z commands with absolute coordinates.

No bpy here; this module runs with a plain Python.
"""
import math
import re

# ------------------------------------------------------------------ patterns

_RE_G_OPEN = re.compile(r"<g\b[^>]*?(/?)>", re.S)
_RE_G_CLOSE = re.compile(r"</g\s*>")
_RE_CLASS = re.compile(r'\bclass="([^"]*)"')
_RE_STYLE = re.compile(r'\bstyle="([^"]*)"')
_RE_GUID_ATTR = re.compile(r'\b[\w-]+:guid="([^"]+)"')
_RE_GLOBAL_ID = re.compile(r"^[0-9A-Za-z_$]{22}$")
_RE_SVG_ROOT = re.compile(r"<svg\b[^>]*>")
_RE_SCALE = re.compile(r'\bdata-scale="1:(\d+(?:\.\d+)?)"')
_RE_PATH_COMMAND = re.compile(r"([MLZmlz])([^MLZmlz]*)")
_RE_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_RE_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S)


# ------------------------------------------------------------------ groups

def groups(svg_text):
    """All <g> elements as (head_start, head_end, content_end), sorted by start.

    content_end is the position of the closing ``</g>``. For an empty element
    ``<g .../>`` it equals head_end. Nested groups are counted, so the content of a
    group is complete.
    """
    marks = []
    for m in _RE_G_OPEN.finditer(svg_text):
        marks.append((m.start(), m.end(), True, m.group(1) == "/"))
    for m in _RE_G_CLOSE.finditer(svg_text):
        marks.append((m.start(), m.end(), False, False))
    marks.sort()
    stack, result = [], []
    for start, end, opening, empty in marks:
        if opening:
            if empty:
                result.append((start, end, end))
            else:
                stack.append((start, end))
        elif stack:
            head_start, head_end = stack.pop()
            result.append((head_start, head_end, start))
    result.sort()
    return result


def group_end(svg_text, head_end, content_end):
    """End of a group including ``</g>``; for ``<g/>`` the end of its head."""
    if content_end <= head_end:
        return head_end
    m = _RE_G_CLOSE.match(svg_text, content_end)
    return m.end() if m else content_end


def outer_groups(svg_text, predicate):
    """Spans (start, end including ``</g>``) of the outermost groups whose head
    satisfies predicate(head). A matching group inside a matching group is not
    listed again."""
    spans = []
    for head_start, head_end, content_end in groups(svg_text):
        if spans and head_start < spans[-1][1]:
            continue
        if predicate(svg_text[head_start:head_end]):
            spans.append((head_start, group_end(svg_text, head_end, content_end)))
    return spans


def remove_spans(svg_text, spans):
    """The text without the given (start, end) spans. Spans must not overlap."""
    for start, end in sorted(spans, reverse=True):
        svg_text = svg_text[:start] + svg_text[end:]
    return svg_text


def replace_spans(svg_text, replacements):
    """The text with each (start, end, new_text) applied. Spans must not overlap."""
    for start, end, new in sorted(replacements, key=lambda r: -r[0]):
        svg_text = svg_text[:start] + new + svg_text[end:]
    return svg_text


# ------------------------------------------------------------------ heads

def classes(head):
    """Classes of an element head as a list, in their order."""
    m = _RE_CLASS.search(head)
    return m.group(1).split() if m else []


def has_class(head, name):
    return name in classes(head)


def add_class(head, name):
    """Head with one more class; unchanged if it is there already."""
    m = _RE_CLASS.search(head)
    if not m:
        return _insert_attribute(head, 'class="%s"' % name)
    if name in m.group(1).split():
        return head
    return head[: m.start()] + 'class="%s %s"' % (m.group(1), name) + head[m.end():]


def attribute(tag, name):
    """Value of an attribute, or None. The name may carry a namespace prefix."""
    m = re.search(r'\s%s="([^"]*)"' % re.escape(name), tag)
    return m.group(1) if m else None


def set_attribute(tag, name, value):
    """Tag with the attribute set; added if missing."""
    pattern = re.compile(r'(\s%s=")[^"]*(")' % re.escape(name))
    if pattern.search(tag):
        return pattern.sub(lambda m: m.group(1) + value + m.group(2), tag, count=1)
    return _insert_attribute(tag, '%s="%s"' % (name, value))


def _insert_attribute(tag, text):
    if tag.endswith("/>"):
        return tag[:-2].rstrip() + " " + text + "/>"
    return tag[:-1].rstrip() + " " + text + ">"


def style_declarations(head):
    """Inline style as a list of (property, value), in their order."""
    m = _RE_STYLE.search(head)
    if not m:
        return []
    result = []
    for part in m.group(1).split(";"):
        if ":" in part:
            prop, value = part.split(":", 1)
            result.append((prop.strip(), value.strip()))
    return result


def set_style(head, prop, value):
    """Head with one inline style property set. An existing declaration of the same
    property is replaced, not repeated, so running a step twice changes nothing.
    The other declarations are kept as they are written."""
    m = _RE_STYLE.search(head)
    if not m:
        return _insert_attribute(head, 'style="%s:%s"' % (prop, value))
    parts = [x.strip() for x in m.group(1).split(";") if x.strip()]
    parts = [x for x in parts if x.split(":", 1)[0].strip() != prop]
    parts.append("%s:%s" % (prop, value))
    return head[: m.start()] + 'style="%s"' % "; ".join(parts) + head[m.end():]


def is_global_id(name):
    """True for a class that looks like an IFC GlobalId (22 characters of the IFC
    base 64 alphabet). Class names of IFC entities (IfcWallStandard…) are excluded."""
    return bool(_RE_GLOBAL_ID.match(name)) and not name.startswith("Ifc")


def global_ids(head):
    """GlobalIds named in a group head: the ``…:guid`` attribute first, then
    classes that look like a GlobalId. Bonsai can put several on one wall group
    (element and related objects); the caller decides which one it needs."""
    result = []
    m = _RE_GUID_ATTR.search(head)
    if m:
        result.append(m.group(1))
    for name in classes(head):
        if is_global_id(name) and name not in result:
            result.append(name)
    return result


def global_id(head):
    """The first GlobalId of a group head, or None (see global_ids)."""
    ids = global_ids(head)
    return ids[0] if ids else None


def canonical_class(name):
    """A name as Bonsai turns it into a class: only a-z, A-Z and 0-9 are kept
    (tool/drawing.py canonicalise_class_name). "Dämmung" becomes "Dmmung", which is
    why the material categories are spelt without umlauts (Daemmung)."""
    return re.sub("[^0-9a-zA-Z]+", "", name or "")


# ------------------------------------------------------------------ paths

def subpaths(d):
    """Subpaths of path data as point lists. Bonsai writes cut areas with absolute
    M, L and Z; a closed subpath ends with its first point again. Relative commands
    are read as absolute, as the post-processing never meets them in Bonsai's
    output."""
    result, current, start = [], [], None
    for command, rest in _RE_PATH_COMMAND.findall(d):
        numbers = [float(n) for n in _RE_NUMBER.findall(rest)]
        if command in "Mm":
            if len(current) > 1:
                result.append(current)
            current = [(numbers[0], numbers[1])] if len(numbers) >= 2 else []
            start = current[0] if current else None
            for i in range(2, len(numbers) - 1, 2):
                current.append((numbers[i], numbers[i + 1]))
        elif command in "Ll":
            for i in range(0, len(numbers) - 1, 2):
                current.append((numbers[i], numbers[i + 1]))
        else:
            if start and current and current[-1] != start:
                current.append(start)
            if len(current) > 1:
                result.append(current)
            current = []
    if len(current) > 1:
        result.append(current)
    return result


def number(value, digits=4):
    """A coordinate as text: fixed number of decimals, no trailing zeros, no "-0"."""
    text = ("%.*f" % (digits, value)).rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def path_d(points, closed=False):
    """Path data of one polyline."""
    if not points:
        return ""
    text = "M" + " L".join("%s,%s" % (number(x), number(y)) for x, y in points)
    return text + " Z" if closed else text


def segments_d(segments):
    """Path data of separate straight segments [((x1, y1), (x2, y2)), ...]."""
    return " ".join(path_d([a, b]) for a, b in segments)


def longest_edge_angle(paths):
    """Angle in degrees (SVG sense, y down) of the longest edge of all paths,
    0 to under 180; None if there is no edge. For a cut layer this is the direction
    of the layer, also when an opening splits it."""
    best, longest = None, 0.0
    for d in paths:
        for points in subpaths(d):
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                length = math.hypot(x2 - x1, y2 - y1)
                if length > longest + 1e-9:
                    longest = length
                    best = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return None if best is None else best % 180.0


# ------------------------------------------------------------------ drawing

def scale_denominator(svg_text):
    """Denominator of the drawing scale from ``<svg data-scale="1:50">``, or None.
    Only the root element is read; a sheet has no data-scale."""
    root = _RE_SVG_ROOT.search(svg_text)
    if not root:
        return None
    m = _RE_SCALE.search(root.group(0))
    return float(m.group(1)) if m else None


def style_text(svg_text):
    """All embedded <style> blocks of a drawing or sheet, joined."""
    return "\n".join(m.group(1) for m in _RE_STYLE_BLOCK.finditer(svg_text))
