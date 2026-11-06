# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Terrain as an IFC element: IfcGeographicElement (TERRAIN) in the IfcSite.

A cut-out around the building on a thinned grid – the full terrain would be far too big for an IFC.
The geometry stays aligned to grid north (axes parallel to east/north, relative to the project
origin); the rotation is stored in the placement. That keeps the mirror check possible in the file:
never bake the rotation into the geometry.
"""
import bpy
import numpy as np
from mathutils import Matrix

from . import buildings, georef, names, raster

IFC_NAME = "Terrain"


def _tool():
    from bonsai import tool
    return tool


def ifc_terrain_entity():
    """(object, entity) of the terrain in the IFC – through the stored GlobalId, else class + name."""
    try:
        tool = _tool()
        f = tool.Ifc.get()
    except Exception:
        return None, None
    if f is None:
        return None, None
    el = None
    gid = bpy.context.scene.get(names.SC_IFC_TERRAIN)
    if gid:
        try:
            el = f.by_guid(gid)
        except Exception:
            el = None
    if el is None:
        for e in f.by_type("IfcGeographicElement"):
            # "Gelände": name used by the earlier German version of these tools
            if getattr(e, "PredefinedType", None) == "TERRAIN" and e.Name in (IFC_NAME, "Gelände"):
                el = e
                break
    if el is None:
        return None, None
    return tool.Ifc.get_object(el), el


def ensure_placement(ob, el):
    """Write the placement from the Blender matrix (Bonsai does not create one when assigning a class)."""
    import ifcopenshell.api.geometry as GE
    f = _tool().Ifc.get()
    v = georef.values(bpy.context.scene)
    if v is not None:   # in double precision from abscissa/ordinate, not from the float32 matrix
        a, o = v[3], v[4]
        M = np.array(((a, o, 0, 0), (-o, a, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)), dtype=np.float64)
    else:
        M = np.array(ob.matrix_world, dtype=np.float64)
    GE.edit_object_placement(f, product=el, matrix=M, is_si=True)


def file_check():
    """Mirror check in the IFC: x axis of the terrain placement against the x axis of the IfcMapConversion."""
    import ifcopenshell.util.geolocation as G
    import ifcopenshell.util.placement as P
    ob, el = ifc_terrain_entity()
    if el is None or el.ObjectPlacement is None:
        return None
    f = _tool().Ifc.get()
    ht = G.get_helmert_transformation_parameters(f)
    if ht is None:
        return None
    M = P.get_placement(el.ObjectPlacement)
    ga, go = float(M[0][0]), float(M[1][0])
    ok = abs(ga - ht.xaa) < 1e-5 and abs(go + ht.xao) < 1e-5
    return ga, go, float(ht.xaa), float(ht.xao), ok


def build(context, props):
    tool = _tool()
    f = tool.Ifc.get()
    if f is None:
        raise ValueError("No IFC loaded in Bonsai")
    scene = context.scene
    v = georef.values(scene)
    if v is None:
        raise ValueError("Project origin missing – set it first in the section Project Origin (From IFC)")
    ob_old, _el_old = ifc_terrain_entity()
    if ob_old is not None:
        raise ValueError(f"“{names.TERRAIN_IFC}” exists already – delete it in Bonsai first (X), then try again")
    e0, n0, h0, a, o = v
    ko = georef.tile_origin(scene)
    dtm = raster.get_raster(bpy.path.abspath(props.dtm_path))
    # centre: the building, else the project origin – converted into map directions (local = R^T · world)
    obs = buildings.buildings()
    if obs:
        b = np.array([buildings.bbox(x) for x in obs])
        cx, cy = (b[:, 0].min() + b[:, 1].max()) / 2, (b[:, 2].min() + b[:, 3].max()) / 2
    else:
        cx = cy = 0.0
    cE, cN = a * cx - o * cy, o * cx + a * cy
    s, r = float(props.ifc_extent), float(props.ifc_grid)
    n = int(round(s / r)) + 1
    dE = cE - s / 2 + np.arange(n) * r
    dN = cN - s / 2 + np.arange(n) * r
    # inside the terrain?
    i = dtm.info
    if (e0 + dE[0] < i['left'] or e0 + dE[-1] > i['right'] or n0 + dN[0] < i['bottom'] or n0 + dN[-1] > i['top']):
        raise ValueError("The cut-out extends beyond the terrain data – choose it smaller")
    EE, NN = np.meshgrid(e0 + dE - ko[0], n0 + dN - ko[1])
    Z = dtm.sample(EE, NN, ko[0], ko[1]) - h0
    from . import build as B
    me = B.grid_mesh(names.TERRAIN_IFC, dE.astype(np.float64), dN.astype(np.float64), Z)
    mat = bpy.data.materials.get(names.MAT_TERRAIN_IFC) or bpy.data.materials.new(names.MAT_TERRAIN_IFC)
    mat.diffuse_color = (0.42, 0.45, 0.36, 1)
    me.materials.append(mat)
    ob = bpy.data.objects.new(names.TERRAIN_IFC, me)
    scene.collection.objects.link(ob)
    # the placement carries the rotation: x axis (a, −o) = mirror image of the IfcMapConversion
    ob.matrix_world = Matrix(((a, o, 0, 0), (-o, a, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    context.view_layer.update()
    import ifcopenshell.util.representation as UR
    body = UR.get_context(f, "Model", "Body", "MODEL_VIEW")
    for x in context.selected_objects:
        x.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    kw = dict(obj=ob.name, ifc_class="IfcGeographicElement", predefined_type="TERRAIN")
    if body is not None:
        kw["context_id"] = body.id()
    res = bpy.ops.bim.assign_class(**kw)
    el = tool.Ifc.get_entity(ob)
    if el is None:
        raise ValueError(f"Bonsai did not take over the terrain ({res})")
    scene[names.SC_IFC_TERRAIN] = el.GlobalId
    ensure_placement(ob, el)
    # in Blender the full terrain (with orthophoto) shows more – the IFC terrain is there for the exchange
    ob = tool.Ifc.get_object(el) or ob
    ob.hide_viewport = True
    ob.hide_render = True
    import ifcopenshell.api.attribute as AA
    import ifcopenshell.api.spatial as SP
    epsg = georef.epsg_of(scene) or names.DEFAULT_EPSG
    AA.edit_attributes(f, product=el, attributes={
        "Name": IFC_NAME,
        "Description": f"Digital terrain model, grid {r:g} m, cut-out {s:g} × {s:g} m, EPSG:{epsg}; "
                       f"geometry aligned to grid north, rotation in the placement"})
    sites = f.by_type("IfcSite")
    if sites:
        SP.assign_container(f, products=[el], relating_structure=sites[0])
        try:
            tool.Collector.assign(ob)
        except Exception:
            pass
    props.info_text = f"Terrain in IFC: {n}×{n} points, {s:g} m, grid {r:g} m – save the IFC!"
    return ob, el
