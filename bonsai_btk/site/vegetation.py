# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Natural vegetation for the terrain: tree species (replaceable) and meadow/stones from the orthophoto.

Collections (hidden; models 1 m high, foot at the origin – your own models may go in):
  names.COL_SPECIES / COL_CONIFERS, COL_BROADLEAVES, COL_SHRUBS
  names.COL_SCATTER_ASSETS / COL_GRASS, COL_STONES
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, noise

from . import names

ASSET_PREFIX = "BTK_"       # models created here; others in the collections are the user's own


# ------------------------------------------------------------------ helpers

def _col(name, parent):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in parent.children:
        parent.children.link(c)
    return c


def _hidden_root(scene, name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in scene.collection.children:
        scene.collection.children.link(c)
    c.hide_viewport = True
    c.hide_render = True
    return c


def _obj(name, bm, mat, col, smooth=True):
    me = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    for m in (mat if isinstance(mat, (list, tuple)) else [mat]):
        me.materials.append(m)
    if smooth:
        me.shade_smooth()
    o = bpy.data.objects.get(name) or bpy.data.objects.new(name, me)
    o.data = me
    if o.name not in col.objects:
        col.objects.link(o)
    return o


def _noise(v, seed, scale=2.0):
    return noise.noise(Vector(v) * scale + Vector((seed * 7.3, seed * 3.1, seed * 5.7)))


def _mat_random(name, c1, c2, rough=0.8, attr=None, attr_mix=0.0):
    """Principled with colour variation per instance (Object Info → Random); optionally orthophoto colour."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    m.diffuse_color = tuple((a + b) / 2 for a, b in zip(c1, c2)) + (1,)
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links
    out = N.new('ShaderNodeOutputMaterial'); out.location = (600, 0)
    bs = N.new('ShaderNodeBsdfPrincipled'); bs.location = (300, 0)
    bs.inputs['Roughness'].default_value = rough
    L.new(bs.outputs[0], out.inputs[0])
    oi = N.new('ShaderNodeObjectInfo'); oi.location = (-500, 0)
    ramp = N.new('ShaderNodeValToRGB'); ramp.location = (-250, 0)
    ramp.color_ramp.elements[0].color = tuple(c1) + (1,)
    ramp.color_ramp.elements[1].color = tuple(c2) + (1,)
    L.new(oi.outputs['Random'], ramp.inputs[0])
    col = ramp.outputs['Color']
    if attr:
        at = N.new('ShaderNodeAttribute'); at.location = (-250, -300)
        at.attribute_type = 'INSTANCER'; at.attribute_name = attr
        mx = N.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.location = (50, -100)
        mx.inputs[0].default_value = attr_mix
        L.new(col, mx.inputs[6]); L.new(at.outputs['Color'], mx.inputs[7])
        col = mx.outputs[2]
    L.new(col, bs.inputs['Base Color'])
    return m


def materials():
    return dict(
        conifer=_mat_random("BTK_Conifer", (0.018, 0.040, 0.020), (0.045, 0.080, 0.035), 0.85),
        broadleaf=_mat_random("BTK_Broadleaf", (0.050, 0.100, 0.020), (0.110, 0.170, 0.040), 0.8),
        trunk=_mat_random("BTK_Trunk", (0.060, 0.045, 0.035), (0.100, 0.080, 0.060), 0.9),
        grass=_mat_random("BTK_Grass", (0.050, 0.090, 0.018), (0.120, 0.160, 0.040), 0.7, names.AT_ORTHO_COLOUR, 0.55),
        stone=_mat_random("BTK_Stone", (0.180, 0.175, 0.165), (0.320, 0.310, 0.290), 0.9, names.AT_ORTHO_COLOUR, 0.35),
    )


# ------------------------------------------------------------------ models (1 m high, foot at the origin)

def _spruce(seed, M):
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=6, radius1=0.018, radius2=0.006, depth=1.0,
                          matrix=Matrix.Translation((0, 0, 0.5)))
    for f in bm.faces:
        f.material_index = 1
    tiers = rnd.randint(8, 11)
    z0 = rnd.uniform(0.08, 0.16)
    seg = 14
    for k in range(tiers):
        f = k / tiers
        zb = z0 + (0.97 - z0) * f
        zt = z0 + (0.97 - z0) * (k + 1.6) / tiers
        r = (0.30 * (1 - f) ** 0.95 + 0.025) * rnd.uniform(0.9, 1.1)
        top = bm.verts.new((0, 0, min(zt, 1.0)))
        ring = []
        for i in range(seg):
            a = 2 * math.pi * (i + rnd.uniform(-0.2, 0.2)) / seg + k * 0.7
            rr = r * (1.0 if i % 2 == 0 else 0.72) * (1 + 0.18 * _noise((math.cos(a), math.sin(a), k), seed))
            droop = rr * 0.35
            ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), zb - droop)))
        for i in range(seg):
            bm.faces.new((ring[i], ring[(i + 1) % seg], top))
    return bm


def _broadleaf(seed, M):
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=6, radius1=0.035, radius2=0.02, depth=0.5,
                          matrix=Matrix.Translation((0, 0, 0.25)))
    for f in bm.faces:
        f.material_index = 1
    for b in range(rnd.randint(3, 5)):
        c = Vector((rnd.uniform(-0.12, 0.12), rnd.uniform(-0.12, 0.12), rnd.uniform(0.55, 0.72)))
        rad = rnd.uniform(0.18, 0.27)
        r = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=rad, matrix=Matrix.Translation(c))
        for v in r['verts']:
            d = v.co - c
            v.co = c + d * (1 + 0.28 * _noise(d, seed + b, 6.0))
    for v in bm.verts:
        v.co.z = min(v.co.z, 1.0)
    return bm


def _shrub(seed, M):
    rnd = random.Random(seed)
    bm = bmesh.new()
    for b in range(rnd.randint(4, 6)):
        c = Vector((rnd.uniform(-0.55, 0.55), rnd.uniform(-0.55, 0.55), 0.0))
        rad = rnd.uniform(0.35, 0.55)
        r = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=rad, matrix=Matrix.Translation(c))
        for v in r['verts']:
            d = v.co - c
            d = d * (1 + 0.3 * _noise(d, seed + b, 5.0))
            v.co = Vector((c.x + d.x, c.y + d.y, max(d.z, -0.05) * (1.0 / rad) * rnd.uniform(0.75, 0.95)))
    return bm


def _grass_tuft(seed, M):
    rnd = random.Random(seed)
    bm = bmesh.new()
    for b in range(rnd.randint(9, 14)):
        a = rnd.uniform(0, 2 * math.pi)
        base = Vector((rnd.uniform(-0.04, 0.04), rnd.uniform(-0.04, 0.04), 0))
        h = rnd.uniform(0.6, 1.0)
        lean = rnd.uniform(0.1, 0.45)
        w = 0.035
        side = Vector((-math.sin(a), math.cos(a), 0))
        fwd = Vector((math.cos(a), math.sin(a), 0))
        prev = None
        for s in range(4):
            t = s / 3
            c = base + fwd * lean * h * t * t + Vector((0, 0, h * t))
            ww = w * (1 - t) + 0.002
            pair = (bm.verts.new(c - side * ww), bm.verts.new(c + side * ww))
            if prev:
                bm.faces.new((prev[0], prev[1], pair[1], pair[0]))
            prev = pair
    return bm


def _stone(seed, M):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
    rnd = random.Random(seed)
    sx, sy, sz = rnd.uniform(0.8, 1.2), rnd.uniform(0.7, 1.1), rnd.uniform(0.45, 0.7)
    for v in bm.verts:
        d = v.co.copy()
        d *= 1 + 0.25 * _noise(d, seed, 2.5) + 0.08 * _noise(d, seed + 9, 8.0)
        v.co = Vector((d.x * sx, d.y * sy, d.z * sz - 0.12))
    return bm


def assets(scene):
    """Create the models (objects already in the collections stay – your own models are allowed)."""
    M = materials()
    root = _hidden_root(scene, names.COL_SPECIES)
    specs = [
        (_col(names.COL_CONIFERS, root), "Spruce", _spruce, 4, [M['conifer'], M['trunk']]),
        (_col(names.COL_BROADLEAVES, root), "Broadleaf", _broadleaf, 3, [M['broadleaf'], M['trunk']]),
        (_col(names.COL_SHRUBS, root), "Shrub", _shrub, 3, [M['conifer']]),
    ]
    sroot = _hidden_root(scene, names.COL_SCATTER_ASSETS)
    specs += [
        (_col(names.COL_GRASS, sroot), "Grass_Tuft", _grass_tuft, 4, [M['grass']]),
        (_col(names.COL_STONES, sroot), "Stone", _stone, 4, [M['stone']]),
    ]
    for col, base, fn, n, mats in specs:
        if len(col.objects) and not any(o.name.startswith(ASSET_PREFIX + base) for o in col.objects):
            continue  # the user's own models – leave them alone
        for i in range(n):
            _obj(f"{ASSET_PREFIX}{base}_{i}", fn(i + 1, M), mats, col, smooth=(base != "Grass_Tuft"))
    return M


# ------------------------------------------------------------------ node helpers

class _NB:
    def __init__(self, ng):
        self.ng, self.N, self.L = ng, ng.nodes, ng.links

    def node(self, t, loc, **kw):
        n = self.N.new(t); n.location = loc
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.L.new(a, b)

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.link(v, sock)
        else:
            sock.default_value = v

    def math(self, op, a, b, loc, c=None):
        m = self.node('ShaderNodeMath', loc, operation=op)
        for k, v in enumerate((a, b, c)):
            if v is not None:
                self.set(m.inputs[k], v)
        return m.outputs[0]

    def value(self, name, v, loc):
        n = self.node('ShaderNodeValue', loc)
        n.name = n.label = name
        n.outputs[0].default_value = v
        return n.outputs[0]

    def attr(self, name, loc, dtype='FLOAT'):
        a = self.node('GeometryNodeInputNamedAttribute', loc, data_type=dtype)
        a.inputs['Name'].default_value = name
        return a.outputs['Attribute']

    def rand(self, lo, hi, seed, loc, dtype='FLOAT'):
        r = self.node('FunctionNodeRandomValue', loc, data_type=dtype)
        r.inputs['Min'].default_value = lo
        r.inputs['Max'].default_value = hi
        r.inputs['Seed'].default_value = seed
        return r.outputs['Value']

    def coll(self, col, loc):
        c = self.node('GeometryNodeCollectionInfo', loc, transform_space='ORIGINAL')
        c.inputs['Collection'].default_value = col
        c.inputs['Separate Children'].default_value = True
        c.inputs['Reset Children'].default_value = True
        return c.outputs[0]

    def xyz(self, x, y, z, loc):
        c = self.node('ShaderNodeCombineXYZ', loc)
        for k, v in enumerate((x, y, z)):
            self.set(c.inputs[k], v)
        return c.outputs[0]

    def instance(self, pts, sel, inst, rot, scale, loc, pick_seed=None):
        n = self.node('GeometryNodeInstanceOnPoints', loc)
        self.link(pts, n.inputs['Points'])
        self.set(n.inputs['Selection'], sel)
        self.link(inst, n.inputs['Instance'])
        if pick_seed is not None:
            n.inputs['Pick Instance'].default_value = True
            self.link(self.rand(0, 999, pick_seed, (loc[0] - 200, loc[1] - 250), 'INT'), n.inputs['Instance Index'])
        self.set(n.inputs['Rotation'], rot)
        self.set(n.inputs['Scale'], scale)
        return n.outputs[0]


def _reset_group(name):
    ng = bpy.data.node_groups.get(name) or bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng.nodes.clear()
    for it in list(ng.interface.items_tree):
        ng.interface.remove(it)
    ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    return ng


# ------------------------------------------------------------------ trees

def tree_nodes(scene, cone, shrub, limit, broadleaf_share=0.15):
    """Geometry nodes group: cardboard model → cones/humps; terrain → tree species (or cones)."""
    assets(scene)
    ng = _reset_group(names.NG_TREES)
    b = _NB(ng)
    gi = b.node('NodeGroupInput', (-1600, 0))
    go = b.node('NodeGroupOutput', (1000, 0))
    on_board = b.value(names.NODE_ON_BOARD, 0.0, (-1600, 500))
    natural = b.value(names.NODE_NATURAL, 1.0, (-1600, 650))
    share = b.value(names.NODE_BROADLEAF_SHARE, broadleaf_share, (-1600, 800))
    height = b.attr(names.AT_HEIGHT, (-1600, -300))
    off = b.math('MULTIPLY', b.attr(names.AT_DZ_BOARD, (-1600, 300)), on_board, (-1350, 300))
    sp = b.node('GeometryNodeSetPosition', (-900, 100))
    b.link(gi.outputs[0], sp.inputs['Geometry'])
    b.link(b.xyz(0, 0, off, (-1150, 300)), sp.inputs['Offset'])
    pts = sp.outputs[0]
    # visible: not at the edge of the board (cardboard model only) and not under buildings
    ok = b.math('LESS_THAN', b.math('ADD', b.math('MULTIPLY', b.attr(names.AT_EDGE, (-1600, -550)), on_board, (-1350, -550)),
                                    b.attr(names.AT_HIDDEN, (-1600, -700)), (-1150, -600)), 0.5, (-950, -600))
    tall = b.math('GREATER_THAN', height, limit - 1e-4, (-1150, -300))
    low = b.math('SUBTRACT', 1.0, tall, (-950, -400))
    model = b.math('MULTIPLY', ok, b.math('SUBTRACT', 1.0, natural, (-1150, 700)), (-950, 700))
    real = b.math('MULTIPLY', ok, natural, (-950, 850))
    is_broadleaf = b.math('LESS_THAN', b.rand(0.0, 1.0, 3, (-1150, 1000)), share, (-950, 1000))
    rot = b.xyz(0, 0, b.rand(0.0, 6.2832, 1, (-900, -900)), (-700, -900))
    width = b.rand(0.85, 1.15, 2, (-900, -1100))
    wh = b.math('MULTIPLY', height, width, (-700, -1100))
    s_real = b.xyz(wh, wh, height, (-500, -1100))
    j = b.node('GeometryNodeJoinGeometry', (800, 0))
    # trees of the cardboard model
    kg = b.node('GeometryNodeObjectInfo', (-300, 600)); kg.inputs['Object'].default_value = cone
    lt = b.node('GeometryNodeObjectInfo', (-300, 350)); lt.inputs['Object'].default_value = shrub
    b.link(b.instance(pts, b.math('MULTIPLY', tall, model, (-500, 600)), kg.outputs['Geometry'], rot, height,
                      (100, 600)), j.inputs[0])
    b.link(b.instance(pts, b.math('MULTIPLY', low, model, (-500, 400)), lt.outputs['Geometry'], rot,
                      b.math('MULTIPLY', height, 1.6, (-500, 250)), (100, 350)), j.inputs[0])
    # natural trees
    t_real = b.math('MULTIPLY', tall, real, (-500, 0))
    sel_c = b.math('MULTIPLY', t_real, b.math('SUBTRACT', 1.0, is_broadleaf, (-700, -150)), (-300, -100))
    sel_b = b.math('MULTIPLY', t_real, is_broadleaf, (-300, -250))
    sel_s = b.math('MULTIPLY', low, real, (-300, -400))
    for k, (col, sel) in enumerate(((names.COL_CONIFERS, sel_c), (names.COL_BROADLEAVES, sel_b),
                                    (names.COL_SHRUBS, sel_s))):
        inst = b.instance(pts, sel, b.coll(bpy.data.collections[col], (-100, -100 - 250 * k)), rot, s_real,
                          (300, -100 - 250 * k), pick_seed=11 + k)
        b.link(inst, j.inputs[0])
    b.link(j.outputs[0], go.inputs[0])
    return ng


# ------------------------------------------------------------------ meadow and stones

def meadow_nodes(terrain, img, grass_density, stone_density, radius):
    ng = _reset_group(names.NG_MEADOW)
    b = _NB(ng)
    go = b.node('NodeGroupOutput', (1600, 0))
    ti = b.node('GeometryNodeObjectInfo', (-1800, 0), transform_space='RELATIVE')
    ti.inputs['Object'].default_value = terrain
    ti.name = ti.label = names.NODE_TERRAIN
    cam = b.node('GeometryNodeInputActiveCamera', (-2000, -400))
    ci = b.node('GeometryNodeObjectInfo', (-1800, -400), transform_space='RELATIVE')
    b.link(cam.outputs[0], ci.inputs['Object'])
    pos = b.node('GeometryNodeInputPosition', (-1800, -700)).outputs[0]
    dist = b.node('ShaderNodeVectorMath', (-1550, -600), operation='DISTANCE')
    b.link(pos, dist.inputs[0]); b.link(ci.outputs['Location'], dist.inputs[1])
    dist = dist.outputs['Value']
    R = b.value(names.NODE_RADIUS, radius, (-1800, -1000))
    # drop faces outside the radius right away (faster)
    dl = b.node('GeometryNodeDeleteGeometry', (-1200, 0), domain='FACE')
    b.link(ti.outputs['Geometry'], dl.inputs['Geometry'])
    b.link(b.math('GREATER_THAN', dist, b.math('MULTIPLY', R, 1.05, (-1550, -900)), (-1350, -700)), dl.inputs['Selection'])
    mesh = dl.outputs[0]
    # fall-off with distance: full up to 0.4·R, then smoothly to 0
    mr = b.node('ShaderNodeMapRange', (-1200, -500), interpolation_type='SMOOTHSTEP')
    b.link(dist, mr.inputs['Value'])
    b.link(b.math('MULTIPLY', R, 0.4, (-1400, -900)), mr.inputs['From Min'])
    b.link(R, mr.inputs['From Max'])
    mr.inputs['To Min'].default_value = 1.0
    mr.inputs['To Max'].default_value = 0.0
    fall = mr.outputs['Result']
    vp = b.node('GeometryNodeIsViewport', (-1200, -800)).outputs[0]
    vpf = b.math('ADD', b.math('MULTIPLY', vp, -0.9, (-1000, -800)), 1.0, (-850, -800))  # viewport: 10 %
    fall = b.math('MULTIPLY', fall, vpf, (-850, -550))
    # orthophoto at the point
    uv = b.attr('UVMap', (-1600, 400), 'FLOAT_VECTOR')
    it = b.node('GeometryNodeImageTexture', (-1350, 400))
    if img is not None:
        it.inputs['Image'].default_value = img
    b.link(uv, it.inputs['Vector'])
    colr = it.outputs['Color']
    sc = b.node('FunctionNodeSeparateColor', (-1100, 400))
    b.link(colr, sc.inputs[0])
    r, g, bl = sc.outputs['Red'], sc.outputs['Green'], sc.outputs['Blue']
    total = b.math('ADD', b.math('ADD', r, g, (-900, 600)), bl, (-750, 600))
    green = b.math('DIVIDE', g, b.math('MAXIMUM', total, 1e-4, (-600, 600)), (-450, 600))   # share of green
    bright = b.math('DIVIDE', total, 3.0, (-600, 450))                                      # linear
    # meadow: greenish and not bright (no snow, no rock)
    m_grass = b.math('MULTIPLY',
                     b.math('MINIMUM', b.math('MAXIMUM', b.math('MULTIPLY', b.math('SUBTRACT', green, 0.345, (-300, 700)), 33.0, (-150, 700)), 0.0, (0, 700)), 1.0, (150, 700)),
                     b.math('LESS_THAN', bright, 0.20, (-300, 450)), (300, 600))
    # stones: grey (little green), medium brightness
    m_stone = b.math('MULTIPLY', b.math('LESS_THAN', green, 0.36, (-300, 300)),
                     b.math('MULTIPLY', b.math('GREATER_THAN', bright, 0.06, (-300, 150)),
                            b.math('LESS_THAN', bright, 0.45, (-150, 150)), (0, 150)), (300, 250))
    free = b.math('SUBTRACT', 1.0, b.attr(names.AT_UNDER_BUILDING, (-600, 100)), (-300, 50))
    dg = b.value(names.NODE_GRASS_DENSITY, grass_density, (-300, 900))
    ds = b.value(names.NODE_STONE_DENSITY, stone_density, (-300, 1000))
    seed = b.node('FunctionNodeInputInt', (-300, 1100)); seed.name = seed.label = names.NODE_SEED
    j = b.node('GeometryNodeJoinGeometry', (1400, 0))
    rot = b.xyz(0, 0, b.rand(0.0, 6.2832, 5, (700, -700)), (900, -700))
    for k, (mask, dens, col, smin, smax) in enumerate(((m_grass, dg, names.COL_GRASS, 0.12, 0.30),
                                                       (m_stone, ds, names.COL_STONES, 0.08, 0.55))):
        y = 200 - 600 * k
        dfield = b.math('MULTIPLY', b.math('MULTIPLY', b.math('MULTIPLY', mask, dens, (500, y + 150)), fall, (650, y + 150)),
                        free, (800, y + 150))
        dp = b.node('GeometryNodeDistributePointsOnFaces', (950, y), distribute_method='RANDOM')
        b.link(mesh, dp.inputs['Mesh'])
        b.link(dfield, dp.inputs['Density'])
        b.link(b.math('ADD', seed.outputs[0], 17 * k, (800, y - 200)), dp.inputs['Seed'])
        st = b.node('GeometryNodeStoreNamedAttribute', (1100, y), data_type='FLOAT_COLOR', domain='POINT')
        st.inputs['Name'].default_value = names.AT_ORTHO_COLOUR
        b.link(dp.outputs['Points'], st.inputs['Geometry'])
        b.link(colr, st.inputs['Value'])
        s = b.rand(smin, smax, 7 + k, (1100, y - 300))
        b.link(b.instance(st.outputs[0], True, b.coll(bpy.data.collections[col], (1100, y - 450)), rot, s,
                          (1250, y), pick_seed=21 + k), j.inputs[0])
    b.link(j.outputs[0], go.inputs[0])
    return ng


def build_meadow(context, props):
    """Object names.MEADOW_OBJECT with geometry nodes – grass and stones from the orthophoto around the active camera."""
    from . import build
    scene = context.scene
    terrain = bpy.data.objects.get(names.TERRAIN)
    if terrain is None:
        raise ValueError("Load the terrain first")
    assets(scene)
    img = None
    m = bpy.data.materials.get(names.MAT_TERRAIN)
    if m and m.node_tree:
        for n in m.node_tree.nodes:
            if n.bl_idname == 'ShaderNodeTexImage' and n.image:
                img = n.image
    if img is None:
        raise ValueError("The meadow needs the orthophoto")
    col = build.collection(names.COL_MEADOW, scene=scene)
    ob = bpy.data.objects.get(names.MEADOW_OBJECT)
    if ob is None:
        me = bpy.data.meshes.new(names.MEADOW_OBJECT)
        ob = bpy.data.objects.new(names.MEADOW_OBJECT, me)
        col.objects.link(ob)
    ng = meadow_nodes(terrain, img, props.grass_density, props.stone_density, props.scatter_radius)
    md = ob.modifiers.get(names.MEADOW_OBJECT) or ob.modifiers.new(names.MEADOW_OBJECT, 'NODES')
    md.node_group = ng
    if scene.camera is None:
        props.info_text = "Meadow created – it appears around the active camera (no camera yet)"
    else:
        props.info_text = (f"Meadow around {scene.camera.name}, radius {props.scatter_radius:g} m "
                           "(viewport: 10 % density)")
    return ob


def relink_terrain(terrain):
    ng = bpy.data.node_groups.get(names.NG_MEADOW)
    if ng and names.NODE_TERRAIN in ng.nodes:
        ng.nodes[names.NODE_TERRAIN].inputs['Object'].default_value = terrain


def update_values(props):
    ng = bpy.data.node_groups.get(names.NG_MEADOW)
    if ng:
        for name, v in ((names.NODE_GRASS_DENSITY, props.grass_density), (names.NODE_STONE_DENSITY, props.stone_density),
                        (names.NODE_RADIUS, props.scatter_radius)):
            if name in ng.nodes:
                ng.nodes[name].outputs[0].default_value = v
    tg = bpy.data.node_groups.get(names.NG_TREES)
    if tg and names.NODE_BROADLEAF_SHARE in tg.nodes:
        tg.nodes[names.NODE_BROADLEAF_SHARE].outputs[0].default_value = props.broadleaf_share / 100.0


def mark_terrain(boxes, margin=1.0):
    """Point attribute on the terrain: 1 under buildings (no meadow there)."""
    ob = bpy.data.objects.get(names.TERRAIN)
    if ob is None:
        return
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    mw = np.array(ob.matrix_world)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    hid = np.zeros(n, dtype=bool)
    for bx in boxes:
        hid |= ((co[:, 0] > bx[0] - margin) & (co[:, 0] < bx[1] + margin)
                & (co[:, 1] > bx[2] - margin) & (co[:, 1] < bx[3] + margin))
    a = me.attributes.get(names.AT_UNDER_BUILDING) or me.attributes.new(names.AT_UNDER_BUILDING, 'FLOAT', 'POINT')
    a.data.foreach_set('value', hid.astype(np.float32))
    me.update()
