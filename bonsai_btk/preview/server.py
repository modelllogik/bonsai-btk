# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The local preview server.

One server per Blender session, on 127.0.0.1 only. It serves three pages and the
state behind them:

    GET  /               drawing page          GET  /sheet          sheet page
    GET  /state          state of the drawing  GET  /sheet/state    state of the sheet
    GET  /drawing.svg    the drawing           GET  /sheet.svg      the sheet
                                               GET  /sheet/pdf      the sheet as PDF (Inkscape)
                                               GET  /print          print page (browser)
    POST /sheet/apply    new positions for the sheet: {layout_sha, positions}

The server thread never touches Blender. POST /sheet/apply only checks the request
and puts a job into ``State.jobs``; Blender's main thread takes it from there
(operators.py), writes the layout and builds the sheet. The pages poll the state
once a second and reload when it changes.

No bpy.
"""
import json
import os
import queue
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import layout, pages

MAX_REQUEST = 100000   # bytes


class State:
    """What the pages show. Written by Blender's main thread, read by the server."""

    def __init__(self):
        self.drawing = {"name": "", "path": "", "mtime": 0, "time": "", "messages": []}
        self.sheet = {"name": "", "sheet_id": 0, "path": "", "layout": "", "layout_sha": "", "mtime": 0,
                      "time": "", "width": 0.0, "height": 0.0, "drawings": [], "messages": [], "building": False}
        self.jobs = queue.Queue()
        self.last_poll = {"drawing": 0.0, "sheet": 0.0}
        self.pdf_maker = None    # callable(sheet svg path) -> PDF bytes

    def set_drawing(self, name, path, messages):
        self.drawing.update(name=name, path=path, mtime=os.path.getmtime(path), time=time.strftime("%H:%M:%S"),
                            messages=list(messages))

    def set_sheet(self, name, sheet_id, path, layout_path, messages):
        with open(layout_path, encoding="utf-8", newline="") as f:
            info = layout.read(f.read())
        self.sheet.update(name=name, sheet_id=sheet_id, path=path, layout=layout_path,
                          layout_sha=layout.checksum(layout_path), mtime=os.path.getmtime(path),
                          time=time.strftime("%H:%M:%S"), width=info["width"], height=info["height"],
                          drawings=info["drawings"], messages=list(messages), building=False)

    def page_open(self, kind, within=3.0):
        """Has a page of this kind asked for its state in the last seconds?"""
        return time.time() - self.last_poll[kind] < within


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, kind, data, extra=()):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code, obj):
            self._send(code, "application/json; charset=utf-8", json.dumps(obj).encode("utf-8"))

        def _text(self, code, text):
            self._send(code, "text/plain; charset=utf-8", text.encode("utf-8"))

        def _file(self, path, kind):
            with open(path, "rb") as f:
                self._send(200, kind, f.read())

        def do_GET(self):
            path = self.path.split("?")[0]
            s, d = state.sheet, state.drawing
            if path == "/":
                self._send(200, "text/html; charset=utf-8", pages.DRAWING_PAGE.encode("utf-8"))
            elif path == "/state":
                state.last_poll["drawing"] = time.time()
                self._json(200, {k: d[k] for k in ("name", "mtime", "time", "messages")})
            elif path == "/drawing.svg" and d["path"] and os.path.exists(d["path"]):
                self._file(d["path"], "image/svg+xml")
            elif path == "/sheet":
                self._send(200, "text/html; charset=utf-8", pages.SHEET_PAGE.encode("utf-8"))
            elif path == "/sheet/state":
                state.last_poll["sheet"] = time.time()
                self._json(200, {k: s[k] for k in ("name", "mtime", "time", "width", "height", "drawings",
                                                   "messages", "layout_sha", "building")})
            elif path == "/sheet.svg" and s["path"] and os.path.exists(s["path"]):
                self._file(s["path"], "image/svg+xml")
            elif path in ("/sheet/pdf", "/print"):
                if not (s["path"] and os.path.exists(s["path"])):
                    return self._text(404, "No sheet built yet: Preview Sheet first.")
                if path == "/print":
                    return self._send(200, "text/html; charset=utf-8",
                                      pages.print_page(s["name"] or "Sheet", s["width"], s["height"]).encode("utf-8"))
                if state.pdf_maker is None:
                    return self._text(500, "No PDF export available.")
                try:
                    data = state.pdf_maker(s["path"])
                except Exception as error:
                    return self._text(500, "PDF not written: %s" % error)
                name = re.sub(r"[^\w .\-]", "_", str(s["name"] or "Sheet"))
                self._send(200, "application/pdf", data, [("Content-Disposition", 'inline; filename="%s.pdf"' % name)])
            else:
                self._text(404, "not found")

        def do_POST(self):
            if self.path.split("?")[0] != "/sheet/apply":
                return self._text(404, "not found")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_REQUEST:
                    raise ValueError("request too large")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if state.sheet["building"]:
                    raise ValueError("the sheet is being built")
                positions = layout.check_positions(data.get("positions"), state.sheet["drawings"])
                if not positions:
                    raise ValueError("no change")
            except Exception as error:
                return self._json(400, {"error": str(error)})
            state.sheet["building"] = True
            state.jobs.put({"kind": "move", "sheet_id": state.sheet["sheet_id"], "layout": state.sheet["layout"],
                            "layout_sha": str(data.get("layout_sha", "")), "positions": positions})
            self._json(202, {"ok": True})

    return Handler


class Server:
    """The HTTP server in a daemon thread."""

    def __init__(self, state, port):
        self.state = state
        self.port = port
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return "http://127.0.0.1:%d/" % self.port

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def run_move_job(state, job, build):
    """In Blender's main thread: back up and write the layout, then build(sheet_id) ->
    (sheet path, report). The result goes into state.sheet; errors into its messages."""
    messages = []
    try:
        if job["sheet_id"] != state.sheet["sheet_id"]:
            raise RuntimeError("another sheet is loaded; nothing written")
        backup, report = layout.write(job["layout"], job["positions"], job["layout_sha"])
        messages += report + ["backup: " + os.path.relpath(backup, os.path.dirname(os.path.dirname(job["layout"])))]
        path, report = build(job["sheet_id"])
        messages += report
        state.set_sheet(state.sheet["name"], job["sheet_id"], path, job["layout"], messages)
    except Exception as error:
        state.sheet["messages"] = ["Error: %s" % error]
    finally:
        state.sheet["building"] = False
