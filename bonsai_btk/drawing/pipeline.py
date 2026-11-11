# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The post-processing of one drawing, in a fixed order.

    1. sill heights (plans)
    2. build-ups as one area (from 1:100, or by the Layers switch)
    3. hatching as real lines, signs, categories of elements without layers;
       structural layers last
    4. joints of the same material merged
    5. windows and doors fine, glass as one line
    6. stairs after DIN 1356-1 (plans)
    7. roof outline, ridge and beams above, dotted (plans)

Each step leaves alone what an earlier run of itself produced, so the whole
post-processing can run again over the same file without changing it further.
The stair placement looks at what is drawn already, so it comes after the hatching.

Text in, text out. The model data come as plain dictionaries: model.read for the
whole model, plan.read for the plan of this drawing. No bpy.
"""
from . import hatching, outline, roof, sill, stair, windows


def process_text(svg_text, model_data=None, plan_data=None):
    """(new text, report) for the SVG text of one drawing."""
    data = model_data or {}
    plan = plan_data or {}
    report = []
    text = svg_text
    if plan:
        text, sill_report = sill.apply(text, plan.get("sills"))
        report += ["sill: " + r for r in sill_report]
    text = outline.remove_joint_groups(text)
    text, omitted, united = outline.simplify_build_ups(text, data.get("roles"))
    text, hatching_report = hatching.apply(text, data.get("rotations"), data.get("categories"))
    report += hatching_report
    if omitted or united:
        report.append("build-ups: %d group(s) of thin claddings left out, %d group(s) as one area"
                      % (omitted, united))
    text, joints = outline.merge_joints(text)
    report.append("%d outline(s) of the same material merged" % joints)
    text, panes, groups = windows.fine(text)
    if groups:
        report.append("windows and doors: %d group(s) narrow %g, %d pane(s) as one line"
                      % (groups, windows.WINDOW_STROKE, panes))
    if plan:
        text, stair_report = stair.apply(text, plan.get("flights"), plan["frame"])
        report += ["stair: " + r for r in stair_report]
        text, roof_report = roof.apply(text, plan.get("roofs"))
        report += ["roof: " + r for r in roof_report]
    return text, report


def process_file(path, model_data=None, plan_data=None):
    """Rewrite the drawing at path in place. Returns the report. The file is written
    only if something changed; line endings are kept as they are."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    new, report = process_text(text, model_data, plan_data)
    if new != text:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    return report


def process_drawing(path, ifc, name):
    """Read model and plan data and rewrite the drawing at path. Returns the report."""
    from . import model, plan
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    return process_file(path, model.read(ifc), plan.read(ifc, text, name))
