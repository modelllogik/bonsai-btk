# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for drawing.svg and drawing.style (no Blender needed).

    python -m unittest discover tests
"""
import os
import sys
import unittest

_PACKAGE_ROOT = os.path.join(os.path.dirname(__file__), "..", "bonsai_btk")
sys.path.insert(0, _PACKAGE_ROOT)
try:
    from drawing import style, svg  # the drawing package does not import bpy
finally:
    sys.path.remove(_PACKAGE_ROOT)


DRAWING = (
    '<?xml version="1.0"?>\n'
    '<svg data-scale="1:50" id="root" xmlns:ifc="http://www.ifcopenshell.org/ns">'
    "<defs><style type=\"text/css\">.cut.IfcMaterialLayer { fill: none; stroke-width: 0.25; }</style></defs>"
    '<g class="material-AW 2U4Ps1cynOaemnr3II8j51 IfcWall cut">'
    '<g class="IfcMaterialLayer layer-material-category-Mauerwerk cut"><path d="M0,0 L10,0 L10,2 L0,2 Z"/></g>'
    '<g class="empty"/>'
    "</g>"
    '<g class="IfcBeam cut" ifc:guid="1xtCbt0GjIXRHcGkq7F07s"><path d="M0,5 L3,5"/></g>'
    "</svg>"
)


class GroupTest(unittest.TestCase):
    def test_nested_and_empty(self):
        spans = svg.groups(DRAWING)
        self.assertEqual(len(spans), 4)
        heads = [DRAWING[a:b] for a, b, _ in spans]
        self.assertTrue(heads[0].startswith('<g class="material-AW'))
        empty = [s for s in spans if DRAWING[s[0]:s[1]].endswith("/>")][0]
        self.assertEqual(empty[1], empty[2])

    def test_outer_groups_skip_nested(self):
        spans = svg.outer_groups(DRAWING, lambda h: svg.has_class(h, "cut"))
        self.assertEqual(len(spans), 2)
        self.assertTrue(DRAWING[spans[0][0]:spans[0][1]].endswith('<g class="empty"/></g>'))

    def test_outer_groups_empty_group(self):
        # an empty <g/> must end at its own head, not at the next tag
        text = '<svg><g class="x"/><g class="y"><path d="M0,0 L1,1"/></g></svg>'
        spans = svg.outer_groups(text, lambda h: True)
        self.assertEqual([text[a:b] for a, b in spans],
                         ['<g class="x"/>', '<g class="y"><path d="M0,0 L1,1"/></g>'])

    def test_remove_and_replace(self):
        spans = svg.outer_groups(DRAWING, lambda h: svg.has_class(h, "IfcBeam"))
        self.assertNotIn("IfcBeam", svg.remove_spans(DRAWING, spans))
        a, b = spans[0]
        self.assertIn("<g/>", svg.replace_spans(DRAWING, [(a, b, "<g/>")]))


class HeadTest(unittest.TestCase):
    def test_classes(self):
        head = '<g class="IfcWall cut">'
        self.assertEqual(svg.classes(head), ["IfcWall", "cut"])
        self.assertEqual(svg.add_class(head, "din-fuge"), '<g class="IfcWall cut din-fuge">')
        self.assertEqual(svg.add_class(head, "cut"), head)
        self.assertEqual(svg.add_class("<g>", "a"), '<g class="a">')

    def test_attributes(self):
        tag = '<path d="M0,0" style="fill:none"/>'
        self.assertEqual(svg.attribute(tag, "d"), "M0,0")
        self.assertIsNone(svg.attribute(tag, "class"))
        self.assertEqual(svg.set_attribute(tag, "d", "M1,1"), '<path d="M1,1" style="fill:none"/>')
        self.assertEqual(svg.set_attribute("<g>", "id", "a"), '<g id="a">')

    def test_set_style_twice_changes_nothing(self):
        head = '<g class="cut" style="stroke:black; fill:url(#a)">'
        once = svg.set_style(head, "fill", "url(#b)")
        self.assertEqual(once, '<g class="cut" style="stroke:black; fill:url(#b)">')
        self.assertEqual(svg.set_style(once, "fill", "url(#b)"), once)
        self.assertEqual(svg.set_style("<g>", "fill", "white"), '<g style="fill:white">')

    def test_global_ids(self):
        self.assertEqual(svg.global_ids('<g class="a 2U4Ps1cynOaemnr3II8j51 IfcWall cut">'),
                         ["2U4Ps1cynOaemnr3II8j51"])
        # serialiser groups carry ifc:guid; on a sheet the prefix is ns3
        self.assertEqual(svg.global_id('<g class="IfcBeam" ifc:guid="1xtCbt0GjIXRHcGkq7F07s">'),
                         "1xtCbt0GjIXRHcGkq7F07s")
        self.assertEqual(svg.global_id('<g ns3:guid="1xtCbt0GjIXRHcGkq7F07s" class="IfcBeam d12">'),
                         "1xtCbt0GjIXRHcGkq7F07s")
        self.assertIsNone(svg.global_id('<g class="IfcMaterialLayer cut">'))

    def test_canonical_class(self):
        self.assertEqual(svg.canonical_class("Dämmung"), "Dmmung")
        self.assertEqual(svg.canonical_class("Bindiger Boden"), "BindigerBoden")


class PathTest(unittest.TestCase):
    def test_subpaths(self):
        self.assertEqual(svg.subpaths("M0,0 L10,0 L10,2 Z M5,5 L6,6"),
                         [[(0, 0), (10, 0), (10, 2), (0, 0)], [(5, 5), (6, 6)]])
        self.assertEqual(svg.subpaths("M0 0 1 0 1 1"), [[(0, 0), (1, 0), (1, 1)]])

    def test_path_d(self):
        self.assertEqual(svg.path_d([(0, 0), (1.25, -0.00001)]), "M0,0 L1.25,0")
        self.assertEqual(svg.path_d([(0, 0), (1, 0), (1, 1)], closed=True), "M0,0 L1,0 L1,1 Z")
        self.assertEqual(svg.segments_d([((0, 0), (1, 0)), ((2, 0), (3, 0))]), "M0,0 L1,0 M2,0 L3,0")

    def test_longest_edge(self):
        self.assertAlmostEqual(svg.longest_edge_angle(["M0,0 L10,0 L10,2 L0,2 Z"]), 0.0)
        self.assertAlmostEqual(svg.longest_edge_angle(["M0,0 L1,1 L1.1,0.9"]), 45.0)
        self.assertIsNone(svg.longest_edge_angle([""]))


class DrawingTest(unittest.TestCase):
    def test_scale(self):
        self.assertEqual(svg.scale_denominator(DRAWING), 50.0)
        self.assertIsNone(svg.scale_denominator('<svg id="root"><g data-scale="1:20"/></svg>'))

    def test_style_text(self):
        self.assertIn(".cut.IfcMaterialLayer", svg.style_text(DRAWING))


PATTERNS = """
<pattern id="din-mauerwerk" width="2" height="2" patternUnits="userSpaceOnUse" patternTransform="rotate(45 0 0)">
  <rect x="0" y="0" width="2" height="2" style="fill:white"/>
  <line x1="0" y1="0" x2="0" y2="2" style="stroke:black; stroke-width:0.1"/>
  <line x1="2" y1="0" x2="2" y2="2" style="stroke:black; stroke-width:0.1"/>
</pattern>
<pattern id="din-holzwerkstoff" width="1" height="4" data-din-bezug="bauteil">
  <line x1="0.5" y1="0" x2="0.5" y2="2" stroke="black" stroke-width="0.1"/>
</pattern>
<pattern id="din-abdichtung" width="1" height="1" data-din-zeichen="mittellinie"></pattern>
<pattern id="din-kies" width="2" height="2"><circle cx="1" cy="1" r="0.2"/></pattern>
"""

CSS = """
.cut.IfcMaterialLayer { /* 4 - comment */ fill: none; stroke: black; stroke-width: 0.25; }
.cut.layer-material-category-Mauerwerk  { fill: url(#din-mauerwerk); stroke-width: 0.50; /* legend */ }
.cut.layer-material-category-Abdichtung { fill: url(#din-abdichtung); stroke-width: 0.25; }
.cut.layer-material-category-Daemmung   { fill: #d9d9d9; stroke-width: 0.25; }
.cut.layer-material-category-Stahl      { fill: white; stroke-width: 0.50; }
.cut.materialCategory-Stahl, .cut.materialCategory-Metall { fill: black; stroke-width: 0.25; }
"""


class PatternTest(unittest.TestCase):
    def test_read(self):
        p = style.read_patterns(PATTERNS)
        self.assertEqual(sorted(p), ["din-abdichtung", "din-holzwerkstoff", "din-kies", "din-mauerwerk"])
        self.assertEqual(p["din-mauerwerk"].base_angle, 45.0)
        self.assertEqual(p["din-holzwerkstoff"].reference, style.REFERENCE_ELEMENT)
        self.assertIsNone(p["din-holzwerkstoff"].base_angle)
        self.assertEqual(p["din-abdichtung"].sign, style.SIGN_CENTRE_LINE)

    def test_line_families(self):
        p = style.read_patterns(PATTERNS)
        families, background = style.line_families(p["din-mauerwerk"].text)
        self.assertEqual(background, "white")
        self.assertEqual(len(families), 1)  # x=0 and x=2 are the same family
        f = families[0]
        self.assertEqual((f.axis, f.offset, f.spacing, f.length, f.period, f.width), ("v", 0.0, 2.0, 2.0, 2.0, 0.1))
        dashed, _ = style.line_families(p["din-holzwerkstoff"].text)
        self.assertEqual((dashed[0].length, dashed[0].period), (2.0, 4.0))
        self.assertIsNone(style.line_families(p["din-kies"].text))
        self.assertIsNone(style.line_families(p["din-abdichtung"].text))


class CategoryTest(unittest.TestCase):
    def test_patterns_and_widths(self):
        self.assertEqual(style.category_patterns(CSS),
                         {"Mauerwerk": "din-mauerwerk", "Abdichtung": "din-abdichtung"})
        self.assertEqual(style.base_layer_width(CSS), 0.25)
        self.assertEqual(style.category_widths(CSS),
                         {"Mauerwerk": 0.5, "Abdichtung": 0.25, "Daemmung": 0.25, "Stahl": 0.5})

    def test_structural(self):
        self.assertEqual(style.structural_categories(CSS), {"Mauerwerk", "Stahl"})
        self.assertEqual(style.structural_categories(".cut { stroke-width: 0.5; }"), set())

    def test_sheet_suffix(self):
        # on a sheet every class carries .d<drawing id>
        css = (".cut.IfcMaterialLayer.d12 { stroke-width: 0.25; }"
               ".cut.d12.layer-material-category-Beton.d12 { stroke-width: 0.5; }")
        self.assertEqual(style.base_layer_width(css), 0.25)
        self.assertEqual(style.structural_categories(css), {"Beton"})

    def test_band(self):
        drawing = "<svg><defs><style>%s</style>%s</defs></svg>" % (CSS, PATTERNS)
        self.assertEqual(style.band_categories(drawing), {"Abdichtung"})

    def test_category_of(self):
        self.assertEqual(style.category_of('<g class="IfcMaterialLayer layer-material-category-Putz cut">'), "Putz")
        self.assertIsNone(style.category_of('<g class="IfcWall cut">'))


if __name__ == "__main__":
    unittest.main()
