# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the preview package: layout file and local server (no Blender).

    python -m unittest discover tests
"""
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

_PACKAGE_ROOT = os.path.join(os.path.dirname(__file__), "..", "bonsai_btk")
sys.path.insert(0, _PACKAGE_ROOT)
try:
    from preview import layout, pages, server
finally:
    sys.path.remove(_PACKAGE_ROOT)

LAYOUT = (
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" id="root" version="1.1" '
    'width="594.0mm" height="420.0mm" viewBox="0 0 594.0 420.0">\n'
    '    <g data-type="titleblock">\n'
    '        <image xlink:href="titleblocks/A2.svg" x="0" y="0" width="594.0" height="420.0" />\n'
    '    </g>\n'
    '<g data-type="drawing" data-id="11" data-drawing="2ZeT0uNobC9wkT6_yh7Gqr">'
    '<image data-type="foreground" xlink:href="..\\drawings\\Ground Floor.svg" x="30.0" y="110.11499786376953" '
    'width="480.0" height="319.77" />'
    '<image data-type="view-title" xlink:href="assets\\view-title.svg" x="30.0" y="434.88500213623047" '
    'width="150.0" height="10.0" /></g>'
    '<g data-type="din-legende" data-x="280.6" data-y="355.75" data-breite="120.4469" data-hoehe="48.0">'
    '<g transform="translate(280.6,355.75)"><text x="0" y="5.0">Legende</text></g></g>'
    '<g data-type="din-nordpfeil" data-x="564.0" data-y="15.0" data-breite="15.0" data-hoehe="22.5">'
    '<g transform="translate(571.5,29.5) rotate(0.0)"><circle r="7.5" /></g></g>'
    '<g data-type="drawing" data-id="12" data-drawing="0MpY9TSfzDTvBey9N589ZT">'
    '<image data-type="foreground" xlink:href="..\\drawings\\Site Plan.svg" x="30.0" y="20.0" '
    'width="240.0" height="160.0" />'
    '<image data-type="view-title" xlink:href="assets\\view-title.svg" x="30.0" y="185.0" '
    'width="150.0" height="10.0" /></g></svg>')


def _write(folder, text=LAYOUT, name="A-01 - Ground Floor.svg"):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


class LayoutReadTest(unittest.TestCase):
    def test_read(self):
        data = layout.read(LAYOUT)
        self.assertEqual((data["width"], data["height"]), (594.0, 420.0))
        self.assertEqual([d["id"] for d in data["drawings"]], ["11", "12", "legend", "north"])
        first = data["drawings"][0]
        self.assertEqual(first["name"], "Ground Floor")
        self.assertEqual(first["guid"], "2ZeT0uNobC9wkT6_yh7Gqr")
        self.assertAlmostEqual(first["title"]["y"], 434.885, places=3)
        self.assertEqual(data["drawings"][2]["drawing"], {"x": 280.6, "y": 355.75, "width": 120.4469, "height": 48.0})
        self.assertNotIn("title", data["drawings"][3])


class LayoutMoveTest(unittest.TestCase):
    def test_title_moves_along(self):
        text, report = layout.move(LAYOUT, {"11": (40.0, 100.0)})
        self.assertIn('data-type="foreground" xlink:href="..\\drawings\\Ground Floor.svg" x="40.0" y="100.0"', text)
        self.assertIn('x="40.0" y="424.77" width="150.0"', text)        # title: same offset
        self.assertIn('x="30.0" y="20.0"', text)                          # the other drawing stays
        self.assertEqual(report, ["reference 11: drawing x 40.0 / y 100.0 · title moved along"])

    def test_title_alone(self):
        text, report = layout.move(LAYOUT, {"12": {"drawing": (30.0, 20.0), "title": (200.0, 185.5)}})
        self.assertIn('x="200.0" y="185.5" width="150.0"', text)
        self.assertIn("title x 200.0 / y 185.5", report[0])

    def test_legend_and_north_arrow(self):
        text, report = layout.move(LAYOUT, {"legend": {"drawing": (300.0, 350.0)}, "north": (560.0, 10.0)})
        self.assertIn('data-type="din-legende" data-x="300.0" data-y="350.0"', text)
        self.assertIn('<g transform="translate(300.0,350.0)">', text)
        self.assertIn('data-type="din-nordpfeil" data-x="560.0" data-y="10.0"', text)
        self.assertIn('translate(567.5,24.5) rotate(0.0)', text)          # circle centre follows
        self.assertEqual(report, ["legend: x 300.0 / y 350.0", "north arrow: x 560.0 / y 10.0"])

    def test_unknown_and_missing(self):
        bare = layout._RE_NORTH.sub("", LAYOUT)
        text, report = layout.move(bare, {"north": (1.0, 1.0), "99": (1.0, 1.0)})
        self.assertEqual(text, bare)
        self.assertEqual(report, ["north arrow not in the layout, skipped", "reference 99 not in the layout, skipped"])

    def test_check_positions(self):
        items = layout.read(LAYOUT)["drawings"]
        self.assertEqual(layout.check_positions({"11": {"drawing": [1, 2], "title": None}}, items),
                         {"11": {"drawing": (1.0, 2.0)}})
        self.assertEqual(layout.check_positions({"north": [3, 4]}, items), {"north": (3.0, 4.0)})
        for bad in ({"99": [1, 2]}, {"11": [1]}, {"11": [float("nan"), 2]}, {"11": [1e6, 2]}, {"11": {"drawing": "x"}}):
            with self.assertRaises(ValueError):
                layout.check_positions(bad, items)


class LayoutWriteTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.path = _write(self.folder)

    def test_changed_file_is_not_written(self):
        old = layout.checksum(self.path)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(" ")
        with self.assertRaises(RuntimeError):
            layout.write(self.path, {"11": (0.0, 0.0)}, old)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "_backup")))

    def test_backup_and_prune(self):
        for i in range(7):
            backup, report = layout.write(self.path, {"11": (float(i), 0.0)}, layout.checksum(self.path),
                                          now=1700000000 + i)
        names = sorted(os.listdir(os.path.join(self.folder, "_backup")))
        self.assertEqual(len(names), layout.BACKUPS_KEPT)
        self.assertTrue(all(n.startswith("A-01 - Ground Floor_") for n in names))
        self.assertTrue(report[-1].startswith("old backup removed: "))
        with open(backup, encoding="utf-8") as f:
            self.assertIn('x="5.0" y="0.0"', f.read())          # the state before the last move
        self.assertEqual(layout.read(open(self.path, encoding="utf-8").read())["drawings"][0]["drawing"]["x"], 6.0)

    def test_prune_leaves_other_files(self):
        folder = os.path.join(self.folder, "_backup")
        os.makedirs(folder)
        for n in ("x_2026-01-01_000000.svg", "A-01 - Ground Floor_2026-01-01_000000.svg",
                  "A-01 - Ground Floor_2026-01-02_000000.svg", "notes.txt"):
            open(os.path.join(folder, n), "w").close()
        self.assertEqual(layout.prune_backups(folder, "A-01 - Ground Floor", keep=1),
                         ["A-01 - Ground Floor_2026-01-01_000000.svg"])
        self.assertEqual(sorted(os.listdir(folder)), ["A-01 - Ground Floor_2026-01-02_000000.svg", "notes.txt",
                                                      "x_2026-01-01_000000.svg"])


class PagesTest(unittest.TestCase):
    def test_pages(self):
        self.assertIn("/drawing.svg", pages.DRAWING_PAGE)
        self.assertIn("/sheet/apply", pages.SHEET_PAGE)
        self.assertIn("GRID = 5.0", pages.SHEET_PAGE)
        self.assertNotIn("%GRID%", pages.SHEET_PAGE)
        page = pages.print_page("A-01 <x>", 594.0, 420.0)
        self.assertIn("size: 594mm 420mm", page)
        self.assertIn("A-01 &lt;x&gt;", page)


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.folder, "layouts"))
        self.layout = _write(os.path.join(self.folder, "layouts"))
        self.sheet = os.path.join(self.folder, "sheet.svg")
        self.drawing = os.path.join(self.folder, "drawing.svg")
        for p in (self.sheet, self.drawing):
            with open(p, "w") as f:
                f.write("<svg/>")
        self.state = server.State()
        self.server = None
        for port in range(18765, 18800):
            try:
                self.server = server.Server(self.state, port)
                break
            except OSError:
                continue
        self.assertIsNotNone(self.server)

    def tearDown(self):
        self.server.stop()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.server.url + path.lstrip("/"), timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def post(self, path, obj):
        request = urllib.request.Request(self.server.url + path.lstrip("/"), data=json.dumps(obj).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_listens_on_loopback_only(self):
        self.assertEqual(self.server.httpd.server_address[0], "127.0.0.1")

    def test_drawing(self):
        self.assertEqual(self.get("/")[0], 200)
        self.assertEqual(self.get("/drawing.svg")[0], 404)
        self.assertFalse(self.state.page_open("drawing"))
        self.state.set_drawing("Ground Floor", self.drawing, ["done"])
        code, body = self.get("/state?t=1")
        self.assertEqual(json.loads(body)["name"], "Ground Floor")
        self.assertTrue(self.state.page_open("drawing"))
        self.assertEqual(self.get("/drawing.svg"), (200, b"<svg/>"))

    def test_print_and_pdf(self):
        self.assertEqual(self.get("/print")[0], 404)
        self.state.set_sheet("A-01 - Ground Floor", 7, self.sheet, self.layout, [])
        code, body = self.get("/print")
        self.assertIn(b"size: 594mm 420mm", body)
        self.assertEqual(self.get("/sheet/pdf")[0], 500)
        self.state.pdf_maker = lambda path: b"%PDF-1.5 " + path.encode("utf-8")
        self.assertEqual(self.get("/sheet/pdf"), (200, b"%PDF-1.5 " + self.sheet.encode("utf-8")))

    def test_apply(self):
        self.state.set_sheet("A-01 - Ground Floor", 7, self.sheet, self.layout, [])
        code, body = self.get("/sheet/state")
        info = json.loads(body)
        self.assertEqual([d["id"] for d in info["drawings"]], ["11", "12", "legend", "north"])
        self.assertEqual(self.post("/sheet/apply", {"layout_sha": info["layout_sha"], "positions": {"99": [1, 2]}}),
                         (400, {"error": "unknown drawing: '99'"}))
        self.assertEqual(self.post("/sheet/apply", {"layout_sha": info["layout_sha"], "positions": {}})[0], 400)
        wish = {"11": {"drawing": [40, 100], "title": None}, "north": {"drawing": [560, 10], "title": None}}
        self.assertEqual(self.post("/sheet/apply", {"layout_sha": info["layout_sha"], "positions": wish}),
                         (202, {"ok": True}))
        self.assertEqual(self.post("/sheet/apply", {"layout_sha": info["layout_sha"], "positions": wish}),
                         (400, {"error": "the sheet is being built"}))
        job = self.state.jobs.get_nowait()
        self.assertEqual((job["kind"], job["sheet_id"]), ("move", 7))
        built = []

        def build(sheet_id):
            built.append(sheet_id)
            time.sleep(0.01)
            with open(self.sheet, "w") as f:
                f.write("<svg>new</svg>")
            return self.sheet, ["sheet built"]

        server.run_move_job(self.state, job, build)
        self.assertEqual(built, [7])
        self.assertFalse(self.state.sheet["building"])
        messages = self.state.sheet["messages"]
        self.assertEqual(messages[0], "reference 11: drawing x 40.0 / y 100.0 · title moved along")
        self.assertTrue(any(m.startswith("backup: layouts") for m in messages))
        self.assertEqual(messages[-1], "sheet built")
        self.assertNotEqual(self.state.sheet["layout_sha"], info["layout_sha"])
        self.assertEqual(self.state.sheet["drawings"][0]["drawing"]["x"], 40.0)
        # the same job again: the layout changed in between, nothing is written
        self.state.sheet["building"] = True
        server.run_move_job(self.state, job, build)
        self.assertTrue(self.state.sheet["messages"][0].startswith("Error: the layout file changed"))
        self.assertFalse(self.state.sheet["building"])
        self.assertEqual(built, [7])


if __name__ == "__main__":
    unittest.main()
