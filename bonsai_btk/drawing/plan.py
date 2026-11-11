# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a plan needs from the model: stairs, roofs and beams above, sill heights.

Bonsai draws a stair flight in plan as a cut slab, does not draw the roof above a
floor plan, and writes no sill height. The text steps for that (stair.py, roof.py,
sill.py) need geometry from the model, seen from the camera of the drawing. This
module computes it and returns plain data (lists, dictionaries, numbers), so that
the text steps can be tested without a model.

Everything is computed from the IFC: the placement of the drawing's camera, the
viewBox and scale of its SVG, and the element geometry from ifcopenshell.geom. Only
plan views (EPset_Drawing.TargetView = PLAN_VIEW) are read.

Camera coordinates: x to the right, y up on the sheet, z towards the viewer; the
cut plane of a plan is z = 0. Sheet coordinates: mm, y down, as in the SVG.

Needs numpy and IfcOpenShell (with Bonsai); shapely for roofs. No bpy.
"""
import math
import re

ANNOTATION_DEPTH = 2.0      # m: the stair note only where the first step is at most this far below the cut
BEAM_TYPES = ("BEAM", "T_BEAM", "SPANDREL", "HOLLOWCORE", None, "USERDEFINED", "NOTDEFINED")  # no JOIST, LINTEL
SLAB_TOUCH = 0.03           # m: a beam touches a floor slab (downstand above, upstand below)
ROOF_GAP = 0.05             # m: gaps between roof slabs up to this width are closed
OWN_STOREY_ROOFS = True     # roofs of the plan's own storey entirely above the cut (carport)
RIDGE_HEIGHT = 0.02         # m, height range of the ridge points
RIDGE_INSIDE = 0.10         # m, the middle of the ridge at least this far inside the outline
RIDGE_WIDTH = 0.15          # m, the highest points may scatter this much across (joint between the slopes)

_RE_VIEWBOX = re.compile(r'viewBox="([^"]+)"')
_RE_SCALE = re.compile(r'data-scale="1:(\d+(?:\.\d+)?)"')


# ------------------------------------------------------------------ frame

def frame(ifc, svg_text, name):
    """dict(drawing, matrix, inverse, width, height, scale) for the drawing called name,
    or None if there is no such plan view. width and height in m, scale in sheet mm
    per model m."""
    import numpy as np
    import ifcopenshell.util.element as util
    import ifcopenshell.util.placement as placement
    drawing = next((a for a in ifc.by_type("IfcAnnotation")
                    if a.ObjectType == "DRAWING" and a.Name == name), None)
    if drawing is None:
        return None
    if (util.get_pset(drawing, "EPset_Drawing") or {}).get("TargetView") != "PLAN_VIEW":
        return None
    head = svg_text[:2000]
    box, scale = _RE_VIEWBOX.search(head), _RE_SCALE.search(head)
    if not box or not scale:
        return None
    _, _, w, h = (float(z) for z in box.group(1).split())
    sk = 1000.0 / float(scale.group(1))
    get = getattr(placement, "get_placement", None) or placement.get_local_placement
    matrix = np.array(get(drawing.ObjectPlacement), dtype=float)
    return dict(drawing=drawing, matrix=matrix, inverse=np.linalg.inv(matrix),
                width=w / sk, height=h / sk, scale=sk)


def to_sheet(f, x, y):
    """Camera (m) to sheet (mm)."""
    return (float((f["width"] / 2 + x) * f["scale"]), float((f["height"] / 2 - y) * f["scale"]))


def _settings():
    import ifcopenshell.geom
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    return s


def _mesh(f, settings, element):
    """(vertices in camera coordinates, faces) of an element."""
    import numpy as np
    import ifcopenshell.geom
    shape = ifcopenshell.geom.create_shape(settings, element)
    v = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
    v = (np.c_[v, np.ones(len(v))] @ f["inverse"].T)[:, :3]
    return v, np.array(shape.geometry.faces).reshape(-1, 3)


def storey_of(element):
    """The container of an element, also through its aggregate (a roof slab in a roof)."""
    import ifcopenshell.util.element as util
    while element is not None:
        container = util.get_container(element)
        if container is not None:
            return container
        element = util.get_aggregate(element)
    return None


# ------------------------------------------------------------------ stairs

def steps_from_faces(faces, tolerance=0.003):
    """faces: [(z, [(x, y), ...])] of upward faces in camera coordinates ->
    [(z, points)] per step, by height, equal heights joined."""
    groups = []
    for z, points in sorted(faces, key=lambda t: t[0]):
        if groups and abs(groups[-1][0] - z) < tolerance:
            groups[-1][1].extend(points)
        else:
            groups.append([z, list(points)])
    return [(z, p) for z, p in groups]


def straight_flight(steps):
    """A straight flight from its steps, or None. u runs from the first to the last
    step, v across; everything in camera coordinates (m).

    dict(o, eu, ev, treads=[(z, u0, u1)], vmin, vmax, going, rise, start_u, end_u, start_z)
    """
    if len(steps) < 2:
        return None

    def centre(p):
        return (sum(q[0] for q in p) / len(p), sum(q[1] for q in p) / len(p))
    a, b = centre(steps[0][1]), centre(steps[-1][1])
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    if n < 1e-6:
        return None
    eu = (dx / n, dy / n)
    ev = (-eu[1], eu[0])
    o = a

    def uv(q):
        rx, ry = q[0] - o[0], q[1] - o[1]
        return rx * eu[0] + ry * eu[1], rx * ev[0] + ry * ev[1]
    treads, vmin, vmax = [], None, None
    for z, p in steps:
        us = [uv(q) for q in p]
        u0, u1 = min(t[0] for t in us), max(t[0] for t in us)
        v0, v1 = min(t[1] for t in us), max(t[1] for t in us)
        vmin = v0 if vmin is None else min(vmin, v0)
        vmax = v1 if vmax is None else max(vmax, v1)
        treads.append((z, u0, u1))
    depths = sorted(t[2] - t[1] for t in treads)
    going = depths[len(depths) // 2]
    heights = [treads[i + 1][0] - treads[i][0] for i in range(len(treads) - 1)]
    rise = sorted(heights)[len(heights) // 2]
    return dict(o=o, eu=eu, ev=ev, treads=treads, vmin=vmin, vmax=vmax, going=going, rise=rise,
                start_u=treads[0][1], end_u=treads[-1][2], start_z=treads[0][0] - rise)


def _number_de(value, digits=2):
    return ("%.*f" % (digits, value)).rstrip("0").rstrip(".").replace(".", ",")


def flight_note(risers, rise_m, going_m):
    """'17 Stg. 17,65/26': number of risers, rise and going in cm, as written on German plans."""
    return "%d Stg. %s/%s" % (risers, _number_de(rise_m * 100), _number_de(going_m * 100))


def flights(ifc, f, svg_text):
    """[dict(guid, name, flight, note)] for the stair flights Bonsai put into this drawing."""
    import numpy as np
    import ifcopenshell.util.element as util
    settings = _settings()
    result = []
    for element in ifc.by_type("IfcStairFlight"):
        if element.GlobalId not in svg_text:
            continue
        try:
            v, faces = _mesh(f, settings, element)
        except Exception:
            continue
        upward = []
        for a, b, c in faces:
            normal = np.cross(v[b] - v[a], v[c] - v[a])
            length = np.linalg.norm(normal)
            if length < 1e-12 or normal[2] / length < 0.99:
                continue
            upward.append((float(v[a, 2]), [tuple(v[i, :2]) for i in (a, b, c)]))
        flight = straight_flight(steps_from_faces(upward))
        if flight is None:
            continue
        note = None
        if flight["start_z"] > -ANNOTATION_DEPTH:
            pset = util.get_pset(element, "Pset_StairFlightCommon") or {}
            risers = pset.get("NumberOfRiser") or (len(flight["treads"]) + 1)
            rise = pset.get("RiserHeight") or flight["rise"]
            going = pset.get("TreadLength") or flight["going"]
            note = flight_note(int(round(risers)), rise, going)
        result.append(dict(guid=element.GlobalId, name=element.Name or "", flight=flight, note=note))
    return result


# ------------------------------------------------------------------ roofs and beams

def ridge(points, outline, height=RIDGE_HEIGHT, inside=RIDGE_INSIDE):
    """Highest points (x, y, z) -> segment ((x, y), (x, y)) of the ridge, or None. A
    ridge is a line: all highest points near one axis (a flat roof has none), inside
    the outline (an eave or a mono-pitch edge on the outline is no ridge)."""
    from shapely.geometry import Point
    if not points:
        return None
    zmax = max(p[2] for p in points)
    top = [(p[0], p[1]) for p in points if p[2] > zmax - height]
    if len(top) < 2:
        return None
    a, b, d = None, None, 0.0
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            dd = math.hypot(top[i][0] - top[j][0], top[i][1] - top[j][1])
            if dd > d:
                a, b, d = top[i], top[j], dd
    if d < 0.2:
        return None
    mx = sum(p[0] for p in top) / len(top)
    my = sum(p[1] for p in top) / len(top)
    sxx = sum((p[0] - mx) ** 2 for p in top)
    syy = sum((p[1] - my) ** 2 for p in top)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in top)
    phi = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ux, uy = math.cos(phi), math.sin(phi)
    a = (mx, my)
    across = [(p[0] - a[0]) * uy - (p[1] - a[1]) * ux for p in top]
    along = [(p[0] - a[0]) * ux + (p[1] - a[1]) * uy for p in top]
    if max(across) - min(across) > RIDGE_WIDTH:
        return None
    q = sum(across) / len(across)
    a = (a[0] + min(along) * ux + q * uy, a[1] + min(along) * uy - q * ux)
    b = (a[0] + (max(along) - min(along)) * ux, a[1] + (max(along) - min(along)) * uy)
    m = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if not outline.contains(m) or outline.exterior.distance(m) < inside:
        return None
    return a, b


def _footprint(v, faces):
    from shapely.geometry import Polygon
    result = []
    for a, b, c in faces:
        p = Polygon([tuple(v[a, :2]), tuple(v[b, :2]), tuple(v[c, :2])])
        if p.is_valid and p.area > 1e-8:
            result.append(p)
    return result


def roofs(ifc, f):
    """dict(outlines=[[ring], ...], ridges=[((x, y), (x, y))], message) in sheet mm, or None.

    Dotted in a plan (DIN 1356-1, edges above the cut): the roof slabs of the storey
    above, roof slabs of the own storey entirely above the cut (carport), and
    downstand and upstand beams of the own storey entirely above the cut that touch a
    floor slab (purlins of a carport are no downstand beams)."""
    from shapely.ops import unary_union
    import ifcopenshell.util.element as util
    camera_z = f["matrix"][2, 3]
    storeys = sorted(ifc.by_type("IfcBuildingStorey"), key=lambda s: s.Elevation or 0.0)
    below = [s for s in storeys if (s.Elevation or 0.0) <= camera_z + 1e-6]
    if not below:
        return None
    own = below[-1]
    i = storeys.index(own)
    above = storeys[i + 1] if i + 1 < len(storeys) else None
    settings = _settings()
    slabs = []
    for element in ifc.by_type("IfcSlab"):
        if util.get_predefined_type(element) != "ROOF":
            continue
        storey = storey_of(element)
        try:
            v, faces = _mesh(f, settings, element)
        except Exception:
            continue
        if above is not None and storey == above:
            pass
        elif OWN_STOREY_ROOFS and storey == own and v[:, 2].min() > 0:
            pass
        else:
            continue
        triangles = _footprint(v, faces)
        if triangles:
            slabs.append((unary_union(triangles).buffer(0.002).buffer(-0.002), [tuple(q) for q in v]))
    floors = []
    for element in ifc.by_type("IfcSlab"):
        if util.get_predefined_type(element) != "FLOOR":
            continue
        try:
            v, faces = _mesh(f, settings, element)
        except Exception:
            continue
        triangles = _footprint(v, faces)
        if triangles:
            floors.append((v[:, 2].min(), v[:, 2].max(), unary_union(triangles)))
    beams = []
    for element in ifc.by_type("IfcBeam"):
        if util.get_predefined_type(element) not in BEAM_TYPES or storey_of(element) != own:
            continue
        try:
            v, faces = _mesh(f, settings, element)
        except Exception:
            continue
        if v[:, 2].min() <= 0:
            continue
        triangles = _footprint(v, faces)
        if triangles:
            u = unary_union(triangles).buffer(0.002).buffer(-0.002).simplify(0.003)
            z_low, z_high = v[:, 2].min(), v[:, 2].max()
            if not any((abs(z_high - fz_low) < SLAB_TOUCH or abs(z_low - fz_high) < SLAB_TOUCH) and fpoly.intersects(u)
                       for fz_low, fz_high, fpoly in floors):
                continue
            beams += list(u.geoms) if hasattr(u, "geoms") else [u]
    if not slabs and not beams:
        return None
    outlines, ridges = [], []
    if slabs:
        whole = unary_union([s[0] for s in slabs]).buffer(ROOF_GAP).buffer(-ROOF_GAP)
        outlines = list(whole.geoms) if hasattr(whole, "geoms") else [whole]
        outlines = [u.simplify(0.003) for u in outlines if u.area > 0.05]
        for u in outlines:
            points = [q for poly, pts in slabs if poly.intersects(u) for q in pts]
            r = ridge(points, u)
            if r:
                ridges.append(r)
    message = "%d roof outline(s), %d ridge(s), %d downstand/upstand beam(s), storey %s, above %s" % (
        len(outlines), len(ridges), len(beams), own.Name, above.Name if above else "-")
    rings = []
    for poly in outlines + beams:
        for ring in [poly.exterior] + list(poly.interiors):
            rings.append([to_sheet(f, x, y) for x, y in ring.coords])
    return dict(outlines=rings,
                ridges=[(to_sheet(f, *a), to_sheet(f, *b)) for a, b in ridges],
                message=message)


# ------------------------------------------------------------------ sill heights

def _format_m(value):
    """1.235 -> '1.23⁵' (metres with the millimetre raised), as German plans write heights."""
    raised = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
    mm_total = abs(int(round(float("%.3f" % value) * 1000)))
    mm = mm_total % 10
    if mm_total >= 1000:
        main = "%d.%02d" % (mm_total // 1000, (mm_total % 1000) // 10)
    else:
        main = "%d" % (mm_total // 10)
    return main + (str(mm).translate(raised) if mm else "")


def sill_text(height_m):
    return "BRH " + _format_m(height_m) if height_m >= 0 else "BRH -" + _format_m(-height_m)


def reading_angle(dx, dy):
    """Readable after DIN 1356: from below or from the right; SVG degrees, y down."""
    a = math.degrees(math.atan2(dy, dx))
    return ((a + 90.0) % 180.0) - 90.0


def cap_height_mm(denominator):
    """Cap height of the texts: 3.5 mm up to 1:50, 2.5 mm from 1:100."""
    return 2.5 if denominator >= 100 else 3.5


SILL_GAP_MM = 1.5    # inner face of the wall to the edge of the text, on paper


def sill_position(p, inward, cap_mm, gap_mm=SILL_GAP_MM):
    """Centre of the text: from the inner face inward by gap + half the cap height."""
    nx, ny = inward
    length = (nx * nx + ny * ny) ** 0.5 or 1.0
    a = gap_mm + cap_mm / 2.0
    return p[0] + nx / length * a, p[1] + ny / length * a


def sills(ifc, f, svg_text):
    """[dict(guid, name, x, y, angle, text)] in sheet mm for the windows Bonsai put into
    this drawing. The sill height is measured from the finished floor of the window's
    storey (EPset_Geschoss.OKFF of the template, otherwise the storey elevation) to
    the bottom of the window; the text stands inside, at the inner face of the opening.

    Window placement as Bonsai builds it: origin at the outer face, local x along the
    wall, local y inward."""
    import numpy as np
    import ifcopenshell.util.element as util
    import ifcopenshell.util.placement as placement
    import ifcopenshell.util.unit as unit
    get = getattr(placement, "get_placement", None) or placement.get_local_placement
    settings = _settings()
    length_scale = unit.calculate_unit_scale(ifc)
    cap = cap_height_mm(1000.0 / f["scale"])

    def sheet(w):
        p = f["inverse"] @ np.array([w[0], w[1], w[2], 1.0])
        return to_sheet(f, p[0], p[1])

    result = []
    for element in ifc.by_type("IfcWindow"):
        if ("GlobalId-" + element.GlobalId) not in svg_text and ('ifc:guid="%s"' % element.GlobalId) not in svg_text:
            continue
        try:
            import ifcopenshell.geom
            shape = ifcopenshell.geom.create_shape(settings, element)
        except Exception:
            continue
        verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
        m = np.array(get(element.ObjectPlacement), dtype=float)
        m[:3, 3] *= length_scale
        storey = util.get_container(element)
        okff = util.get_pset(storey, "EPset_Geschoss", "OKFF") if storey is not None else None
        if okff is None:
            okff = float(getattr(storey, "Elevation", 0.0) or 0.0) * length_scale
        ax = m[:3, 0] / np.linalg.norm(m[:3, 0])
        ay = m[:3, 1] / np.linalg.norm(m[:3, 1])
        origin = m[:3, 3].copy()
        depth = 0.0
        opening = next((r.RelatingOpeningElement for r in element.FillsVoids), None)
        if opening is not None:
            try:
                o_shape = ifcopenshell.geom.create_shape(settings, opening)
                ov = np.array(o_shape.geometry.verts, dtype=float).reshape(-1, 3)
                depth = max(float((p - origin) @ ay) for p in ov)
            except Exception:
                depth = 0.0
        width = float(element.OverallWidth or 0.0) * length_scale
        half = width / 2.0 if width else max(float((p - origin) @ ax) for p in verts) / 2.0
        point = origin + ax * half + ay * depth
        p, q, r = sheet(point), sheet(point + ay), sheet(point + ax)
        x, y = sill_position(p, (q[0] - p[0], q[1] - p[1]), cap)
        result.append(dict(guid=element.GlobalId, name=element.Name or element.GlobalId, x=float(x), y=float(y),
                           angle=float(reading_angle(r[0] - p[0], r[1] - p[1])),
                           text=sill_text(float(verts[:, 2].min()) - float(okff))))
    return result


# ------------------------------------------------------------------ all of it

def read(ifc, svg_text, name):
    """dict(flights, roofs, sills, frame=dict(width, height, scale)) for a plan view,
    or {} for any other drawing."""
    f = frame(ifc, svg_text, name)
    if f is None:
        return {}
    return dict(flights=flights(ifc, f, svg_text), roofs=roofs(ifc, f), sills=sills(ifc, f, svg_text),
                frame=dict(width=f["width"], height=f["height"], scale=f["scale"]))
