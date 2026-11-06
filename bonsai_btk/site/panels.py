# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Panel Site in the sidebar tab BTK.

On top the display (variant, orthophoto, trees, meadow, camera). Below the work in the order it is
done, numbered 1–7. Each step: file, main button, result; the fine settings fold away under it.
The header of each step shows its state, so a closed panel still tells what is done.
"""
import math

import bpy

from . import buildings, georef, ifc_terrain, lod2, names


# ------------------------------------------------------------------ state of each step

def _state_origin(scene):
    g = scene.bonsai_btk_site
    if not g.use_origin:
        return None, ""
    if georef.values(scene) is None:
        return False, "invalid"
    pr = georef.mirror_check(scene)
    if pr:
        return bool(pr[4]), "mirror check" if pr[4] else "mirror check failed"
    return None, "set"


def _state_terrain(scene):
    ob = bpy.data.objects.get(names.TERRAIN)
    return (True, "loaded") if ob else (None, "")


def _state_buildings(scene):
    n, sur = len(buildings.buildings()), len(lod2.surroundings())
    parts = ([f"house {n}"] if n else []) + ([f"LoD2 {sur}"] if sur else [])
    return (True if n else None), ", ".join(parts)


def _state_vegetation(scene):
    ob = bpy.data.objects.get(names.MODEL_TREES)
    parts = []
    if ob is not None and ob.type == 'MESH':
        parts.append(f"{len(ob.data.vertices)} trees")
    if bpy.data.objects.get(names.MEADOW_OBJECT):
        parts.append("meadow")
    return (True if parts else None), ", ".join(parts)


def _state_cardboard(scene):
    pp = scene.get(names.SC_BOARD)
    if not pp:
        return None, ""
    n = int(round((pp['Lmax'] - pp['L0']) / pp['interval'])) + 1
    return True, f"{n} layers of {pp['interval']:g} m"


def _state_cameras(scene):
    n = sum(1 for name in (names.CAMERA_EYE, names.CAMERA_AERIAL) if bpy.data.objects.get(name))
    return (True, f"{n} found") if n else (None, "")


def _state_ifc(scene):
    ob, el = ifc_terrain.ifc_terrain_entity()
    if ob is None:
        return None, ""
    if el is None:
        return False, "no IFC class"
    try:
        pr = ifc_terrain.file_check()
    except Exception:
        pr = None
    if pr and not pr[4]:
        return False, "mirror check failed"
    return True, "in the IFC"


# ------------------------------------------------------------------ panels

class BONSAI_BTK_PT_site(bpy.types.Panel):
    bl_label = "Site"
    bl_idname = "BONSAI_BTK_PT_site"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BTK"
    bl_order = 10

    def draw(self, context):
        g = context.scene.bonsai_btk_site
        lay = self.layout
        row = lay.row(align=True)
        row.scale_y = 1.3
        row.prop(g, "variant", expand=True)
        row = lay.row(align=True)
        row.prop(g, "show_ortho", toggle=True, icon='IMAGE_DATA')
        ob = bpy.data.objects.get(names.MODEL_TREES)
        if ob:
            row.prop(ob, "hide_viewport", text="", icon='OUTLINER_OB_POINTCLOUD', invert_checkbox=True, toggle=True)
        if bpy.data.objects.get(names.MEADOW_OBJECT):
            row.prop(g, "show_meadow", text="", icon='OUTLINER_OB_CURVES', toggle=True)
        row = lay.row(align=True)
        row.prop(context.scene, "camera", text="", icon='CAMERA_DATA')
        row.operator("view3d.view_camera", text="", icon='VIEW_CAMERA')
        if g.variant == 'CARDBOARD' and buildings.buildings():
            lay.label(text="House shown on its layer – move it only in Terrain", icon='INFO')
        if g.info_text:
            lay.label(text=g.info_text, icon='INFO')


class _Step:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BTK"
    bl_parent_id = "BONSAI_BTK_PT_site"
    bl_options = {'DEFAULT_CLOSED'}
    icon = 'NONE'
    state = None

    def draw_header(self, context):
        self.layout.label(icon=self.icon)

    def draw_header_preset(self, context):
        if self.state is None:
            return
        ok, text = type(self).state(context.scene)
        if not text:
            return
        if ok is None:
            return
        # only the icon: the sidebar is narrow, the text would run into the label
        self.layout.label(text="", icon='CHECKMARK' if ok else 'ERROR')


class _Settings:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BTK"
    bl_label = "Settings"
    bl_options = {'DEFAULT_CLOSED'}


# 1 -------------------------------------------------------------- project origin

class BONSAI_BTK_PT_site_origin(_Step, bpy.types.Panel):
    bl_label = "1  Project Origin"
    bl_order = 0
    state = staticmethod(_state_origin)

    def draw_header(self, context):
        self.layout.prop(context.scene.bonsai_btk_site, "use_origin", text="")

    def draw(self, context):
        g = context.scene.bonsai_btk_site
        lay = self.layout
        lay.active = g.use_origin
        row = lay.row(align=True)
        row.operator("bonsai_btk.site_origin_from_ifc", icon='IMPORT')
        row.operator("bonsai_btk.site_origin_to_ifc", icon='EXPORT')
        row.operator("bonsai_btk.site_origin_at_cursor", text="", icon='PIVOT_CURSOR')
        col = lay.column(align=True)
        col.prop(g, "origin_e", text="E")
        col.prop(g, "origin_n", text="N")
        col.prop(g, "origin_h", text="H ±0.00")
        col = lay.column(align=True)
        col.prop(g, "x_axis_abscissa")
        col.prop(g, "x_axis_ordinate")
        rv = georef.raw_vector(context.scene)
        pr = georef.mirror_check(context.scene) if g.use_origin else None
        if g.use_origin and georef.values(context.scene) is None:
            lay.label(text="E, N or abscissa/ordinate invalid", icon='ERROR')
        elif rv and abs(rv[2] - 1) > 1e-5:
            lay.label(text=f"Vector length {rv[2]:.6f} – will be normalised", icon='ERROR')
        elif pr:
            lay.label(text="Mirror check passed" if pr[4] else "Mirror check failed",
                      icon='CHECKMARK' if pr[4] else 'ERROR')
        elif g.use_origin:
            lay.label(text="Mirror check once the terrain is built", icon='INFO')


class BONSAI_BTK_PT_site_origin_details(_Settings, bpy.types.Panel):
    bl_label = "Check Values and North"
    bl_parent_id = "BONSAI_BTK_PT_site_origin"

    def draw(self, context):
        lay = self.layout
        col = lay.column(align=True)
        col.scale_y = 0.85
        rv = georef.raw_vector(context.scene)
        if rv and abs(rv[1]) > 1e-12:
            col.label(text=f"Shown in Bonsai: Grid North {-math.degrees(math.atan2(rv[1], rv[0])):.4f}°")
        pr = georef.mirror_check(context.scene)
        if pr:
            col.label(text=f"Mirror check terrain {pr[0]:.6f} / {pr[1]:+.6f}")
            col.label(text=f"Mirror check IFC       {pr[2]:.6f} / {pr[3]:+.6f}")
        nd = georef.north(context.scene)
        if nd:
            col.label(text=f"TrueNorth {nd['tn'][0]:+.6f} / {nd['tn'][1]:+.6f}")
            col.label(text=f"Meridian convergence γ {nd['gamma']:.2f}°")
            lay.operator("bonsai_btk.site_sun_position", icon='LIGHT_SUN')


# 2 -------------------------------------------------------------- terrain

class BONSAI_BTK_PT_site_terrain(_Step, bpy.types.Panel):
    bl_label = "2  Terrain"
    bl_order = 1
    icon = 'WORLD'
    state = staticmethod(_state_terrain)

    def draw(self, context):
        g = context.scene.bonsai_btk_site
        lay = self.layout
        lay.prop(g, "dtm_path")
        lay.prop(g, "ortho_path")
        lay.operator("bonsai_btk.site_terrain", icon='WORLD')


# 3 -------------------------------------------------------------- buildings

class BONSAI_BTK_PT_site_buildings(_Step, bpy.types.Panel):
    bl_label = "3  Buildings"
    bl_order = 2
    icon = 'HOME'
    state = staticmethod(_state_buildings)

    def draw(self, context):
        lay = self.layout
        found = buildings.buildings()
        lay.label(text=f"Your house: {len(found)} objects" if found else "Your house: select its objects, then")
        row = lay.row(align=True)
        row.operator("bonsai_btk.site_building_set", icon='ADD')
        row.operator("bonsai_btk.site_building_clear", text="", icon='REMOVE')
        lay.separator()
        lay.label(text="Surroundings (LoD2)")
        lay.prop(context.scene.bonsai_btk_site, "lod2_path")
        lay.operator("bonsai_btk.site_lod2", icon='IMPORT')
        sur = lod2.surroundings()
        if sur:
            c = bpy.data.collections.get(names.COL_LOD2)
            hidden = sum(1 for o in sur if o.get(names.OB_LOD2_HIDDEN))
            row = lay.row(align=True)
            row.label(text=f"{len(sur)} LoD2 buildings" + (f", {hidden} hidden at the house" if hidden else ""))
            if c:
                row.prop(c, "hide_viewport", text="", icon='HIDE_OFF', invert_checkbox=True, toggle=True)


# 4 -------------------------------------------------------------- vegetation

class BONSAI_BTK_PT_site_vegetation(_Step, bpy.types.Panel):
    bl_label = "4  Vegetation"
    bl_order = 3
    icon = 'OUTLINER_OB_POINTCLOUD'
    state = staticmethod(_state_vegetation)

    def draw(self, context):
        g = context.scene.bonsai_btk_site
        lay = self.layout
        lay.label(text="Trees")
        lay.row().prop(g, "tree_source", expand=True)
        if g.tree_source == 'GPKG':
            lay.prop(g, "trees_gpkg_path")
        else:
            lay.prop(g, "ndsm_path")
            lay.prop(g, "ndsm_is_dsm")
        lay.operator("bonsai_btk.site_trees", icon='PARTICLES')
        ob = bpy.data.objects.get(names.MODEL_TREES)
        if ob:
            row = lay.row(align=True)
            row.prop(ob, "hide_render", text="Render", invert_checkbox=True, toggle=True)
            row.prop(g, "natural_trees", toggle=True)
        lay.separator()
        lay.label(text="Meadow around the camera")
        lay.operator("bonsai_btk.site_meadow", icon='OUTLINER_OB_CURVES')


class BONSAI_BTK_PT_site_vegetation_settings(_Settings, bpy.types.Panel):
    bl_parent_id = "BONSAI_BTK_PT_site_vegetation"

    def draw(self, context):
        g = context.scene.bonsai_btk_site
        lay = self.layout
        col = lay.column(align=True)
        col.prop(g, "min_tree_height")
        col.prop(g, "shrub_limit")
        lay.prop(g, "broadleaf_share")
        lay.prop(g, "tree_color", text="Model Tree Colour")
        col = lay.column(align=True)
        col.prop(g, "grass_density")
        col.prop(g, "stone_density")
        col.prop(g, "scatter_radius")


# 5 -------------------------------------------------------------- cardboard model

class BONSAI_BTK_PT_site_cardboard(_Step, bpy.types.Panel):
    bl_label = "5  Cardboard Model"
    bl_order = 4
    icon = 'MOD_ARRAY'
    state = staticmethod(_state_cardboard)

    def draw(self, context):
        g = context.scene.bonsai_btk_site
        lay = self.layout
        row = lay.row(align=True)
        row.prop(g, "contour_interval")
        row.operator("bonsai_btk.site_cardboard", text="", icon='FILE_REFRESH')
        lay.prop(g, "board_color")


class BONSAI_BTK_PT_site_cardboard_settings(_Settings, bpy.types.Panel):
    bl_parent_id = "BONSAI_BTK_PT_site_cardboard"

    def draw(self, context):
        g = context.scene.bonsai_btk_site
        col = self.layout.column(align=True)
        col.prop(g, "contour_grid")
        col.prop(g, "min_area")


# 6 -------------------------------------------------------------- cameras

class BONSAI_BTK_PT_site_cameras(_Step, bpy.types.Panel):
    bl_label = "6  Cameras"
    bl_order = 5
    icon = 'CAMERA_DATA'
    state = staticmethod(_state_cameras)

    def draw(self, context):
        lay = self.layout
        if not buildings.buildings():
            lay.label(text="No house marked – aims at the 3D cursor", icon='INFO')
        row = lay.row(align=True)
        row.operator("bonsai_btk.site_cameras_find", text="Find", icon='VIEWZOOM')
        row.operator("bonsai_btk.site_camera_check", text="Check", icon='CHECKMARK')


# 7 -------------------------------------------------------------- terrain into the IFC

class BONSAI_BTK_PT_site_terrain_ifc(_Step, bpy.types.Panel):
    bl_label = "7  Terrain to IFC"
    bl_order = 6
    icon = 'FILE_3D'
    state = staticmethod(_state_ifc)

    def draw(self, context):
        g = context.scene.bonsai_btk_site
        lay = self.layout
        row = lay.row(align=True)
        row.prop(g, "ifc_extent")
        row.prop(g, "ifc_grid")
        ob, el = ifc_terrain.ifc_terrain_entity()
        if ob is None:
            lay.operator("bonsai_btk.site_terrain_ifc", icon='EXPORT')
            return
        row = lay.row(align=True)
        row.label(text="IfcGeographicElement TERRAIN" if el else "Object without IFC class",
                  icon='CHECKMARK' if el else 'ERROR')
        row.prop(ob, "hide_viewport", text="", icon='HIDE_OFF', invert_checkbox=True, toggle=True)
        try:
            pr = ifc_terrain.file_check()
        except Exception:
            pr = None
        if pr:
            lay.label(text="Mirror check in the IFC passed" if pr[4] else "Mirror check in the IFC failed",
                      icon='CHECKMARK' if pr[4] else 'ERROR')


CLASSES = (BONSAI_BTK_PT_site,
           BONSAI_BTK_PT_site_origin, BONSAI_BTK_PT_site_origin_details,
           BONSAI_BTK_PT_site_terrain,
           BONSAI_BTK_PT_site_buildings,
           BONSAI_BTK_PT_site_vegetation, BONSAI_BTK_PT_site_vegetation_settings,
           BONSAI_BTK_PT_site_cardboard, BONSAI_BTK_PT_site_cardboard_settings,
           BONSAI_BTK_PT_site_cameras,
           BONSAI_BTK_PT_site_terrain_ifc)
