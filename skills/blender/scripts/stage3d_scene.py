# -*- coding: utf-8 -*-
"""参数化 3D 产品镜头：设备 / 动作 / 机位全部来自环境变量，不含任何题材或品牌分支。

上游（product_director 等）只需准备好屏幕贴图序列帧并设置环境变量，再交给 harness 渲染：
  S3D_DEVICE     laptop | phone
  S3D_ACTION     open | scroll | push | tilt | static
  S3D_AZIMUTH    机位方位角（度）：0=正面，正=绕到左侧，负=绕到右侧
  S3D_ELEVATION  机位仰角（度）：0=平视，正=俯视
  S3D_ANGLE      方位/仰角的命名简写（azimuth/elevation 缺席时才用）
  S3D_UI_DIR     屏幕贴图目录（ui_0001.png …）
  S3D_UI_FRAMES  贴图帧数（1 = 静态单帧，整段复用同一张）
  S3D_OPEN_DEG   笔记本开盖角度（默认 108）
  S3D_SHIFT      横向构图偏移 -1..1（负数把设备推到画面右侧，给左侧标题留白）
  S3D_SHIFT_Y    纵向构图偏移 -1..1（正数把设备推向画面下方）
  S3D_FIT        取景安全边距系数（1.0=刚好塞满，越大越小）
  S3D_BG         全片画布底色（#RRGGBB）：背景与影棚亮度都跟它走

机位不是写死的坐标：先量出设备的真实包围点，再按镜头视锥反解拍摄距离，
所以换任何尺寸的机型都不用手调相机。
"""
import math
import os

import bpy
from mathutils import Vector

import devices as D

DEVICE = os.environ.get("S3D_DEVICE", "laptop").strip().lower()
ACTION = os.environ.get("S3D_ACTION", "push").strip().lower()
ANGLE = os.environ.get("S3D_ANGLE", "three-quarter").strip().lower()
UI_DIR = os.environ.get("S3D_UI_DIR", "")
UI_FRAMES = int(os.environ.get("S3D_UI_FRAMES") or 1)
OPEN_DEG = float(os.environ.get("S3D_OPEN_DEG") or 108.0)
SHIFT = float(os.environ.get("S3D_SHIFT") or 0.0)
SHIFT_Y = float(os.environ.get("S3D_SHIFT_Y") or 0.0)
FIT = float(os.environ.get("S3D_FIT") or 1.22)
BG_HEX = os.environ.get("S3D_BG", "").strip()


def _parse_hex(s):
    """#RRGGBB / #RGB → (r,g,b) 0~1（sRGB）。解析不了返回 None。"""
    t = (s or "").strip().lstrip("#")
    if len(t) == 3:
        t = "".join(ch * 2 for ch in t)
    if len(t) != 6:
        return None
    try:
        return tuple(int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None


def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

# 命名简写只作为缺省值；真正的机位由 azimuth/elevation 连续决定。
ANGLE_AZEL = {
    "three-quarter": (29.0, 16.5),
    "front": (6.0, 7.0),
    "side": (54.0, 11.5),
}

# 镜头运动全部由「起止机位 + 起止距离」六个连续量决定（S3D_AZ0/AZ1/EL0/EL1/D0/D1），
# 这里只保留一个缺省值表，供没传数字时兜底；动作名本身不参与运镜。
DEFAULT_MOVE = {
    "open": (3.0, 7.0, 1.00, 0.95),
    "scroll": (2.0, 1.0, 1.00, 0.96),
    "push": (1.5, 1.5, 1.00, 0.90),
    "tilt": (14.0, 0.0, 1.00, 0.99),
    "static": (0.8, 0.5, 1.00, 0.985),
}

LENS = 50.0
SENSOR = 36.0


def _world_verts(objs):
    out = []
    for o in objs:
        if o.type != 'MESH':
            continue
        mw = o.matrix_world
        for c in o.bound_box:
            out.append(mw @ Vector(c))
    return out


def _basis(direction):
    """由「相机相对目标的方向」建立相机的右/上基向量。

    right 必须是**相机自己的右**（f × worldUp，f=-d）；如果顺手写成 d × worldUp，
    得到的其实是相机左，构图偏移与仰角偏移会整体镜像，标题在左时设备反而往左让。
    """
    d = Vector(direction).normalized()
    f = -d
    right = f.cross(Vector((0, 0, 1)))
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()
    up = right.cross(f).normalized()
    return d, right, up


def _dir_from_azel(az_deg, el_deg):
    """方位角/仰角 → 相机相对设备的方向向量（屏幕朝 -Y，所以 0° 在 -Y 方向）。"""
    a = math.radians(az_deg)
    e = math.radians(el_deg)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def _fit_distance(verts, center, d, right, up, tan_h, tan_v):
    """反解能把所有点收进画面的最近距离，返回 (距离, 所需半宽半高比例)。"""
    best = 0.0
    for v in verts:
        rel = v - center
        depth = rel.dot(d)
        best = max(best,
                   depth + abs(rel.dot(right)) / tan_h,
                   depth + abs(rel.dot(up)) / tan_v)
    return best


def build():
    scn = bpy.context.scene
    frames = scn.frame_end
    # 机位是自己按缓出曲线算好再打关键帧的，这里要线性插值，否则叠加 Bezier 会变成双缓动
    bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
    try:
        scn.view_settings.view_transform = 'Standard'
        scn.view_settings.look = 'None'
    except Exception:
        pass

    # 底色跟全片画布色走：深色片就深底 + 暗环境（金属靠灯打边缘高光），
    # 浅色片就浅底 + 亮环境。环境亮度按底色的相对亮度连续过渡，不做"深/浅"两套分支。
    bg = _parse_hex(BG_HEX)
    if bg:
        lum = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]
        env_k = 0.10 + 0.90 * lum
        backdrop_rgb = tuple(_srgb_to_linear(c) for c in bg)
    else:
        env_k, backdrop_rgb = 1.0, None
    # 环境别太亮：金属侧壁反射的是"地平线带"，带太亮会烧成一条白边，机身就读不出厚度
    D.studio_world(horizon=0.45 * env_k, top=0.24 * env_k, floor=0.12 * env_k,
                   backdrop=(0.90, 0.99), backdrop_rgb=backdrop_rgb)

    tex = os.path.join(UI_DIR, "ui_0001.png")
    if not os.path.isfile(tex):
        raise RuntimeError("缺少屏幕贴图: %s" % tex)

    if DEVICE == "phone":
        dev = D.build_phone(D.PHONE_6_1, screen_texture=tex, frames=UI_FRAMES)
        hinge = None
    else:
        dev = D.build_laptop(D.LAPTOP_14, screen_texture=tex, frames=UI_FRAMES,
                             open_deg=OPEN_DEG)
        hinge = dev["hinge"]

    root = dev["root"]
    bpy.context.view_layer.update()

    # ── 量真实包围盒（用完全打开的姿态，保证整段都不出画）──
    verts = _world_verts(dev["parts"])
    mn = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
    mx = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
    center = (mn + mx) * 0.5
    radius = max(0.05, (mx - mn).length * 0.5)
    floor_z = mn.z

    # ── 灯：按包围半径等比布光，能量随距离平方走，换机型不用重调 ──
    def rig(name, direction, k_energy, k_size, color=(1.0, 1.0, 1.0)):
        dn = Vector(direction).normalized()
        dist = radius * 3.0
        L = D.area_light(name, center + dn * dist, (0, 0, 0),
                         k_energy * 16.5 * dist * dist, k_size * radius, color)
        D.aim(L, center)
        return L

    rig("key", (0.62, -0.72, 0.55), 1.00, 1.60, (1.0, 0.99, 0.97))
    rig("fill", (-0.78, -0.52, 0.18), 0.30, 1.85, (0.88, 0.91, 1.0))
    rig("rim", (0.30, 0.86, 0.42), 0.75, 1.15, (0.94, 0.96, 1.0))
    rig("top", (0.0, -0.18, 0.98), 0.55, 2.20, (1.0, 0.99, 0.98))

    D.shadow_floor(floor_z - 0.003, center=(center.x, center.y), size=radius * 10)

    # ── 相机：先按视锥反解基准距离，再按动作推拉 / 绕行 ──
    cd = bpy.data.cameras.new("Cam")
    cd.lens = LENS
    cam = bpy.data.objects.new("Cam", cd)
    scn.collection.objects.link(cam)
    scn.camera = cam

    # ── 机位：起止方位/仰角/距离全部是环境变量给的连续量，不存在"第几种运镜" ──
    az_def, el_def = ANGLE_AZEL.get(ANGLE, ANGLE_AZEL["three-quarter"])
    mv = DEFAULT_MOVE.get(ACTION, DEFAULT_MOVE["push"])
    az1 = float(os.environ.get("S3D_AZ1") or os.environ.get("S3D_AZIMUTH") or az_def)
    el1 = float(os.environ.get("S3D_EL1") or os.environ.get("S3D_ELEVATION") or el_def)
    az0 = float(os.environ.get("S3D_AZ0") or (az1 - mv[0]))
    el0 = float(os.environ.get("S3D_EL0") or (el1 - mv[1]))
    d0k = float(os.environ.get("S3D_D0") or mv[2])
    d1k = float(os.environ.get("S3D_D1") or mv[3])

    # 取景按起止两个方向都要装得下，否则绕行途中会出画
    tan_h = (SENSOR * 0.5) / LENS
    tan_v = tan_h * float(scn.render.resolution_y) / float(scn.render.resolution_x)
    b1, r1, u1 = _basis(_dir_from_azel(az1, el1))
    b0, r0, u0 = _basis(_dir_from_azel(az0, el0))
    fit = max(_fit_distance(verts, center, b1, r1, u1, tan_h, tan_v),
              _fit_distance(verts, center, b0, r0, u0, tan_h, tan_v))
    base_dist = fit * FIT          # FIT 是安全边距（竖长设备也不会顶满画面）

    # 构图偏移必须加在"看向的目标点"上：相机被 TRACK_TO 锁着目标，
    # 只挪相机等于原地转向，设备会一直钉在画面正中（挪相机是无效的）。
    offset = (r1 * (SHIFT * 2.0 * base_dist * tan_h)
              + u1 * (SHIFT_Y * 2.0 * base_dist * tan_v))

    target = bpy.data.objects.new("CamTarget", None)
    scn.collection.objects.link(target)
    target.location = center + offset
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'

    cd.lens = LENS
    # 缓出：起步快、落位稳（产品片基本都是"推过去停住"，不是匀速）
    for f in (1, max(2, int(frames * 0.45)), max(2, frames)):
        p = 0.0 if frames <= 1 else (f - 1) / float(max(1, frames - 1))
        u = 1.0 - (1.0 - p) ** 2
        pos = center + _dir_from_azel(az0 + (az1 - az0) * u,
                                      el0 + (el1 - el0) * u) * (base_dist * (d0k + (d1k - d0k) * u))
        cam.location = pos
        cam.keyframe_insert("location", frame=f)

    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 5.6
    cd.dof.focus_distance = base_dist * d1k

    # ── 开盖：只有笔记本有这个动作 ──
    if hinge is not None and ACTION == "open":
        for deg, f in ((OPEN_DEG * 0.52, 1),
                       (OPEN_DEG * 0.97, int(frames * 0.42)),
                       (OPEN_DEG * 1.015, int(frames * 0.55)),
                       (OPEN_DEG, int(frames * 0.70))):
            hinge.rotation_euler = (math.radians(90.0 - deg), 0, 0)
            hinge.keyframe_insert("rotation_euler", frame=f)
