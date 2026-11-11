# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Buttons for the post-processing: panel *Drawing* in the sidebar tab BTK.

Update Drawing
    Bonsai's *Create Drawing* for the active drawing, then the post-processing
    (pipeline.py) over the SVG it wrote.
Update Sheet
    For the sheet selected in Bonsai's sheet list: every drawing on it as with Update
    Drawing, then legend and north arrow into the layout (sheet.py), then Bonsai's
    *Create Sheets*. The active drawing stays the active drawing. If the layout file is
    missing, Bonsai writes it anew from the IFC once the drawings exist.
Print Sheet (PDF)
    The selected sheet as PDF through Inkscape (printing.py), to a file you choose.
    By default the sheet is updated first.
Layers On/Off
    For the selected elements: draw them with layers or as one area, in every scale.
    If all of them are off they go on, otherwise off; with Ctrl back to automatic
    (layers up to 1:50, one area from 1:100). Stored as EPset_BTK_Hatching.Layers.
Rotate Hatching
    15 degrees more for the hatching of the selected elements, stored as
    EPset_BTK_Hatching.Rotation.
Preview Drawing / Preview Sheet
    Update Drawing or Update Sheet, then show the result in the web browser
    (package preview). The page reloads by itself after every later update. On the
    sheet page drawings, view titles, legend and north arrow can be moved; Apply
    writes the layout (with a backup) and builds the sheet again. Stop Preview ends
    the local server.

Both property buttons regenerate the active drawing afterwards, so the result shows
at once. The work is in plain functions (update_active_drawing and so on), so that
it can also be called from a script.
"""
import os
import tempfile

import bpy

from . import model, pipeline, printing, sheet
from ..preview import server as preview_server

DEFAULT_PORT = 8765
JOB_INTERVAL = 0.25   # seconds between two looks at the job queue of the preview
_preview = {"state": None, "server": None}


# ------------------------------------------------------------------ functions

def active_drawing():
    """The IfcAnnotation of the active drawing, or None."""
    import bonsai.tool as tool
    camera = bpy.context.scene.camera
    return tool.Ifc.get_entity(camera) if camera else None


def drawing_path(drawing):
    """Path of the SVG Bonsai writes for a drawing."""
    import bonsai.tool as tool
    try:
        document = tool.Drawing.get_drawing_document(drawing)
        uri = tool.Drawing.get_document_uri(document)
        if uri:
            return uri
    except Exception:
        pass
    return os.path.join(os.path.dirname(tool.Ifc.get_path()), "drawings", drawing.Name + ".svg")


def update_active_drawing():
    """(path, report). Create the active drawing with Bonsai, then post-process it.
    Raises RuntimeError if Bonsai did not write the file."""
    import bonsai.tool as tool
    drawing = active_drawing()
    if drawing is None:
        raise RuntimeError("no active drawing")
    path = drawing_path(drawing)
    before = os.path.getmtime(path) if os.path.exists(path) else 0
    bpy.ops.bim.create_drawing()
    if not os.path.exists(path) or os.path.getmtime(path) <= before:
        raise RuntimeError("drawing not written: %s" % path)
    report = pipeline.process_drawing(path, tool.Ifc.get(), drawing.Name)
    if _preview["state"] is not None:
        _preview["state"].set_drawing(drawing.Name, path, report)
    return path, report


def active_sheet():
    """The selected sheet (IfcDocumentInformation) in Bonsai's sheet list, or None."""
    import bonsai.tool as tool
    item = tool.Drawing.get_active_sheet_item(is_sheet=True)
    return tool.Ifc.get().by_id(item.ifc_definition_id) if item else None


def select_sheet(sheet_entity):
    """Select the sheet in Bonsai's sheet list (loading the list if needed)."""
    import bonsai.tool as tool
    props = tool.Drawing.get_document_props()
    for attempt in range(2):
        for i, item in enumerate(props.sheets):
            if item.is_sheet and item.ifc_definition_id == sheet_entity.id():
                props.active_sheet_index = i
                return
        bpy.ops.bim.load_sheets()
    raise RuntimeError("sheet %s not in Bonsai's sheet list" % sheet_entity[0])


def sheet_path(sheet_entity):
    import bonsai.tool as tool
    return tool.Ifc.resolve_uri(tool.Drawing.get_default_sheet_path(sheet_entity[0], sheet_entity.Name))


def sheet_drawings(sheet_entity):
    """The drawings (IfcAnnotation) a sheet references in the IFC, as Bonsai finds them:
    by the file name of the DRAWING reference."""
    import bonsai.tool as tool
    names = [os.path.splitext(os.path.basename(r.Location))[0]
             for r in tool.Drawing.get_document_references(sheet_entity)
             if tool.Drawing.get_reference_description(r) == "DRAWING" and r.Location]
    found = {a.Name: a for a in tool.Ifc.get().by_type("IfcAnnotation") if a.ObjectType == "DRAWING"}
    return [found[n] for n in names if n in found]


def update_sheet(sheet_entity):
    """(path of the built sheet, report). Every drawing on the sheet is created and
    post-processed, legend and north arrow go into the layout, Bonsai builds the sheet.
    A missing layout file (a model whose sheets exist only in the IFC, such as the example
    house) is written anew by Bonsai once the drawings exist. Raises RuntimeError."""
    import bonsai.tool as tool
    import ifcopenshell.util.element as util
    ifc = tool.Ifc.get()
    layout = tool.Drawing.get_document_uri(sheet_entity, "LAYOUT")
    was_active = active_drawing() if tool.Drawing.is_drawing_active() else None
    report, done, has_plan, texts = [], [], False, {}

    def make(drawing):
        """Create and post-process a drawing once per call; its SVG text."""
        if drawing.GlobalId not in texts:
            path = drawing_path(drawing)
            before = os.path.getmtime(path) if os.path.exists(path) else 0
            bpy.ops.bim.activate_drawing(drawing=drawing.id(), should_view_from_camera=False)
            bpy.ops.bim.create_drawing()
            if not os.path.exists(path) or os.path.getmtime(path) <= before:
                raise RuntimeError("drawing not written: %s" % drawing.Name)
            report.extend("%s: %s" % (drawing.Name, r) for r in pipeline.process_drawing(path, ifc, drawing.Name))
            with open(path, encoding="utf-8", newline="") as f:
                texts[drawing.GlobalId] = f.read()
        return texts[drawing.GlobalId]

    try:
        if not os.path.exists(layout):
            import bonsai.core.drawing as core
            for drawing in sheet_drawings(sheet_entity):
                make(drawing)
            core.regenerate_sheet(tool.Drawing, sheet_entity)
            if not os.path.exists(layout):
                raise RuntimeError("layout not written: %s (title block %s in Bonsai's data dir?)"
                                   % (layout, tool.Drawing.get_document_uri(sheet_entity, "TITLEBLOCK")))
            report.append("layout written anew by Bonsai: %s" % os.path.basename(layout))
        with open(layout, encoding="utf-8", newline="") as f:
            layout_text = f.read()
        for placed in sheet.layout_drawings(layout_text):
            drawing = ifc.by_guid(placed["guid"])
            has_plan = has_plan or util.get_pset(drawing, "EPset_Drawing", "TargetView") == "PLAN_VIEW"
            done.append((placed["id"], make(drawing)))
    finally:
        if was_active is not None:
            bpy.ops.bim.activate_drawing(drawing=was_active.id(), should_view_from_camera=False)
    entries, legend_report = sheet.legend_entries(done)
    notes = [sheet.SILL_NOTE] if sheet.has_sills(t for _, t in done) else []
    text, placed_report = sheet.place_legend(layout_text, entries, notes)
    text, north_report = sheet.place_north_arrow(text, has_plan)
    if text != layout_text:
        with open(layout, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    report += ["legend: " + r for r in legend_report + placed_report] + ["north arrow: " + r for r in north_report]
    path = sheet_path(sheet_entity)
    before = os.path.getmtime(path) if os.path.exists(path) else 0
    select_sheet(sheet_entity)          # Create Sheets builds the sheet selected in the list
    bpy.ops.bim.create_sheets()
    if not os.path.exists(path) or os.path.getmtime(path) <= before:
        raise RuntimeError("sheet not written: %s" % path)
    if _preview["state"] is not None:
        _preview["state"].set_sheet("%s - %s" % (sheet_entity[0], sheet_entity.Name), sheet_entity.id(),
                                    path, layout, report)
    return path, report


def inkscape():
    """Path of Inkscape from the add-on preferences or found on this computer."""
    configured = ""
    try:
        from .. import preferences
        prefs = preferences()
        configured = prefs.inkscape_path if prefs else ""
    except Exception:
        pass
    return printing.find_inkscape(bpy.path.abspath(configured) if configured else "")


def _port():
    try:
        from .. import preferences
        prefs = preferences()
        return prefs.preview_port if prefs else DEFAULT_PORT
    except Exception:
        return DEFAULT_PORT


def _pdf_bytes(exe, sheet_svg):
    """For GET /sheet/pdf, in the server thread: no bpy, only Inkscape."""
    folder = tempfile.mkdtemp(prefix="btk-pdf-")
    target = os.path.join(folder, "sheet.pdf")
    try:
        printing.sheet_pdf(sheet_svg, target, exe)
        with open(target, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(target):
            os.remove(target)
        os.rmdir(folder)


def _build(sheet_id):
    """For a move job: build the sheet again (main thread)."""
    import bonsai.tool as tool
    return update_sheet(tool.Ifc.get().by_id(sheet_id))


def _run_jobs():
    """Timer in Blender's main thread: the jobs the preview pages sent."""
    state = _preview["state"]
    if state is None:
        return None
    while not state.jobs.empty():
        job = state.jobs.get_nowait()
        if job.get("kind") == "move":
            preview_server.run_move_job(state, job, _build)
    return JOB_INTERVAL


def start_preview():
    """The running server, started if needed. Raises OSError if the port is taken."""
    if _preview["server"] is None:
        state = preview_server.State()
        exe = inkscape()
        state.pdf_maker = (lambda svg: _pdf_bytes(exe, svg)) if exe else None
        _preview["server"] = preview_server.Server(state, _port())
        _preview["state"] = state
        if not bpy.app.timers.is_registered(_run_jobs):
            bpy.app.timers.register(_run_jobs, first_interval=JOB_INTERVAL, persistent=True)
    return _preview["server"]


def stop_preview():
    if bpy.app.timers.is_registered(_run_jobs):
        bpy.app.timers.unregister(_run_jobs)
    if _preview["server"] is not None:
        _preview["server"].stop()
    _preview["server"] = _preview["state"] = None


def _open_page(kind, url):
    """Open the page unless one of this kind is already showing (it reloads by itself)."""
    if not _preview["state"].page_open(kind):
        bpy.ops.wm.url_open(url=url)


def selected_elements(context):
    import bonsai.tool as tool
    result = []
    for obj in context.selected_objects:
        element = tool.Ifc.get_entity(obj)
        if element is not None and not element.is_a("IfcAnnotation"):
            result.append(element)
    return result


# ------------------------------------------------------------------ operators

def _poll(cls, context, needs_selection):
    import bonsai.tool as tool
    if not tool.Ifc.get():
        cls.poll_message_set("No IFC project loaded.")
        return False
    if not tool.Drawing.is_drawing_active():
        cls.poll_message_set("No active drawing (double-click it in the drawing list).")
        return False
    if needs_selection:
        if context.scene.BIMGeometryProperties.mode != "OBJECT":
            cls.poll_message_set("Only in IFC Object Mode.")
            return False
        if not selected_elements(context):
            cls.poll_message_set("No element selected.")
            return False
    return True


def _update_after(operator, message):
    try:
        update_active_drawing()
    except Exception as error:
        operator.report({"WARNING"}, "%s; drawing not updated: %s" % (message, error))
        return {"FINISHED"}
    operator.report({"INFO"}, message)
    return {"FINISHED"}


class BONSAI_BTK_OT_update_drawing(bpy.types.Operator):
    bl_idname = "bonsai_btk.update_drawing"
    bl_label = "Update Drawing"
    bl_description = ("Create the active drawing with Bonsai and post-process it after DIN 1356:\n"
                      "hatching as real lines, joints of the same material merged, build-ups,\n"
                      "windows and doors fine")

    @classmethod
    def poll(cls, context):
        return _poll(cls, context, needs_selection=False)

    def execute(self, context):
        try:
            path, report = update_active_drawing()
        except Exception as error:
            self.report({"ERROR"}, "Update Drawing: %s" % error)
            return {"CANCELLED"}
        for line in report:
            print("BTK Tools for Bonsai: " + line)
        self.report({"INFO"}, "%s: %s" % (os.path.basename(path), report[-1] if report else "done"))
        return {"FINISHED"}


class BONSAI_BTK_OT_layers(bpy.types.Operator):
    bl_idname = "bonsai_btk.layers"
    bl_label = "Layers On/Off"
    bl_description = ("Draw the selected elements with layers or as one area, in every scale.\n"
                      "If all are off they go on, otherwise off. Ctrl: back to automatic\n"
                      "(one area from 1:%d). Stored as %s.%s and kept in the IFC"
                      % (100, model.PSET, model.LAYERS))
    bl_options = {"REGISTER", "UNDO"}
    automatic: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return _poll(cls, context, needs_selection=True)

    def invoke(self, context, event):
        self.automatic = event.ctrl
        return self.execute(context)

    def execute(self, context):
        import bonsai.tool as tool
        elements = selected_elements(context)
        try:
            value = model.toggle_layers(tool.Ifc.get(), elements, self.automatic, run=tool.Ifc.run)
        except Exception as error:
            self.report({"ERROR"}, "Layers: %s" % error)
            return {"CANCELLED"}
        text = {None: "automatic", True: "layers on", False: "one area"}[value]
        return _update_after(self, "%d element(s): %s" % (len(elements), text))


class BONSAI_BTK_OT_rotate_hatching(bpy.types.Operator):
    bl_idname = "bonsai_btk.rotate_hatching"
    bl_label = "Rotate Hatching"
    bl_description = ("Turn the hatching of the selected elements by %g degrees.\n"
                      "Stored as %s.%s and kept in the IFC" % (model.ROTATION_STEP, model.PSET, model.ROTATION))
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _poll(cls, context, needs_selection=True)

    def execute(self, context):
        import bonsai.tool as tool
        done = []
        try:
            for element in selected_elements(context):
                before, after = model.rotate(tool.Ifc.get(), element, run=tool.Ifc.run)
                done.append("%s %g to %g degrees" % (element.Name or element.is_a(), before, after))
        except Exception as error:
            self.report({"ERROR"}, "Rotate Hatching: %s" % error)
            return {"CANCELLED"}
        return _update_after(self, "; ".join(done))


def _poll_sheet(cls):
    import bonsai.tool as tool
    if not tool.Ifc.get():
        cls.poll_message_set("No IFC project loaded.")
        return False
    if not tool.Drawing.get_active_sheet_item(is_sheet=True):
        cls.poll_message_set("No sheet selected in the sheet list.")
        return False
    return True


class BONSAI_BTK_OT_update_sheet(bpy.types.Operator):
    bl_idname = "bonsai_btk.update_sheet"
    bl_label = "Update Sheet"
    bl_description = ("Update every drawing on the selected sheet, put legend and north arrow\n"
                      "into its layout and build the sheet with Bonsai")

    @classmethod
    def poll(cls, context):
        return _poll_sheet(cls)

    def execute(self, context):
        entity = active_sheet()
        try:
            path, report = update_sheet(entity)
        except Exception as error:
            self.report({"ERROR"}, "Update Sheet: %s" % error)
            return {"CANCELLED"}
        for line in report:
            print("BTK Tools for Bonsai: " + line)
        self.report({"INFO"}, "Sheet %s: %d drawing(s) updated" % (entity.Name, sum(1 for r in report if "outline(s) of the same material" in r)))
        return {"FINISHED"}


class BONSAI_BTK_OT_print_sheet(bpy.types.Operator):
    bl_idname = "bonsai_btk.print_sheet"
    bl_label = "Print Sheet (PDF)"
    bl_description = ("The selected sheet as PDF through Inkscape, to a file you choose.\n"
                      "Browsers rasterise the hatching when they print; Inkscape keeps it as lines")

    filepath: bpy.props.StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})
    filter_glob: bpy.props.StringProperty(default="*.pdf", options={"HIDDEN"})
    update_first: bpy.props.BoolProperty(name="Update Sheet First", default=True)

    @classmethod
    def poll(cls, context):
        return _poll_sheet(cls)

    def invoke(self, context, event):
        import bonsai.tool as tool
        entity = active_sheet()
        folder = os.path.dirname(tool.Ifc.get_path() or bpy.data.filepath or os.path.expanduser("~"))
        self.filepath = os.path.join(folder, bpy.path.clean_name("%s - %s" % (entity[0], entity.Name)) + ".pdf")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        exe = inkscape()
        if not exe:
            self.report({"ERROR"}, "Inkscape not found; set its path in the add-on preferences")
            return {"CANCELLED"}
        entity = active_sheet()
        target = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), ".pdf")
        try:
            path = update_sheet(entity)[0] if self.update_first else sheet_path(entity)
            printing.sheet_pdf(path, target, exe)
        except Exception as error:
            self.report({"ERROR"}, "Print Sheet: %s" % error)
            return {"CANCELLED"}
        self.report({"INFO"}, "PDF written: %s" % target)
        return {"FINISHED"}


class BONSAI_BTK_OT_preview_drawing(bpy.types.Operator):
    bl_idname = "bonsai_btk.preview_drawing"
    bl_label = "Preview Drawing"
    bl_description = ("Update the active drawing and show it in the web browser.\n"
                      "The page reloads by itself after every later update")

    @classmethod
    def poll(cls, context):
        return _poll(cls, context, needs_selection=False)

    def execute(self, context):
        try:
            server = start_preview()
            path, report = update_active_drawing()
        except Exception as error:
            self.report({"ERROR"}, "Preview Drawing: %s" % error)
            return {"CANCELLED"}
        _open_page("drawing", server.url)
        self.report({"INFO"}, "Preview: %s" % server.url)
        return {"FINISHED"}


class BONSAI_BTK_OT_preview_sheet(bpy.types.Operator):
    bl_idname = "bonsai_btk.preview_sheet"
    bl_label = "Preview Sheet"
    bl_description = ("Update the selected sheet and show it in the web browser.\n"
                      "There drawings, view titles, legend and north arrow can be moved;\n"
                      "Apply writes the layout (with a backup) and builds the sheet again")

    @classmethod
    def poll(cls, context):
        return _poll_sheet(cls)

    def execute(self, context):
        entity = active_sheet()
        try:
            server = start_preview()
            update_sheet(entity)
        except Exception as error:
            self.report({"ERROR"}, "Preview Sheet: %s" % error)
            return {"CANCELLED"}
        _open_page("sheet", server.url + "sheet")
        self.report({"INFO"}, "Preview: %ssheet" % server.url)
        return {"FINISHED"}


class BONSAI_BTK_OT_stop_preview(bpy.types.Operator):
    bl_idname = "bonsai_btk.stop_preview"
    bl_label = "Stop Preview"
    bl_description = "End the local preview server; open pages stop updating"

    @classmethod
    def poll(cls, context):
        return _preview["server"] is not None

    def execute(self, context):
        stop_preview()
        self.report({"INFO"}, "Preview stopped")
        return {"FINISHED"}


class BONSAI_BTK_PT_drawing(bpy.types.Panel):
    bl_label = "Drawing"
    bl_idname = "BONSAI_BTK_PT_drawing"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BTK"
    bl_order = 1

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("bonsai_btk.update_drawing", icon="FILE_REFRESH")
        row = col.row(align=True)
        row.operator("bonsai_btk.layers", icon="ALIGN_JUSTIFY")
        row.operator("bonsai_btk.rotate_hatching", text="Rotate", icon="DRIVER_ROTATIONAL_DIFFERENCE")
        col = self.layout.column(align=True)
        col.operator("bonsai_btk.update_sheet", icon="DOCUMENTS")
        col.operator("bonsai_btk.print_sheet", icon="EXPORT")
        col = self.layout.column(align=True)
        row = col.row(align=True)
        row.operator("bonsai_btk.preview_drawing", text="Preview Drawing", icon="WORLD")
        row.operator("bonsai_btk.preview_sheet", text="Preview Sheet", icon="WORLD")
        if _preview["server"] is not None:
            row = col.row(align=True)
            row.label(text=_preview["server"].url)
            row.operator("bonsai_btk.stop_preview", text="", icon="X")


CLASSES = (BONSAI_BTK_OT_update_drawing, BONSAI_BTK_OT_layers, BONSAI_BTK_OT_rotate_hatching,
           BONSAI_BTK_OT_update_sheet, BONSAI_BTK_OT_print_sheet, BONSAI_BTK_OT_preview_drawing,
           BONSAI_BTK_OT_preview_sheet, BONSAI_BTK_OT_stop_preview, BONSAI_BTK_PT_drawing)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    stop_preview()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
