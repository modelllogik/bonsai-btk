# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A sheet as PDF, made by Inkscape.

Browsers rasterise SVG patterns when they print: the hatching comes out grey and
stepped. Inkscape writes them as vectors, keeps the real hatching lines as lines and
embeds the fonts. So a sheet is printed through Inkscape (1.x, command line).

Inkscape is an external program. It is found, in this order: the path set in the
add-on preferences, the search path (``inkscape``), the usual install folders.

The PDF is written where the user asks for it. While Inkscape runs it goes to a
temporary folder first, so that a failed run leaves nothing half written behind.

No bpy here.
"""
import os
import shutil
import subprocess
import tempfile

CANDIDATES = (r"C:\Program Files\Inkscape\bin\inkscape.com",
              r"C:\Program Files\Inkscape\bin\inkscape.exe",
              r"C:\Program Files (x86)\Inkscape\bin\inkscape.com",
              r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
              "/Applications/Inkscape.app/Contents/MacOS/inkscape",
              "/usr/bin/inkscape",
              "/usr/local/bin/inkscape",
              "/snap/bin/inkscape")
TIMEOUT = 300   # s; an A3 sheet takes about 5 s


def find_inkscape(configured=""):
    """Path of the Inkscape executable, or None."""
    if configured:
        path = os.path.expanduser(configured)
        return path if os.path.isfile(path) else None
    found = shutil.which("inkscape")
    if found:
        return found
    return next((c for c in CANDIDATES if os.path.isfile(c)), None)


def sheet_pdf(sheet_svg, pdf_path, inkscape):
    """Export sheet_svg to pdf_path with the given Inkscape. Raises RuntimeError."""
    if not inkscape:
        raise RuntimeError("Inkscape not found; set its path in the add-on preferences")
    folder = tempfile.mkdtemp(prefix="bonsai_btk_pdf_")
    target = os.path.join(folder, "sheet.pdf")
    try:
        run = subprocess.run([inkscape, "--export-type=pdf", "--export-filename=" + target, sheet_svg],
                             capture_output=True, text=True, timeout=TIMEOUT)
        if run.returncode != 0 or not os.path.exists(target):
            message = (run.stderr or run.stdout or "").strip()[:300]
            raise RuntimeError("Inkscape: %s" % (message or "no PDF written"))
        os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
        shutil.move(target, pdf_path)
        return pdf_path
    finally:
        shutil.rmtree(folder, ignore_errors=True)
