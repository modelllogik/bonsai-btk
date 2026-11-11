# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The layout file of a sheet: what is placed where, and moving it.

Bonsai keeps the arrangement of a sheet in ``layouts/<sheet>.svg``: one group
``data-type="drawing"`` per placed drawing with two images, the drawing itself
(``data-type="foreground"``) and its view title (``data-type="view-title"``), each
with x, y, width and height in mm. Legend and north arrow (drawing.sheet) are groups
of their own with data-x and data-y. Moving something changes only these numbers;
the IFC is not touched.

Before writing, the layout is compared with the checksum it had when the page was
loaded: if it changed in between, nothing is written. Every write keeps a backup in
``layouts/_backup/``, the latest five per sheet.

No bpy.
"""
import hashlib
import math
import os
import re
import shutil
import time

BACKUPS_KEPT = 5
NORTH_CENTRE = (7.5, 14.5)   # circle centre in the north arrow frame, as drawing.sheet draws it
LIMIT_MM = 5000.0

_RE_DRAWING = re.compile(r'<g\b(?=[^>]*\bdata-type="drawing")[^>]*>.*?</g>', re.S)
_RE_IMAGE = re.compile(r"<image\b[^>]*/>", re.S)
_RE_LEGEND = re.compile(r'<g\b(?=[^>]*\bdata-type="din-legende")[^>]*>\s*<g\b[^>]*>.*?</g>\s*</g>', re.S)
_RE_NORTH = re.compile(r'<g\b(?=[^>]*\bdata-type="din-nordpfeil")[^>]*>\s*<g\b[^>]*>.*?</g>\s*</g>', re.S)

LEGEND_ID, NORTH_ID = "legend", "north"


def _attr(tag, name):
    m = re.search(r'\s%s="([^"]*)"' % re.escape(name), tag)
    return m.group(1) if m else None


def _set_attr(tag, name, value):
    return re.sub(r'(\s%s=")[^"]*(")' % re.escape(name), lambda m: m.group(1) + value + m.group(2), tag, count=1)


def _mm(text):
    return float(re.sub(r"[a-z]+$", "", text or "0"))


def _num(v):
    """As Bonsai writes numbers: decimal point, no needless digits."""
    return repr(float(round(v, 4)))


def checksum(text_or_path):
    if os.path.exists(str(text_or_path)):
        with open(text_or_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    return hashlib.sha256(text_or_path.encode("utf-8")).hexdigest()


def _frame(tag):
    return {k: _mm(_attr(tag, k)) for k in ("x", "y", "width", "height")}


def read(layout_text):
    """dict(width, height, drawings=[dict(id, guid, name, drawing={x,y,width,height}, title=...)]).
    Legend and north arrow are entries with the ids "legend" and "north"."""
    root = re.search(r"<svg\b[^>]*>", layout_text).group(0)
    items = []
    for g in _RE_DRAWING.finditer(layout_text):
        entry = {"id": _attr(g.group(0), "data-id"), "guid": _attr(g.group(0), "data-drawing"), "name": ""}
        for im in _RE_IMAGE.finditer(g.group(0)):
            tag = im.group(0)
            kind = _attr(tag, "data-type")
            if kind == "foreground":
                entry["drawing"] = _frame(tag)
                href = (_attr(tag, "xlink:href") or "").replace("\\", "/")
                entry["name"] = os.path.splitext(os.path.basename(href))[0]
            elif kind == "view-title":
                entry["title"] = _frame(tag)
        if "drawing" in entry:
            items.append(entry)
    for regex, ident, name in ((_RE_LEGEND, LEGEND_ID, "Legend"), (_RE_NORTH, NORTH_ID, "North arrow")):
        m = regex.search(layout_text)
        if m:
            head = m.group(0)
            items.append({"id": ident, "guid": "", "name": name,
                          "drawing": {"x": _mm(_attr(head, "data-x")), "y": _mm(_attr(head, "data-y")),
                                      "width": _mm(_attr(head, "data-breite")), "height": _mm(_attr(head, "data-hoehe"))}})
    return {"width": _mm(_attr(root, "width")), "height": _mm(_attr(root, "height")), "drawings": items}


def check_positions(data, items):
    """Positions from the browser, checked: known ids only, finite numbers in a sane
    range. {id: {"drawing": (x, y), "title": (x, y)}} or {id: (x, y)}."""
    known = {i["id"] for i in items}
    result = {}

    def pair(xy, ident):
        if not isinstance(xy, (list, tuple)) or len(xy) != 2:
            raise ValueError("wrong format: %r" % ident)
        x, y = float(xy[0]), float(xy[1])
        if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > LIMIT_MM or abs(y) > LIMIT_MM:
            raise ValueError("position out of range: %r" % ident)
        return (x, y)

    for ident, wish in (data or {}).items():
        if ident not in known:
            raise ValueError("unknown drawing: %r" % ident)
        if isinstance(wish, dict):
            result[ident] = {"drawing": pair(wish.get("drawing"), ident)}
            if wish.get("title") is not None:
                result[ident]["title"] = pair(wish["title"], ident)
        else:
            result[ident] = pair(wish, ident)
    return result


def move(layout_text, positions):
    """(text, report). positions = {id: {"drawing": (x, y), "title": (x, y)}} with the
    top left corners in mm. Without "title" (or for a plain pair) the view title moves
    by the same offset as the drawing."""
    report = []
    pending = dict(positions)

    def replace_group(g):
        text = g.group(0)
        ident = _attr(text, "data-id")
        if ident not in pending:
            return text
        wish = pending.pop(ident)
        if not isinstance(wish, dict):
            wish = {"drawing": wish}
        x_new, y_new = wish["drawing"]
        fg = next((im.group(0) for im in _RE_IMAGE.finditer(text) if _attr(im.group(0), "data-type") == "foreground"), None)
        dx, dy = x_new - _mm(_attr(fg, "x")), y_new - _mm(_attr(fg, "y"))
        title = wish.get("title")

        def replace_image(im):
            tag = im.group(0)
            kind = _attr(tag, "data-type")
            if kind == "view-title" and title is not None:
                return _set_attr(_set_attr(tag, "x", _num(title[0])), "y", _num(title[1]))
            if kind not in ("foreground", "view-title"):
                return tag
            tag = _set_attr(tag, "x", _num(_mm(_attr(tag, "x")) + dx))
            return _set_attr(tag, "y", _num(_mm(_attr(tag, "y")) + dy))

        report.append("reference %s: drawing x %s / y %s%s" % (
            ident, _num(x_new), _num(y_new),
            " · title x %s / y %s" % (_num(title[0]), _num(title[1])) if title is not None else " · title moved along"))
        return _RE_IMAGE.sub(replace_image, text)

    text = _RE_DRAWING.sub(replace_group, layout_text)
    for ident, regex, name, centre in ((LEGEND_ID, _RE_LEGEND, "legend", (0.0, 0.0)),
                                       (NORTH_ID, _RE_NORTH, "north arrow", NORTH_CENTRE)):
        if ident not in pending:
            continue
        wish = pending.pop(ident)
        x_new, y_new = wish["drawing"] if isinstance(wish, dict) else wish
        m = regex.search(text)
        if not m:
            report.append("%s not in the layout, skipped" % name)
            continue
        outer = re.match(r"<g\b[^>]*>", m.group(0)).group(0)
        rest = m.group(0)[len(outer):]
        outer = _set_attr(_set_attr(outer, "data-x", _num(x_new)), "data-y", _num(y_new))
        if ident == LEGEND_ID:
            rest = re.sub(r'transform="translate\([^)]*\)"', 'transform="translate(%s,%s)"'
                          % (_num(x_new), _num(y_new)), rest, count=1)
        else:
            rest = re.sub(r"translate\([^)]*\)", "translate(%s,%s)"
                          % (_num(x_new + centre[0]), _num(y_new + centre[1])), rest, count=1)
        text = text[:m.start()] + outer + rest + text[m.end():]
        report.append("%s: x %s / y %s" % (name, _num(x_new), _num(y_new)))
    for ident in pending:
        report.append("reference %s not in the layout, skipped" % ident)
    return text, report


def prune_backups(folder, stem, keep=BACKUPS_KEPT):
    """Keep only the latest backups of this sheet. Touches only files named exactly
    <stem>_YYYY-MM-DD_HHMMSS.svg; anything else in the folder stays."""
    pattern = re.compile(r"^%s_\d{4}-\d{2}-\d{2}_\d{6}\.svg$" % re.escape(stem))
    own = sorted(n for n in os.listdir(folder) if pattern.match(n) and os.path.isfile(os.path.join(folder, n)))
    gone = own[:-keep] if keep > 0 else []
    for n in gone:
        os.remove(os.path.join(folder, n))
    return gone


def write(path, positions, expected_checksum, now=None):
    """Move and write the layout at path. Returns (backup path, report). Raises
    RuntimeError if the file changed since expected_checksum was taken."""
    if checksum(path) != expected_checksum:
        raise RuntimeError("the layout file changed since the page was loaded; nothing written. "
                           "Update the preview first.")
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    new, report = move(text, positions)
    folder = os.path.join(os.path.dirname(path), "_backup")
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    backup = os.path.join(folder, "%s_%s.svg" % (stem, time.strftime("%Y-%m-%d_%H%M%S", time.localtime(now))))
    shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    report += ["old backup removed: " + n for n in prune_backups(folder, stem)]
    return backup, report
