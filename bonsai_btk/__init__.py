# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BTK Tools for Bonsai.

Release 0.1.0: intersection snap (key S) and dimension chain from snapped points.
Bonsai must be installed and enabled. The tools are in the sidebar of the 3D view,
tab BTK.
"""
import importlib

import bpy

# Modules that import Bonsai; registered once Bonsai is available.
_TOOL_MODULES = ("snap", "dimension", "ui")
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


def register():
    global _attempts
    _attempts = 0
    if _register_tools() is not None:
        bpy.app.timers.register(_register_tools, first_interval=0.5)


def unregister():
    if bpy.app.timers.is_registered(_register_tools):
        bpy.app.timers.unregister(_register_tools)
    while _registered:
        _registered.pop().unregister()
