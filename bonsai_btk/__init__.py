# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BTK Tools for Bonsai.

Drafting: intersection snap (key S) and dimension chain from snapped points.
Drawing: post-processing of Bonsai drawings after DIN 1356 (hatching as real lines,
joints of the same material, build-ups, windows, stairs, roofs, sill heights), legend
and north arrow on the sheet, sheets as PDF through Inkscape; see the package drawing.
Preview: drawings and sheets in the web browser, arranging a sheet there; see the
package preview.
Site: terrain, cardboard contour model, trees, meadow, surroundings and cameras from geodata.
Bonsai must be installed and enabled. The tools are in the sidebar of the 3D view,
tab BTK.
"""
import importlib

import bpy

# Modules that import Bonsai; registered once Bonsai is available.
_TOOL_MODULES = ("snap", "dimension", "ui", "drawing.operators", "site")
_registered = []
_attempts = 0


def _register_tools():
    """Register the tool modules. Returns None when done, or a delay to retry while
    Bonsai is not loaded yet (the order in which extensions load is not fixed)."""
    global _attempts
    _attempts += 1
    try:
        import bonsai.tool  # noqa: F401
    except ImportError:
        if _attempts < 20:
            return 0.5
        print("BTK Tools for Bonsai: Bonsai not found, tools not registered")
        return None
    for name in _TOOL_MODULES:
        module = importlib.import_module("." + name, __package__)
        module.register()
        _registered.append(module)
    return None


class BONSAI_BTK_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    inkscape_path: bpy.props.StringProperty(
        name="Inkscape",
        description=("Inkscape executable for Print Sheet (PDF). Empty: searched on the path "
                     "and in the usual install folders"),
        subtype="FILE_PATH",
        default="",
    )
    preview_port: bpy.props.IntProperty(
        name="Preview Port",
        description=("Port of the local preview server (127.0.0.1 only). Takes effect "
                     "the next time the preview starts"),
        default=8765, min=1024, max=65535,
    )

    def draw(self, context):
        self.layout.prop(self, "inkscape_path")
        self.layout.prop(self, "preview_port")


def preferences():
    """The add-on preferences, or None (for example when run from a script)."""
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def register():
    global _attempts
    _attempts = 0
    bpy.utils.register_class(BONSAI_BTK_Preferences)
    if _register_tools() is not None:
        bpy.app.timers.register(_register_tools, first_interval=0.5)


def unregister():
    if bpy.app.timers.is_registered(_register_tools):
        bpy.app.timers.unregister(_register_tools)
    while _registered:
        _registered.pop().unregister()
    bpy.utils.unregister_class(BONSAI_BTK_Preferences)
