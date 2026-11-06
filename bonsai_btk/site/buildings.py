# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Buildings: in the cardboard model they sit on the layer below; trees underneath are hidden.

Buildings = objects with the custom property names.OB_BUILDING (button *Selection as Building*)
or objects in the collection names.COL_BUILDINGS. Objects close to each other
(walls and slabs of an IFC house, for example) form a group and move together.
They are moved only through *Delta Location Z* – the actual position stays.
"""
import bpy
import numpy as np
from mathutils import Vector

from . import names

GROUP_DISTANCE = 2.0           # objects closer than this belong to one building
TREE_MARGIN = 3.0              # no trees this close around the building
LOD2_MARGIN = 0.5              # LoD2 buildings touching the house this closely are hidden


_NOT_BUILDING = ("IfcSite", "IfcGeographicElement", "IfcSpace", "IfcAnnotation", "IfcGrid")


def is_site_object(o):
    """Terrain, cardboard model and other objects of these tools, or IFC site elements – never a building."""
    if o.name.startswith("BTK_"):
        return True
    try:
        from bonsai import tool
        el = tool.Ifc.get_entity(o)
    except Exception:
        el = None
    return el is not None and any(el.is_a(c) for c in _NOT_BUILDING)


def buildings():
    obs = [o for o in bpy.data.objects if o.get(names.OB_BUILDING)]
    c = bpy.data.collections.get(names.COL_BUILDINGS)
    if c:
        obs += [o for o in c.all_objects if o not in obs]
    obs = [o for o in obs if o.type not in {'EMPTY', 'CAMERA', 'LIGHT'} and not o.get(names.OB_LOD2)
           and not is_site_object(o)]
    s = set(obs)

    def ancestor_in(o):
        p = o.parent
        while p:
            if p in s:
                return True
            p = p.parent
        return False
    return [o for o in obs if not ancestor_in(o)]


def bbox(o):
    """World coordinate box without the object's own offset: (x0, x1, y0, y1, z0, z1)."""
    off = float(o.get(names.OB_DZ_ACTIVE, 0.0))
    # every object with geometry (meshes, but also curves such as Bonsai's pipe segments)
    if o.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES', 'POINTCLOUD'} and any(o.dimensions):
        P = np.array([tuple(o.matrix_world @ Vector(c)) for c in o.bound_box])
    else:
        P = np.array([tuple(o.matrix_world.translation)])
    return (P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(),
            P[:, 2].min() - off, P[:, 2].max() - off)


def groups(obs, boxes):
    """Group objects whose footprints (almost) touch."""
    n = len(obs)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    d = GROUP_DISTANCE
    for i in range(n):
        a = boxes[i]
        for j in range(i + 1, n):
            b = boxes[j]
            if a[0] - d <= b[1] and b[0] - d <= a[1] and a[2] - d <= b[3] and b[2] - d <= a[3]:
                parent[find(i)] = find(j)
    out = {}
    for i in range(n):
        out.setdefault(find(i), []).append(i)
    return list(out.values())


def layer_top(z, pp):
    """Top of the cardboard layer that something with its underside at z stands on."""
    dz = pp['interval']
    t = np.floor(z / dz + 1e-6) * dz
    if t < pp['L0']:
        return pp['zbase']
    return min(t, pp['Lmax'])


def apply(context, board):
    """Set the offset (cardboard model) or take it back (terrain); mark the trees."""
    scene = context.scene
    context.view_layer.update()
    obs = buildings()
    boxes = [bbox(o) for o in obs]
    pp = scene.get(names.SC_BOARD)
    from . import georef
    zo = georef.z_offset(scene)          # world z = orthometric height + zo
    keep = _unmoved_ifc_objects(obs + [o for o in bpy.data.objects if names.OB_DZ_ACTIVE in o])
    for grp in groups(obs, boxes):
        z0 = min(boxes[i][4] for i in grp)
        dz = (layer_top(z0 - zo, pp) + zo - z0) if (board and pp) else 0.0
        for i in grp:
            o = obs[i]
            old = float(o.get(names.OB_DZ_ACTIVE, 0.0))
            o.delta_location.z += dz - old
            o[names.OB_DZ_ACTIVE] = dz
    # surroundings (LoD2): every building on its own onto the layer below
    from . import lod2
    lod = lod2.surroundings()
    lboxes = [bbox(o) for o in lod]
    for o, b in zip(lod, lboxes):
        dz = (layer_top(b[4] - zo, pp) + zo - b[4]) if (board and pp) else 0.0
        old = float(o.get(names.OB_DZ_ACTIVE, 0.0))
        o.delta_location.z += dz - old
        o[names.OB_DZ_ACTIVE] = dz
    # reset objects that are no longer buildings
    for o in bpy.data.objects:
        if names.OB_DZ_ACTIVE in o and o not in obs and o not in lod:
            o.delta_location.z -= float(o[names.OB_DZ_ACTIVE])
            del o[names.OB_DZ_ACTIVE]
    _record_unmoved(context, keep)
    mark_all(boxes, lboxes)
    return len(obs)


def _unmoved_ifc_objects(obs):
    """IFC objects (with their children) whose position Bonsai still regards as saved."""
    try:
        from bonsai import tool
    except ImportError:
        return []
    todo, seen = list(obs), set()
    while todo:
        o = todo.pop()
        if o in seen:
            continue
        seen.add(o)
        todo.extend(o.children)
    return [o for o in seen if tool.Ifc.get_entity(o) is not None and not tool.Ifc.is_moved(o)]


def _record_unmoved(context, objs):
    """The cardboard offset is only for the view: tell Bonsai the objects are where they were, so
    saving the IFC in the cardboard variant does not write the offset into the placements."""
    if not objs:
        return
    from bonsai import tool
    context.view_layer.update()
    for o in objs:
        tool.Geometry.record_object_position(o)


def mark_trees(boxes=None):
    ob = bpy.data.objects.get(names.MODEL_TREES)
    if ob is None or ob.type != 'MESH':
        return
    if boxes is None:
        boxes = [bbox(o) for o in buildings()]
    me = ob.data
    n = len(me.vertices)
    if names.AT_HIDDEN not in me.attributes:
        me.attributes.new(names.AT_HIDDEN, 'FLOAT', 'POINT')
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    mw = np.array(ob.matrix_world)
    W = co @ mw[:3, :3].T + mw[:3, 3]
    x, y = W[:, 0], W[:, 1]
    hid = np.zeros(n, dtype=bool)
    r = TREE_MARGIN
    for b in boxes:
        hid |= (x > b[0] - r) & (x < b[1] + r) & (y > b[2] - r) & (y < b[3] + r)
    me.attributes[names.AT_HIDDEN].data.foreach_set('value', hid.astype(np.float32))
    me.update()
    return int(hid.sum())


def _overlap(a, b, d):
    return a[0] - d <= b[1] and b[0] - d <= a[1] and a[2] - d <= b[3] and b[2] - d <= a[3]


def mark_all(boxes=None, lboxes=None):
    """Hide meadow and trees under buildings; hide LoD2 buildings at your own house."""
    if boxes is None:
        boxes = [bbox(o) for o in buildings()]
    from . import lod2, vegetation
    lod = lod2.surroundings()
    if lboxes is None:
        lboxes = [bbox(o) for o in lod]
    visible = []
    for o, b in zip(lod, lboxes):
        hide = any(_overlap(b, h, LOD2_MARGIN) for h in boxes)
        o[names.OB_LOD2_HIDDEN] = int(hide)
        o.hide_viewport = hide
        o.hide_render = hide
        if not hide:
            visible.append(b)
    all_boxes = list(boxes) + visible
    vegetation.mark_terrain(all_boxes)
    return mark_trees(all_boxes)


# ------------------------------------------------------------------ operators

class BONSAI_BTK_OT_site_building_set(bpy.types.Operator):
    bl_idname = "bonsai_btk.site_building_set"
    bl_label = "Selection as Building"
    bl_description = ("Mark the selected objects (the IFC house, for example) as building: "
                      "in the cardboard model they move onto the layer below, trees underneath disappear")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = [o for o in context.selected_objects if o.type not in {'EMPTY', 'CAMERA', 'LIGHT'}]
        skipped = [o for o in sel if is_site_object(o)]
        sel = [o for o in sel if o not in skipped]
        if not sel:
            self.report({'WARNING'}, "Nothing selected (cameras, lights, empties, terrain and site elements do not count)")
            return {'CANCELLED'}
        for o in sel:
            o[names.OB_BUILDING] = 1
        from . import build
        build.apply_variant(context)
        n = len(buildings())
        self.report({'INFO'}, f"{n} objects count as building"
                    + (f" – {len(skipped)} terrain or site objects left out" if skipped else ""))
        return {'FINISHED'}


class BONSAI_BTK_OT_site_building_clear(bpy.types.Operator):
    bl_idname = "bonsai_btk.site_building_clear"
    bl_label = "Release Selection"
    bl_description = "The selected objects are no longer a building (the offset is taken back)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for o in context.selected_objects:
            if names.OB_BUILDING in o:
                del o[names.OB_BUILDING]
        from . import build
        build.apply_variant(context)
        return {'FINISHED'}


CLASSES = (BONSAI_BTK_OT_site_building_set, BONSAI_BTK_OT_site_building_clear)
