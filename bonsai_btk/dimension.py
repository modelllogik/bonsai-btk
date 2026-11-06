# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dimension chain from snapped points, and flipping a chain.

Dimension from points (horizontal, vertical and inclined, e.g. an inclined wall in a
plan or a roof slope in a section):
    1. Pick element vertices with the mouse (M = next vertex nearby, Backspace = remove
       the last point, S = intersection of two edges, see snap.py). Point 1 -> point 2
       gives the direction; every further point is projected onto the dimension line,
       and the points are sorted along the direction.
    2. Enter: the mouse sets side and offset, on a 5 mm grid on the sheet. Typing a
       number sets the offset in mm on the sheet. Backspace without input goes back
       to picking.
       Outside the outer face of the walls, the first chain of a block starts on the grid
       from that outer face, and every further parallel chain is placed 10 mm beyond the
       outermost one.
    3. Click/Enter creates the chain with Bonsai's add_annotation (DIMENSION) in the
       ACTIVE drawing and writes the points directly into its IfcIndexedPolyCurve.
    Esc or right click cancels at any time; nothing is created.

Flip dimension: reverses the point order of the selected dimension chains, so the
figures turn with it. Readable after DIN 1356 is a chain that runs left to right
(horizontal) or bottom to top (vertical). For inclined chains the eye decides.

Scale changes: a chain created here stores its offset on the sheet, the drawing scale
and its side in EPset_BTK_DimensionChain. A timer compares the scale of the active
drawing with it once per second and moves the chain sideways so that its offset on the
sheet stays the same. Chains without this property set are left alone.

Dimension points stay free points; nothing is attached to the element.
"""
import math
from fractions import Fraction

GRID_MM = 5.0            # mouse grid for the offset, mm on the sheet
DEFAULT_MM = 10.0        # offset before the mouse is moved
CHAIN_SPACING_MM = 10.0  # spacing of the chains in a block, mm on the sheet
PARALLEL_SIN = 0.0175    # parallel = within 1 degree
SAME_M = 1e-5            # points closer than 0.01 mm count as the same
PSET = "EPset_BTK_DimensionChain"


# ============================================================ geometry (no bpy)
def scale_ratio(text):
    """'1/50' -> 0.02 (sheet mm per model mm)."""
    return float(Fraction(str(text).replace(":", "/")))


def mm_to_m(mm, ratio):
    return mm / 1000.0 / ratio


def m_to_mm(m, ratio):
    return m * 1000.0 * ratio


def snap_to_grid(offset_m, ratio, step_mm=GRID_MM):
    mm = round(m_to_mm(offset_m, ratio) / step_mm) * step_mm
    return mm_to_m(mm, ratio)


def needs_flip(points_xy):
    """Points in drawing coordinates. Horizontal (|dx| >= |dy|): left -> right;
    vertical: bottom -> top. True if the order has to be reversed."""
    if len(points_xy) < 2:
        return False
    dx = points_xy[-1][0] - points_xy[0][0]
    dy = points_xy[-1][1] - points_xy[0][1]
    if math.hypot(dx, dy) < 1e-9:
        return False
    return dx < 0 if abs(dx) >= abs(dy) else dy < 0


def reverse_segments(segments, n):
    """[(type, (i, j, ...)), ...] with 1-based indices -> reversed chain."""
    return [(kind, tuple(n + 1 - i for i in reversed(idx))) for kind, idx in reversed(segments)]


def type_input(text, char):
    """Input buffer for the offset: digits, one decimal separator, backspace = '\\b'."""
    if char == "\b":
        return text[:-1]
    if char in ",.":
        return text if ("." in text) else (text or "0") + "."
    if char.isdigit():
        return text + char
    return text


def number(text):
    try:
        return float(text) if text not in ("", ".") else None
    except ValueError:
        return None


def fmt_mm(mm):
    return ("%.1f" % mm).rstrip("0").rstrip(".")


def direction(points_xy):
    """Unit vector from point 1 to the first point that differs from it, else None."""
    if len(points_xy) < 2:
        return None
    x0, y0 = points_xy[0]
    for x, y in points_xy[1:]:
        length = math.hypot(x - x0, y - y0)
        if length > SAME_M:
            return ((x - x0) / length, (y - y0) / length)
    return None


def normal_left(d):
    """Normal to the left of the direction (for left -> right: up)."""
    return (-d[1], d[0])


def side_and_offset(points_xy, mouse_xy):
    """Side (+1 left / -1 right of the direction) and offset in model m from the line through point 1."""
    d = direction(points_xy)
    if d is None:
        return 1, 0.0
    n = normal_left(d)
    s = (mouse_xy[0] - points_xy[0][0]) * n[0] + (mouse_xy[1] - points_xy[0][1]) * n[1]
    return (1 if s >= 0 else -1), abs(s)


def chain_from_points(points_xy, side, offset_m):
    """Dimension points of the chain: every point projected onto the dimension line (the
    line through point 1 in the direction point 1 -> point 2, moved offset_m to the side),
    sorted along the direction, duplicates removed. Returns [(x, y), ...] in drawing
    coordinates."""
    d = direction(points_xy)
    if d is None:
        return []
    n = normal_left(d)
    x0, y0 = points_xy[0]
    bx, by = x0 + n[0] * side * offset_m, y0 + n[1] * side * offset_m
    ts = sorted((x - x0) * d[0] + (y - y0) * d[1] for x, y in points_xy)
    single = []
    for t in ts:
        if not single or t - single[-1] > SAME_M:
            single.append(t)
    return [(bx + d[0] * t, by + d[1] * t) for t in single]


def is_new_point(points_xy, xy):
    """True if xy is not yet in the list (within 0.01 mm)."""
    return all(math.hypot(xy[0] - x, xy[1] - y) > SAME_M for x, y in points_xy)


def shift_m(offset_mm, old_scale, new_scale):
    """Sideways shift of a chain in model m so that its offset on the sheet stays the same
    when the scale changes ('1/50' -> '1/100': 10 mm -> +0.5 m)."""
    return offset_mm / 1000.0 * (1.0 / scale_ratio(new_scale) - 1.0 / scale_ratio(old_scale))


# ============================================================ Blender
try:
    import bpy
except ImportError:
    bpy = None

if bpy is not None:
    import gpu
    from gpu_extras.batch import batch_for_shader
    from mathutils import Vector
    from mathutils.geometry import intersect_line_plane
    from bpy_extras import view3d_utils
    import bonsai.tool as _tool

    from . import snap

    def _bonsai_ready(context, cls=None):
        import bonsai.tool as tool
        reason = None
        if not tool.Ifc.get():
            reason = "No IFC project loaded."
        elif not tool.Drawing.is_drawing_active() or not context.scene.camera:
            reason = "No drawing active."
        elif context.scene.BIMGeometryProperties.mode != "OBJECT" or context.mode != "OBJECT":
            reason = "Only in IFC Object Mode."
        if reason and cls is not None:
            cls.poll_message_set(reason)
        return reason is None

    def _poly_curves(element):
        curves = []
        for rep in (element.Representation.Representations if element and element.Representation else []):
            for it in rep.Items:
                for k in (it.Elements if it.is_a("IfcGeometricCurveSet") else [it]):
                    if k.is_a("IfcIndexedPolyCurve"):
                        curves.append(k)
        return curves

    def _own_point_list(ifc, curve):
        """The curve's point list, copied first if other curves share it."""
        ptl = curve.Points
        if len(ifc.get_inverse(ptl)) > 1:
            ptl = ifc.create_entity(ptl.is_a(), CoordList=ptl.CoordList)
            curve.Points = ptl
        return ptl

    class BONSAI_BTK_OT_dimension_flip(bpy.types.Operator, _tool.Ifc.Operator):
        bl_idname = "bonsai_btk.dimension_flip"
        bl_label = "Flip Dimension"
        bl_description = ("Reverse the point order of the selected dimension chains; the figures turn with it.\n"
                          "Readable after DIN 1356: horizontal left → right, vertical bottom → top.\n"
                          "Rewrites the point list in the IFC")
        bl_options = {"REGISTER", "UNDO"}

        @classmethod
        def poll(cls, context):
            import bonsai.tool as tool
            if not tool.Ifc.get():
                return False
            if context.scene.BIMGeometryProperties.mode != "OBJECT" or context.mode != "OBJECT":
                cls.poll_message_set("Only in IFC Object Mode.")
                return False
            if not any(cls._dimension(o) for o in context.selected_objects):
                cls.poll_message_set("No dimension chain selected.")
                return False
            return True

        @staticmethod
        def _dimension(obj):
            import bonsai.tool as tool
            import ifcopenshell.util.element as ue
            e = tool.Ifc.get_entity(obj)
            return e if e and e.is_a("IfcAnnotation") and ue.get_predefined_type(e) == "DIMENSION" else None

        def _execute(self, context):
            import bonsai.tool as tool
            ifc = tool.Ifc.get()
            flipped, without = [], []
            for obj in context.selected_objects:
                e = self._dimension(obj)
                if not e or not e.Representation:
                    continue
                changed = False
                for k in _poly_curves(e):
                    coords = [tuple(p) for p in k.Points.CoordList]
                    if len(coords) < 2:
                        continue
                    _own_point_list(ifc, k).CoordList = list(reversed(coords))
                    if k.Segments:
                        seg = [(s.is_a(), tuple(s.wrappedValue)) for s in k.Segments]
                        k.Segments = [ifc.create_entity(kind, idx) for kind, idx in reverse_segments(seg, len(coords))]
                    changed = True
                if changed:
                    tool.Geometry.reload_representation(obj)
                    flipped.append(obj.name)
                else:
                    without.append(obj.name)
            self.report({"INFO"}, "Flipped: %s%s" % (
                ", ".join(flipped) or "–", (" · without curve: " + ", ".join(without)) if without else ""))

    class BONSAI_BTK_OT_dimension_from_points(bpy.types.Operator):
        bl_idname = "bonsai_btk.dimension_from_points"
        bl_label = "Dimension from Points"
        bl_description = ("Dimension chain from snapped element vertices, also inclined.\n"
                          "Click = point (M = next vertex nearby, Backspace = remove last, "
                          "S = intersection of two edges), point 1 → 2 = direction.\n"
                          "Enter = offset with the mouse or type mm, Click/Enter = create, Esc = cancel")
        bl_options = {"REGISTER"}

        @classmethod
        def poll(cls, context):
            return _bonsai_ready(context, cls)

        def invoke(self, context, event):
            import bonsai.tool as tool
            import ifcopenshell.util.element as ue
            if context.area is None or context.area.type != "VIEW_3D":
                self.report({"ERROR"}, "The mouse must be in the 3D view")
                return {"CANCELLED"}
            self.area = context.area
            self.image_region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
            self.rv3d = context.area.spaces.active.region_3d
            if self.image_region is None or self.rv3d is None:
                self.report({"ERROR"}, "No 3D image region found")
                return {"CANCELLED"}
            self.camera = context.scene.camera
            self.scale_text = ue.get_pset(tool.Ifc.get_entity(self.camera), "EPset_Drawing", "Scale") or "1/100"
            self.ratio = scale_ratio(self.scale_text)
            self.normal = self.camera.matrix_world.to_quaternion() @ Vector((0, 0, 1))
            self.phase = "PICK"
            self.points_xy, self.points_world = [], []
            self.cz = None
            self.current, self.snap_type = None, ""
            self.side, self.offset_m, self.typed = 1, mm_to_m(DEFAULT_MM, self.ratio), ""
            self.block, self.block_text, self.outer_face = None, "", None
            self.candidates, self.candidate = [], 0   # vertices near the mouse; M steps through them
            r = self.image_region
            context.window.cursor_warp(r.x + r.width // 2, r.y + r.height // 2)
            self.handle = bpy.types.SpaceView3D.draw_handler_add(self.draw, (context,), "WINDOW", "POST_PIXEL")
            context.window_manager.modal_handler_add(self)
            self.status(context)
            return {"RUNNING_MODAL"}

        # ---------------------------------------------------------- helpers
        def xy(self, world):
            p = self.camera.matrix_world.inverted() @ world
            return (p.x, p.y), p.z

        def world(self, xy):
            z = self.cz if self.cz is not None else 0.0
            return self.camera.matrix_world @ Vector((xy[0], xy[1], z))

        def on_plane(self, event):
            """Mouse ray intersected with the drawing plane through point 1 or the 3D cursor."""
            region, rv3d = self.image_region, self.rv3d
            co = (event.mouse_x - region.x, event.mouse_y - region.y)
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
            ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
            ref = self.points_world[0] if self.points_world else bpy.context.scene.cursor.location
            p = intersect_line_plane(origin, origin + ray, ref, self.normal)
            return p if p is not None else view3d_utils.region_2d_to_location_3d(region, rv3d, co, ref)

        def take_snap(self, event):
            """Without S: the nearest mesh vertex (M steps to the next one).
            With S the intersection snap takes the clicks; the mouse point is only shown."""
            if snap.is_active(self):
                self.candidates, self.candidate = [], 0
                self.current, self.snap_type = self.on_plane(event), "edge"
                return
            self.candidates = [w for w, _ in snap.vertices_under_mouse(self, snap.mouse(self, event))]
            self.candidate = 0
            # free mouse position, only for the preview line between vertices (clicks still need a vertex)
            self.mouse_world = None if self.candidates else self.on_plane(event)
            self.show_candidate()

        def show_candidate(self):
            if self.candidates:
                self.current = self.candidates[self.candidate % len(self.candidates)]
                n = len(self.candidates)
                self.snap_type = "vertex" if n == 1 else "vertex %d of %d" % (self.candidate % n + 1, n)
            else:
                self.current, self.snap_type = None, "no vertex"

        def current_offset(self):
            mm = number(self.typed)
            if mm is not None and self.outer_face is not None:   # typed mm count from the outer face
                return self.outer_face + mm_to_m(mm, self.ratio)
            return mm_to_m(mm, self.ratio) if mm is not None else self.offset_m

        def status(self, context):
            n = len(self.points_xy)
            if self.phase == "PICK":
                text = ("Dimension from points · %d point%s · snap: %s  ·  Click = point · M = next vertex · "
                        "Backspace = remove last · Enter = offset · Esc = cancel" % (n, "" if n == 1 else "s", self.snap_type or "–"))
            else:
                a = self.current_offset()
                text = ("Dimension from points · %s · offset %s mm on the sheet = %.3f m%s  ·  Click/Enter = create · "
                        "type mm · Backspace = back to points · Esc = cancel" % (
                            "left of the direction" if self.side > 0 else "right of the direction",
                            fmt_mm(m_to_mm(a, self.ratio)), a,
                            ("  ·  input: " + self.typed) if self.typed else ""))
                text += self.block_text
            self.area.header_text_set(text + snap.hint(self))
            self.area.tag_redraw()

        def draw(self, context):
            try:
                region, rv3d = self.image_region, self.rv3d
                if context.region != region:
                    return

                def px(w):
                    p = view3d_utils.location_3d_to_region_2d(region, rv3d, w)
                    return None if p is None else (p.x, p.y, 0.0)

                orange, blue = (1.0, 0.45, 0.0, 1.0), (0.1, 0.55, 1.0, 1.0)
                shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
                gpu.state.blend_set("ALPHA")
                shader.uniform_float("viewportSize", (region.width, region.height))

                def lines(pos, colour, width):
                    pos = [p for p in pos if p is not None]
                    if len(pos) >= 2:
                        shader.uniform_float("lineWidth", width)
                        shader.uniform_float("color", colour)
                        batch_for_shader(shader, "LINES", {"pos": pos[: len(pos) // 2 * 2]}).draw(shader)

                def cross(w, colour, g=6):
                    p = px(w)
                    if p:
                        lines([(p[0] - g, p[1] - g, 0), (p[0] + g, p[1] + g, 0),
                               (p[0] - g, p[1] + g, 0), (p[0] + g, p[1] - g, 0)], colour, 2.0)

                def square(w, colour, g=5):
                    p = px(w)
                    if p:
                        c = [(p[0] - g, p[1] - g, 0), (p[0] + g, p[1] - g, 0), (p[0] + g, p[1] + g, 0), (p[0] - g, p[1] + g, 0)]
                        lines([c[0], c[1], c[1], c[2], c[2], c[3], c[3], c[0]], colour, 2.0)

                for w in self.points_world:
                    cross(w, orange)
                snap.draw(self, px, lines, square)
                if self.phase == "PICK":
                    chain = self.points_world + ([self.current] if self.current is not None else [])
                    pos = []
                    for a, b in zip(chain, chain[1:]):
                        pos += [px(a), px(b)]
                    lines(pos, orange, 1.5)
                    if self.current is not None:
                        square(self.current, blue)
                    elif self.points_world and getattr(self, "mouse_world", None) is not None:
                        # no vertex near the mouse: thin grey line, so the preview keeps following
                        lines([px(self.points_world[-1]), px(self.mouse_world)], (0.5, 0.5, 0.5, 0.8), 1.0)
                else:
                    offset = self.current_offset()
                    q = chain_from_points(self.points_xy, self.side, offset)
                    if len(q) >= 2:
                        qw = [self.world(p) for p in q]
                        lines([px(qw[0]), px(qw[-1])], orange, 2.0)
                        d = direction(self.points_xy)
                        n = normal_left(d)
                        s = mm_to_m(1.5, self.ratio)
                        ticks = []
                        for p in q:
                            ticks += [px(self.world((p[0] + (d[0] + n[0]) * s, p[1] + (d[1] + n[1]) * s))),
                                      px(self.world((p[0] - (d[0] + n[0]) * s, p[1] - (d[1] + n[1]) * s)))]
                        lines(ticks, orange, 2.0)
                        helpers = []
                        x0, y0 = self.points_xy[0]
                        for p, w in zip(self.points_xy, self.points_world):
                            t = (p[0] - x0) * d[0] + (p[1] - y0) * d[1]
                            target = (x0 + n[0] * self.side * offset + d[0] * t,
                                      y0 + n[1] * self.side * offset + d[1] * t)
                            helpers += [px(w), px(self.world(target))]
                        lines(helpers, orange, 1.0)
                gpu.state.blend_set("NONE")
            except Exception:
                pass

        def clean_up(self, context):
            if getattr(self, "handle", None) is not None:
                bpy.types.SpaceView3D.draw_handler_remove(self.handle, "WINDOW")
                self.handle = None
            self.area.header_text_set(None)
            self.area.tag_redraw()

        # ---------------------------------------------------------- modal
        def modal(self, context, event):
            if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM"}:
                return {"PASS_THROUGH"}   # view changes; snap.py notices them by itself
            if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
                self.clean_up(context)
                self.report({"INFO"}, "Dimension from points cancelled")
                return {"CANCELLED"}
            r = snap.handle_event(self, context, event)
            if r is not None:
                return r
            if self.phase == "PICK":
                if event.type == "MOUSEMOVE":
                    self.take_snap(event)
                elif event.type == "INBETWEEN_MOUSEMOVE":
                    return {"RUNNING_MODAL"}   # intermediate positions: skip, the next MOUSEMOVE follows
                elif event.value == "PRESS" and event.type == "M" and len(self.candidates) > 1:
                    self.candidate += 1
                    self.show_candidate()
                elif event.value == "PRESS" and event.type == "LEFTMOUSE" and self.current is not None:
                    xy, z = self.xy(self.current)
                    if self.cz is None:
                        self.cz = z
                    if is_new_point(self.points_xy, xy):
                        self.points_xy.append(xy)
                        self.points_world.append(self.world(xy))
                elif event.value == "PRESS" and event.type == "BACK_SPACE" and self.points_xy:
                    self.points_xy.pop()
                    self.points_world.pop()
                    if not self.points_xy:
                        self.cz = None
                elif event.value == "PRESS" and event.type in {"RET", "NUMPAD_ENTER"}:
                    if direction(self.points_xy) is None:
                        self.report({"WARNING"}, "Pick at least two different points")
                    else:
                        self.phase = "OFFSET"
                        self.block, self.block_text, self.outer_face = None, "", None
                        self.typed = ""
                        q = chain_from_points(self.points_xy, self.side, self.offset_m)
                        middle = ((q[0][0] + q[-1][0]) / 2, (q[0][1] + q[-1][1]) / 2)
                        co = view3d_utils.location_3d_to_region_2d(self.image_region, self.rv3d, self.world(middle))
                        r = self.image_region
                        if co is not None and 0 <= co.x < r.width and 0 <= co.y < r.height:
                            context.window.cursor_warp(r.x + int(co.x), r.y + int(co.y))
                self.status(context)
                return {"RUNNING_MODAL"}
            # phase OFFSET
            if event.type == "MOUSEMOVE":
                if self.block is None:
                    _collect_block(self)
                mouse_xy, _ = self.xy(self.on_plane(event))
                self.side, raw = side_and_offset(self.points_xy, mouse_xy)
                self.offset_m, self.block_text, self.outer_face = _block_offset(self, self.side, raw)
            elif event.value == "PRESS" and event.type == "BACK_SPACE":
                if self.typed:
                    self.typed = type_input(self.typed, "\b")
                else:
                    self.phase = "PICK"
                    self.block, self.block_text, self.outer_face = None, "", None
            elif event.value == "PRESS" and event.unicode and event.unicode in "0123456789.,":
                self.typed = type_input(self.typed, event.unicode)
            elif event.value == "PRESS" and event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"}:
                import json
                a = self.current_offset()
                q = chain_from_points(self.points_xy, self.side, a)
                self.clean_up(context)
                if len(q) < 2:
                    self.report({"WARNING"}, "No chain: too few different points")
                    return {"CANCELLED"}
                world = [tuple(self.world(p)) for p in q]
                n = normal_left(direction(self.points_xy))
                with context.temp_override(area=self.area, region=self.image_region):
                    bpy.ops.bonsai_btk.dimension_create(
                        coordinates=json.dumps(world), offset_mm=m_to_mm(a, self.ratio), scale=self.scale_text,
                        normal=json.dumps([n[0] * self.side, n[1] * self.side]))
                self.report({"INFO"}, "Dimension from %d points, offset %s mm on the sheet. Figures upside down? Flip it" % (
                    len(q), fmt_mm(m_to_mm(a, self.ratio))))
                return {"FINISHED"}
            self.status(context)
            return {"RUNNING_MODAL"}

    class BONSAI_BTK_OT_dimension_create(bpy.types.Operator, _tool.Ifc.Operator):
        bl_idname = "bonsai_btk.dimension_create"
        bl_label = "Create Dimension from Points"
        bl_description = "Creates a dimension chain in the active drawing and writes its points (internal)"
        bl_options = {"REGISTER", "UNDO", "INTERNAL"}
        coordinates: bpy.props.StringProperty()
        offset_mm: bpy.props.FloatProperty(default=-1.0)
        scale: bpy.props.StringProperty()
        normal: bpy.props.StringProperty()

        @classmethod
        def poll(cls, context):
            return _bonsai_ready(context, cls)

        def _execute(self, context):
            import json
            import bonsai.tool as tool
            import bonsai.core.drawing as core
            import ifcopenshell.util.unit as uu
            points = [Vector(p) for p in json.loads(self.coordinates)]
            drawing = tool.Drawing.get_document_props().get_active_drawing()
            if len(points) < 2 or drawing is None:
                self.report({"ERROR"}, "No active drawing or too few points")
                return
            cursor_before = context.scene.cursor.location.copy()
            try:
                context.scene.cursor.location = points[0]
                obj = core.add_annotation(tool.Ifc, tool.Collector, tool.Drawing, drawing=drawing,
                                          object_type="DIMENSION", relating_type=None, enable_editing=False)
            finally:
                context.scene.cursor.location = cursor_before
            ifc = tool.Ifc.get()
            e = tool.Ifc.get_entity(obj)
            curves = _poly_curves(e)
            if not curves:
                self.report({"ERROR"}, "Dimension %s created, but no IfcIndexedPolyCurve found" % obj.name)
                return
            k = curves[0]
            unit = uu.calculate_unit_scale(ifc)
            local = [obj.matrix_world.inverted() @ p for p in points]
            ptl = _own_point_list(ifc, k)
            if ptl.is_a("IfcCartesianPointList2D"):
                ptl.CoordList = [(p.x / unit, p.y / unit) for p in local]
            else:
                ptl.CoordList = [(p.x / unit, p.y / unit, 0.0) for p in local]
            k.Segments = None
            if self.offset_mm >= 0 and self.scale and self.normal:
                remember_chain(ifc, e, self.offset_mm, self.scale, json.loads(self.normal))
            tool.Geometry.reload_representation(obj)
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj

    def _collect_block(op):
        """Once per offset step: wall vertices and existing parallel chains of the drawing,
        both in coordinates of the new chain (t along the direction, o across, from point 1)."""
        import bonsai.tool as tool
        import ifcopenshell.util.unit as uu
        d = direction(op.points_xy)
        n = normal_left(d)
        x0, y0 = op.points_xy[0]

        def to(x, y):
            return ((x - x0) * d[0] + (y - y0) * d[1], (x - x0) * n[0] + (y - y0) * n[1])
        ts = [to(x, y)[0] for x, y in op.points_xy]
        inv = op.camera.matrix_world.inverted()
        walls = []
        for o in bpy.context.view_layer.objects:
            try:
                if o.type != "MESH" or not o.visible_get():
                    continue
                e = tool.Ifc.get_entity(o)
                if e is None or not e.is_a("IfcWall"):
                    continue
                mw = o.matrix_world
                for v in o.data.vertices:
                    p = inv @ (mw @ v.co)
                    walls.append(to(p.x, p.y))
            except ReferenceError:
                continue
        chains = []
        unit = uu.calculate_unit_scale(tool.Ifc.get())
        drawing = tool.Drawing.get_document_props().get_active_drawing()
        group = tool.Drawing.get_drawing_group(drawing) if drawing else None
        for rel in (group.IsGroupedBy if group else []):
            for e in rel.RelatedObjects:
                if not (e.is_a("IfcAnnotation") and e.ObjectType == "DIMENSION"):
                    continue
                o = tool.Ifc.get_object(e)
                if o is None or not e.Representation:
                    continue
                pts = []
                for k in _poly_curves(e):
                    for c in k.Points.CoordList:
                        w = o.matrix_world @ Vector((c[0] * unit, c[1] * unit, (c[2] * unit) if len(c) > 2 else 0.0))
                        p = inv @ w
                        pts.append(to(p.x, p.y))
                if len(pts) < 2:
                    continue
                (ta, oa), (tb, ob) = pts[0], pts[-1]
                length = math.hypot(tb - ta, ob - oa)
                if length < 1e-6 or abs(ob - oa) / length > PARALLEL_SIN:
                    continue
                chains.append(((oa + ob) / 2, min(t for t, _ in pts), max(t for t, _ in pts)))
        op.block = dict(walls=walls, chains=chains, t=(min(ts), max(ts)))

    def _block_offset(op, side, raw):
        """(offset in m from point 1, message, outer face in m from point 1 or None).
        With the mouse inside the outer face nothing changes (inner dimensions)."""
        b = op.block
        t_min, t_max = b["t"]
        margin = mm_to_m(2.0, op.ratio)
        across = [side * o for t, o in b["walls"] if t_min - margin <= t <= t_max + margin]
        outer = max(across) if across else None
        if outer is None or raw <= outer:
            return snap_to_grid(raw, op.ratio), "", None
        block = [side * o for o, ta, tb in b["chains"]
                 if side * o > outer + 1e-6 and tb >= t_min - margin and ta <= t_max + margin]
        if block:
            a = max(block) + mm_to_m(CHAIN_SPACING_MM, op.ratio)
            return a, "  ·  block: chain %d, %s mm beyond the outermost" % (len(block) + 1, fmt_mm(CHAIN_SPACING_MM)), outer
        a = outer + snap_to_grid(raw - outer, op.ratio)
        return a, "  ·  first chain of the block: %s mm from the outer face" % fmt_mm(m_to_mm(a - outer, op.ratio)), outer

    def remember_chain(ifc, element, offset_mm, scale_text, normal):
        """Store offset on the sheet, scale and the side away from the element points on the chain."""
        import ifcopenshell.api.pset
        pset = ifcopenshell.api.pset.add_pset(ifc, product=element, name=PSET)
        ifcopenshell.api.pset.edit_pset(ifc, pset=pset, properties={
            "Offset": float(offset_mm), "Scale": str(scale_text),
            "NormalX": float(normal[0]), "NormalY": float(normal[1])})

    def _chains_of_drawing(drawing):
        """[(element, pset)] of the dimension chains with EPset_BTK_DimensionChain in the drawing."""
        import bonsai.tool as tool
        import ifcopenshell.util.element as ue
        group = tool.Drawing.get_drawing_group(drawing)
        if group is None:
            return []
        result = []
        for rel in group.IsGroupedBy:
            for e in rel.RelatedObjects:
                if e.is_a("IfcAnnotation") and e.ObjectType == "DIMENSION":
                    ps = ue.get_pset(e, PSET)
                    if ps and ps.get("Scale") and ps.get("Offset") is not None:
                        result.append((e, ps))
        return result

    class BONSAI_BTK_OT_dimension_follow_scale(bpy.types.Operator, _tool.Ifc.Operator):
        bl_idname = "bonsai_btk.dimension_follow_scale"
        bl_label = "Adapt Dimension Chains to Scale"
        bl_description = ("Moves chains made with Dimension from Points sideways so that their offset on the "
                          "sheet stays the same when the scale changes (internal, called by a timer)")
        bl_options = {"REGISTER", "UNDO", "INTERNAL"}

        def _execute(self, context):
            import bonsai.tool as tool
            import ifcopenshell.util.element as ue
            import ifcopenshell.util.unit as uu
            import ifcopenshell.api.pset
            ifc = tool.Ifc.get()
            drawing = tool.Drawing.get_document_props().get_active_drawing()
            camera = context.scene.camera
            if drawing is None or camera is None:
                return
            new = ue.get_pset(drawing, "EPset_Drawing", "Scale")
            if not new:
                return
            unit = uu.calculate_unit_scale(ifc)
            rotation = camera.matrix_world.to_quaternion()
            moved = []
            for e, ps in _chains_of_drawing(drawing):
                if ps["Scale"] == new:
                    continue
                obj = tool.Ifc.get_object(e)
                if obj is None:
                    continue
                d = shift_m(ps["Offset"], ps["Scale"], new)
                offset = rotation @ Vector((ps.get("NormalX") or 0.0, ps.get("NormalY") or 0.0, 0.0)) * d
                v = (obj.matrix_world.inverted().to_3x3() @ offset) / unit
                for k in _poly_curves(e):
                    ptl = _own_point_list(ifc, k)
                    ptl.CoordList = [tuple([c[0] + v.x, c[1] + v.y] + list(c[2:])) for c in ptl.CoordList]
                ifcopenshell.api.pset.edit_pset(ifc, pset=ifc.by_id(ps["id"]), properties={"Scale": new})
                tool.Geometry.reload_representation(obj)
                moved.append(obj.name)
            if moved:
                self.report({"INFO"}, "Dimension chains adapted to %s: %s" % (new, ", ".join(moved)))

    def scale_watcher():
        """Timer: if the active drawing has another scale than one of its chains, adapt them."""
        try:
            import bonsai.tool as tool
            import ifcopenshell.util.element as ue
            ctx = bpy.context
            if not tool.Ifc.get() or ctx.scene is None or ctx.scene.camera is None:
                return 1.0
            if ctx.mode != "OBJECT" or ctx.scene.BIMGeometryProperties.mode != "OBJECT":
                return 1.0
            drawing = tool.Drawing.get_document_props().get_active_drawing()
            if drawing is None:
                return 1.0
            new = ue.get_pset(drawing, "EPset_Drawing", "Scale")
            if not new or all(ps["Scale"] == new for _, ps in _chains_of_drawing(drawing)):
                return 1.0
            for window in ctx.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        region = next(r for r in area.regions if r.type == "WINDOW")
                        with ctx.temp_override(window=window, area=area, region=region):
                            bpy.ops.bonsai_btk.dimension_follow_scale()
                        return 1.0
        except Exception as error:
            print("BTK dimension chains:", error)
        return 1.0

    CLASSES = (
        BONSAI_BTK_OT_dimension_flip,
        BONSAI_BTK_OT_dimension_from_points,
        BONSAI_BTK_OT_dimension_create,
        BONSAI_BTK_OT_dimension_follow_scale,
    )

    def register():
        for cls in CLASSES:
            bpy.utils.register_class(cls)
        if not bpy.app.timers.is_registered(scale_watcher):
            bpy.app.timers.register(scale_watcher, first_interval=1.0, persistent=True)

    def unregister():
        if bpy.app.timers.is_registered(scale_watcher):
            bpy.app.timers.unregister(scale_watcher)
        for cls in reversed(CLASSES):
            bpy.utils.unregister_class(cls)
