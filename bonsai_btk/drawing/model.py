# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the post-processing reads from the IFC model, and the two properties it writes.

Everything that changes the drawing of one element travels with the IFC, in one
property set on the element or on its type (the value on the element wins):

``EPset_BTK_Hatching.Rotation``
    extra degrees for the hatching of this element (button *Rotate Hatching*)
``EPset_BTK_Hatching.Layers``
    True: draw the layers in every scale; False: one area in every scale;
    not set: layers up to 1:50, one area from 1:100 (button *Layers On/Off*)

Read as well, without own properties:

- the material category of elements without a layer set (Bonsai writes it only per
  layer), and
- the role of coverings and roof slabs for build-ups: floor, ceiling and roofing
  build-ups and roof slabs are build-ups, insulation joins a build-up it touches,
  membranes and plaster claddings are left out from 1:100.

The functions take an IfcOpenShell file and do not import bpy.
"""
import ifcopenshell.api
import ifcopenshell.util.element as util

from . import outline

PSET = "EPset_BTK_Hatching"
ROTATION = "Rotation"
LAYERS = "Layers"
ROTATION_STEP = 15.0
TURN = 180.0


def rotations(ifc):
    """{GlobalId: degrees}; a value on the type applies, the one on the element wins."""
    result = {}
    for element in ifc.by_type("IfcProduct"):
        value = None
        element_type = util.get_type(element)
        if element_type is not None:
            pset = util.get_psets(element_type).get(PSET)
            if pset and pset.get(ROTATION) is not None:
                value = pset[ROTATION]
        pset = util.get_psets(element).get(PSET)
        if pset and pset.get(ROTATION) is not None:
            value = pset[ROTATION]
        if value is not None:
            try:
                result[element.GlobalId] = float(value)
            except (TypeError, ValueError):
                pass
    return result


def categories(ifc):
    """{GlobalId: category} for elements WITHOUT a layer set. Read is the single
    material, the profile materials, the constituents or the material list, the first
    one with a Category. For layer sets Bonsai writes the category itself."""
    result = {}
    for element in ifc.by_type("IfcProduct"):
        if element.is_a("IfcAnnotation") or element.is_a("IfcSpatialElement"):
            continue
        material = util.get_material(element, should_skip_usage=True)   # as Bonsai's get_svg_classes
        if material is None or material.is_a("IfcMaterialLayerSet"):
            continue
        category = None
        if material.is_a("IfcMaterial"):
            category = material.Category
        else:
            parts = []
            if material.is_a("IfcMaterialProfileSet"):
                parts = [p.Material for p in (material.MaterialProfiles or [])]
            elif material.is_a("IfcMaterialConstituentSet"):
                parts = [c.Material for c in (material.MaterialConstituents or [])]
            elif material.is_a("IfcMaterialList"):
                parts = list(material.Materials or [])
            for part in parts:
                if part is not None and getattr(part, "Category", None):
                    category = part.Category
                    break
        if category:
            result[element.GlobalId] = category
    return result


def _layers_switch(ifc):
    result = {}
    for element in ifc.by_type("IfcElement"):
        value = util.get_pset(element, PSET, LAYERS)
        if value is not None:
            result[element.GlobalId] = bool(value)
    return result


def roles(ifc):
    """{GlobalId: role} for outline.simplify_build_ups. An element with the Layers
    switch set is decided by the switch alone."""
    result = {}
    switch = _layers_switch(ifc)
    for element in ifc.by_type("IfcCovering") + ifc.by_type("IfcSlab"):
        if element.GlobalId in switch:
            continue
        kind = util.get_predefined_type(element)
        if element.is_a("IfcSlab"):
            if kind == "ROOF":
                result[element.GlobalId] = outline.ROLE_BUILD_UP
            continue
        if kind in ("FLOORING", "CEILING", "ROOFING"):
            result[element.GlobalId] = outline.ROLE_BUILD_UP
        elif kind == "INSULATION":
            result[element.GlobalId] = outline.ROLE_INSULATION
        elif kind == "MEMBRANE":
            result[element.GlobalId] = outline.ROLE_OMIT
        elif kind == "CLADDING":
            material = util.get_material(element, should_skip_usage=True)
            materials = []
            if material is not None and material.is_a("IfcMaterialLayerSet"):
                materials = [layer.Material for layer in (material.MaterialLayers or []) if layer.Material]
            elif material is not None and material.is_a("IfcMaterial"):
                materials = [material]
            if materials and all((m.Category or "") == "Putz" for m in materials):
                result[element.GlobalId] = outline.ROLE_OMIT
    for guid, show in switch.items():
        if not show:
            result[guid] = outline.ROLE_FORCED
    return result


def read(ifc):
    """Everything the post-processing needs from the model, as plain dictionaries."""
    return {"rotations": rotations(ifc), "categories": categories(ifc), "roles": roles(ifc)}


# ------------------------------------------------------------------ writing

def _own_pset(ifc, element, run, create=True):
    """The element's own EPset_BTK_Hatching (not the one of its type), created if
    asked for."""
    psets = util.get_psets(element, psets_only=True, should_inherit=False)
    if PSET in psets:
        return ifc.by_id(psets[PSET]["id"])
    if not create:
        return None
    return run("pset.add_pset", product=element, name=PSET)


def _runner(ifc, run):
    """run(usecase, **settings): Bonsai's tool.Ifc.run in Blender (undo, sync), plain
    ifcopenshell.api.run otherwise."""
    if run is not None:
        return run
    return lambda usecase, **settings: ifcopenshell.api.run(usecase, ifc, **settings)


def rotate(ifc, element, step=ROTATION_STEP, run=None):
    """Add step degrees to the hatching rotation of one element. Returns (before, after)."""
    run = _runner(ifc, run)
    before = 0.0
    pset = util.get_psets(element).get(PSET)
    if pset and pset.get(ROTATION) is not None:
        try:
            before = float(pset[ROTATION])
        except (TypeError, ValueError):
            before = 0.0
    after = (before + step) % TURN
    own = _own_pset(ifc, element, run)
    run("pset.edit_pset", pset=own, properties={ROTATION: after})
    return before, after


def toggle_layers(ifc, elements, automatic=False, run=None):
    """Switch layers of the elements: if all are off they go on, otherwise off; with
    automatic the switch is removed (set to None). Returns the value written."""
    run = _runner(ifc, run)
    elements = list(elements)
    all_off = all(util.get_pset(e, PSET, LAYERS) is False for e in elements)
    value = None if automatic else all_off
    for element in elements:
        own = _own_pset(ifc, element, run, create=value is not None)
        if own is None:
            continue
        run("pset.edit_pset", pset=own, properties={LAYERS: value})
    return value
