# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar tab BTK in the 3D view (key N)."""
import bpy


class BONSAI_BTK_PT_dimensions(bpy.types.Panel):
    bl_label = "Dimensions"
    bl_idname = "BONSAI_BTK_PT_dimensions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BTK"
    bl_order = 0

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("bonsai_btk.dimension_from_points", text="Dimension from Points", icon="DRIVER_DISTANCE")
        col.operator("bonsai_btk.dimension_flip", text="Flip Dimension", icon="ARROW_LEFTRIGHT")
        hint = self.layout.column(align=True)
        hint.scale_y = 0.8
        hint.label(text="While picking: S = intersection of two edges", icon="INFO")


CLASSES = (BONSAI_BTK_PT_dimensions,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
