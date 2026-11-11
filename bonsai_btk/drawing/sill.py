# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sill heights (BRH) of windows in plan.

German plans write the sill height of every window into the plan, inside the
room, at the inner face of the opening and readable along the wall: "BRH 1.00",
"BRH 1.23⁵" (metres, the millimetre raised). It is measured from the finished floor;
the legend of the sheet says so once. Position and text come from plan.sills.

Text in, text out. No bpy.
"""
import re

TEXT_CLASS = "din-brh"
# the block of an earlier run, with the one newline apply() put after it
_RE_OLD = re.compile(r'(?:\n  <text data-din-brh="[^"]*"[^>]*>.*?</text>)+\n?', re.S)


def apply(svg_text, sills):
    """(text, report). Earlier sill texts out, new ones before </svg>. Only windows
    that Bonsai wrote into this drawing are in sills (plan.sills checks that)."""
    text = _RE_OLD.sub("", svg_text)
    new, report = [], []
    for s in sills or []:
        new.append('\n  <text data-din-brh="%s" dominant-baseline="middle" style="font-size: 0;" text-anchor="middle" '
                   'transform="translate(%s, %s) rotate(%s)"><tspan class="%s" dy="0em" x="0" y="0">%s</tspan></text>'
                   % (s["guid"], repr(round(float(s["x"]), 4)), repr(round(float(s["y"]), 4)),
                      repr(round(float(s["angle"]), 3)),
                      TEXT_CLASS, s["text"]))
        report.append("%s: %s" % (s["name"], s["text"]))
    if new:
        end = text.rfind("</svg>")
        text = text[:end] + "".join(new) + "\n" + text[end:]
    return text, report
