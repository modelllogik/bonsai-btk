# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Surroundings from LoD2 (CityGML): official 3D buildings with roof shapes.

Reads a CityGML file (tested with LoD2 from the OpenData portal of Bavaria), takes the
buildings whose footprint lies completely inside the terrain tile, and builds one object
per building in the collection names.COL_LOD2 (tile coordinates, hung on the origin empty).

- The ground of an LoD2 building is flat (HoeheGrund). It is extended down to the lowest
  terrain point under the ground corners – otherwise there is a gap on slopes (downhill side).
- Buildings touching your own house (section Buildings) are hidden (existing buildings on
  the plot) – see buildings.mark_all.
- In the cardboard model every LoD2 building moves onto the layer below (buildings.apply).
"""
import xml.etree.ElementTree as ET

import bmesh
import bpy
import numpy as np

from . import names

G = '{http://www.opengis.net/gml}'
SURFACES = ('RoofSurface', 'WallSurface', 'GroundSurface')
ATTRIBUTES = ('HoeheGrund', 'HoeheDach', 'Grundrissaktualitaet')   # German AdV attributes, read as they are
COLOURS = {names.MAT_LOD2_ROOF: (0.45, 0.20, 0.14), names.MAT_LOD2_WALL: (0.86, 0.84, 0.80),
           names.MAT_LOD2_GROUND: (0.35, 0.35, 0.35)}


def _ns_bldg(root):
    """Namespace of the building schema (CityGML 1.0 or 2.0) from the file."""
    for el in root.iter():
        if el.tag.endswith('}Building'):
            return el.tag[:-len('Building')]
    return None


def read(path):
    """[(info, [(surface kind 0..2, points n×3), …]), …] in map coordinates."""
    root = ET.parse(path).getroot()
    B = _ns_bldg(root)
    if B is None:
        return []
    out = []
    for b in root.iter(B + 'Building'):
        polys = []
        for k, kind in enumerate(SURFACES):
            for s in b.iter(B + kind):
                for q in s.iter(G + 'posList'):
                    v = np.array(q.text.split(), dtype=np.float64)
                    dim = int(q.get('srsDimension', 3))
                    P = v.reshape(-1, dim)[:, :3]
                    if len(P) > 1 and np.allclose(P[0], P[-1]):
                        P = P[:-1]
                    if len(P) >= 3:
                        polys.append((k, P))
        if not polys:
            continue
        info = {'gml_id': b.get(G + 'id') or ''}
        e = b.find(G + 'name')
        info['name'] = e.text if e is not None and e.text else ''
        for t in ('function', 'roofType', 'measuredHeight'):
            e = b.find(B + t)
            if e is not None and e.text:
                info[t] = e.text
        for s in b:
            if s.tag.endswith('stringAttribute') and s.get('name') in ATTRIBUTES:
                val = next((c.text for c in s if c.tag.endswith('value')), None)
                if val:
                    info[s.get('name')] = val
        out.append((info, polys))
    return out


def _material(name):
    rgb = COLOURS[name]
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgb + (1.0,)          # Solid view
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    if bs:
        bs.inputs['Base Color'].default_value = rgb + (1.0,)
        bs.inputs['Roughness'].default_value = 0.8
    return m


def surroundings():
    c = bpy.data.collections.get(names.COL_LOD2)
    return [o for o in c.objects if o.type == 'MESH'] if c else []


def build(context, props):
    from . import build as bd, buildings, georef, raster
    scene = context.scene
    dtm = raster.get_raster(bd.abspath(props.dtm_path))
    ox, oy = bd.origin(scene, dtm)
    di = dtm.info
    x0, x1, y0, y1 = di['left'], di['right'], di['bottom'], di['top']
    data = read(bd.abspath(props.lod2_path))
    if not data:
        raise ValueError("No buildings found in the file (CityGML with bldg:Building expected)")
    col = bd.collection(names.COL_LOD2, scene=scene)
    bd.clear_collection(col)
    mats = [_material(n) for n in (names.MAT_LOD2_ROOF, names.MAT_LOD2_WALL, names.MAT_LOD2_GROUND)]
    n = outside = 0
    plinth_max = 0.0
    for info, polys in data:
        A = np.vstack([P for _, P in polys])
        if A[:, 0].min() < x0 or A[:, 0].max() > x1 or A[:, 1].min() < y0 or A[:, 1].max() > y1:
            outside += 1
            continue
        bm = bmesh.new()
        for k, P in polys:
            vs = [bm.verts.new((p[0] - ox, p[1] - oy, p[2])) for p in P]
            try:
                f = bm.faces.new(vs)
                f.material_index = k
            except ValueError:
                pass
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
        # extend the flat ground down to the lowest terrain point under the ground corners
        zb = min(v.co.z for v in bm.verts)
        bottom = [v for v in bm.verts if v.co.z <= zb + 0.01]
        g = dtm.sample(np.array([v.co.x for v in bottom]), np.array([v.co.y for v in bottom]), ox, oy)
        znew = float(np.min(g)) - 0.05
        plinth = 0.0
        if znew < zb:
            plinth = zb - znew
            for v in bottom:
                v.co.z = znew
        plinth_max = max(plinth_max, plinth)
        name = info['name'] or info['gml_id'] or "LoD2"
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for m in mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        ob[names.OB_LOD2] = 1
        for key, val in info.items():
            ob[key] = val
        ob["plinth_m"] = round(plinth, 2)
        georef.attach(ob, scene)
        n += 1
    buildings.mark_all()
    bd.apply_variant(context)
    if n == 0:
        props.info_text = f"No LoD2 building lies completely inside the terrain tile ({outside} outside)"
    else:
        props.info_text = (f"{n} LoD2 buildings, {outside} outside the tile; "
                           f"plinths extended by up to {plinth_max:.1f} m")
    return n
