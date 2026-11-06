# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Building the site: terrain, cardboard contour layers, model trees, variants."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from . import buildings, georef, names, raster, vegetation


# ------------------------------------------------------------------ helpers

def abspath(p):
    return bpy.path.abspath(p) if p else ""


def collection(name, parent=None, scene=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = parent or scene.collection
    if c.name not in parent.children:
        parent.children.link(c)
    return c


def clear_collection(col):
    for o in list(col.objects):
        data = o.data
        bpy.data.objects.remove(o)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)


def sock(sockets, ident):
    for s in sockets:
        if s.identifier == ident:
            return s
    return sockets[ident]


def origin(scene, dtm=None):
    """Scene origin in map coordinates (set once, then fixed)."""
    if names.SC_ORIGIN in scene:
        o = scene[names.SC_ORIGIN]
        return float(o[0]), float(o[1])
    if "crs x" in scene and "crs y" in scene:
        ox, oy = float(scene["crs x"]), float(scene["crs y"])
    elif dtm is not None:
        i = dtm.info
        ox = round((i['left'] + i['right']) / 2)
        oy = round((i['top'] + i['bottom']) / 2)
    else:
        raise ValueError("Load the terrain first")
    scene[names.SC_ORIGIN] = (ox, oy)
    scene["crs x"] = ox
    scene["crs y"] = oy
    if dtm is not None and dtm.info.get('epsg'):
        scene["SRID"] = f"EPSG:{dtm.info['epsg']}"
    return ox, oy


def grid_mesh(name, X, Y, Z, uv=None):
    h, w = Z.shape
    co = np.empty((h, w, 3), dtype=np.float32)
    co[:, :, 0] = X[None, :]
    co[:, :, 1] = Y[:, None]
    co[:, :, 2] = Z
    idx = np.arange(h * w, dtype=np.int32).reshape(h, w)
    quads = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1)
    nq = (h - 1) * (w - 1)
    me = bpy.data.meshes.new(name)
    me.vertices.add(h * w)
    me.vertices.foreach_set('co', co.ravel())
    me.loops.add(nq * 4)
    me.loops.foreach_set('vertex_index', quads)
    me.polygons.add(nq)
    me.polygons.foreach_set('loop_start', np.arange(0, nq * 4, 4, dtype=np.int32))
    if uv is not None:
        lay = me.uv_layers.new(name='UVMap')
        lay.data.foreach_set('uv', uv.reshape(-1, 2)[quads].astype(np.float32).ravel())
    me.update(calc_edges=True)
    return me


def ortho_mapping(ortho_info, ox, oy):
    """(scale, offset) for u = x*s + l from world coordinates."""
    w = ortho_info['right'] - ortho_info['left']
    h = ortho_info['top'] - ortho_info['bottom']
    return (1 / w, 1 / h), ((ox - ortho_info['left']) / w, (oy - ortho_info['bottom']) / h)


def ortho_image(props):
    p = abspath(props.ortho_path)
    if not p:
        return None, None
    return raster.load_image(p, False), raster.georef(p)


def setup_viewports(context, size):
    """Fit the clipping of the 3D views to the terrain size, show the orthophoto in Solid mode."""
    for win in context.window_manager.windows:
        for a in win.screen.areas:
            if a.type == 'VIEW_3D':
                sp = a.spaces[0]
                sp.clip_start = max(sp.clip_start, 0.1)
                sp.clip_end = max(sp.clip_end, size * 20)
                if sp.shading.type == 'SOLID':
                    sp.shading.color_type = 'TEXTURE'
                a.tag_redraw()


SUN_ELEVATION, SUN_AZIMUTH = 32.0, 290.0   # light from the north-west, as on relief maps


def sun(context):
    """One sun for both variants (collection names.COL_LIGHT)."""
    so = bpy.data.objects.get(names.SUN)
    if so is None:
        ld = bpy.data.lights.new(names.SUN, 'SUN'); ld.energy = 4.5; ld.angle = math.radians(3)
        so = bpy.data.objects.new(names.SUN, ld)
        collection(names.COL_LIGHT, scene=context.scene).objects.link(so)
    el, az = math.radians(SUN_ELEVATION), math.radians(SUN_AZIMUTH)
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    so.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    return so


def sky_world():
    """Physical sky matching the sun (background and ambient light for the terrain)."""
    w = bpy.data.worlds.get(names.WORLD_SKY)
    if w is not None:
        return w
    w = bpy.data.worlds.new(names.WORLD_SKY); w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get('Background')
    sky = nt.nodes.new('ShaderNodeTexSky'); sky.location = (-300, 300)
    for t in ('MULTIPLE_SCATTERING', 'NISHITA'):
        try:
            sky.sky_type = t
            break
        except TypeError:
            pass
    for attr, val in (('sun_disc', False), ('sun_elevation', math.radians(SUN_ELEVATION)),
                      ('sun_rotation', math.radians((-SUN_AZIMUTH) % 360)), ('altitude', 1000.0)):
        try:
            setattr(sky, attr, val)
        except (AttributeError, TypeError, ValueError):
            pass
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.12
    return w


def _is_default_world(w):
    if w is None:
        return True
    if not w.use_nodes:
        return True
    types = sorted(n.bl_idname for n in w.node_tree.nodes)
    if types != ['ShaderNodeBackground', 'ShaderNodeOutputWorld']:
        return False
    bg = w.node_tree.nodes[[n.bl_idname for n in w.node_tree.nodes].index('ShaderNodeBackground')]
    return not bg.inputs[0].is_linked and max(bg.inputs[0].default_value[:3]) < 0.1


# ------------------------------------------------------------------ terrain

def build_terrain(context, props):
    scene = context.scene
    dtm = raster.get_raster(abspath(props.dtm_path))
    ox, oy = origin(scene, dtm)
    H, W = dtm.A.shape
    st = max(1, math.ceil(math.sqrt(W * H / 1.1e6)))
    Z = dtm.A[::st, ::st]
    X = dtm.xs(ox)[::st]
    Y = dtm.ys(oy)[::st]
    img, oinfo = ortho_image(props)
    uv = None
    if oinfo:
        (su, sv), (lu, lv) = ortho_mapping(oinfo, ox, oy)
        uv = np.empty(Z.shape + (2,), dtype=np.float32)
        uv[:, :, 0] = X[None, :] * su + lu
        uv[:, :, 1] = Y[:, None] * sv + lv

    col = collection(names.COL_TERRAIN, scene=scene)
    clear_collection(col)
    me = grid_mesh(names.TERRAIN, X, Y, Z, uv)
    mat = bpy.data.materials.get(names.MAT_TERRAIN) or bpy.data.materials.new(names.MAT_TERRAIN)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    bs = nt.nodes.new('ShaderNodeBsdfPrincipled'); bs.location = (100, 0)
    bs.inputs['Roughness'].default_value = 0.9
    nt.links.new(bs.outputs[0], out.inputs[0])
    grey = tuple(props.board_color) + (1,)   # without orthophoto: the same colour as the cardboard
    if img:
        it = nt.nodes.new('ShaderNodeTexImage'); it.location = (-500, 0)
        it.image = img
        it.extension = 'EXTEND'
        nt.nodes.active = it
        sw = nt.nodes.new('ShaderNodeValue'); sw.name = sw.label = names.NODE_ORTHO; sw.location = (-500, 250)
        sw.outputs[0].default_value = 1.0
        mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.location = (-200, 0)
        mx.name = mx.label = names.NODE_TERRAIN_COLOUR
        nt.links.new(sw.outputs[0], sock(mx.inputs, 'Factor_Float'))
        sock(mx.inputs, 'A_Color').default_value = grey
        nt.links.new(it.outputs['Color'], sock(mx.inputs, 'B_Color'))
        nt.links.new(sock(mx.outputs, 'Result_Color'), bs.inputs['Base Color'])
    else:
        bs.inputs['Base Color'].default_value = grey
    me.materials.append(mat)
    ob = bpy.data.objects.new(names.TERRAIN, me)
    col.objects.link(ob)
    vegetation.relink_terrain(ob)
    if dtm.info.get('epsg'):
        scene[names.SC_EPSG] = int(dtm.info['epsg'])
    georef.attach(ob, scene)
    georef.update(context)
    setup_viewports(context, max(W * dtm.dx, H * dtm.dy))
    sun(context)
    if _is_default_world(scene.world):
        scene.world = sky_world()
    if scene.world and scene.world.name != names.WORLD_MODEL:
        scene[names.SC_TERRAIN_WORLD] = scene.world.name
    props.info_text = (f"Terrain {W}×{H}, {dtm.dx:g} m, EPSG {dtm.info.get('epsg')}, "
                       f"origin {ox:.0f} / {oy:.0f}")
    return ob


# ------------------------------------------------------------------ cardboard model

_TAB = {1: [('L', 'B')], 2: [('B', 'R')], 3: [('L', 'R')], 4: [('R', 'T')], 6: [('B', 'T')],
        7: [('L', 'T')], 8: [('T', 'L')], 9: [('B', 'T')], 11: [('R', 'T')], 12: [('L', 'R')],
        13: [('B', 'R')], 14: [('L', 'B')]}


def board_grid(scene, props):
    """Smoothed, thinned terrain on which the contour lines are traced."""
    dtm = raster.get_raster(abspath(props.dtm_path))
    ox, oy = origin(scene, dtm)
    H, W = dtm.A.shape
    ext = max(H * dtm.dy, W * dtm.dx)
    res = max(props.contour_grid, dtm.dx, ext / 800.0)
    s_px = max(1, int(round(res / dtm.dx)))
    Zs = raster.gauss(dtm.A, 1.5 / dtm.dx)[::s_px, ::s_px]
    return Zs, float(dtm.xs(ox)[0]), float(dtm.ys(oy)[0]), s_px * dtm.dx


def _contours(Z, x0, y0, s, h):
    """Marching squares: contour segments at level h."""
    P = np.pad(Z, 1, constant_values=-1e9)
    Hp, Wp = P.shape
    X0, Y0 = x0 - s, y0 - s
    ins = P >= h
    case = ins[:-1, :-1] * 1 + ins[:-1, 1:] * 2 + ins[1:, 1:] * 4 + ins[1:, :-1] * 8
    cen = (P[:-1, :-1] + P[:-1, 1:] + P[1:, 1:] + P[1:, :-1]) / 4 >= h
    I, J = np.indices(case.shape)
    N = Hp * Wp

    def eid(sym, i, j):
        return {'B': i * Wp + j, 'T': (i + 1) * Wp + j, 'L': N + i * Wp + j, 'R': N + i * Wp + j + 1}[sym]

    A, B = [], []

    def add(mask, pairs):
        ii, jj = I[mask], J[mask]
        for a, b in pairs:
            A.append(eid(a, ii, jj)); B.append(eid(b, ii, jj))

    for c, pairs in _TAB.items():
        add(case == c, pairs)
    add((case == 5) & cen, [('B', 'R'), ('T', 'L')]); add((case == 5) & ~cen, [('L', 'B'), ('R', 'T')])
    add((case == 10) & cen, [('L', 'B'), ('R', 'T')]); add((case == 10) & ~cen, [('B', 'R'), ('T', 'L')])
    A = np.concatenate(A); B = np.concatenate(B)
    if A.size == 0:
        return None, None
    ids, inv = np.unique(np.concatenate([A, B]), return_inverse=True)
    hor = ids < N
    e = np.where(hor, ids, ids - N)
    i, j = e // Wp, e % Wp
    Pf = P.ravel()
    a = Pf[e]
    b = np.where(hor, Pf[np.minimum(e + 1, N - 1)], Pf[np.minimum(e + Wp, N - 1)])
    t = np.clip((h - a) / (b - a), 0, 1)
    x = X0 + j * s + np.where(hor, t * s, 0)
    y = Y0 + i * s + np.where(hor, 0, t * s)
    return np.stack([x, y], 1), inv.reshape(2, -1).T


def _layer(Z, x0, y0, s, h, dz, min_area):
    pts, edges = _contours(Z, x0, y0, s, h)
    if pts is None:
        return None
    bm = bmesh.new()
    vs = [bm.verts.new((float(p[0]), float(p[1]), h - dz)) for p in pts]
    for a, b in edges:
        if a != b:
            try:
                bm.edges.new((vs[a], vs[b]))
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.triangle_fill(bm, use_beauty=False, use_dissolve=False, edges=bm.edges[:])
    seen = set()
    for f in list(bm.faces):
        if f in seen or not f.is_valid:
            continue
        stack, isl = [f], []
        seen.add(f)
        while stack:
            g = stack.pop(); isl.append(g)
            for e in g.edges:
                for n in e.link_faces:
                    if n not in seen:
                        seen.add(n); stack.append(n)
        if sum(x.calc_area() for x in isl) < min_area:
            bmesh.ops.delete(bm, geom=isl, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    if not bm.faces:
        bm.free(); return None
    r = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, verts=[g for g in r['geom'] if isinstance(g, bmesh.types.BMVert)], vec=(0, 0, dz))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def _planar_uv(me, mapping):
    """UV map seen from above, matching the orthophoto: the Solid view (colour Texture) reads the
    image through the UV map, the material through the position – both then show the same."""
    import numpy as np
    (su, sv), (lu, lv) = mapping
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    vi = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", vi)
    uv = np.column_stack((co[vi, 0] * su + lu, co[vi, 1] * sv + lv)).astype(np.float32)
    me.uv_layers.new(name="Orthophoto").data.foreach_set("uv", uv.ravel())


def board_material(props, dz, ox, oy):
    mat = bpy.data.materials.get(names.MAT_BOARD) or bpy.data.materials.new(names.MAT_BOARD)
    mat.use_nodes = True
    mat.diffuse_color = (0.19, 0.17, 0.145, 1)  # Solid view: grey board
    nt = mat.node_tree; nt.nodes.clear()
    N, L = nt.nodes, nt.links
    out = N.new('ShaderNodeOutputMaterial'); out.location = (1400, 0)
    bs = N.new('ShaderNodeBsdfPrincipled'); bs.location = (1100, 0)
    bs.inputs['Roughness'].default_value = 0.85
    L.new(bs.outputs[0], out.inputs[0])
    geo = N.new('ShaderNodeNewGeometry'); geo.location = (-900, 0)
    noise = N.new('ShaderNodeTexNoise'); noise.location = (-600, 300)
    noise.inputs['Scale'].default_value = 0.8; noise.inputs['Detail'].default_value = 8
    oi = N.new('ShaderNodeObjectInfo'); oi.location = (-600, 550)
    ramp = N.new('ShaderNodeValToRGB'); ramp.location = (-350, 300)
    ramp.name = ramp.label = names.NODE_BOARD_COLOUR
    ramp.color_ramp.elements[0].color = (0.155, 0.140, 0.118, 1)
    ramp.color_ramp.elements[1].color = (0.225, 0.205, 0.175, 1)
    mv = N.new('ShaderNodeMath'); mv.operation = 'MULTIPLY_ADD'; mv.location = (-400, 500)
    mv.inputs[1].default_value = 0.35
    L.new(oi.outputs['Random'], mv.inputs[0]); L.new(noise.outputs['Fac'], mv.inputs[2])
    L.new(mv.outputs[0], ramp.inputs[0])
    sep = N.new('ShaderNodeSeparateXYZ'); sep.location = (-700, -300); L.new(geo.outputs['Position'], sep.inputs[0])
    wr = N.new('ShaderNodeMath'); wr.operation = 'WRAP'; wr.location = (-500, -300)
    wr.inputs[1].default_value = dz; wr.inputs[2].default_value = 0.0
    L.new(sep.outputs['Z'], wr.inputs[0])
    lt = N.new('ShaderNodeMath'); lt.operation = 'LESS_THAN'; lt.location = (-300, -300)
    lt.inputs[1].default_value = 0.035 * dz; L.new(wr.outputs[0], lt.inputs[0])
    nz = N.new('ShaderNodeSeparateXYZ'); nz.location = (-700, -600); L.new(geo.outputs['Normal'], nz.inputs[0])
    wall = N.new('ShaderNodeMath'); wall.operation = 'LESS_THAN'; wall.location = (-500, -600)
    wall.inputs[1].default_value = 0.5; L.new(nz.outputs['Z'], wall.inputs[0])
    joint = N.new('ShaderNodeMath'); joint.operation = 'MULTIPLY'; joint.location = (-100, -400)
    L.new(lt.outputs[0], joint.inputs[0]); L.new(wall.outputs[0], joint.inputs[1])
    hs = N.new('ShaderNodeHueSaturation'); hs.location = (-100, 100)
    hs.inputs['Value'].default_value = 0.8; L.new(ramp.outputs['Color'], hs.inputs['Color'])

    def mix(loc):
        m = N.new('ShaderNodeMix'); m.data_type = 'RGBA'; m.location = loc
        return m, sock(m.inputs, 'Factor_Float'), sock(m.inputs, 'A_Color'), sock(m.inputs, 'B_Color'), sock(m.outputs, 'Result_Color')

    _c, cf, ca, cb, cr = mix((100, 200))
    L.new(wall.outputs[0], cf); L.new(ramp.outputs['Color'], ca); L.new(hs.outputs['Color'], cb)
    _d, df, da, db, dr = mix((300, 100))
    L.new(joint.outputs[0], df); L.new(cr, da); db.default_value = (0.05, 0.045, 0.04, 1)
    final = dr
    img, oinfo = ortho_image(props)
    if img:
        (su, sv), (lu, lv) = ortho_mapping(oinfo, ox, oy)
        mp = N.new('ShaderNodeMapping'); mp.location = (-500, -900)
        mp.inputs['Location'].default_value = (lu, lv, 0)
        mp.inputs['Scale'].default_value = (su, sv, 1)
        L.new(geo.outputs['Position'], mp.inputs['Vector'])
        it = N.new('ShaderNodeTexImage'); it.location = (-250, -900); it.image = img; it.extension = 'EXTEND'
        N.active = it   # the Solid view (colour Texture) shows the image of the active node
        L.new(mp.outputs[0], it.inputs[0])
        sw = N.new('ShaderNodeValue'); sw.name = sw.label = names.NODE_ORTHO; sw.location = (-250, -650)
        sw.outputs[0].default_value = 0.0
        top = N.new('ShaderNodeMath'); top.operation = 'SUBTRACT'; top.location = (0, -600)
        top.inputs[0].default_value = 1; L.new(wall.outputs[0], top.inputs[1])
        fo = N.new('ShaderNodeMath'); fo.operation = 'MULTIPLY'; fo.location = (200, -600)
        L.new(top.outputs[0], fo.inputs[0]); L.new(sw.outputs[0], fo.inputs[1])
        _l, lf, la, lb, lr = mix((600, 0))
        L.new(fo.outputs[0], lf); L.new(dr, la); L.new(it.outputs['Color'], lb)
        final = lr
    L.new(final, bs.inputs['Base Color'])
    bump = N.new('ShaderNodeBump'); bump.location = (800, -400); bump.inputs['Strength'].default_value = 0.08
    n2 = N.new('ShaderNodeTexNoise'); n2.location = (500, -500)
    n2.inputs['Scale'].default_value = 3.0; n2.inputs['Detail'].default_value = 10
    L.new(n2.outputs['Fac'], bump.inputs['Height']); L.new(bump.outputs[0], bs.inputs['Normal'])
    apply_board_color(tuple(props.board_color))
    return mat


def apply_board_color(c):
    """Colour of the cardboard: mean c, fibre variation ±18 %; also in the Solid view."""
    g = bpy.data.materials.get(names.MAT_TERRAIN)
    if g is not None:
        g.diffuse_color = tuple(c) + (1,)
        if g.node_tree:
            n = g.node_tree.nodes.get(names.NODE_TERRAIN_COLOUR)
            if n is not None:
                sock(n.inputs, 'A_Color').default_value = tuple(c) + (1,)
            else:
                for p in g.node_tree.nodes:
                    if p.bl_idname == 'ShaderNodeBsdfPrincipled' and not p.inputs['Base Color'].is_linked:
                        p.inputs['Base Color'].default_value = tuple(c) + (1,)
    m = bpy.data.materials.get(names.MAT_BOARD)
    if m is None:
        return
    m.diffuse_color = tuple(c) + (1,)
    if m.node_tree and names.NODE_BOARD_COLOUR in m.node_tree.nodes:
        el = m.node_tree.nodes[names.NODE_BOARD_COLOUR].color_ramp.elements
        el[0].color = tuple(min(1.0, x * 0.82) for x in c) + (1,)
        el[1].color = tuple(min(1.0, x * 1.18) for x in c) + (1,)


def _simple_mat(name, color, rough=0.7):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    if p:
        p.inputs['Base Color'].default_value = color
        p.inputs['Roughness'].default_value = rough
    m.diffuse_color = color  # Solid view
    return m


def _box(name, x0, x1, y0, y1, z0, z1, mat, col):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0),
                       (z0 + z1) / 2 + v.co.z * (z1 - z0)))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); col.objects.link(ob)
    return ob


def build_board(context, props):
    scene = context.scene
    Zs, x0, y0, s = board_grid(scene, props)
    ox, oy = origin(scene)
    dz = float(props.contour_interval)
    L0 = math.ceil(float(Zs.min()) / dz) * dz
    Lmax = math.floor(float(Zs.max()) / dz) * dz
    n = int(round((Lmax - L0) / dz)) + 1
    if n > 200:
        raise ValueError(f"{n} layers – choose a larger layer height (at most 200 layers)")
    pm = collection(names.COL_BOARD, scene=scene)
    col = collection(names.COL_LAYERS, parent=pm)
    clear_collection(col)
    mat = board_material(props, dz, ox, oy)
    _img, oinfo = ortho_image(props)
    uvmap = ortho_mapping(oinfo, ox, oy) if _img else None
    wm = context.window_manager
    wm.progress_begin(0, n)
    for k in range(n):
        h = L0 + k * dz
        bm = _layer(Zs, x0, y0, s, h, dz, props.min_area)
        wm.progress_update(k)
        if bm is None:
            continue
        me = bpy.data.meshes.new(f"{names.LAYER_PREFIX}{h:g}")
        bm.to_mesh(me); bm.free()
        me.materials.append(mat)
        if uvmap:
            _planar_uv(me, uvmap)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(35))
        ob = bpy.data.objects.new(f"{names.LAYER_PREFIX}{h:g}", me)
        ob["top_level"] = h
        col.objects.link(ob)
        georef.attach(ob, scene)
    wm.progress_end()
    h_, w_ = Zs.shape
    x1, y1 = x0 + (w_ - 1) * s, y0 + (h_ - 1) * s
    zb = L0 - dz
    georef.attach(_box(names.BASE_PLATE, x0, x1, y0, y1, zb - 2 * dz, zb, mat, col), scene)
    scene[names.SC_BOARD] = dict(interval=dz, L0=L0, Lmax=Lmax, zbase=zb, x0=x0, y0=y0, x1=x1, y1=y1)
    _staging(context, pm, (x0, x1, y0, y1), zb - 2 * dz, float(Zs.max()))
    update_tree_offsets(context, props)
    props.info_text = f"{n} layers of {dz:g} m ({L0:g}–{Lmax:g} m), grid {s:g} m"


def _staging(context, col, ext, zlow, ztop):
    """Table, light, model world, camera."""
    scene = context.scene
    x0, x1, y0, y1 = ext
    size = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    t = bpy.data.objects.get(names.TABLE)
    if t is None:
        me = bpy.data.meshes.new(names.TABLE)
        me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
        me.materials.append(_simple_mat(names.MAT_TABLE, (0.6, 0.6, 0.6, 1)))
        t = bpy.data.objects.new(names.TABLE, me); col.objects.link(t)
    georef.attach(t, scene)
    t.location = (cx, cy, zlow)
    t.scale = (3 * size, 3 * size, 1)
    sun(context)
    w = bpy.data.worlds.get(names.WORLD_MODEL)
    if w is None:
        w = bpy.data.worlds.new(names.WORLD_MODEL); w.use_nodes = True
        bg = w.node_tree.nodes.get('Background')
        bg.inputs[0].default_value = (0.75, 0.78, 0.82, 1); bg.inputs[1].default_value = 0.35
    if _is_default_world(scene.world):
        scene.world = sky_world()
    if scene.world and scene.world != w:
        scene[names.SC_TERRAIN_WORLD] = scene.world.name
    cam = bpy.data.objects.get(names.MODEL_CAMERA)
    if cam is None:
        cd = bpy.data.cameras.new(names.MODEL_CAMERA)
        cam = bpy.data.objects.new(names.MODEL_CAMERA, cd); col.objects.link(cam)
    georef.attach(cam, scene)
    cam.data.lens = 50
    cam.data.clip_end = size * 20
    tgt = Vector((cx, cy, (zlow + ztop) / 2))
    cam.location = tgt + Vector((-0.45, -0.65, 0.62)) * size * 2
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    context.view_layer.update()
    M = georef.matrix(scene)
    pts = []
    for x in (x0, x1):
        for y in (y0, y1):
            for z in (zlow, ztop):
                pts += list(M @ Vector((x, y, z)))
    co, _sc = cam.camera_fit_coords(context.evaluated_depsgraph_get(), pts)
    cam.location = tgt + (M.inverted() @ co - tgt) * 1.12
    if scene.camera is None:
        scene.camera = cam
    setup_viewports(context, size)


# ------------------------------------------------------------------ trees

def detect_trees(props, ox, oy, dtm):
    """Tree positions and heights from a normalised surface model (nDSM) or a DSM."""
    path = abspath(props.ndsm_path)
    nd = raster.Raster(path)
    A = np.nan_to_num(nd.A, nan=0.0)
    p = nd.dx
    b = max(1, int(round(1.0 / p)))
    H, W = A.shape
    H2, W2 = H // b * b, W // b * b
    blk = A[:H2, :W2].reshape(H2 // b, b, W2 // b, b).transpose(0, 2, 1, 3).reshape(H2 // b, W2 // b, b * b)
    crown = blk.max(-1).astype(np.float64)
    ground = np.median(blk, -1).astype(np.float64)
    del blk, A
    cs = p * b
    xc = nd.info['left'] + (np.arange(W2 // b) + 0.5) * cs - ox
    yc = nd.info['bottom'] + (np.arange(H2 // b) + 0.5) * cs - oy
    del nd
    XX, YY = np.meshgrid(xc, yc)
    if props.ndsm_is_dsm:
        g = dtm.sample(XX, YY, ox, oy)
        crown -= g
        ground -= g
    # subtract the local ground level (a snow cover, for example)
    gl = raster.gauss(raster.window(ground, max(1, int(round(6.5 / cs))), np.min), 3.0 / cs)
    ch_raw = crown - gl
    ch = raster.gauss(ch_raw, 0.6 / cs)
    rng = np.random.default_rng(1)
    chj = ch + rng.uniform(0, 1e-4, ch.shape)
    m5 = raster.window(chj, max(1, int(round(2.0 / cs))), np.max)
    m7 = raster.window(chj, max(1, int(round(3.0 / cs))), np.max)
    peak = (ch >= props.min_tree_height) & (((ch < 15) & (chj >= m5)) | ((ch >= 15) & (chj >= m7)))
    ii, jj = np.nonzero(peak)
    x, y = xc[jj], yc[ii]
    h = np.clip(np.maximum(ch[ii, jj], ch_raw[ii, jj]), props.min_tree_height, 45.0)
    di = dtm.info
    inside = ((x + ox > di['left']) & (x + ox < di['right']) & (y + oy > di['bottom']) & (y + oy < di['top']))
    x, y, h = x[inside], y[inside], h[inside]
    z = dtm.sample(x, y, ox, oy)
    return x, y, z, h


def detect_trees_gpkg(props, ox, oy, dtm):
    """Trees from a GeoPackage of single trees (points with a height column).

    Tested with the Bavarian dataset "Einzelbäume" (LDBV). Only the points inside the
    terrain tile are read, through the spatial index (R-tree) of every table whose extent
    touches the tile. The file may be huge.
    """
    import sqlite3
    import struct
    path = abspath(props.trees_gpkg_path)
    di = dtm.info
    x0, x1, y0, y1 = di['left'], di['right'], di['bottom'], di['top']
    con = sqlite3.connect(path)
    try:
        c = con.cursor()
        tabs = c.execute("select c.table_name, g.column_name from gpkg_contents c "
                         "join gpkg_geometry_columns g on g.table_name = c.table_name "
                         "where c.data_type = 'features' and c.max_x >= ? and c.min_x <= ? "
                         "and c.max_y >= ? and c.min_y <= ?", (x0, x1, y0, y1)).fetchall()
        if not tabs:
            raise ValueError("The GeoPackage does not cover the terrain tile")
        pts = []
        for t, gc in tabs:
            cols = [r[1] for r in c.execute(f'pragma table_info("{t}")')]
            hcol = next((k for k in cols if k.lower() in ("baumhoehe", "hoehe", "height")), None)
            if hcol is None:
                raise ValueError(f"Table {t}: no height column (baumhoehe, hoehe or height)")
            rt = f"rtree_{t}_{gc}"
            has_rt = c.execute("select 1 from sqlite_master where name = ?", (rt,)).fetchone()
            if has_rt:
                q = (f'select t."{gc}", t."{hcol}" from "{t}" t join "{rt}" r on t.rowid = r.id '
                     'where r.maxx >= ? and r.minx <= ? and r.maxy >= ? and r.miny <= ?')
                rows = c.execute(q, (x0, x1, y0, y1))
            else:
                rows = c.execute(f'select "{gc}", "{hcol}" from "{t}"')
            for blob, h in rows:
                if blob is None or h is None:
                    continue
                flags = blob[3]
                env = (flags >> 1) & 7
                if env >= 1:          # envelope in the header: minx, maxx, miny, maxy – for a point = coordinate
                    x, y = struct.unpack('<d', blob[8:16])[0], struct.unpack('<d', blob[24:32])[0]
                else:                 # WKB (multi)point after the 8 byte header
                    w = blob[8:]
                    bo = '<' if w[0] == 1 else '>'
                    typ = struct.unpack(bo + 'I', w[1:5])[0] % 1000
                    off = 5 if typ == 1 else 5 + 4 + 5
                    x, y = struct.unpack(bo + 'dd', w[off:off + 16])
                if x0 <= x <= x1 and y0 <= y <= y1:
                    pts.append((x, y, h))
    finally:
        con.close()
    if not pts:
        raise ValueError("No trees found in the tile")
    P = np.array(pts, dtype=np.float64)
    x, y, h = P[:, 0] - ox, P[:, 1] - oy, P[:, 2]
    keep = h >= props.min_tree_height
    x, y, h = x[keep], y[keep], np.clip(h[keep], props.min_tree_height, 60.0)
    z = dtm.sample(x, y, ox, oy)
    return x, y, z, h


def _tree_assets(color):
    ac = bpy.data.collections.get(names.COL_TREE_ASSETS) or bpy.data.collections.new(names.COL_TREE_ASSETS)
    mt = _simple_mat(names.MAT_MODEL_TREE, color, 0.9)
    from mathutils import Matrix

    def mk(name, bm):
        me = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)
        bm.to_mesh(me); bm.free()
        me.materials.clear(); me.materials.append(mt)
        me.shade_smooth(); me.set_sharp_from_angle(angle=math.radians(40))
        o = bpy.data.objects.get(name) or bpy.data.objects.new(name, me)
        o.data = me
        if o.name not in ac.objects:
            ac.objects.link(o)
        return o

    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.30, radius2=0.0, depth=0.82,
                          matrix=Matrix.Translation((0, 0, 0.59)))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.025, radius2=0.025, depth=0.2,
                          matrix=Matrix.Translation((0, 0, 0.1)))
    cone = mk(names.TREE_CONE, bm)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.5)
    for v in bm.verts:
        v.co.z = max(v.co.z, 0) * 0.9
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    shrub = mk(names.TREE_SHRUB, bm)
    return ac, cone, shrub


def build_trees(context, props):
    scene = context.scene
    dtm = raster.get_raster(abspath(props.dtm_path))
    ox, oy = origin(scene, dtm)
    if props.tree_source == 'GPKG':
        x, y, z, h = detect_trees_gpkg(props, ox, oy, dtm)
    else:
        x, y, z, h = detect_trees(props, ox, oy, dtm)
    n = len(x)
    col = collection(names.COL_TREES, scene=scene)
    clear_collection(col)
    me = bpy.data.meshes.new(names.MODEL_TREES_POINTS)
    me.vertices.add(n)
    me.vertices.foreach_set('co', np.stack([x, y, z], 1).astype(np.float32).ravel())
    for name, vals in ((names.AT_HEIGHT, h), (names.AT_DZ_BOARD, np.zeros(n)),
                       (names.AT_EDGE, np.zeros(n)), (names.AT_HIDDEN, np.zeros(n))):
        a = me.attributes.new(name, 'FLOAT', 'POINT')
        a.data.foreach_set('value', np.asarray(vals, dtype=np.float32))
    me.update()
    ob = bpy.data.objects.new(names.MODEL_TREES, me)
    col.objects.link(ob)
    georef.attach(ob, scene)
    ac, cone, shrub = _tree_assets(tuple(props.tree_color) + (1.0,))
    if ac.name not in scene.collection.children:
        scene.collection.children.link(ac)
    ac.hide_viewport = True
    ac.hide_render = True
    md = ob.modifiers.new(names.MODEL_TREES, 'NODES')
    md.node_group = vegetation.tree_nodes(scene, cone, shrub, props.shrub_limit, props.broadleaf_share / 100.0)
    update_tree_offsets(context, props)
    apply_variant(context)
    props.info_text = f"{n} trees, {(h < props.shrub_limit).sum()} of them below {props.shrub_limit:g} m"


def update_tree_offsets(context, props):
    """Height difference terrain → cardboard layer per tree (dz_cardboard) and edge mark."""
    scene = context.scene
    ob = bpy.data.objects.get(names.MODEL_TREES)
    if ob is None or names.SC_BOARD not in scene:
        return
    pp = scene[names.SC_BOARD]
    Zs, x0, y0, s = board_grid(scene, props)
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    h_, w_ = Zs.shape
    fx = (co[:, 0] - x0) / s
    fy = (co[:, 1] - y0) / s
    edge = (fx < 0.5) | (fy < 0.5) | (fx > w_ - 1.5) | (fy > h_ - 1.5)
    fx = np.clip(fx, 0, w_ - 1.0001); fy = np.clip(fy, 0, h_ - 1.0001)
    j = np.floor(fx).astype(int); i = np.floor(fy).astype(int); tx = fx - j; ty = fy - i
    v = (Zs[i, j] * (1 - tx) * (1 - ty) + Zs[i, j + 1] * tx * (1 - ty)
         + Zs[i + 1, j] * (1 - tx) * ty + Zs[i + 1, j + 1] * tx * ty)
    dz = pp['interval']
    top = np.floor(v / dz + 1e-6) * dz
    top = np.where(top < pp['L0'], pp['zbase'], np.minimum(top, pp['Lmax']))
    me.attributes[names.AT_DZ_BOARD].data.foreach_set('value', (top - co[:, 2]).astype(np.float32))
    me.attributes[names.AT_EDGE].data.foreach_set('value', edge.astype(np.float32))
    me.update()


# ------------------------------------------------------------------ variants

def _vis(obj_or_col, show):
    if obj_or_col is not None:
        obj_or_col.hide_viewport = not show
        obj_or_col.hide_render = not show


def _ortho_in_solid_view(mat, show):
    """The Solid view (colour Texture) shows the image of the image node directly and ignores the
    mix node – so the image is taken out of the node when the orthophoto is off, and put back."""
    for n in mat.node_tree.nodes:
        if n.bl_idname != 'ShaderNodeTexImage':
            continue
        if n.image is not None:
            mat[names.MAT_ORTHO_IMAGE] = n.image.name
        if show:
            n.image = bpy.data.images.get(mat.get(names.MAT_ORTHO_IMAGE, ""))
        elif n.image is not None:
            n.image.use_fake_user = True   # keep it in the file while no node uses it
            n.image = None
    if not show:
        mix = mat.node_tree.nodes.get(names.NODE_TERRAIN_COLOUR)
        a = mix and next((s for s in mix.inputs if s.identifier == 'A_Color'), None)
        if a is not None:
            mat.diffuse_color = tuple(a.default_value)


def apply_variant(context):
    scene = context.scene
    g = scene.bonsai_btk_site
    ortho = 1.0 if g.show_ortho else 0.0
    board = g.variant == 'CARDBOARD'
    _vis(bpy.data.collections.get(names.COL_TERRAIN), not board)
    _vis(bpy.data.collections.get(names.COL_LAYERS), board)
    _vis(bpy.data.objects.get(names.TABLE), board)
    # the terrain keeps its material (in case it was overwritten by accident)
    ter, tm = bpy.data.objects.get(names.TERRAIN), bpy.data.materials.get(names.MAT_TERRAIN)
    if ter is not None and tm is not None and ter.type == 'MESH':
        if not ter.data.materials:
            ter.data.materials.append(tm)
        elif ter.data.materials[0] is not tm:
            ter.data.materials[0] = tm
    for name in (names.MAT_BOARD, names.MAT_TERRAIN):
        m = bpy.data.materials.get(name)
        if m and m.node_tree and names.NODE_ORTHO in m.node_tree.nodes:
            m.node_tree.nodes[names.NODE_ORTHO].outputs[0].default_value = ortho
            _ortho_in_solid_view(m, bool(ortho))
    ng = bpy.data.node_groups.get(names.NG_TREES)
    if ng and names.NODE_ON_BOARD in ng.nodes:
        ng.nodes[names.NODE_ON_BOARD].outputs[0].default_value = 1.0 if board else 0.0
    if ng and names.NODE_NATURAL in ng.nodes:
        ng.nodes[names.NODE_NATURAL].outputs[0].default_value = 0.0 if (board or not g.natural_trees) else 1.0
    _vis(bpy.data.collections.get(names.COL_MEADOW), not board and g.show_meadow)
    buildings.apply(context, board)
    mw = bpy.data.worlds.get(names.WORLD_MODEL)
    if board and mw:
        if scene.world and scene.world != mw:
            scene[names.SC_TERRAIN_WORLD] = scene.world.name
        scene.world = mw
    elif not board and names.SC_TERRAIN_WORLD in scene:
        w = bpy.data.worlds.get(scene[names.SC_TERRAIN_WORLD])
        if w:
            scene.world = w
    for win in context.window_manager.windows:
        for a in win.screen.areas:
            a.tag_redraw()
