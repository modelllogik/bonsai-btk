# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Preview of drawings and sheets in the web browser, and arranging a sheet there.

Bonsai shows a drawing in the 3D view, not as it will print. The preview shows the
post-processed SVG of the active drawing, or the built sheet, in the browser at
http://127.0.0.1:<port>/ and reloads it by itself after every update. On the sheet
page the drawings, their view titles, the legend and the north arrow can be moved
with the mouse (5 mm grid, Alt = free, snapping to two guide lines that exist only
in the browser) and the new positions applied: they are written to the layout file
of the sheet (with a backup) and the sheet is built again.

    layout   reading the layout file, writing new positions, backups
    server   the local HTTP server (127.0.0.1 only) and the state it serves
    pages    the HTML pages

The server only listens on 127.0.0.1. It runs in a thread; everything that touches
Blender or the IFC is handed to Blender's main thread as a job (operators.py runs
them from a timer). None of these modules imports bpy.
"""
