# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the geometry parts that run without Blender.

    python -m unittest discover tests
"""
import importlib.util
import math
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "bonsai_btk")


def _load(name):
    """Load a module on its own, without its Blender part: inside Blender (tests run from
    its Python console) bpy is hidden while loading, so the module takes its plain branch."""
    spec = importlib.util.spec_from_file_location("btk_" + name, os.path.join(ROOT, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    saved = sys.modules.get("bpy", False)
    sys.modules["bpy"] = None          # makes "import bpy" raise ImportError
    try:
        spec.loader.exec_module(module)
    finally:
        if saved is False:
            del sys.modules["bpy"]
        else:
            sys.modules["bpy"] = saved
    return module


snap = _load("snap")
dim = _load("dimension")


class IntersectionTest(unittest.TestCase):
    def test_beyond_edge_ends(self):
        # two short edges whose lines meet outside both of them
        x, y, t = snap.intersect_2d((0, 0), (1, 0), (3, 1), (3, 2))
        self.assertAlmostEqual(x, 3.0)
        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(t, 3.0)

    def test_parallel(self):
        self.assertIsNone(snap.intersect_2d((0, 0), (1, 0), (0, 1), (1, 1)))


class ChainTest(unittest.TestCase):
    def test_scale(self):
        self.assertAlmostEqual(dim.scale_ratio("1/50"), 0.02)
        self.assertAlmostEqual(dim.scale_ratio("1:100"), 0.01)

    def test_grid(self):
        # 1:50, 0.37 m = 7.4 mm on the sheet -> 5 mm = 0.25 m
        self.assertAlmostEqual(dim.snap_to_grid(0.37, 0.02), 0.25)

    def test_chain_sorted_and_projected(self):
        pts = [(0, 0), (4, 0), (1.5, 0.3), (4, 0.0000001)]
        chain = dim.chain_from_points(pts, 1, 0.5)
        self.assertEqual([round(x, 6) for x, _ in chain], [0, 1.5, 4])
        self.assertTrue(all(math.isclose(y, 0.5) for _, y in chain))

    def test_side(self):
        self.assertEqual(dim.side_and_offset([(0, 0), (1, 0)], (0.5, -2))[0], -1)

    def test_flip(self):
        self.assertTrue(dim.needs_flip([(4, 0), (0, 0)]))
        self.assertFalse(dim.needs_flip([(0, 0), (0, 3)]))
        self.assertEqual(dim.reverse_segments([("IfcLineIndex", (1, 2)), ("IfcLineIndex", (2, 3))], 3),
                         [("IfcLineIndex", (1, 2)), ("IfcLineIndex", (2, 3))])

    def test_shift_on_scale_change(self):
        self.assertAlmostEqual(dim.shift_m(10, "1/50", "1/100"), 0.5)

    def test_typed_input(self):
        s = ""
        for c in "12,5":
            s = dim.type_input(s, c)
        self.assertEqual(dim.number(s), 12.5)


if __name__ == "__main__":
    unittest.main()
