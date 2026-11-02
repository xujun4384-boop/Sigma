# -*- coding: utf-8 -*-
"""Blender 真 3D demo 场景（用 bpy 无头渲染）。

用法：
  blender.exe -b --factory-startup -noaudio --python demos.py -- <demo> <outdir> [W H fps frames samples]

demo ∈ {phone, logo, materials}
渲染输出为 PNG 序列（outdir/f_0001.png ...），再交 ffmpeg 合成 mp4。
"""
import sys
import os
import math

import bpy
from mathutils import Vector


# ────────────────────────── 通用工具 ──────────────────────────
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def activate(o):
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def set_in(node, key, val):
    if key in node.inputs:
        node.inputs[key].default_value = val


def principled(name, color, metallic=0.0, roughness=0.4, emission=None,
               emission_strength=0.0, transmission=0.0, ior=1.45, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_in(bsdf, "Base Color", (color[0], color[1], color[2], 1.0))
    set_in(bsdf, "Metallic", metallic)
    set_in(bsdf, "Roughness", roughness)
    set_in(bsdf, "IOR", ior)
    if transmission:
        set_in(bsdf, "Transmission Weight", transmission)
        set_in(bsdf, "Transmission", transmission)      # 旧版命名兜底
    if alpha < 1.0:
        set_in(bsdf, "Alpha", alpha)
        try:
            mat.blend_method = 'BLEND'
        except Exception:
            pass
    if emission:
        set_in(bsdf, "Emission Color", (emission[0], emission[1], emission[2], 1.0))
        set_in(bsdf, "Emission", (emission[0], emission[1], emission[2], 1.0))
        set_in(bsdf, "Emission Strength", emission_strength)
    return mat


def add_world(color=(0.02, 0.02, 0.03), strength=1.0):
    w = bpy.data.worlds.new("W")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    set_in(bg, "Color", (color[0], color[1], color[2], 1.0))
    set_in(bg, "Strength", strength)


def add_area(name, loc, rot, size, energy, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.size = size
    ld.color = color
    o = bpy.data.objects.new(name, ld)
    o.location = loc
    o.rotation_euler = rot
    bpy.context.scene.collection.objects.link(o)
    return o


def add_camera(loc, target=(0, 0, 0), focal=55):
    cd = bpy.data.cameras.new("Cam")
    cd.lens = focal
    o = bpy.data.objects.new("Cam", cd)
    o.location = loc
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.collection.objects.link(o)
    bpy.context.scene.camera = o
    return o


def add_cube(loc, scale, bevel=0.0, segments=4, name="Cube"):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    activate(o)
    bpy.ops.object.transform_apply(scale=True)
    if bevel > 0:
        m = o.modifiers.new("bev", 'BEVEL')
        m.width = bevel
        m.segments = segments
        try:
            m.limit_method = 'ANGLE'
        except Exception:
            pass
    return o


def setup_render(W, H, fps, frames, samples, outdir):
    # 新关键帧默认线性插值（Blender 4.4+/5.x 已移除 action.fcurves 直连，故不碰 fcurve）
    try:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
    except Exception:
        pass
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'
    scn.cycles.device = 'CPU'
    scn.cycles.samples = samples
    try:
        scn.cycles.use_denoising = True
    except Exception:
        pass
    try:
        scn.cycles.max_bounces = 8
        scn.cycles.transmission_bounces = 8
    except Exception:
        pass
    scn.render.resolution_x = W
    scn.render.resolution_y = H
    scn.render.resolution_percentage = 100
    scn.render.fps = fps
    scn.frame_start = 1
    scn.frame_end = frames
    scn.render.image_settings.file_format = 'PNG'
    os.makedirs(outdir, exist_ok=True)
    scn.render.filepath = os.path.join(outdir, "f_")
    return scn


def turntable(pivot, frames, turns=1.0):
    """绕 Z 轴匀速旋转（关键帧默认 LINEAR，见 setup_render）。"""
    pivot.rotation_euler = (0.0, 0.0, 0.0)
    pivot.keyframe_insert("rotation_euler", frame=1)
    pivot.rotation_euler = (0.0, 0.0, 2.0 * math.pi * turns)
    pivot.keyframe_insert("rotation_euler", frame=frames)


# ────────────────────────── Demo 1：写实旋转手机 ──────────────────────────
def scene_phone(outdir, W, H, fps, frames, samples):
    reset()
    setup_render(W, H, fps, frames, samples, outdir)
    add_world((0.012, 0.012, 0.018), 0.6)

    pivot = bpy.data.objects.new("Pivot", None)
    bpy.context.scene.collection.objects.link(pivot)

    body = add_cube((0, 0, 0), (0.36, 0.075, 0.72), bevel=0.030, segments=6, name="Body")
    body.data.materials.append(principled("titanium", (0.055, 0.06, 0.07), metallic=0.85, roughness=0.34))

    # 正面：发光屏幕（微内嵌）
    scr = add_cube((0, -0.041, 0.0), (0.325, 0.006, 0.665), bevel=0.022, segments=5, name="Screen")
    scr.data.materials.append(principled("screen", (0.01, 0.02, 0.06), roughness=0.15,
                                         emission=(0.07, 0.24, 0.85), emission_strength=1.25))

    # 背面：摄像头模组（贴在后表面、靠上左）+ 三颗镜头
    cam_mod = add_cube((0.15, 0.048, 0.20), (0.15, 0.03, 0.15), bevel=0.022, segments=5, name="CamMod")
    cam_mod.data.materials.append(principled("camglass", (0.02, 0.02, 0.03), metallic=0.6, roughness=0.12))
    for j, (dx, dz) in enumerate([(-0.035, 0.035), (-0.035, -0.035), (0.035, 0.035)]):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.026, depth=0.022, location=(0.15 + dx, 0.078, 0.20 + dz))
        lens = bpy.context.active_object
        lens.rotation_euler = (math.pi / 2, 0, 0)
        lens.data.materials.append(principled(f"lens{j}", (0.01, 0.01, 0.02), metallic=1.0, roughness=0.05))
        lens.parent = pivot

    # 地面（产品质感）
    floor = add_cube((0, 0, -0.47), (6.0, 6.0, 0.05), name="Floor")
    floor.data.materials.append(principled("floor", (0.02, 0.02, 0.025), metallic=0.3, roughness=0.35))

    for o in (body, scr, cam_mod):
        o.parent = pivot

    add_camera((0.95, -1.55, 0.52), (0.0, 0.0, 0.0), focal=58)
    add_area("key", (1.10, -1.30, 1.70), (math.radians(36), 0, math.radians(40)), 2.4, 420)
    add_area("fill", (-1.60, -0.90, 0.30), (math.radians(80), 0, math.radians(-60)), 2.8, 110, (0.72, 0.84, 1.0))
    add_area("rim", (0.50, 1.80, 1.30), (math.radians(-42), 0, math.radians(168)), 2.2, 300, (1.0, 0.9, 0.78))
    add_area("strip", (0.0, -1.6, 1.9), (math.radians(24), 0, 0), 3.2, 130, (1.0, 0.95, 0.9))

    turntable(pivot, frames, turns=1.0)


# ────────────────────────── Demo 2：3D 文字 Logo ──────────────────────────
def scene_logo(outdir, W, H, fps, frames, samples):
    reset()
    setup_render(W, H, fps, frames, samples, outdir)
    add_world((0.01, 0.01, 0.015), 0.6)

    bpy.ops.object.text_add(location=(0, 0, 0))
    txt = bpy.context.active_object
    txt.data.body = "SIGMA"
    txt.data.align_x = 'CENTER'
    txt.data.align_y = 'CENTER'
    txt.data.size = 1.0
    txt.data.extrude = 0.09
    txt.data.bevel_depth = 0.014
    txt.data.bevel_resolution = 4
    txt.rotation_euler = (math.radians(90), 0, 0)   # 文字默认躺在 XY 平面 → 立起来面向相机
    activate(txt)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    txt.data.materials.append(principled("gold", (1.0, 0.78, 0.32), metallic=1.0, roughness=0.18))

    floor = add_cube((0, 0, -0.75), (8.0, 8.0, 0.1), bevel=0.0, name="Floor")
    floor.data.materials.append(principled("floor", (0.03, 0.03, 0.04), metallic=0.25, roughness=0.45))

    add_camera((0.0, -5.4, 0.40), (0.0, 0.0, 0.0), focal=50)
    add_area("key", (1.6, -2.2, 2.4), (math.radians(42), 0, math.radians(36)), 3.0, 900)
    add_area("rim", (-2.0, 1.6, 1.6), (math.radians(-38), 0, math.radians(-150)), 3.0, 500, (0.7, 0.82, 1.0))
    add_area("strip", (0.0, -3.0, -0.4), (math.radians(96), 0, 0), 4.0, 120, (1.0, 0.85, 0.7))

    pivot = bpy.data.objects.new("Pivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    txt.parent = pivot
    turntable(pivot, frames, turns=0.25)


# ────────────────────────── Demo 3：材质静物（金属/玻璃/哑光）──────────────────────────
def scene_materials(outdir, W, H, fps, frames, samples):
    reset()
    setup_render(W, H, fps, frames, samples, outdir)
    add_world((0.02, 0.02, 0.025), 0.8)

    floor = add_cube((0, 0, -1.02), (9.0, 9.0, 0.1), name="Floor")
    floor.data.materials.append(principled("floor", (0.05, 0.05, 0.06), metallic=0.15, roughness=0.45))

    objs = []

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.45, location=(-2.4, 0, -0.55))
    s = bpy.context.active_object
    s.data.materials.append(principled("chrome", (0.95, 0.96, 1.0), metallic=1.0, roughness=0.03))
    objs.append(s)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.45, location=(-1.2, 0, -0.55))
    g = bpy.context.active_object
    g.data.materials.append(principled("glass", (1.0, 1.0, 1.0), roughness=0.02, transmission=1.0, ior=1.5))
    objs.append(g)

    bpy.ops.mesh.primitive_torus_add(location=(0.0, 0, -0.55), major_radius=0.33, minor_radius=0.135)
    t = bpy.context.active_object
    t.data.materials.append(principled("gold", (1.0, 0.76, 0.3), metallic=1.0, roughness=0.2))
    objs.append(t)

    c = add_cube((1.2, 0, -0.55), (0.60, 0.60, 0.60), bevel=0.06, segments=5, name="MatteCube")
    c.data.materials.append(principled("matte", (0.85, 0.22, 0.22), metallic=0.0, roughness=0.75))
    objs.append(c)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.45, location=(2.4, 0, -0.55))
    e = bpy.context.active_object
    e.data.materials.append(principled("emissive", (0.05, 0.9, 0.8), roughness=0.4,
                                       emission=(0.05, 0.9, 0.8), emission_strength=6.0))
    objs.append(e)

    for i, o in enumerate(objs):
        o.rotation_euler = (0.0, 0.0, 0.0)
        o.keyframe_insert("rotation_euler", frame=1)
        o.rotation_euler = (0.0, 0.0, 2.0 * math.pi * (1.0 + 0.12 * i))
        o.keyframe_insert("rotation_euler", frame=frames)

    add_camera((0.0, -7.4, 1.7), (0.0, 0.0, -0.45), focal=52)
    add_area("key", (3.2, -4.2, 4.2), (math.radians(40), 0, math.radians(38)), 4.0, 1600)
    add_area("fill", (-4.2, -2.8, 1.4), (math.radians(72), 0, math.radians(-55)), 4.0, 380, (0.7, 0.8, 1.0))
    add_area("top", (0.0, 0.0, 5.2), (0, 0, 0), 5.0, 700)


# ────────────────────────── 入口 ──────────────────────────
DEMOS = {"phone": scene_phone, "logo": scene_logo, "materials": scene_materials}


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if len(args) < 2:
        print("usage: --python demos.py -- <demo> <outdir> [W H fps frames samples]")
        return
    demo = args[0]
    outdir = os.path.abspath(args[1])   # Blender 里相对路径会落到盘根，必须绝对化
    W = int(args[2]) if len(args) > 2 else 720
    H = int(args[3]) if len(args) > 3 else 720
    fps = int(args[4]) if len(args) > 4 else 24
    frames = int(args[5]) if len(args) > 5 else 72
    samples = int(args[6]) if len(args) > 6 else 32
    fn = DEMOS.get(demo)
    if not fn:
        print(f"unknown demo: {demo}")
        return
    fn(outdir, W, H, fps, frames, samples)
    print(f">>> rendering {demo} {W}x{H} {frames}f samples={samples} -> {outdir}")
    bpy.ops.render.render(animation=True)
    print(">>> done")


main()
