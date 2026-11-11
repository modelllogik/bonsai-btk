# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for drawing.sheet and drawing.printing (no Blender, no Inkscape).

    python -m unittest discover tests
"""
import os
import stat
import sys
import tempfile
import unittest

_PACKAGE_ROOT = os.path.join(os.path.dirname(__file__), "..", "bonsai_btk")
sys.path.insert(0, _PACKAGE_ROOT)
try:
    from drawing import printing, sheet
finally:
    sys.path.remove(_PACKAGE_ROOT)

STYLE = """<style type="text/css">
.cut.IfcMaterialLayer { stroke-width: 0.25; }
.cut.layer-material-category-Mauerwerk { fill: url(#din-mauerwerk); stroke-width: 0.50; /* legend: Mauerwerk - masonry */ }
.cut.layer-material-category-Holz { fill: url(#din-holz); stroke-width: 0.50; /* Legende: Holz */ }
.cut.layer-material-category-Daemmung { fill: #d9d9d9; stroke-width: 0.25; /* legend: Dämmung - insulation */ }
.cut.layer-material-category-Beton { fill: url(#din-beton); stroke-width: 0.50; /* legend: Beton, unbewehrt - plain concrete */ }
</style>"""
PATTERNS = """<pattern id="din-mauerwerk" width="2" height="2" patternTransform="rotate(45 0 0)"><line x1="0" y1="0" x2="0" y2="2" style="stroke:black; stroke-width:0.1"/></pattern>
<pattern id="din-holz" width="1" height="1" data-din-zeichen="kreuz"></pattern>"""


def drawing(categories):
    body = "".join('<g class="IfcMaterialLayer layer-material-category-%s cut"><path d="M0,0 L1,0 L1,1 Z"/></g>' % c
                   for c in categories)
    return '<svg data-scale="1:50"><defs>%s%s</defs><g>%s</g></svg>' % (STYLE, PATTERNS, body)


LAYOUT = ('<svg xmlns="http://www.w3.org/2000/svg" width="594mm" height="420mm">'
          '<g data-type="drawing" data-id="7" data-drawing="1JOSaYvg9QdvPpCuVJHziO"></g></svg>')


class LegendTest(unittest.TestCase):
    def test_name(self):
        self.assertEqual(sheet.legend_name("fill: x; /* legend: Dämmung - insulation */", "Daemmung"), "Dämmung")
        self.assertEqual(sheet.legend_name("/* legend: Beton, unbewehrt - plain concrete */", "Beton"), "Beton, unbewehrt")
        self.assertEqual(sheet.legend_name("/* Legende: Holz */", "Holz"), "Holz")
        self.assertEqual(sheet.legend_name("fill: white;", "Stahl"), "Stahl")

    def test_entries_only_cut_categories_in_style_order(self):
        entries, report = sheet.legend_entries([("7", drawing(["Daemmung", "Mauerwerk", "Holz", "Putz"]))])
        self.assertEqual([e[0] for e in entries], ["Mauerwerk", "Holz", "Daemmung"])
        self.assertEqual(entries[0][2], "url(#d7-din-mauerwerk)")       # id prefix of the sheet
        self.assertEqual(entries[1][3], "kreuz")
        self.assertEqual(report, ["category Putz has no style rule, not in the legend"])

    def test_profile_box_as_drawn(self):
        css = STYLE.replace("</style>", ".cut.layer-material-category-Stahl { fill: white; stroke-width: 0.50; }\n"
                                        ".cut.materialCategory-Stahl, .cut.materialCategory-Metall {\n"
                                        "  /* 4b - fill: none in a comment */\n  fill: black; stroke: black;\n}\n</style>")
        layer = '<g class="IfcMaterialLayer layer-material-category-Stahl cut"><path d="M0,0 L1,0 Z"/></g>'
        profile = '<g class="IfcMember layer-material-category-Stahl materialCategory-Stahl cut"><path d="M0,0 L1,0 Z"/></g>'
        make = lambda body: '<svg><defs>%s%s</defs><g>%s</g></svg>' % (css, PATTERNS, body)
        entries, report = sheet.legend_entries([("7", make(layer))])
        self.assertEqual(entries[0][2], "white")                 # only a layer: outlined
        entries, report = sheet.legend_entries([("7", make(profile))])
        self.assertEqual(entries[0][2], "black")                 # only a profile: black
        self.assertIn("category Stahl: box as the profile is drawn (black)", report)
        entries, _ = sheet.legend_entries([("7", make(layer)), ("8", make(profile))])
        self.assertEqual([e[2] for e in entries], ["black"])     # both: black
        entries, _ = sheet.legend_entries([("7", drawing(["Mauerwerk"]).replace("cut\"", "cut materialCategory-Mauerwerk\""))])
        self.assertEqual(entries[0][2], "url(#d7-din-mauerwerk)")   # no profile rule: layer rule

    def test_place_keep_remove(self):
        entries, _ = sheet.legend_entries([("7", drawing(["Mauerwerk", "Holz"]))])
        once, report = sheet.place_legend(LAYOUT, entries, [sheet.SILL_NOTE])
        self.assertIn('data-type="din-legende"', once)
        self.assertIn(">Legende</text>", once)
        self.assertIn("stroke-linecap:butt", once)          # masonry as real lines in its box
        self.assertIn("M 0 15.0 L 10.0 20.0 M 10.0 15.0 L 0 20.0", once)   # the timber cross in the second box
        self.assertIn(sheet.SILL_NOTE, once)
        self.assertIn("left of the title block", report[0])
        self.assertEqual(sheet.place_legend(once, entries, [sheet.SILL_NOTE])[0], once)
        moved = once.replace('data-x="', 'data-x="1', 1)
        again, report = sheet.place_legend(moved, entries, [sheet.SILL_NOTE])
        self.assertIn("position from the layout", report[0])
        self.assertEqual(sheet.place_legend(once, [])[0], LAYOUT)

    def test_portrait_a4_above_title_block(self):
        entries, _ = sheet.legend_entries([("7", drawing(["Mauerwerk"]))])
        layout = LAYOUT.replace('width="594mm" height="420mm"', 'width="210mm" height="297mm"')
        self.assertIn("above the title block", sheet.place_legend(layout, entries)[1][0])

    def test_layout_drawings_and_sills(self):
        self.assertEqual(sheet.layout_drawings(LAYOUT), [dict(id="7", guid="1JOSaYvg9QdvPpCuVJHziO")])
        self.assertTrue(sheet.has_sills(['<text data-din-brh="x">']))
        self.assertFalse(sheet.has_sills(["<svg/>"]))


class NorthArrowTest(unittest.TestCase):
    def test_place_keep_remove(self):
        once, report = sheet.place_north_arrow(LAYOUT, True)
        self.assertIn('data-type="din-nordpfeil" data-x="564.0" data-y="15.0"', once)
        self.assertEqual(report, ["top right x 564.0 / y 15.0"])
        self.assertEqual(sheet.place_north_arrow(once, True)[0], once)
        self.assertEqual(sheet.place_north_arrow(once, False)[0], LAYOUT)
        self.assertEqual(sheet.place_north_arrow(LAYOUT, False), (LAYOUT, []))


class PrintingTest(unittest.TestCase):
    def test_configured_path_must_exist(self):
        self.assertIsNone(printing.find_inkscape("/no/such/inkscape"))

    def test_no_inkscape(self):
        with self.assertRaises(RuntimeError):
            printing.sheet_pdf("sheet.svg", "sheet.pdf", None)

    @unittest.skipIf(os.name == "nt", "needs a shell script as stand-in for Inkscape")
    def test_export_through_stand_in(self):
        folder = tempfile.mkdtemp()
        fake = os.path.join(folder, "inkscape")
        with open(fake, "w") as f:
            f.write('#!/bin/sh\nfor a in "$@"; do case "$a" in --export-filename=*) echo pdf > "${a#*=}";; esac; done\n')
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        target = os.path.join(folder, "out", "W-02.pdf")
        self.assertEqual(printing.sheet_pdf(os.path.join(folder, "sheet.svg"), target, fake), target)
        self.assertTrue(os.path.exists(target))
        failing = os.path.join(folder, "failing")
        with open(failing, "w") as f:
            f.write("#!/bin/sh\necho broken >&2\nexit 1\n")
        os.chmod(failing, os.stat(failing).st_mode | stat.S_IEXEC)
        with self.assertRaises(RuntimeError) as error:
            printing.sheet_pdf("sheet.svg", os.path.join(folder, "x.pdf"), failing)
        self.assertIn("broken", str(error.exception))
        self.assertFalse(os.path.exists(os.path.join(folder, "x.pdf")))


if __name__ == "__main__":
    unittest.main()
