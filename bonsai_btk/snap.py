# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Intersection snap: the intersection of two edges as a snap point (key S).

Used by the point-picking tools of this add-on (so far: the dimension chain).

    S              toggle intersection snap
    1st click      on an edge
    2nd click      on a second edge -> the intersection of the two infinite LINES
                   (also beyond the edge ends) is taken like a snapped point
    Backspace      removes the first edge again

The typical case is a point that does not exist in the drawing, for example the eaves
point where the outer face of a wall meets the outer face of the roof build-up. In CAD
this is done with tracking lines; here the 3D view shows them while snapping (blue,
extended across the view) together with the intersection (orange).

Edges are taken from the meshes of the visible elements whose screen rectangle is under
the mouse: the edge closest to the mouse in screen space, at most SNAP_PX pixels away.
Edges that collapse to a point in the drawing plane (vertical edges in a plan) and edges
outside the drawing's clipping planes are skipped. The intersection is computed in the
drawing plane; its depth comes from the first edge.

The module also provides vertex snapping from the meshes (vertices_under_mouse), which
the dimension chain uses when intersection snap is off.

Snapping does not call Bonsai's own snap detection on every mouse move. Its result was
not needed here, and in a plan with about 130 elements it took about 100 ms per mouse
move (Bonsai 0.9.1-alpha261106), which made the tools feel slow.

A tool that uses this module provides these attributes on its operator:
    phase          snapping is active while phase is in PHASES
    image_region   the WINDOW region of the 3D view
    rv3d           its RegionView3D
    camera         the active drawing camera
    current, snap_type   set here when an intersection is found
    status(context)      redraws the header text
"""

PHASES = {"PICK"}       # operator phases in which snapping is active
FAR = 200.0             # extend tracking lines by this much in each direction (m)
SHORT = 1e-4            # shorter than this in the drawing plane = not an edge (m)
SNAP_PX = 12.0          # an edge or vertex must be this close to the mouse (pixels)


def intersect_2d(a0, a1, b0, b1):
    """Intersection of two lines in the plane -> (x, y, t along a) or None if parallel."""
    dax, day = a1[0] - a0[0], a1[1] - a0[1]
    dbx, dby = b1[0] - b0[0], b1[1] - b0[1]
    n = dax * dby - day * dbx
    la = (dax * dax + day * day) ** 0.5
    lb = (dbx * dbx + dby * dby) ** 0.5
    if la < 1e-12 or lb < 1e-12 or abs(n) < 1e-9 * la * lb:
        return None
    t = ((b0[0] - a0[0]) * dby - (b0[1] - a0[1]) * dbx) / n
    return a0[0] + t * dax, a0[1] + t * day, t


try:
    import bpy
except ImportError:
    bpy = None

if bpy is not None:
    from mathutils import Vector

    def mouse(op, event):
        """Mouse position relative to the operator's image region."""
        r = getattr(op, "image_region", None)
        if r is None:
            return None
        return (event.mouse_x - r.x, event.mouse_y - r.y)

    def _clipped(world_point):
        """True if the point lies outside the clipping planes of the active drawing."""
        try:
            import bonsai.tool as tool
            return not tool.Raycast.point_is_visible_in_clipping_plane(world_point)
        except Exception:
            return False

    def _meshes_near(op, mouse_xy):
        """Visible meshes whose screen rectangle is within SNAP_PX of the mouse."""
        region, rv3d = getattr(op, "image_region", None), getattr(op, "rv3d", None)
        if mouse_xy is None or region is None or rv3d is None:
            return []
        mx, my = mouse_xy
        return [o for o, box in _visible_meshes(op, region, rv3d)
                if box[0] - SNAP_PX <= mx <= box[1] + SNAP_PX and box[2] - SNAP_PX <= my <= box[3] + SNAP_PX]

    def edge_under_mouse(op, mouse_xy):
        """World end points of the mesh edge closest to the mouse, or None.

        The edge is looked up in the meshes themselves: in a plan, the edge vertices
        reported with Bonsai's "Edge" snap point were not usable for this (Bonsai 0.9.1)."""
        from bpy_extras import view3d_utils
        region, rv3d, camera = getattr(op, "image_region", None), getattr(op, "rv3d", None), getattr(op, "camera", None)
        objects = _meshes_near(op, mouse_xy)
        if not objects:
            return None
        inv = camera.matrix_world.inverted() if camera is not None else None
        mx, my = mouse_xy
        best, best_d = None, SNAP_PX
        for o in objects:
            try:
                me, mw = o.data, o.matrix_world
                world = [mw @ v.co for v in me.vertices]
            except ReferenceError:
                continue
            screen = [view3d_utils.location_3d_to_region_2d(region, rv3d, w) for w in world]
            plane = [inv @ w for w in world] if inv is not None else None
            clipped = {}
            for e in me.edges:
                i, j = e.vertices
                if plane is not None:
                    pa, pb = plane[i], plane[j]
                    if ((pa.x - pb.x) ** 2 + (pa.y - pb.y) ** 2) ** 0.5 < SHORT:
                        continue
                a, b = screen[i], screen[j]
                if a is None or b is None:
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                l2 = dx * dx + dy * dy
                if l2 < 1e-6:
                    continue
                s = max(0.0, min(1.0, ((mx - a.x) * dx + (my - a.y) * dy) / l2))
                d = ((a.x + s * dx - mx) ** 2 + (a.y + s * dy - my) ** 2) ** 0.5
                if d >= best_d:
                    continue
                for k in (i, j):
                    if k not in clipped:
                        clipped[k] = _clipped(world[k])
                if clipped[i] and clipped[j]:   # edge entirely outside the drawing's clipping planes
                    continue
                best, best_d = (world[i].copy(), world[j].copy()), d
        return best

    def intersect(camera, e1, e2):
        """Intersection of two world edges in the drawing plane of the camera, in world space."""
        inv = camera.matrix_world.inverted()
        a0, a1 = inv @ e1[0], inv @ e1[1]
        b0, b1 = inv @ e2[0], inv @ e2[1]
        s = intersect_2d(a0, a1, b0, b1)
        if s is None:
            return None
        x, y, t = s
        z = a0.z + t * (a1.z - a0.z)
        return camera.matrix_world @ Vector((x, y, z))

    def _state(op):
        z = getattr(op, "btk_track", None)
        if z is None:
            z = dict(active=False, edges=[])
            op.btk_track = z
        return z

    def is_active(op):
        return bool((getattr(op, "btk_track", None) or {}).get("active"))

    def handle_event(op, context, event):
        """Call at the start of modal(). Returns a return value for modal(), or None to
        continue normally (after a finished intersection it is already in op.current)."""
        if getattr(op, "phase", None) not in PHASES:
            return None
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            op.btk_mouse = mouse(op, event)
            return None
        if event.value != "PRESS":
            return None
        z = _state(op)
        if event.type == "S" and not (event.ctrl or event.alt or event.shift):
            z["active"], z["edges"] = not z["active"], []
            op.status(context)
            return {"RUNNING_MODAL"}
        if not z["active"]:
            return None
        if event.type == "BACK_SPACE":
            if z["edges"]:
                z["edges"].pop()
            else:
                z["active"] = False
            op.status(context)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE":
            edge = edge_under_mouse(op, mouse(op, event))
            if edge is None:
                op.report({"WARNING"}, "Intersection: no edge under the mouse, move closer to an edge")
                op.status(context)
                return {"RUNNING_MODAL"}
            z["edges"].append(edge)
            if len(z["edges"]) < 2:
                op.status(context)
                return {"RUNNING_MODAL"}
            p = intersect(op.camera, *z["edges"])
            z["active"], z["edges"] = False, []
            if p is None:
                op.report({"WARNING"}, "Intersection: the two edges are parallel")
                op.status(context)
                return {"RUNNING_MODAL"}
            op.current, op.snap_type = p, "Intersection"
            return None   # continue normally: the click takes op.current
        return None

    def hint(op):
        """Text appended to the tool's header line."""
        if getattr(op, "phase", None) not in PHASES:
            return ""
        z = _state(op)
        if not z["active"]:
            return "  ·  S = intersection of two edges"
        return "  ·  INTERSECTION: click edge %d · Backspace = back · S = off" % (len(z["edges"]) + 1)

    def draw(op, px, lines, square):
        """Call from the tool's draw handler: tracking lines and the intersection."""
        if getattr(op, "phase", None) not in PHASES:
            return
        z = _state(op)
        if not z["active"]:
            return
        blue, orange = (0.1, 0.55, 1.0, 1.0), (1.0, 0.45, 0.0, 1.0)
        edges = list(z["edges"])
        now = edge_under_mouse(op, getattr(op, "btk_mouse", None))
        if now is not None:
            edges.append(now)
        for a, b in edges:
            d = b - a
            if d.length < 1e-9:
                continue
            d.normalize()
            lines([px(a - d * FAR), px(b + d * FAR)], blue, 1.0)
        if len(edges) >= 2:
            p = intersect(op.camera, edges[0], edges[1])
            if p is not None:
                square(p, orange, 6)

    def _visible_meshes(op, region, rv3d):
        """Visible meshes with their screen rectangle, computed once per view.

        Bonsai's own list of on-screen bounding boxes left out some walls in a plan
        (tested with Bonsai 0.9.1), so the rectangles are computed here."""
        from bpy_extras import view3d_utils
        key = (tuple(rv3d.view_matrix.col[3]), rv3d.view_distance, tuple(rv3d.view_camera_offset), rv3d.view_camera_zoom)
        if getattr(op, "btk_meshes_key", None) == key and getattr(op, "btk_meshes", None) is not None:
            return op.btk_meshes
        meshes = []
        for o in bpy.context.view_layer.objects:
            try:
                if o.type != "MESH" or not o.visible_get() or not len(o.data.vertices):
                    continue
                mw = o.matrix_world
                ps = [view3d_utils.location_3d_to_region_2d(region, rv3d, mw @ Vector(c)) for c in o.bound_box]
                ps = [p for p in ps if p is not None]
                if not ps:
                    continue
                meshes.append((o, (min(p.x for p in ps), max(p.x for p in ps), min(p.y for p in ps), max(p.y for p in ps))))
            except ReferenceError:
                continue
        op.btk_meshes, op.btk_meshes_key = meshes, key
        return meshes

    def vertices_under_mouse(op, mouse_xy):
        """Mesh vertices of visible elements near the mouse, sorted by screen distance
        (at most SNAP_PX). Vertices outside the drawing's clipping planes are skipped.
        Returns [(world point, object), ...]."""
        import bonsai.tool as tool
        from bpy_extras import view3d_utils
        if mouse_xy is None:
            return []
        region, rv3d = getattr(op, "image_region", None), getattr(op, "rv3d", None)
        if region is None or rv3d is None:
            return []
        mx, my = mouse_xy
        found = {}
        for o, box in _visible_meshes(op, region, rv3d):
            if not (box[0] - SNAP_PX <= mx <= box[1] + SNAP_PX and box[2] - SNAP_PX <= my <= box[3] + SNAP_PX):
                continue
            try:
                mw = o.matrix_world
                for v in o.data.vertices:
                    w = mw @ v.co
                    p = view3d_utils.location_3d_to_region_2d(region, rv3d, w)
                    if p is None:
                        continue
                    dd = ((p.x - mx) ** 2 + (p.y - my) ** 2) ** 0.5
                    if dd > SNAP_PX:
                        continue
                    try:
                        if not tool.Raycast.point_is_visible_in_clipping_plane(w):
                            continue
                    except Exception:
                        pass
                    k = (round(p.x), round(p.y))
                    if k not in found or found[k][0] > dd:
                        found[k] = (dd, w.copy(), o)
            except ReferenceError:
                continue
        return [(w, o) for dd, w, o in sorted(found.values(), key=lambda x: x[0])]


def register():
    pass


def unregister():
    pass
