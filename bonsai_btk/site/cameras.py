# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cameras without terrain edges in the picture: check and search.

Rays through a grid of the camera frame against the terrain (BVH):
- hit closer than a few metres to the tile edge   → edge in the picture (bad)
- no hit, ray points downwards                    → void below the tile (bad)
- no hit, ray points upwards                      → sky
Plus: how much of the building is visible (sample points on its box).
"""
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import buildings, names


class Terrain:
    def __init__(self, context):
        ob = bpy.data.objects.get(names.TERRAIN)
        if ob is None:
            raise ValueError("Load the terrain first")
        dg = context.evaluated_depsgraph_get()
        self.bvh = BVHTree.FromObject(ob, dg)
        self.mw = ob.matrix_world.copy()
        self.mi = self.mw.inverted()
        me = ob.data
        co = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        self.x0, self.y0, self.zmin = co.min(0)
        self.x1, self.y1, self.zmax = co.max(0)
        cell = math.sqrt((self.x1 - self.x0) * (self.y1 - self.y0) / max(len(co), 1))
        self.margin = max(4.0, 2.5 * cell)
        self.ztop = (self.mw @ Vector((0, 0, float(self.zmax)))).z

    def ray(self, o, d, dist=1e7):
        lo = self.mi @ o
        ld = (self.mi.to_3x3() @ d).normalized()
        loc, _n, _i, t = self.bvh.ray_cast(lo, ld, dist)
        if loc is None:
            return None, None
        return self.mw @ loc, t

    def load_trees(self):
        """Tree points (x, y, foot z, height) for the visibility check; without those under buildings."""
        self.trees = None
        ob = bpy.data.objects.get(names.MODEL_TREES)
        if ob is None or ob.type != 'MESH' or names.AT_HEIGHT not in ob.data.attributes:
            return
        me = ob.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
        h = np.empty(n, dtype=np.float32); me.attributes[names.AT_HEIGHT].data.foreach_get('value', h)
        keep = np.ones(n, dtype=bool)
        if names.AT_HIDDEN in me.attributes:
            v = np.empty(n, dtype=np.float32); me.attributes[names.AT_HIDDEN].data.foreach_get('value', v)
            keep = v < 0.5
        mw = np.array(ob.matrix_world)
        co = co @ mw[:3, :3].T + mw[:3, 3]
        self.trees = np.column_stack([co[keep], h[keep]]).astype(np.float64)

    def load_buildings(self):
        """Visible LoD2 neighbours as obstacles: one BVH in world coordinates, plus their boxes."""
        self.bld = None
        self.bld_boxes = np.zeros((0, 6))
        from . import buildings, lod2
        verts, polys, boxes = [], [], []
        for o in lod2.surroundings():
            if o.type != 'MESH' or o.get(names.OB_LOD2_HIDDEN) or o.hide_get():
                continue
            me = o.data
            n = len(me.vertices)
            if n == 0:
                continue
            co = np.empty(n * 3, dtype=np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
            mw = np.array(o.matrix_world)
            co = co @ mw[:3, :3].T + mw[:3, 3]
            k = len(verts)
            verts.extend(map(tuple, co))
            polys.extend(tuple(k + i for i in pl.vertices) for pl in me.polygons)
            boxes.append(buildings.bbox(o))
        if polys:
            self.bld = BVHTree.FromPolygons(verts, polys)
            self.bld_boxes = np.array(boxes, dtype=np.float64)

    def building_blocks(self, a, b):
        """Is a neighbouring building on the line of sight a→b?"""
        if getattr(self, 'bld', None) is None:
            return False
        d = b - a
        loc, _n, _i, _t = self.bld.ray_cast(a, d.normalized(), max(d.length - 0.5, 0.0))
        return loc is not None

    def in_building(self, p, margin=1.0):
        B = getattr(self, 'bld_boxes', None)
        if B is None or not len(B):
            return False
        m = margin
        return bool(np.any((B[:, 0] - m < p.x) & (p.x < B[:, 1] + m) & (B[:, 2] - m < p.y) & (p.y < B[:, 3] + m)
                           & (p.z < B[:, 5] + m)))

    def tree_blocks(self, a, b):
        """Is a tree (cone, radius 0.3·h) on the line of sight a→b?"""
        T = getattr(self, 'trees', None)
        if T is None or not len(T):
            return False
        d = np.array(b - a); a = np.array(a)
        L2 = d[0] ** 2 + d[1] ** 2
        if L2 < 1e-6:
            return False
        t = np.clip(((T[:, 0] - a[0]) * d[0] + (T[:, 1] - a[1]) * d[1]) / L2, 0, 1)
        px, py, pz = a[0] + t * d[0], a[1] + t * d[1], a[2] + t * d[2]
        r = 0.3 * T[:, 3]
        dist2 = (T[:, 0] - px) ** 2 + (T[:, 1] - py) ** 2
        return bool(np.any((dist2 < r * r) & (pz > T[:, 2]) & (pz < T[:, 2] + T[:, 3]) & (t > 0.02) & (t < 0.98)))

    def in_tree(self, p):
        T = getattr(self, 'trees', None)
        if T is None or not len(T):
            return False
        r = 0.3 * T[:, 3] + 1.0
        return bool(np.any(((T[:, 0] - p.x) ** 2 + (T[:, 1] - p.y) ** 2 < r * r) & (p.z < T[:, 2] + T[:, 3] + 1)))

    def height(self, x, y):
        loc, _t = self.ray(Vector((x, y, self.ztop + 100)), Vector((0, 0, -1)))
        return None if loc is None else loc.z

    def near_edge(self, p):
        r = self.margin
        p = self.mi @ p
        return p.x < self.x0 + r or p.x > self.x1 - r or p.y < self.y0 + r or p.y > self.y1 - r

    def inside(self, x, y, m):
        p = self.mi @ Vector((x, y, 0))
        x, y = p.x, p.y
        return self.x0 + m < x < self.x1 - m and self.y0 + m < y < self.y1 - m


def frame_dirs(rot, lens, sensor, aspect, nx, ny):
    if aspect >= 1:
        hw = sensor / 2 / lens; hh = hw / aspect
    else:
        hh = sensor / 2 / lens; hw = hh * aspect
    m = rot.to_matrix()
    out = []
    for j in range(ny):
        v = ((j + 0.5) / ny - 0.5) * 2 * hh
        for i in range(nx):
            u = ((i + 0.5) / nx - 0.5) * 2 * hw
            out.append((m @ Vector((u, v, -1))).normalized())
    return out, hw, hh


def target_box(context, terrain):
    """Box (x0, x1, y0, y1, z0, z1) of the building, or around the 3D cursor."""
    obs = buildings.buildings()
    if obs:
        b = np.array([buildings.bbox(o) for o in obs])
        # leave the active offset out: the camera is meant for the terrain
        return (b[:, 0].min(), b[:, 1].max(), b[:, 2].min(), b[:, 3].max(), b[:, 4].min(), b[:, 5].max())
    c = context.scene.cursor.location
    z = terrain.height(c.x, c.y)
    z = c.z if z is None else z
    return (c.x - 10, c.x + 10, c.y - 10, c.y + 10, z, z + 10)


def box_points(b, terrain=None):
    """Sample points on the building box – only those above the terrain (on a slope the foot is in the ground)."""
    x0, x1, y0, y1, z0, z1 = b
    xs, ys, zs = (x0, (x0 + x1) / 2, x1), (y0, (y0 + y1) / 2, y1), (z0 + 0.3, (z0 + z1) / 2, z1)
    pts = []
    for x in xs:
        for y in ys:
            for z in zs:
                if (x, y) == (xs[1], ys[1]) and z != zs[2]:
                    continue
                if terrain is not None:
                    zg = terrain.height(x, y)
                    if zg is not None and z < zg + 0.3:
                        continue
                pts.append(Vector((x, y, z)))
    return pts


def evaluate(terrain, pos, rot, lens, aspect, box, nx=48, ny=27, sensor=36.0):
    dirs, hw, hh = frame_dirs(rot, lens, sensor, aspect, nx, ny)
    edge = sky = 0
    for d in dirs:
        loc, _t = terrain.ray(pos, d)
        if loc is None:
            if d.z < 0.0:
                edge += 1
            else:
                sky += 1
        elif terrain.near_edge(loc):
            edge += 1
    n = len(dirs)
    # building: visible = in the frame and not hidden by terrain, trees or neighbouring buildings
    mi = rot.to_matrix().inverted()
    vis = 0
    us, vs = [], []
    pts = box_points(box, terrain)
    for p in pts:
        c = mi @ (p - pos)
        if c.z >= -0.1:
            continue
        u, v = -c.x / c.z, -c.y / c.z
        us.append(u); vs.append(v)
        if abs(u) > hw or abs(v) > hh:
            continue
        d = p - pos
        loc, t = terrain.ray(pos, d.normalized(), d.length)
        if ((loc is None or t > d.length - 0.5) and not terrain.tree_blocks(pos, p)
                and not terrain.building_blocks(pos, p)):
            vis += 1
    width = (max(us) - min(us)) / (2 * hw) if len(us) > 1 else 0.0
    return dict(edge=edge / n, sky=sky / n, building=vis / max(1, len(pts)), width=width)


def aspect_of(scene):
    r = scene.render
    return (r.resolution_x * r.pixel_aspect_x) / max(1, r.resolution_y * r.pixel_aspect_y)


def look(pos, tgt):
    return (tgt - pos).to_track_quat('-Z', 'Y')


def lens_for(width_m, dist, share, sensor=36.0, lo=24.0, hi=100.0):
    fov = 2 * math.atan(width_m / 2 / max(dist, 1e-3)) / share
    fov = min(fov, math.radians(120))
    return float(np.clip(sensor / 2 / math.tan(fov / 2), lo, hi))


def fit_lens(pos, rot, box, aspect, fill=0.85, sensor=36.0, lo=14.0):
    """Longest lens at which the whole building box is in the picture (at most fill of width/height)."""
    x0, x1, y0, y1, z0, z1 = box
    mi = rot.to_matrix().inverted()
    need = 0.0
    for x in (x0, x1):
        for y in (y0, y1):
            for z in (z0, z1):
                c = mi @ (Vector((x, y, z)) - pos)
                if c.z >= -0.1:
                    return lo
                u, v = abs(c.x / c.z), abs(c.y / c.z)
                # half of the longer picture side needed at distance 1 (the sensor fits the longer side)
                need = max(need, (max(u, v * aspect) if aspect >= 1 else max(u / aspect, v)) / fill)
    return max(lo, sensor / 2 / need) if need > 0 else lo


def search(context, kind):
    """Best camera for 'EYE' (eye level) or 'AERIAL' (oblique aerial view)."""
    t = Terrain(context)
    t.load_trees()
    t.load_buildings()
    box = target_box(context, t)
    cx, cy = (box[0] + box[1]) / 2, (box[2] + box[3]) / 2
    size = max(box[1] - box[0], box[3] - box[2], 10.0)
    height = box[5] - box[4]
    aspect = aspect_of(context.scene)
    best = None
    if kind == 'EYE':
        dists = [f * size for f in (3, 5, 8, 12)]
        dists = sorted(set(max(25.0, a) for a in dists))
        heights = [1.7]
        share, target_sky, ideal = 0.35, 0.22, 6 * size
    else:
        dists = [f * size for f in (5, 8, 12)]
        dists = sorted(set(max(60.0, a) for a in dists))
        heights = None
        share, target_sky, ideal = 0.25, 0.05, 8 * size
    tgt = Vector((cx, cy, box[4] + 0.45 * height))
    for k in range(24):
        az = 2 * math.pi * k / 24
        for a in dists:
            x, y = cx + a * math.sin(az), cy + a * math.cos(az)
            if not t.inside(x, y, t.margin + 10):
                continue
            zg = t.height(x, y)
            if zg is None:
                continue
            zlist = [zg + h for h in heights] if heights else [max(zg + 5, tgt.z + a * math.tan(math.radians(e))) for e in (25, 35)]
            for z in zlist:
                pos = Vector((x, y, z))
                if t.in_tree(pos) or t.in_building(pos):
                    continue
                rot = look(pos, tgt)
                lens = min(lens_for(size, a, share), fit_lens(pos, rot, box, aspect))
                r = evaluate(t, pos, rot, lens, aspect, box)
                if r['edge'] > 0 or r['building'] < 0.7:
                    continue
                score = r['building'] - abs(r['sky'] - target_sky) * 2 - 0.6 * abs(math.log(a / ideal))
                if best is None or score > best[0]:
                    best = (score, pos, rot, lens, r)
    if best is None:
        return None, t, box, aspect
    # check again on a finer grid
    _s, pos, rot, lens, _r = best
    r = evaluate(t, pos, rot, lens, aspect, box, 96, 54)
    return (pos, rot, lens, r), t, box, aspect


def make_camera(context, name, pos, rot, lens, clip):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cd = bpy.data.cameras.new(name)
        cam = bpy.data.objects.new(name, cd)
        col = bpy.data.collections.get(names.COL_CAMERAS) or bpy.data.collections.new(names.COL_CAMERAS)
        if col.name not in context.scene.collection.children:
            context.scene.collection.children.link(col)
        col.objects.link(cam)
    cam.location = pos
    cam.rotation_euler = rot.to_euler()
    cam.data.lens = lens
    cam.data.sensor_fit = 'AUTO'
    cam.data.clip_start = 0.1
    cam.data.clip_end = clip
    return cam


def _text(r):
    return (f"edge {r['edge'] * 100:.1f} %, sky {r['sky'] * 100:.0f} %, "
            f"building visible {r['building'] * 100:.0f} %")


# ------------------------------------------------------------------ operators

class BONSAI_BTK_OT_site_camera_check(bpy.types.Operator):
    bl_idname = "bonsai_btk.site_camera_check"
    bl_label = "Check Camera"
    bl_description = ("Check the active camera: is the edge of the terrain tile in the picture? "
                      "How much sky? Is the building visible?")

    def execute(self, context):
        cam = context.scene.camera
        if cam is None or cam.type != 'CAMERA':
            self.report({'ERROR'}, "No active camera")
            return {'CANCELLED'}
        try:
            t = Terrain(context)
        except ValueError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        t.load_trees()
        t.load_buildings()
        box = target_box(context, t)
        mw = cam.matrix_world
        r = evaluate(t, mw.translation.copy(), mw.to_quaternion(), cam.data.lens, aspect_of(context.scene),
                     box, 96, 54, cam.data.sensor_width)
        context.scene.bonsai_btk_site.info_text = f"{cam.name}: " + _text(r)
        self.report({'WARNING'} if r['edge'] > 0 else {'INFO'},
                    ("Terrain edge in the picture! " if r['edge'] > 0 else "No edge. ") + _text(r))
        return {'FINISHED'}


class BONSAI_BTK_OT_site_cameras_find(bpy.types.Operator):
    bl_idname = "bonsai_btk.site_cameras_find"
    bl_label = "Find Cameras"
    bl_description = ("Find two cameras on the building (or the 3D cursor) whose picture shows no terrain "
                      "edge: eye level and oblique aerial view (takes a few seconds)")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        g = context.scene.bonsai_btk_site
        if g.variant != 'TERRAIN':
            g.variant = 'TERRAIN'
        msgs = []
        first = None
        for kind, name in (('EYE', names.CAMERA_EYE), ('AERIAL', names.CAMERA_AERIAL)):
            try:
                res, t, _box, _a = search(context, kind)
            except ValueError as ex:
                self.report({'ERROR'}, str(ex))
                return {'CANCELLED'}
            if res is None:
                msgs.append(f"{name}: no position without edges found")
                continue
            pos, rot, lens, r = res
            clip = 3 * max(t.x1 - t.x0, t.y1 - t.y0)
            cam = make_camera(context, name, pos, rot, lens, clip)
            first = first or cam
            msgs.append(f"{name} {lens:.0f} mm – " + _text(r))
        if first:
            context.scene.camera = first
            _look_through(context)
        if not buildings.buildings():
            msgs.insert(0, "No building marked – aimed at 20 m around the 3D cursor")
        g.info_text = msgs[0] if msgs else ""
        self.report({'INFO'}, " | ".join(msgs))
        return {'FINISHED'}


def _look_through(context):
    """Show the 3D views through the scene camera (like numpad 0), so the result is visible at once."""
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces[0].region_3d.view_perspective = 'CAMERA'
                area.tag_redraw()


CLASSES = (BONSAI_BTK_OT_site_camera_check, BONSAI_BTK_OT_site_cameras_find)
