"""Headless Blender layouts for 〈拿下頭套的人〉. Source scene: 動畫版 classroom_anim_p1.blend (opened read-only, never saved over).
Run: blender.exe -b <classroom_anim_p1.blend> --python render_layouts.py -- camera_plan_v1.json <out_dir> [save_blend]
Raw Blender renders have the window on the wrong side; the PNGs are mirrored afterwards by make_sheet.py (project rule:
students face the board, windows on the students' left)."""
import json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
out_dir = Path(argv[1]); out_dir.mkdir(parents=True, exist_ok=True)
save_blend = argv[2] if len(argv) > 2 else None
sc = bpy.context.scene

def parts(prefix):
    return [o for o in sc.objects if o.name.startswith(prefix) and not any(k in o.name for k in ("desk", "chair", "bag", "book"))]

TEACHER = parts("LR3_teacher_")
KIDS = {"ahe": parts("LR3_ahe_"), "xiaowen": parts("LR3_S03_"), "afu": parts("LR3_S05_")}
STUDENTS = {}
for o in sc.objects:
    p = o.name.split("_")
    if len(p) > 2 and p[1].startswith("S") and p[1][1:].isdigit() and p[1] not in ("S03", "S05") \
            and not any(k in o.name for k in ("desk", "chair", "book", "bag")):
        STUDENTS.setdefault(p[1], []).append(o)
for o in sc.objects:
    if o.name.startswith("LR3_mother"):
        o.hide_render = True

# --- new props (PV_ prefix) ---
def box(name, size, loc, color):
    me = bpy.data.meshes.new(name)
    import bmesh
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob)
    ob.scale = size; ob.location = loc; ob.color = color
    return ob

PROPS = {}
PROPS["arm3"] = [box("PV_afu_arm3", (0.08, 0.32, 0.08), (-0.62, 0.48, 0.80), (1, 0.15, 0.15, 1))]
PROPS["bottle"] = [box("PV_afu_bottle", (0.08, 0.08, 0.22), (-0.70, 0.42, 0.91), (0.2, 0.9, 1, 1))]
PROPS["cookie"] = [box("PV_cookie", (0.07, 0.07, 0.015), (-0.14, -0.72, 1.5), (0.95, 0.7, 0.25, 1))]
PROPS["hood"] = [box("PV_hood_in_hand", (0.2, 0.2, 0.2), (0, 0, 0), (0.78, 0.62, 0.42, 1))]
PROPS["notebook"] = [box("PV_xw_notebook", (0.2, 0.14, 0.02), (2.05, -0.80, 0.80), (1, 0.4, 0.6, 1))]
fl = []
import random
random.seed(7)
for i in range(18):
    x = random.uniform(-2.6, 2.3); y = random.uniform(-1.6, 4.6); z = random.uniform(1.75, 2.75)
    fl.append(box(f"PV_float_{i:02d}", (0.22, 0.16, 0.04), (x, y, z), (0.95, 0.85, 0.3, 1)))
    fl[-1].rotation_euler = (random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6), random.uniform(0, 3))
PROPS["float"] = fl

BASE = {o.name: (o.location.copy(), o.rotation_euler.copy(), o.scale.copy()) for o in sc.objects}
DEFAULT_COL = {o.name: tuple(o.color) for o in sc.objects}

def reset():
    for o in sc.objects:
        if o.name in BASE:
            o.location, o.rotation_euler, o.scale = (v.copy() for v in BASE[o.name])
            o.color = DEFAULT_COL[o.name]
        o.hide_render = o.name.startswith(("PV_", "LR3_mother"))

def move(objs, d=(0, 0, 0), rot_z=0.0):
    pivot = sum((o.location for o in objs), Vector()) / len(objs)
    R = Matrix.Rotation(rot_z, 4, "Z")
    for o in objs:
        o.location = pivot + (R @ (o.location - pivot)) + Vector(d)
        o.rotation_euler.z += rot_z

def tint(objs, c):
    for o in objs:
        if any(k in o.name for k in ("torso", "sleeve", "waist")):
            o.color = c

def grow(objs, k=1.3):
    pivot = sum((o.location for o in objs), Vector()) / len(objs); pivot.z = 0
    for o in objs:
        o.location = pivot + (o.location - pivot) * k
        o.scale = o.scale * k

# teacher spots: (x, y, facing rot about +y default)
SPOTS = {"desk": (0.6, -2.62, 0.0), "board": (-0.8, -2.74, math.pi), "board_face": (-0.8, -2.74, 0.0),
         "aisle_walk": (-0.14, 1.6, 0.0), "at_afu": (-0.14, 0.95, -math.pi / 2), "aisle_face": (-0.14, 0.95, 0.0), "aisle_front": (-0.14, 0.95, math.pi),
         "clock": (2.85, -2.45, math.pi), "clock_turn": (2.75, -2.45, 0.55), "solo": (0.6, -2.62, 0.0), "door": (3.25, -2.3, 0.7)}

def pose(s):
    t = s.get("teacher", "desk")
    hood = s.get("hood", "on")  # on (animated layer) / hand (real layer, hood held) / off
    if t == "hidden":
        for o in TEACHER: o.hide_render = True
    else:
        x, y, r = SPOTS[t]
        move(TEACHER, (x - 0.6, y + 2.62, 0.0 if t in ("desk", "solo") else 0.12), r)
        for o in TEACHER:
            if "head" in o.name or "hair" in o.name:
                o.color = (0.78, 0.62, 0.42, 1) if hood == "on" else ((0.86, 0.68, 0.56, 1) if "head" in o.name else (0.03, 0.03, 0.03, 1))
            elif any(k in o.name for k in ("torso", "arm", "legs")):
                o.color = (0.05, 0.05, 0.05, 1)
        if hood == "hand":
            h = PROPS["hood"][0]; h.hide_render = False
            tor = next(o for o in TEACHER if "torso" in o.name)
            fwd = Matrix.Rotation(r, 4, "Z") @ Vector((0, 0.32, 0))
            h.location = tor.location + fwd + Vector((0, 0, 0.12))
    tint(KIDS["ahe"], (0.25, 0.45, 0.95, 1)); tint(KIDS["xiaowen"], (1, 0.45, 0.7, 1)); tint(KIDS["afu"], (1, 0.55, 0.1, 1))
    if s.get("adults"):
        for k in KIDS.values(): grow(k, 1.3)
    if s.get("kids_hidden"):
        for k in KIDS.values():
            for o in k: o.hide_render = True
    if s.get("students") == "hidden":
        for v in STUDENTS.values():
            for o in v: o.hide_render = True
    if s.get("xiaowen") == "hand_up":
        arm = [o for o in KIDS["xiaowen"] if o.name.endswith(("sleeve1", "forearm1"))]
        for o in arm: o.location.z += 0.45; o.location.y += 0.18
    for p in s.get("props", []):
        for o in PROPS[p]: o.hide_render = False
    if s.get("room") == "hidden":  # travel shots: figure only, framing reference
        for o in sc.objects:
            if o.type == "MESH" and o not in TEACHER and not o.name.startswith("PV_hood"):
                o.hide_render = True

def camera(name, c):
    cam = bpy.data.objects.get("PV_CAM_" + name)
    if cam is None:
        cam = bpy.data.objects.new("PV_CAM_" + name, bpy.data.cameras.new("PV_CAM_" + name))
        sc.collection.objects.link(cam)
    cam.location = Vector(c["loc"])
    cam.rotation_euler = (Vector(c["target"]) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = c.get("lens", 28); cam.data.clip_start = 0.05
    return cam

sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.color_type = "OBJECT"; sc.display.shading.light = "STUDIO"
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = 960, 540
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGB"
cams = {n: camera(n, c) for n, c in spec["cameras"].items()}
for s in spec["setups"]:
    reset(); pose(s)
    sc.camera = cams[s["camera"]]
    sc.render.filepath = str(out_dir / f"{s['id']}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", s["id"])
reset()
if save_blend:
    sc.render.resolution_x, sc.render.resolution_y = 1536, 864
    bpy.ops.wm.save_as_mainfile(filepath=save_blend, copy=True)
    print("SAVED", save_blend)
