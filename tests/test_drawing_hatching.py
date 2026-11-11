# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for drawing.hatching, outline, windows, pipeline and model (no Blender).

    python -m unittest discover tests

The shapely parts need shapely, the model tests IfcOpenShell; both come with Bonsai.
Tests that need them are skipped where they are missing.
"""
import importlib.util
import os
import sys
import unittest

_PACKAGE_ROOT = os.path.join(os.path.dirname(__file__), "..", "bonsai_btk")
sys.path.insert(0, _PACKAGE_ROOT)
try:
    from drawing import hatching, outline, pipeline, style, svg, windows
finally:
    sys.path.remove(_PACKAGE_ROOT)

HAS_SHAPELY = importlib.util.find_spec("shapely") is not None
HAS_IFCOPENSHELL = importlib.util.find_spec("ifcopenshell") is not None

STYLE = """<style type="text/css">
.cut.IfcMaterialLayer { fill: none; stroke: black; stroke-width: 0.25; }
.cut.layer-material-category-Mauerwerk { fill: url(#din-mauerwerk); stroke-width: 0.50; }
.cut.layer-material-category-Putz { fill: url(#din-putz); stroke-width: 0.25; }
.cut.layer-material-category-Holz { fill: url(#din-holz); stroke-width: 0.50; }
.cut.layer-material-category-Stahl { fill: white; stroke-width: 0.50; }
</style>"""
PATTERNS = """<pattern id="din-mauerwerk" width="2" height="2" patternUnits="userSpaceOnUse" patternTransform="rotate(45 0 0)"><line x1="0" y1="0" x2="0" y2="2" style="stroke:black; stroke-width:0.1"/></pattern>
<pattern id="din-putz" width="2" height="2"><circle cx="1" cy="1" r="0.1"/></pattern>
<pattern id="din-holz" width="1" height="1" data-din-zeichen="kreuz"></pattern>"""


def drawing(body, scale=50):
    return ('<svg data-scale="1:%d" id="root"><defs>%s%s</defs><g class="target-view-SECTIONVIEW">%s</g></svg>'
            % (scale, STYLE, PATTERNS, body))


def layer(category, d, material="MW", guid="2U4Ps1cynOaemnr3II8j51"):
    return ('<g class="IfcMaterialLayer layer-material-%s layer-material-category-%s %s cut"><path d="%s"/></g>'
            % (material, category, guid, d))


WALL = layer("Mauerwerk", "M0,0 L20,0 L20,5 L0,5 Z")


class AngleTest(unittest.TestCase):
    def test_target_angle(self):
        self.assertEqual(hatching.target_angle(45, 0, "", 0), 45)
        self.assertEqual(hatching.target_angle(45, 30, "", 0), 75)
        self.assertEqual(hatching.target_angle(45, 120, "", 0), 75)       # mod 90
        self.assertEqual(hatching.target_angle(0, 120, style.REFERENCE_ELEMENT, 0), 120)
        self.assertEqual(hatching.target_angle(45, 30, style.REFERENCE_SHEET, 15), 60)
        self.assertEqual(hatching.target_angle(None, 0, "", 190), 10)

    def test_pattern_copy_id(self):
        self.assertEqual(hatching.pattern_copy_id("din-kies", 52.5), "din-kies-w52p5")

    def test_line_paths_cover_area(self):
        families, _ = style.line_families(style.read_patterns(PATTERNS)["din-mauerwerk"].text)
        paths = hatching.line_paths(families, 0, [(0, 0), (10, 0), (10, 4), (0, 4)])
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].count("M"), 6)   # x = 0, 2, ..., 10

    def test_lines_in_rectangle_are_clipped(self):
        families, _ = style.line_families(style.read_patterns(PATTERNS)["din-mauerwerk"].text)
        paths = hatching.lines_in_rectangle(families, 45, 0, 0, 10, 4)
        self.assertTrue(paths)
        for p in paths:
            for points in svg.subpaths(svg.attribute(p, "d")):
                for x, y in points:
                    self.assertTrue(-1e-6 <= x <= 10 + 1e-6 and -1e-6 <= y <= 4 + 1e-6)


class HatchingTest(unittest.TestCase):
    def test_real_lines_and_white_area(self):
        text, report = hatching.apply(drawing(WALL))
        self.assertIn('class="%s"' % hatching.LINES_CLASS, text)
        self.assertIn("<clipPath id=\"din-schraffur-clip-", text)
        self.assertIn('style="fill:white"', text)
        self.assertIn("1 area(s) with real lines", report[-1])

    def test_second_run_changes_nothing(self):
        once, _ = hatching.apply(drawing(WALL))
        twice, _ = hatching.apply(once)
        self.assertEqual(once, twice)

    def test_rotation_turns_lines(self):
        plain, _ = hatching.apply(drawing(WALL))
        turned, _ = hatching.apply(drawing(WALL), rotations={"2U4Ps1cynOaemnr3II8j51": 15})
        self.assertNotEqual(plain, turned)

    def test_dot_pattern_turned_as_copy(self):
        text, _ = hatching.apply(drawing(layer("Putz", "M0,0 L20,10 L19,12 L-1,2 Z")))
        self.assertNotIn(hatching.LINES_CLASS + '"', text)      # dots stay a pattern fill
        self.assertEqual(text.count("<pattern"), 3)             # no base angle: not turned

    def test_timber_cross_only_on_short_sections(self):
        short, _ = hatching.apply(drawing(layer("Holz", "M0,0 L8,0 L8,16 L0,16 Z", "Holz")))
        self.assertIn('class="%s"' % hatching.SIGN_CLASS, short)
        long, _ = hatching.apply(drawing(layer("Holz", "M0,0 L80,0 L80,4 L0,4 Z", "Holz")))
        self.assertNotIn('class="%s"' % hatching.SIGN_CLASS, long)

    def test_no_cross_in_windows(self):
        body = ('<g class="IfcWindow material-Holz cut layer-material-category-Holz" ifc:guid="1xtCbt0GjIXRHcGkq7F07s">'
                '<path d="M0,0 L8,0 L8,8 L0,8 Z"/></g>')
        text, report = hatching.apply(drawing(body))
        self.assertNotIn('class="%s"' % hatching.SIGN_CLASS, text)
        self.assertTrue(any("no timber cross" in r for r in report))

    def test_categories_for_elements_without_layers(self):
        body = '<g class="IfcColumn material-HEA cut" ifc:guid="1xtCbt0GjIXRHcGkq7F07s"><path d="M0,0 L3,0 L3,3 L0,3 Z"/></g>'
        text, n = hatching.add_categories(drawing(body), {"1xtCbt0GjIXRHcGkq7F07s": "Stahl"})
        self.assertEqual(n, 1)
        self.assertIn("layer-material-category-Stahl materialCategory-Stahl", text)
        plain, _ = hatching.add_categories(drawing(body), {"1xtCbt0GjIXRHcGkq7F07s": "Stahl"},
                                           material_category_class=False)
        self.assertNotIn("materialCategory-", plain)
        again, n2 = hatching.add_categories(text, {"1xtCbt0GjIXRHcGkq7F07s": "Stahl"})
        self.assertEqual((again, n2), (text, 0))


class RingTest(unittest.TestCase):
    def test_square_with_hole_from_loose_edges(self):
        def square(a, b):
            return [[(a, a), (b, a)], [(b, a), (b, b)], [(b, b), (a, b)], [(a, b), (a, a)]]
        rings, report = outline.rings_from_edges(square(0, 10) + square(3, 6) + [[(20, 20), (21, 21)]])
        self.assertEqual(len(rings), 2)
        areas, holes = outline.sort_rings(rings)
        self.assertEqual((len(areas), len(holes)), (1, 1))
        self.assertTrue(any("loose edge" in r for r in report))

    def test_has_ring(self):
        self.assertTrue(outline.has_ring([[(0, 0), (1, 0), (1, 1), (0, 0)]]))
        self.assertFalse(outline.has_ring([[(0, 0), (1, 0)]]))

    def test_loose_edges_get_an_outline_group(self):
        body = ('<g class="IfcMaterialLayer layer-material-MW layer-material-category-Mauerwerk 2U4Ps1cynOaemnr3II8j51 cut">'
                '<path d="M0,0 L10,0"/><path d="M10,0 L10,5"/><path d="M10,5 L0,5"/><path d="M0,5 L0,0"/></g>')
        text, _ = hatching.apply(drawing(body))
        self.assertIn('class="%s"' % outline.OUTLINE_CLASS, text)
        self.assertEqual(hatching.apply(text)[0], text)


class OrderTest(unittest.TestCase):
    def test_structural_last(self):
        body = WALL + layer("Putz", "M0,5 L20,5 L20,6 L0,6 Z", "KZP", "2u8ryBKcnMi8eBwox1iow6")
        text, n = outline.structural_last(drawing(body))
        self.assertEqual(n, 1)
        self.assertLess(text.find("category-Putz"), text.find("category-Mauerwerk", text.find("<g")))
        self.assertEqual(outline.structural_last(text), (text, 0))


@unittest.skipUnless(HAS_SHAPELY, "shapely not installed")
class JointTest(unittest.TestCase):
    def test_same_material_one_outline(self):
        body = (layer("Mauerwerk", "M0,0 L10,0 L10,5 L0,5 Z") +
                layer("Mauerwerk", "M10,0 L20,0 L20,5 L10,5 Z", guid="2u8ryBKcnMi8eBwox1iow6"))
        text, n = outline.merge_joints(drawing(body))
        self.assertEqual(n, 1)
        joint = text[text.find('din-fuge'):]
        path = joint[joint.find(' d="') + 4:]
        rings = svg.subpaths(path[:path.find('"')])
        self.assertEqual(len(rings), 1)                                     # one outline
        self.assertAlmostEqual(outline.area(rings[0]), 100.0)
        self.assertNotIn("2U4Ps1cynOaemnr3II8j51 din-fuge", text)            # no GlobalId on the union
        self.assertEqual(outline.merge_joints(text)[0], text)

    def test_different_materials_keep_their_joint(self):
        body = (layer("Mauerwerk", "M0,0 L10,0 L10,5 L0,5 Z") +
                layer("Mauerwerk", "M10,0 L20,0 L20,5 L10,5 Z", "KS", "2u8ryBKcnMi8eBwox1iow6"))
        self.assertEqual(outline.merge_joints(drawing(body))[1], 2)

    def test_build_ups_from_1_100(self):
        floor = ('<g class="IfcCovering cut" ifc:guid="0gZmpr$39QEu$uA4CFn3Wy">'
                 '<g class="IfcMaterialLayer 0gZmpr$39QEu$uA4CFn3Wy cut"><path d="M0,0 L10,0 L10,1 L0,1 Z"/></g>'
                 '<g class="IfcMaterialLayer 0gZmpr$39QEu$uA4CFn3Wy cut"><path d="M0,1 L10,1 L10,2 L0,2 Z"/></g></g>')
        roles = {"0gZmpr$39QEu$uA4CFn3Wy": outline.ROLE_BUILD_UP}
        self.assertEqual(outline.simplify_build_ups(drawing(floor, 50), roles)[1:], (0, 0))
        text, omitted, united = outline.simplify_build_ups(drawing(floor, 100), roles)
        self.assertEqual((omitted, united), (0, 3))     # element group and its two layers
        self.assertEqual(text.count('class="cut %s"' % outline.BUILD_UP_CLASS), 1)
        self.assertNotIn("IfcMaterialLayer", text[text.find("target-view"):])
        forced = {"0gZmpr$39QEu$uA4CFn3Wy": outline.ROLE_FORCED}
        self.assertEqual(outline.simplify_build_ups(drawing(floor, 50), forced)[2], 3)


class WindowTest(unittest.TestCase):
    def test_glass_pair_becomes_one_line(self):
        # 1:50: Bonsai's 10 mm glass gives two lines 0.2 mm apart
        body = ('<g class="IfcWindow projection" ifc:guid="1xtCbt0GjIXRHcGkq7F07s">'
                '<path d="M0,0 L0,20"/><path d="M0.2,0 L0.2,20"/><path d="M-2,0 L2,0"/></g>')
        text, panes, groups = windows.fine(drawing(body))
        self.assertEqual((panes, groups), (1, 1))
        self.assertIn('class="%s"' % windows.PANE_CLASS, text)
        self.assertEqual(text.count("stroke:none"), 2)            # the pair is hidden, not removed
        self.assertIn('style="stroke-width:0.13" d="M-2,0 L2,0"', text)
        self.assertEqual(windows.fine(text)[0], text)


@unittest.skipUnless(HAS_SHAPELY, "shapely not installed")
class PipelineTest(unittest.TestCase):
    def test_second_run_changes_nothing(self):
        body = (WALL + layer("Mauerwerk", "M20,0 L40,0 L40,5 L20,5 Z", guid="2u8ryBKcnMi8eBwox1iow6") +
                '<g class="IfcWindow cut layer-material-category-Holz" ifc:guid="1xtCbt0GjIXRHcGkq7F07s">'
                '<path d="M5,0 L5,5"/><path d="M5.2,0 L5.2,5"/><path d="M4,0 L6,0 L6,5 L4,5 Z"/></g>')
        once, report = pipeline.process_text(drawing(body), {})
        self.assertEqual(pipeline.process_text(once, {})[0], once)
        self.assertTrue(any("merged" in r for r in report))


@unittest.skipUnless(HAS_IFCOPENSHELL, "IfcOpenShell not installed")
class ModelTest(unittest.TestCase):
    def setUp(self):
        import ifcopenshell
        import ifcopenshell.api
        sys.path.insert(0, _PACKAGE_ROOT)
        try:
            from drawing import model
        finally:
            sys.path.remove(_PACKAGE_ROOT)
        self.model = model
        f = ifcopenshell.file(schema="IFC4")
        ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject")
        self.f = f
        self.wall = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall")
        self.floor = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcCovering", predefined_type="FLOORING")
        self.membrane = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcCovering", predefined_type="MEMBRANE")
        column = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcColumn")
        steel = ifcopenshell.api.run("material.add_material", f, name="S235", category="Stahl")
        ifcopenshell.api.run("material.assign_material", f, products=[column], material=steel)
        self.column = column

    def test_read(self):
        data = self.model.read(self.f)
        self.assertEqual(data["categories"], {self.column.GlobalId: "Stahl"})
        self.assertEqual(data["roles"], {self.floor.GlobalId: outline.ROLE_BUILD_UP,
                                         self.membrane.GlobalId: outline.ROLE_OMIT})
        self.assertEqual(data["rotations"], {})

    def test_rotate(self):
        self.assertEqual(self.model.rotate(self.f, self.wall), (0.0, 15.0))
        self.assertEqual(self.model.rotate(self.f, self.wall, step=170), (15.0, 5.0))
        self.assertEqual(self.model.rotations(self.f), {self.wall.GlobalId: 5.0})

    def test_layers_switch(self):
        self.assertIs(self.model.toggle_layers(self.f, [self.floor]), False)   # not all off -> off
        self.assertEqual(self.model.roles(self.f)[self.floor.GlobalId], outline.ROLE_FORCED)
        self.assertIs(self.model.toggle_layers(self.f, [self.floor]), True)    # all off -> on
        self.assertNotIn(self.floor.GlobalId, self.model.roles(self.f))       # on: never united
        self.assertIsNone(self.model.toggle_layers(self.f, [self.floor], automatic=True))
        self.assertEqual(self.model.roles(self.f)[self.floor.GlobalId], outline.ROLE_BUILD_UP)


if __name__ == "__main__":
    unittest.main()
