# -*- coding: utf-8 -*-
"""Blender 场景渲染 harness（部门内部固定运行时）。

契约：用户脚本（scene.py）只需定义 `def build():`，用 bpy 搭建场景
（物体 / 材质 / 灯光 / 相机 / 关键帧）。本 harness 负责：
  - 清空默认场景、设好时间轴（脚本可读 scene.frame_end 安排动画，保证时长精确）
  - 统一渲染设置（Cycles CPU / 采样 / 分辨率 / 帧率 / PNG 序列 / 输出目录）
  - 渲染动画并打印标记

由 scripts/renderer.py 调用：
  blender.exe -b --factory-startup -noaudio --python harness.py -- <scene.py> <outdir> W H fps frames samples
"""
import importlib.util
import os
import sys

import bpy

argv = sys.argv
_args = argv[argv.index("--") + 1:] if "--" in argv else []
if len(_args) < 2:
    print("[harness] usage: -- <scene.py> <outdir> W H fps frames samples")
    sys.exit(1)

scene_path = os.path.abspath(_args[0])
outdir = os.path.abspath(_args[1])
W = int(_args[2]) if len(_args) > 2 else 1280
H = int(_args[3]) if len(_args) > 3 else 720
fps = int(_args[4]) if len(_args) > 4 else 24
frames = int(_args[5]) if len(_args) > 5 else 48
samples = int(_args[6]) if len(_args) > 6 else 24

# 1) 干净场景 + 时间轴（脚本据此安排动画；总帧数=目标时长×帧率，保证成片时长精确）
bpy.ops.wm.read_factory_settings(use_empty=True)
_scene = bpy.context.scene
_scene.frame_start = 1
_scene.frame_end = max(2, frames)
_scene.render.fps = fps

# 2) 载入并执行用户场景脚本
_spec = importlib.util.spec_from_file_location("sigma_user_scene", scene_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
if not hasattr(_mod, "build"):
    raise RuntimeError("scene.py 必须定义 def build(): 来搭建场景")
_mod.build()

# 3) 统一渲染设置（脚本不要自己设这些）
_scene.render.engine = 'CYCLES'
_scene.cycles.device = 'CPU'
_scene.cycles.samples = samples
try:
    _scene.cycles.use_denoising = True
except Exception:
    pass
_scene.render.resolution_x = W
_scene.render.resolution_y = H
_scene.render.resolution_percentage = 100
_scene.render.image_settings.file_format = 'PNG'
os.makedirs(outdir, exist_ok=True)
_scene.render.filepath = os.path.join(outdir, "f_")

if _scene.camera is None:
    raise RuntimeError("场景缺少相机：请在 build() 里创建相机并设 scene.camera")

print(f"[harness] rendering {W}x{H} {frames}f @{fps}fps samples={samples} -> {outdir}")
bpy.ops.render.render(animation=True)
print("[harness] done")
