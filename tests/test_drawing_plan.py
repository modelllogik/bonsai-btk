# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for drawing.stair, roof, sill and the pure parts of plan (no Blender).

    python -m unittest discover tests
"""
import importlib.util
import os
import sys
import unittest

_PACKAGE_ROOT = os.path.join(os.path.dirname(__file__), "..", "bonsai_btk")
sys.path.insert(0, _PACKAGE_ROOT)
try:
    from drawing import pipeline, plan, roof, sill, stair
finally:
    sys.path.remove(_PACKAGE_ROOT)

HAS_SHAPELY = importlib.util.find_spec("shapely") is not None
FRAME = dict(width=10.0, height=8.0, scale=20.0)   # 10 x 8 m at 1:50


def steps(n=16, going=0.26, rise=0.1765, start_z=-1.45, width=1.0):
    """Upward faces of a straight flight along x, as plan.flights collects them."""
    faces = []
    for i in range(n):
        z = start_z + (i + 1) * rise
        x0, x1 = i * going, (i + 1) * going
        faces.append((z, [(x0, 0.0), (x1, 0.0), (x1, width)]))
        faces.append((z, [(x0, 0.0), (x1, width), (x0, width)]))
    return plan.steps_from_faces(faces)


def drawing(body=""):
    return '<svg data-scale="1:50" viewBox="0 0 200 160"><defs/><g class="target-view-PLANVIEW">%s</g>\n</svg>' % body


class FlightTest(unittest.TestCase):
    def test_straight_flight(self):
        f = plan.straight_flight(steps())
        self.assertEqual(len(f["treads"]), 16)
        self.assertAlmostEqual(f["going"], 0.26)
        self.assertAlmostEqual(f["rise"], 0.1765)
        self.assertAlmostEqual(f["start_z"], -1.45)
        self.assertAlmostEqual(f["eu"][0], 1.0)

    def test_note(self):
        self.assertEqual(plan.flight_note(17, 0.1765, 0.26), "17 Stg. 17,65/26")
        self.assertEqual(plan.flight_note(16, 0.18, 0.275), "16 Stg. 18/27,5")

    def test_cut_at_first_step_above(self):
        f = plan.straight_flight(steps())
        u, span = stair.cut(f)
        above = [t for t in f["treads"] if t[0] > 0]
        self.assertEqual(u, above[0][1])
        self.assertAlmostEqual(span, 2 * f["going"])

    def test_not_cut_below_or_above(self):
        self.assertIsNone(stair.cut(plan.straight_flight(steps(start_z=-4.0))))
        self.assertIsNone(stair.cut(plan.straight_flight(steps(start_z=0.5))))

    def test_lines_drawn_below_dashed_above(self):
        f = plan.straight_flight(steps())
        li = stair.lines(f)
        u_cut = stair.cut(f)[0]
        self.assertTrue(all(min(a[0], b[0]) <= u_cut + 2 * f["going"] + 1e-9 for a, b in li["drawn"]))
        self.assertTrue(all(max(a[0], b[0]) >= u_cut - 1e-9 for a, b in li["dashed"]))
        self.assertEqual(len(li["cut"]), 2)

    def test_apply_replaces_bonsai_groups_and_is_repeatable(self):
        f = plan.straight_flight(steps())
        body = '<g class="IfcStairFlight cut" ifc:guid="1JOSaYvg9QdvPpCuVJHziO"><path d="M0,0 L1,1"/></g>'
        flights = [dict(guid="1JOSaYvg9QdvPpCuVJHziO", name="Lauf & Co", flight=f, note="17 Stg. 17,65/26")]
        once, report = stair.apply(drawing(body), flights, FRAME)
        self.assertNotIn('class="IfcStairFlight cut"', once)
        self.assertIn('class="%s"' % stair.GROUP_CLASS, once)
        self.assertIn('ifc:name="Lauf &amp; Co"', once)          # escaped
        self.assertIn(">17 Stg. 17,65/26</text>", once)
        self.assertIn("cut at step", report[0])
        self.assertEqual(stair.apply(once, flights, FRAME)[0], once)


class SillTest(unittest.TestCase):
    def test_text(self):
        self.assertEqual(plan.sill_text(1.0), "BRH 1.00")
        self.assertEqual(plan.sill_text(1.235), "BRH 1.23⁵")
        self.assertEqual(plan.sill_text(0.6), "BRH 60")
        self.assertEqual(plan.sill_text(-0.15), "BRH -15")

    def test_angle_readable(self):
        self.assertEqual(plan.reading_angle(1, 0), 0.0)
        self.assertEqual(plan.reading_angle(-1, 0), 0.0)
        self.assertEqual(plan.reading_angle(0, 1), 90.0 - 180.0)
        self.assertEqual(plan.reading_angle(0, -1), -90.0)

    def test_position_and_cap_height(self):
        self.assertEqual(plan.cap_height_mm(50), 3.5)
        self.assertEqual(plan.cap_height_mm(100), 2.5)
        x, y = plan.sill_position((10.0, 10.0), (0.0, 5.0), 3.5)
        self.assertAlmostEqual((x, y), (10.0, 10.0 + 1.5 + 1.75))

    def test_apply_repeatable(self):
        sills = [dict(guid="1xtCbt0GjIXRHcGkq7F07s", name="Fenster", x=12.34567, y=8.0, angle=0.0, text="BRH 1.00")]
        once, report = sill.apply(drawing(), sills)
        self.assertIn('transform="translate(12.3457, 8.0) rotate(0.0)"', once)
        self.assertEqual(report, ["Fenster: BRH 1.00"])
        self.assertEqual(sill.apply(once, sills)[0], once)
        self.assertEqual(sill.apply(once, [])[0], drawing())


class RoofTest(unittest.TestCase):
    def test_apply_and_remove(self):
        roofs = dict(outlines=[[(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)]], ridges=[((0, 2.5), (10, 2.5))],
                     message="1 roof outline(s)")
        once, report = roof.apply(drawing(), roofs)
        self.assertIn('id="%s"' % roof.GROUP_ID, once)
        self.assertIn("stroke-dasharray:%s" % roof.DOTS, once)
        self.assertEqual(report, ["1 roof outline(s)"])
        self.assertEqual(roof.apply(once, roofs)[0], once)
        self.assertEqual(roof.apply(once, None)[0], drawing())

    @unittest.skipUnless(HAS_SHAPELY, "shapely not installed")
    def test_ridge(self):
        from shapely.geometry import box
        outline = box(-1, -1, 11, 7)
        gable = [(x, y, 3.0 if y == 3.0 else 0.0) for x in (0, 10) for y in (0.0, 3.0, 6.0)]
        a, b = plan.ridge(gable, outline)
        self.assertAlmostEqual(a[1], 3.0)
        self.assertAlmostEqual(abs(b[0] - a[0]), 10.0)
        flat = [(x, y, 3.0) for x in (0, 10) for y in (0, 6)]
        self.assertIsNone(plan.ridge(flat, outline))        # highest points not on one line
        mono = [(x, y, 3.0 if y == 6 else 0.0) for x in (0, 10) for y in (0, 6)]
        self.assertIsNone(plan.ridge(mono, box(0, 0, 10, 6)))   # the high edge is on the outline


@unittest.skipUnless(HAS_SHAPELY, "shapely not installed")
class PlanPipelineTest(unittest.TestCase):
    def test_second_run_changes_nothing(self):
        f = plan.straight_flight(steps())
        data = dict(frame=FRAME,
                    flights=[dict(guid="1JOSaYvg9QdvPpCuVJHziO", name="Lauf", flight=f, note="17 Stg. 17,65/26")],
                    roofs=dict(outlines=[[(0, 0), (10, 0), (10, 5), (0, 0)]], ridges=[], message="m"),
                    sills=[dict(guid="1xtCbt0GjIXRHcGkq7F07s", name="F", x=1.0, y=2.0, angle=0.0, text="BRH 1.00")])
        once, _ = pipeline.process_text(drawing(), {}, data)
        self.assertEqual(pipeline.process_text(once, {}, data)[0], once)
        self.assertLess(once.find("data-din-brh"), once.find(stair.GROUP_CLASS))
        self.assertLess(once.find(stair.GROUP_CLASS), once.find(roof.GROUP_ID))


if __name__ == "__main__":
    unittest.main()
