# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Site tools: terrain, cardboard contour model, trees, meadow, surroundings and cameras from geodata.

Sidebar of the 3D view (N) → tab BTK → panel Site.
The settings live in the scene as ``scene.bonsai_btk_site``.
"""
import os
import traceback

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, PointerProperty, StringProperty

from . import build, buildings, cameras, georef, ifc_terrain, lod2, names, panels, vegetation

VARIANTS = [
    ('TERRAIN', "Terrain", "Original terrain from the digital terrain model"),
    ('CARDBOARD', "Cardboard Model", "Cardboard layers along the contour lines"),
]


def _upd_variant(self, context):
    build.apply_variant(context)


def _upd_origin(self, context):
    if context.scene.get(names.SC_ORIGIN) is None:
        return
    georef.update(context)
    build.apply_variant(context)


def _upd_board_color(self, context):
    build.apply_board_color(tuple(self.board_color))


def _upd_values(self, context):
    vegetation.update_values(self)


def _upd_tree_color(self, context):
    m = bpy.data.materials.get(names.MAT_MODEL_TREE)
    if m and m.use_nodes and 'Principled BSDF' in m.node_tree.nodes:
        m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = tuple(self.tree_color) + (1.0,)
    if m:
        m.diffuse_color = tuple(self.tree_color) + (1.0,)  # colour in the Solid view


class BONSAI_BTK_SiteProperties(bpy.types.PropertyGroup):
    use_origin: BoolProperty(name="Project Origin", default=False, update=_upd_origin,
                             description="Place the terrain in the project coordinates of the IFC (origin at 0, rotated)")
    origin_e: StringProperty(name="Easting E", default="", update=_upd_origin,
                             description="Easting of the project origin in m (e.g. 752814.500) – as text, so the millimetres stay")
    origin_n: StringProperty(name="Northing N", default="", update=_upd_origin,
                             description="Northing of the project origin in m (e.g. 5294662.500)")
    origin_h: FloatProperty(name="Height ±0.00", default=0.0, precision=3, update=_upd_origin, unit='LENGTH',
                            description=("Height of ±0.00 in the vertical datum below "
                                         "(IfcMapConversion.OrthogonalHeight)"))
    vertical_datum: StringProperty(name="Vertical Datum", default="",
                                   description=("Vertical datum of the heights as EPSG code, written to "
                                                "IfcProjectedCRS.VerticalDatum (e.g. EPSG:7837 for DHHN2016 in Germany). "
                                                "Empty: To IFC leaves the value in the IFC as it is"))
    x_axis_abscissa: StringProperty(name="Abscissa", default="1.0", update=_upd_origin,
                                    description=("XAxisAbscissa: east component of the project x axis in map axes. "
                                                 "Tells how much it is rotated (not rotated: 1)"))
    x_axis_ordinate: StringProperty(name="Ordinate", default="0.0", update=_upd_origin,
                                    description=("XAxisOrdinate: north component of the project x axis in map axes. "
                                                 "Tells in which direction it is rotated (not rotated: 0)"))
    dtm_path: StringProperty(name="Terrain", subtype='FILE_PATH',
                             description="Digital terrain model as GeoTIFF (Float32, e.g. DGM1 from OpenData Bayern)")
    ortho_path: StringProperty(name="Orthophoto", subtype='FILE_PATH',
                               description="Orthophoto as GeoTIFF – optional")
    ndsm_path: StringProperty(name="nDSM / DSM", subtype='FILE_PATH',
                              description="Vegetation height (nDSM) or digital surface model (DSM) as GeoTIFF – for the trees")
    tree_source: EnumProperty(name="Source", default='GPKG', items=[
        ('GPKG', "Single Trees", "GeoPackage of single trees with a height column (e.g. LDBV “Einzelbäume”): fast"),
        ('NDSM', "From DSM", "Own detection from an nDSM/DSM raster – slow, needs a lot of memory, also finds shrubs")])
    trees_gpkg_path: StringProperty(name="Single Trees", subtype='FILE_PATH',
                                    description="GeoPackage of single trees – may be much larger than the terrain tile")
    lod2_path: StringProperty(name="LoD2", subtype='FILE_PATH',
                              description="3D building model LoD2 as CityGML (e.g. LoD2 from OpenData Bayern) – "
                                          "neighbouring buildings with roof shapes; the file may be larger than the terrain tile")
    ndsm_is_dsm: BoolProperty(name="File is a DSM (surface)", default=False,
                              description="On: the terrain is subtracted from the DSM. Off: the file is already an nDSM (DSM − DTM)")
    contour_interval: FloatProperty(name="Layer Height", default=10.0, min=0.1, max=200.0, unit='LENGTH',
                                    description="Height difference between the cardboard layers (contour interval)")
    contour_grid: FloatProperty(name="Contour Grid", default=2.0, min=0.5, max=50.0, unit='LENGTH',
                                description="Grid on which the contour lines are computed (finer = smoother edges, slower)")
    min_area: FloatProperty(name="Minimum Area", default=40.0, min=0.0, unit='AREA',
                            description="Smaller cardboard islands are left out")
    min_tree_height: FloatProperty(name="Minimum Tree Height", default=2.5, min=0.5, max=20.0, unit='LENGTH')
    shrub_limit: FloatProperty(name="Shrub up to", default=4.0, min=0.0, max=20.0, unit='LENGTH',
                               description="Below: flat shrub (mountain pine), above: cone tree")
    tree_color: FloatVectorProperty(name="Tree Colour", subtype='COLOR', size=3, min=0, max=1,
                                    default=(0.20, 0.27, 0.16), update=_upd_tree_color)
    natural_trees: BoolProperty(name="Natural Trees", default=True, update=_upd_variant,
                                description="On the terrain: spruces, broadleaf trees and shrubs instead of model cones")
    broadleaf_share: FloatProperty(name="Broadleaf Trees", default=15.0, min=0.0, max=100.0, subtype='PERCENTAGE',
                                   update=_upd_values, description="Share of broadleaf trees among the trees above the shrub limit")
    show_meadow: BoolProperty(name="Meadow", default=True, update=_upd_variant,
                              description="Show grass and stones on the terrain")
    grass_density: FloatProperty(name="Grass per m²", default=40.0, min=0.0, max=400.0, update=_upd_values,
                                 description="Grass tufts per square metre near the camera (viewport: one tenth)")
    stone_density: FloatProperty(name="Stones per m²", default=0.5, min=0.0, max=20.0, update=_upd_values)
    scatter_radius: FloatProperty(name="Radius", default=120.0, min=10.0, max=2000.0, unit='LENGTH', update=_upd_values,
                                  description="Meadow only up to this distance from the active camera")
    board_color: FloatVectorProperty(name="Cardboard Colour", subtype='COLOR', size=3, min=0, max=1,
                                     default=(0.19, 0.172, 0.146), update=_upd_board_color,
                                     description=("Base colour of the cardboard layers, the base plate and the terrain "
                                                  "without orthophoto (grey board, card, cork …)"))
    ifc_extent: FloatProperty(name="Cut-out", default=300.0, min=20.0, max=2000.0, unit='LENGTH',
                              description="Side length of the terrain in the IFC (square around the building, aligned to grid north)")
    ifc_grid: FloatProperty(name="Grid", default=2.0, min=0.5, max=20.0, unit='LENGTH',
                            description="Point spacing of the terrain in the IFC (coarser = smaller file)")
    variant: EnumProperty(name="Variant", items=VARIANTS, default='TERRAIN', update=_upd_variant)
    show_ortho: BoolProperty(name="Orthophoto", default=True, update=_upd_variant,
                             description="Orthophoto on the terrain or on the tops of the cardboard layers")
    info_text: StringProperty(default="")


class _Base:
    bl_options = {'REGISTER', 'UNDO'}

    def run(self, context):
        raise NotImplementedError

    def execute(self, context):
        try:
            self.run(context)
        except Exception as ex:  # message for the user interface
            traceback.print_exc()
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        return {'FINISHED'}


def _check(path, what):
    p = build.abspath(path)
    if not p:
        raise ValueError(f"{what}: no file chosen")
    if not os.path.isfile(p):
        raise ValueError(f"{what}: file not found")


class BONSAI_BTK_OT_site_terrain(_Base, bpy.types.Operator):
    bl_idname = "bonsai_btk.site_terrain"
    bl_label = "Load Terrain"
    bl_description = "Create the terrain from the digital terrain model and put the orthophoto on it"

    def run(self, context):
        g = context.scene.bonsai_btk_site
        _check(g.dtm_path, "Terrain")
        if g.ortho_path:
            _check(g.ortho_path, "Orthophoto")
        build.build_terrain(context, g)
        g.variant = 'TERRAIN'
        buildings.mark_all()
        build.apply_variant(context)
        self.report({'INFO'}, g.info_text)


class BONSAI_BTK_OT_site_cardboard(_Base, bpy.types.Operator):
    bl_idname = "bonsai_btk.site_cardboard"
    bl_label = "Create Cardboard Model"
    bl_description = "Compute the contour lines and build them up as cardboard layers"

    def run(self, context):
        g = context.scene.bonsai_btk_site
        _check(g.dtm_path, "Terrain")
        build.build_board(context, g)
        g.variant = 'CARDBOARD'
        self.report({'INFO'}, g.info_text)


class BONSAI_BTK_OT_site_trees(_Base, bpy.types.Operator):
    bl_idname = "bonsai_btk.site_trees"
    bl_label = "Detect Trees"
    bl_description = "Find tree positions and heights and place model trees (takes a while)"

    def run(self, context):
        g = context.scene.bonsai_btk_site
        _check(g.dtm_path, "Terrain")
        if g.tree_source == 'GPKG':
            _check(g.trees_gpkg_path, "Single trees")
        else:
            _check(g.ndsm_path, "nDSM/DSM")
        build.build_trees(context, g)
        self.report({'INFO'}, g.info_text)


class BONSAI_BTK_OT_site_meadow(_Base, bpy.types.Operator):
    bl_idname = "bonsai_btk.site_meadow"
    bl_label = "Create Meadow"
    bl_description = ("Scatter grass and stones following the orthophoto – dense near the active camera, "
                      "thinner further away")

    def run(self, context):
        g = context.scene.bonsai_btk_site
        vegetation.build_meadow(context, g)
        g.show_meadow = True
        buildings.mark_all()
        build.apply_variant(context)
        self.report({'INFO'}, g.info_text)


class BONSAI_BTK_OT_site_lod2(_Base, bpy.types.Operator):
    bl_idname = "bonsai_btk.site_lod2"
    bl_label = "Load Surroundings"
    bl_description = ("Put neighbouring buildings from LoD2 (CityGML) on the terrain – only buildings completely "
                      "inside the terrain tile; buildings at your own house are hidden. Pressing again replaces them")

    def run(self, context):
        g = context.scene.bonsai_btk_site
        _check(g.dtm_path, "Terrain")
        _check(g.lod2_path, "LoD2")
        lod2.build(context, g)
        self.report({'INFO'}, g.info_text)


class BONSAI_BTK_OT_site_terrain_ifc(_Base, bpy.types.Operator):
    bl_idname = "bonsai_btk.site_terrain_ifc"
    bl_label = "Terrain to IFC"
    bl_description = ("Create a cut-out of the terrain as IfcGeographicElement (TERRAIN) in the IfcSite – "
                      "geometry aligned to grid north, rotation in the placement. Save the IFC afterwards")

    def run(self, context):
        g = context.scene.bonsai_btk_site
        _check(g.dtm_path, "Terrain")
        ifc_terrain.build(context, g)
        self.report({'INFO'}, g.info_text)


OPERATORS = (BONSAI_BTK_OT_site_terrain, BONSAI_BTK_OT_site_terrain_ifc, BONSAI_BTK_OT_site_cardboard,
             BONSAI_BTK_OT_site_trees, BONSAI_BTK_OT_site_meadow, BONSAI_BTK_OT_site_lod2)

CLASSES = ((BONSAI_BTK_SiteProperties,) + OPERATORS + georef.CLASSES + buildings.CLASSES
           + cameras.CLASSES + panels.CLASSES)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.bonsai_btk_site = PointerProperty(type=BONSAI_BTK_SiteProperties)


def unregister():
    del bpy.types.Scene.bonsai_btk_site
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
