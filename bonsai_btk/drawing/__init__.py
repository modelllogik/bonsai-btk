# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Post-processing of Bonsai drawings after DIN 1356-1.

Bonsai writes each drawing as an SVG. The modules of this package rewrite that SVG
in place, in a fixed order, so that the drawing looks like the plans taught in
German vocational training: hatching as real lines, joints of the same material
merged, windows drawn fine, stairs and roofs in the plan, sill heights, legend and
north arrow on the sheet.

Layout of the package:

    svg        reading and editing the SVG text: groups, classes, paths, scale
    style      reading the drawing style: patterns, categories, line weights
    hatching   hatching as real lines, turned with the element; signs; categories
    outline    rings from loose edges, drawing order, joints, build-ups
    windows    windows and doors fine, the glass as one line
    sill       sill heights (BRH) in plan
    stair      stairs in plan after DIN 1356-1
    roof       roof outline, ridge and beams above the cut, dotted in plan
    pipeline   the steps in their order, for one drawing
    model      what is read from the IFC and the two properties written to it
    plan       geometry a plan needs from the IFC, seen from its camera
    operators  buttons and panel (the only module that imports bpy)

Further modules follow (see the roadmap in the README). All modules except
operators work on text, plain numbers and an IfcOpenShell file, so they can be
tested without Blender.
"""
