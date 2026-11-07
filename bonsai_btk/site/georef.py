# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Project origin: placing the terrain in the project coordinates of the IFC.

Blender world = project coordinates (origin at 0, building axes = x/y, z = 0 at ±0.00).
Everything the tools create hangs on an empty (names.ORIGIN) and is stored in tile
coordinates (map coordinates − tile origin, orthometric heights). The empty carries the
transformation: when the project origin changes, everything moves along and nothing is
recomputed.

The rotation is kept as a VECTOR, not as an angle, the way it is stored in the file:
XAxisAbscissa (a) and XAxisOrdinate (o) = project x axis in map axes (east, north).
    E = E0 + a·x − o·y      N = N0 + o·x + a·y      H = H0 + z
An angle only appears in a display, and every display counts it differently
(Bonsai: −atan2(o, a)).
"""
import math

import bpy
from mathutils import Matrix, Vector

from . import names


# ------------------------------------------------------------------ values

def parse(s):
    s = (s or "").strip().replace(" ", "").replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    return float(s)


def fmt(v, nd=3):
    return f"{v:.{nd}f}"


def fmt_vec(v):
    return repr(float(v))


def raw_vector(scene):
    """(a, o, length) as entered, or None."""
    g = scene.bonsai_btk_site
    try:
        a, o = parse(g.x_axis_abscissa), parse(g.x_axis_ordinate)
    except ValueError:
        return None
    return a, o, math.hypot(a, o)


def values(scene):
    """(E0, N0, H0, a, o) with unit vector (a, o), or None if no project origin is in use."""
    g = scene.bonsai_btk_site
    if not g.use_origin:
        return None
    try:
        e0 = parse(g.origin_e)
        n0 = parse(g.origin_n)
    except ValueError:
        return None
    rv = raw_vector(scene)
    if rv is None or rv[2] < 1e-9:
        return None
    a, o, L = rv
    return e0, n0, float(g.origin_h), a / L, o / L


def tile_origin(scene):
    o = scene.get(names.SC_ORIGIN)
    return (float(o[0]), float(o[1])) if o is not None else None


def matrix(scene):
    """Tile coordinates → Blender world (project coordinates)."""
    v = values(scene)
    ko = tile_origin(scene)
    if v is None or ko is None:
        return Matrix.Identity(4)
    e0, n0, h0, a, o = v
    # compute the differences in double precision, only then go into the (float32) matrix
    t = Matrix.Translation((ko[0] - e0, ko[1] - n0, -h0))
    # inverse of the map rotation: x = a·dE + o·dN,  y = −o·dE + a·dN
    r = Matrix(((a, o, 0, 0), (-o, a, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    return r @ t


def z_offset(scene):
    """World z = orthometric height + z_offset."""
    v = values(scene)
    return -v[2] if v else 0.0


def world_to_map(scene, p):
    """World → (E, N, H) in map coordinates."""
    ko = tile_origin(scene)
    lp = matrix(scene).inverted() @ Vector(p)
    return ko[0] + lp.x, ko[1] + lp.y, lp.z


# ------------------------------------------------------------------ empty

def empty(scene, create=True):
    e = bpy.data.objects.get(names.ORIGIN)
    if e is None and create:
        e = bpy.data.objects.new(names.ORIGIN, None)
        e.empty_display_type = 'ARROWS'
        e.empty_display_size = 5
        scene.collection.objects.link(e)
        e.hide_select = True
        e.matrix_world = matrix(scene)
    return e


def attach(ob, scene):
    """Hang an object (built in tile coordinates) on the origin empty."""
    e = empty(scene)
    if ob.parent is not e:
        ob.parent = e
        ob.matrix_parent_inverse = Matrix.Identity(4)


def update(context):
    scene = context.scene
    e = empty(scene)
    e.matrix_world = matrix(scene)
    for n in names.CREATED_OBJECTS:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            attach(ob, scene)
    for cn in names.CREATED_COLLECTIONS:
        c = bpy.data.collections.get(cn)
        if c:
            for ob in c.objects:
                attach(ob, scene)
    context.view_layer.update()


# ------------------------------------------------------------------ north

def epsg_of(scene):
    e = scene.get(names.SC_EPSG)
    if e:
        return int(e)
    s = str(scene.get("SRID", ""))
    if s.upper().startswith("EPSG:"):
        try:
            return int(s[5:])
        except ValueError:
            pass
    return None


def utm_zone(epsg):
    if epsg is None:
        return None
    epsg = int(epsg)
    if 25828 <= epsg <= 25838:
        return epsg - 25800
    if 32601 <= epsg <= 32660:
        return epsg - 32600
    return None


def utm_to_geo(E, N, zone):
    """ETRS89/GRS80 UTM (northern hemisphere) → (latitude, longitude, central meridian) in degrees."""
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x, y = E - 500000.0, N
    lam0 = math.radians(zone * 6 - 183)
    M = y / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
          + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    s, c, t = math.sin(p1), math.cos(p1), math.tan(p1)
    N1 = a / math.sqrt(1 - e2 * s * s)
    T1, C1 = t * t, ep2 * c * c
    R1 = a * (1 - e2) / (1 - e2 * s * s) ** 1.5
    D = x / (N1 * k0)
    lat = p1 - (N1 * t / R1) * (D ** 2 / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
                                + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6 / 720)
    lon = lam0 + (D - (1 + 2 * T1 + C1) * D ** 3 / 6
                  + (5 - 2 * C1 + 28 * T1 - 24 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5 / 120) / c
    return math.degrees(lat), math.degrees(lon), math.degrees(lam0)


def north(scene):
    """Latitude, longitude, meridian convergence γ and the direction of true north in the world.

    'geo' = direction of true north against +y, counter-clockwise (internal and for display only).
    'tn'  = the same north as a vector (x, y) in project coordinates – what goes into TrueNorth.
    """
    ko = tile_origin(scene)
    zone = utm_zone(epsg_of(scene))
    if ko is None or zone is None:
        return None
    v = values(scene)
    E, N = (v[0], v[1]) if v else ko
    a, o = (v[3], v[4]) if v else (1.0, 0.0)
    lat, lon, lon0 = utm_to_geo(E, N, zone)
    gamma = math.degrees(math.atan(math.tan(math.radians(lon - lon0)) * math.sin(math.radians(lat))))
    # grid north in project coordinates = (o, a); true north lies γ counter-clockwise from it
    g = math.radians(gamma)
    gx, gy = o, a
    tn = (gx * math.cos(g) - gy * math.sin(g), gx * math.sin(g) + gy * math.cos(g))
    geo = math.degrees(math.atan2(-tn[0], tn[1]))
    return dict(lat=lat, lon=lon, gamma=gamma, geo=geo, tn=tn, grid=(gx, gy))


def set_sun_position(scene):
    """Pass location and north direction to the add-on "Sun Position" (if it is enabled)."""
    nd = north(scene)
    sp = getattr(scene, "sun_pos_properties", None)
    if nd is None or sp is None:
        return False
    sp.latitude = nd['lat']
    sp.longitude = nd['lon']
    # Sun Position counts the north offset clockwise (checked against the sun at noon on 21 June)
    sp.north_offset = -math.radians(nd['geo'])
    return True


# ------------------------------------------------------------------ IFC

def _ifc():
    try:
        from bonsai import tool
    except ImportError:
        return None
    try:
        return tool.Ifc.get()
    except Exception:
        return None


def _unit_scale(unit, ifc):
    import ifcopenshell.util.unit as U
    if unit is None:
        return U.calculate_unit_scale(ifc)
    if unit.is_a('IfcSIUnit'):
        return U.get_prefix_multiplier(unit.Prefix) if unit.Prefix else 1.0
    if unit.is_a('IfcConversionBasedUnit'):
        return float(unit.ConversionFactor.ValueComponent.wrappedValue)
    return 1.0


def ifc_vector():
    """(XAxisAbscissa, XAxisOrdinate) of the loaded IFC, or None."""
    ifc = _ifc()
    if ifc is None:
        return None
    try:
        import ifcopenshell.util.geolocation as G
        ht = G.get_helmert_transformation_parameters(ifc)
    except Exception:
        return None
    return None if ht is None else (float(ht.xaa), float(ht.xao))


def mirror_check(scene):
    """Mirror check: x axis of the terrain origin against the x axis of the IfcMapConversion.

    Passed when the abscissas are equal and the ordinates opposite (the rotations cancel out).
    Returns (terrain_a, terrain_o, ifc_a, ifc_o, passed) or None.
    """
    e = bpy.data.objects.get(names.ORIGIN)
    iv = ifc_vector()
    if e is None or iv is None:
        return None
    m = e.matrix_world
    ga, go = float(m[0][0]), float(m[1][0])
    ok = abs(ga - iv[0]) < 1e-5 and abs(go + iv[1]) < 1e-5
    return ga, go, iv[0], iv[1], ok


def datum_code(text):
    """Normalise a vertical datum entry: '7837' → 'EPSG:7837'; empty stays empty."""
    t = (text or "").strip()
    if t.isdigit():
        return f"EPSG:{t}"
    if t.lower().startswith("epsg:"):
        return "EPSG:" + t[5:].strip()
    return t


def ifc_vertical_datum():
    """VerticalDatum of the IfcProjectedCRS in the loaded IFC, or ''."""
    ifc = _ifc()
    if ifc is None:
        return ""
    for crs in ifc.by_type("IfcProjectedCRS"):
        if getattr(crs, "VerticalDatum", None):
            return str(crs.VerticalDatum)
    return ""


def read_ifc(context):
    """Values from the IfcMapConversion of the loaded IFC: ((E, N, H, a, o), warnings)."""
    import ifcopenshell.util.geolocation as G
    ifc = _ifc()
    if ifc is None:
        raise ValueError("No IFC loaded in Bonsai")
    ht = G.get_helmert_transformation_parameters(ifc)
    if ht is None:
        raise ValueError("The IFC is not georeferenced (no IfcMapConversion)")
    warn = []
    crs = G.get_crs(ifc) if hasattr(G, 'get_crs') else None
    ms = 1.0
    name = ""
    if crs is not None:
        name = getattr(crs, 'Name', "") or ""
        ms = _unit_scale(getattr(crs, 'MapUnit', None), ifc)
    epsg = epsg_of(context.scene)
    if epsg and name and str(epsg) not in name:
        warn.append(f"CRS of the IFC {name} ≠ terrain EPSG:{epsg}")
    ps = _unit_scale(None, ifc)
    if crs is not None and getattr(crs, 'MapUnit', None) is None and ms != 1.0 and 1e5 < abs(ht.e) < 1e6:
        # common: MapUnit missing, values in metres anyway (project unit mm) – the easting shows it
        warn.append("IFC without MapUnit – easting and northing read as metres")
        ms = 1.0
    if abs(ht.scale * ms - ps) > 1e-6 * max(ps, 1):
        warn.append(f"Scale of the conversion {ht.scale:g} does not match the units")
    L = math.hypot(ht.xaa, ht.xao)
    if abs(L - 1) > 1e-6:
        warn.append(f"Abscissa/ordinate vector has length {L:.6f} instead of 1")
    bp = getattr(context.scene, "BIMGeoreferenceProperties", None)
    if bp is not None and getattr(bp, "has_blender_offset", False):
        warn.append("Bonsai shows the IFC with an offset (large coordinates) – check the position")
    return (ht.e * ms, ht.n * ms, ht.h * ms, float(ht.xaa), float(ht.xao)), warn


def write_ifc(context):
    """Write the project origin as IfcMapConversion (+ true north) into the loaded IFC."""
    import ifcopenshell.api.georeference as AG
    ifc = _ifc()
    if ifc is None:
        raise ValueError("No IFC loaded in Bonsai")
    if ifc.schema == "IFC2X3":
        raise ValueError("IFC2X3 has no IfcMapConversion – export as IFC4")
    v = values(context.scene)
    if v is None:
        raise ValueError("The project origin is missing or invalid")
    e0, n0, h0, a, o = v
    epsg = epsg_of(context.scene) or names.DEFAULT_EPSG
    if not ifc.by_type("IfcCoordinateOperation"):
        AG.add_georeferencing(ifc, ifc_class="IfcMapConversion", name=f"EPSG:{epsg}")
    metre = None
    for u in ifc.by_type("IfcSIUnit"):
        if u.UnitType == "LENGTHUNIT" and u.Name == "METRE" and not u.Prefix:
            metre = u
            break
    if metre is None:
        metre = ifc.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")
    ps = _unit_scale(None, ifc)          # project unit → m
    crs_attrs = {"Name": f"EPSG:{epsg}", "MapUnit": metre}
    vd = datum_code(context.scene.bonsai_btk_site.vertical_datum)
    if vd:
        crs_attrs["VerticalDatum"] = vd
    AG.edit_georeferencing(ifc, projected_crs=crs_attrs,
                           coordinate_operation={"Eastings": e0, "Northings": n0, "OrthogonalHeight": h0,
                                                 "XAxisAbscissa": a, "XAxisOrdinate": o, "Scale": ps})
    nd = north(context.scene)
    if nd is not None:
        AG.edit_true_north(ifc, true_north=nd['tn'])
    return v


# ------------------------------------------------------------------ operators

def _set(context, e=None, n=None, h=None, vec=None):
    g = context.scene.bonsai_btk_site
    if e is not None:
        g.origin_e = fmt(e)
    if n is not None:
        g.origin_n = fmt(n)
    if h is not None:
        g.origin_h = h
    if vec is not None:
        g.x_axis_abscissa, g.x_axis_ordinate = fmt_vec(vec[0]), fmt_vec(vec[1])
    g.use_origin = True


def _vtext(a, o):
    return f"abscissa {a:.6f}  ordinate {o:+.6f}"


class BONSAI_BTK_OT_site_origin_from_ifc(bpy.types.Operator):
    bl_idname = "bonsai_btk.site_origin_from_ifc"
    bl_label = "From IFC"
    bl_description = ("Take the project origin (E, N, H) and the rotation (abscissa/ordinate) from the "
                      "IfcMapConversion of the loaded IFC")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        g = context.scene.bonsai_btk_site
        try:
            v, warn = read_ifc(context)
        except ValueError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        old = values(context.scene)
        vec = (v[3], v[4])
        if abs(v[4]) < 1e-12 and abs(v[3] - 1) < 1e-12 and old and abs(old[4]) > 1e-9:
            warn.append("IFC without rotation – abscissa/ordinate kept from the add-on; write them with To IFC")
            vec = (old[3], old[4])
            g.info_text = "Rotation only in the add-on – not yet in the IFC"
        _set(context, v[0], v[1], v[2], vec)
        vd = ifc_vertical_datum()
        if vd:
            g.vertical_datum = vd
        else:
            warn.append("IFC without vertical datum – the height has no reference")
        msg = f"E {v[0]:.3f}  N {v[1]:.3f}  H {v[2]:.3f}  " + _vtext(*vec)
        self.report({'WARNING'} if warn else {'INFO'}, msg + (" – " + " | ".join(warn) if warn else ""))
        return {'FINISHED'}


class BONSAI_BTK_OT_site_origin_to_ifc(bpy.types.Operator):
    bl_idname = "bonsai_btk.site_origin_to_ifc"
    bl_label = "To IFC"
    bl_description = ("Write the project origin and rotation (abscissa/ordinate) as georeference into the loaded IFC "
                      "(IfcMapConversion with the EPSG code of the terrain, MapUnit metre, Scale, vertical datum; "
                      "plus true north). "
                      "Save the IFC in Bonsai afterwards")
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            v = write_ifc(context)
        except ValueError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        context.scene.bonsai_btk_site.info_text = "Georeference written to the IFC – save the IFC!"
        msg = f"To IFC: E {v[0]:.3f} N {v[1]:.3f} H {v[2]:.3f}  " + _vtext(v[3], v[4]) + " – save the IFC!"
        if ifc_vertical_datum():
            self.report({'INFO'}, msg)
        else:
            self.report({'WARNING'}, msg + " | No vertical datum – enter one under H Datum")
        return {'FINISHED'}


class BONSAI_BTK_OT_site_origin_at_cursor(bpy.types.Operator):
    bl_idname = "bonsai_btk.site_origin_at_cursor"
    bl_label = "Origin at 3D Cursor"
    bl_description = ("Put the project origin at the 3D cursor (position and height of the cursor; "
                      "place the cursor on the terrain with Shift+right click, for example). The rotation stays")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if tile_origin(scene) is None:
            self.report({'ERROR'}, "Load the terrain first")
            return {'CANCELLED'}
        E, N, H = world_to_map(scene, scene.cursor.location)
        rv = raw_vector(scene)
        vec = None if (rv and rv[2] > 1e-9) else (1.0, 0.0)
        _set(context, E, N, round(H, 3), vec)
        scene.cursor.location = (0, 0, 0)
        self.report({'INFO'}, f"Origin E {E:.3f} N {N:.3f} H {H:.3f}")
        return {'FINISHED'}


class BONSAI_BTK_OT_site_sun_position(bpy.types.Operator):
    bl_idname = "bonsai_btk.site_sun_position"
    bl_label = "Location for Sun Position"
    bl_description = ("Pass latitude, longitude and north direction (including meridian convergence) "
                      "to the add-on Sun Position")

    def execute(self, context):
        if not set_sun_position(context.scene):
            self.report({'ERROR'}, "Sun Position is not enabled, or the terrain has no UTM reference")
            return {'CANCELLED'}
        nd = north(context.scene)
        self.report({'INFO'}, f"{nd['lat']:.5f}° N, {nd['lon']:.5f}° E, true north as vector "
                              f"({nd['tn'][0]:+.6f} / {nd['tn'][1]:+.6f})")
        return {'FINISHED'}


CLASSES = (BONSAI_BTK_OT_site_origin_from_ifc, BONSAI_BTK_OT_site_origin_to_ifc,
           BONSAI_BTK_OT_site_origin_at_cursor, BONSAI_BTK_OT_site_sun_position)
