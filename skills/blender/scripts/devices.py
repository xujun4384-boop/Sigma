# -*- coding: utf-8 -*-
"""参数化设备模型库（手机 / 笔记本）。

单位约定：1 单位 = 10 cm；设备屏幕法线朝 -Y，机身以原点为中心。
设计约束：
  - 外形只由物理尺寸参数推导，没有任何品牌 / 型号分支；
  - 屏幕内容一律从外部贴图（HTML 逐帧截图）进来，本库不画界面；
  - 每个 build_* 返回 dict：root(Empty) / screen / parts，便于外层做动画与镜头。

用法（scene.py，由 harness.py 提供本目录到 sys.path）：
    import devices as D
    dev = D.build_laptop(D.LAPTOP_14, screen_texture=SEQUENCE_FIRST_FRAME, frames=180)
    D.studio_world()
    D.aim(cam, (0, -1.0, 1.6))

⚠️ skill.md 第五节内嵌了本文件「设备外观」部分的完整副本（供无法 import 时整段照抄）；
   改动 build_phone / build_laptop / 预设 / 几何后，要同步更新那边。
"""
import math

import bmesh
import bpy
from mathutils import Vector


# ═══════════════════════════ 基础工具 ═══════════════════════════

def set_in(node, key, val):
    """安全设置节点输入（不同版本可能缺项）。"""
    if key in node.inputs:
        node.inputs[key].default_value = val


def mat(name, color, metallic=0.0, roughness=0.4, spec=0.5, coat=0.0, coat_rough=0.03):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    set_in(b, "Base Color", (color[0], color[1], color[2], 1.0))
    set_in(b, "Metallic", metallic)
    set_in(b, "Roughness", roughness)
    set_in(b, "Specular IOR Level", spec)
    if coat > 0:
        set_in(b, "Coat Weight", coat)
        set_in(b, "Coat Roughness", coat_rough)
    return m


def empty(name, loc=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None)
    o.location = loc
    bpy.context.scene.collection.objects.link(o)
    if parent is not None:
        o.parent = parent
    return o


def aim(obj, target):
    """让 -Z 轴指向 target（相机/聚光灯通用）。"""
    d = Vector(target) - Vector(obj.location)
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


# ═══════════════════════════ 几何：圆角板 ═══════════════════════════

def rounded_pts(w, h, r, seg):
    """平面内的圆角矩形轮廓（逆时针，中心在原点）。"""
    r = min(r, w * 0.5, h * 0.5)
    cx, cz = w * 0.5 - r, h * 0.5 - r
    corners = [(cx, cz, 0.0), (-cx, cz, math.pi * 0.5),
               (-cx, -cz, math.pi), (cx, -cz, math.pi * 1.5)]
    pts = []
    for ox, oz, a0 in corners:
        for i in range(seg + 1):
            a = a0 + (math.pi * 0.5) * i / seg
            pts.append((ox + r * math.cos(a), oz + r * math.sin(a)))
    return pts


def rounded_slab(name, w, h, d, r, seg, mats, chamfer=0.004, plane='XZ'):
    """圆角矩形板：平面轮廓 (w×h) 沿法线挤出厚度 d，边缘倒角。

    plane='XZ' → 轮廓在 XZ 平面、厚度沿 Y（竖立的机身 / 屏盖）
    plane='XY' → 轮廓在 XY 平面、厚度沿 Z（平放的底座）
    mats=(负向面材质, 正向面材质, 侧面材质)
    """
    pts = rounded_pts(w, h, r, seg)
    if plane == 'XZ':
        def P(u, v, dep):
            return (u, dep, v)
        neg_dir = Vector((0, -1, 0))
    elif plane == 'XY':
        def P(u, v, dep):
            return (u, v, dep)
        neg_dir = Vector((0, 0, -1))
    else:
        raise ValueError("plane must be 'XZ' or 'XY'")

    bm = bmesh.new()
    vn = [bm.verts.new(P(u, v, -d * 0.5)) for (u, v) in pts]
    vp = [bm.verts.new(P(u, v, +d * 0.5)) for (u, v) in pts]
    n = len(pts)
    f_neg = bm.faces.new(vn)
    f_pos = bm.faces.new(list(reversed(vp)))
    sides = []
    for i in range(n):
        j = (i + 1) % n
        sides.append(bm.faces.new([vn[i], vn[j], vp[j], vp[i]]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()

    for f, want in ((f_neg, neg_dir), (f_pos, -neg_dir)):
        if f.normal.dot(want) < 0:
            bmesh.ops.reverse_faces(bm, faces=[f])

    f_neg.material_index = 0
    f_pos.material_index = 1
    for f in sides:
        f.material_index = 2

    rim = set()
    for f in (f_neg, f_pos):
        rim.update(f.edges)
    if chamfer > 0 and rim:
        bmesh.ops.bevel(bm, geom=list(rim), offset=chamfer, segments=3,
                        affect='EDGES', clamp_overlap=True, profile=0.62)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    for m in mats:
        me.materials.append(m)
    return obj


def rounded_face(name, w, h, r, seg, material, thickness_axis=None):
    """带 UV 的圆角矩形平面（屏幕 / 触控板），UV 按包围盒归一化。"""
    pts = rounded_pts(w, h, r, seg)
    bm = bmesh.new()
    vs = [bm.verts.new((x, 0.0, z)) for (x, z) in pts]
    f = bm.faces.new(vs)
    bm.normal_update()
    if f.normal.y > 0:
        bmesh.ops.reverse_faces(bm, faces=[f])
    uv = bm.loops.layers.uv.new("UVMap")
    for loop in f.loops:
        co = loop.vert.co
        loop[uv].uv = ((co.x + w * 0.5) / w, (co.z + h * 0.5) / h)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    me.materials.append(material)
    return obj


def flat_rect(name, w, h, material, plane='XY'):
    """无倒角的矩形面（键盘底槽等），平面朝向由 plane 决定。"""
    bm = bmesh.new()
    if plane == 'XY':
        co = [(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)]
    else:
        co = [(-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2)]
    vs = [bm.verts.new(p) for p in co]
    bm.faces.new(vs)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    me.materials.append(material)
    return obj


def box(name, loc, size, material, bevel=0.0, seg=2):
    """带倒角的方块（按键 / 侧键）。size=(x,y,z)。"""
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        m = o.modifiers.new("bev", 'BEVEL')
        m.width = bevel
        m.segments = seg
        try:
            m.limit_method = 'ANGLE'
        except Exception:
            pass
    o.data.materials.append(material)
    return o


# ═══════════════════════════ 材质：屏幕 ═══════════════════════════

def screen_material(first_frame, frames=1, name="screen",
                    roughness=0.22, coat=0.4, coat_rough=0.05):
    """屏幕材质：贴图自发光 + 玻璃高光。

    自发光用 Light Path → Is Camera Ray 门控：只对相机可见。
    否则屏幕会像灯一样照亮机身边框，边框"消失"、整机看起来更平。
    """
    img = bpy.data.images.load(first_frame, check_existing=False)
    if frames > 1:
        img.source = 'SEQUENCE'
    try:
        img.colorspace_settings.name = 'sRGB'
    except Exception:
        pass

    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = 'Linear'
    tex.extension = 'CLIP'
    iu = tex.image_user
    iu.frame_duration = max(1, frames)
    iu.frame_start = 1
    iu.frame_offset = 0
    iu.use_auto_refresh = True
    iu.use_cyclic = False

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    set_in(bsdf, "Base Color", (0.004, 0.004, 0.005, 1.0))
    set_in(bsdf, "Metallic", 0.0)
    set_in(bsdf, "Roughness", roughness)
    set_in(bsdf, "Coat Weight", coat)
    set_in(bsdf, "Coat Roughness", coat_rough)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])

    lpath = nt.nodes.new("ShaderNodeLightPath")
    nt.links.new(lpath.outputs["Is Camera Ray"], bsdf.inputs["Emission Strength"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.blend_method = 'OPAQUE'
    return m


# ═══════════════════════════ 影棚：世界 / 灯 / 地面 ═══════════════════════════

def studio_world(horizon=0.62, top=0.10, floor=0.045, backdrop=(0.88, 0.99),
                 strength=1.0, backdrop_rgb=None):
    """两层世界：相机射线看干净背景，其余射线看"上亮下暗"的影棚环境。

    只给一层均匀色，金属侧壁会反射成一整片死白/死灰，厚度就没了。
    ⚠️ 世界里的 Generated 是未归一化的方向向量（-1~1），必须重映射到 0~1，
    否则 ColorRamp 的取值全被钳在端点。

    backdrop_rgb：给定时用作**整块背景底色**（线性空间的三元组），
    用来对齐全片画布色（深色片就用深色底），此时 backdrop 的(下,上)两色参数不再生效。
    """
    scn = bpy.context.scene
    w = bpy.data.worlds.new("StudioWorld")
    scn.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputWorld")
    mix = nt.nodes.new("ShaderNodeMixShader")
    lp = nt.nodes.new("ShaderNodeLightPath")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])

    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    remap = nt.nodes.new("ShaderNodeMath")
    remap.operation = 'MULTIPLY_ADD'
    remap.inputs[1].default_value = 0.5
    remap.inputs[2].default_value = 0.5
    nt.links.new(sep.outputs["Z"], remap.inputs[0])

    env = nt.nodes.new("ShaderNodeBackground")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(remap.outputs[0], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    els[0].position = 0.0
    els[0].color = (floor * 0.9, floor, floor * 1.2, 1)
    els[1].position = 1.0
    els[1].color = (top, top * 1.02, top * 1.15, 1)
    for pos, v in ((0.40, 0.22), (0.50, horizon), (0.56, 1.0), (0.64, 0.30)):
        e = els.new(pos)
        e.color = (v, v * 1.01, v * 1.07, 1)
    nt.links.new(ramp.outputs["Color"], env.inputs["Color"])
    set_in(env, "Strength", strength)
    nt.links.new(env.outputs["Background"], mix.inputs[1])

    bd = nt.nodes.new("ShaderNodeBackground")
    bramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(remap.outputs[0], bramp.inputs["Fac"])
    b = bramp.color_ramp.elements
    if backdrop_rgb is not None:
        # 画布底色对齐：同色相做极轻的上下渐变，避免大平色带来的色带
        c = backdrop_rgb
        b[0].position = 0.0
        b[0].color = (c[0] * 0.94, c[1] * 0.94, c[2] * 0.94, 1)
        b[1].position = 1.0
        b[1].color = (c[0] * 1.06, c[1] * 1.06, c[2] * 1.06, 1)
    else:
        b[0].position = 0.30
        b[0].color = (backdrop[0], backdrop[0] * 1.01, backdrop[0] * 1.06, 1)
        b[1].position = 0.80
        b[1].color = (backdrop[1], backdrop[1], 1.0, 1)
    nt.links.new(bramp.outputs["Color"], bd.inputs["Color"])
    set_in(bd, "Strength", 1.0)
    nt.links.new(bd.outputs["Background"], mix.inputs[2])
    return w


def area_light(name, loc, rot_deg, energy, size, color=(1, 1, 1), shape=None, size_y=0.0):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.color = color
    if shape == 'RECTANGLE':
        ld.shape = 'RECTANGLE'
        ld.size = size
        ld.size_y = size_y
    else:
        ld.size = size
    L = bpy.data.objects.new(name, ld)
    L.location = loc
    L.rotation_euler = tuple(math.radians(a) for a in rot_deg)
    bpy.context.scene.collection.objects.link(L)
    return L


def shadow_floor(z, center=(0.0, 0.0), size=12):
    """只接收阴影的地面（不出现实物面）。center=(x, y)。"""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(center[0], center[1], z))
    o = bpy.context.active_object
    o.name = "ShadowCatcher"
    try:
        o.is_shadow_catcher = True
    except Exception:
        o.data.materials.append(mat("shadow", (0.86, 0.87, 0.92), roughness=0.9))
    return o


# ═══════════════════════════ 预设（按物理尺寸命名，不含品牌）═══════════════════════════

# 6.1 英寸直板机：71.5 × 148 × 9.5 mm（单位换算 1 单位 = 100 mm）
PHONE_6_1 = dict(
    body=(0.715, 1.480, 0.095),
    corner_ratio=0.137,       # 圆角半径 / 机身宽
    bezel_ratio=0.031,        # 黑边 / 机身宽
    island=dict(width_ratio=0.313, height_ratio=0.044, gap_ratio=0.0126),
    # 侧键 (朝向 ±X, 中心 z 占比, 长度占比)
    buttons=((1, 0.203, 0.118), (-1, 0.243, 0.071),
             (-1, 0.142, 0.071), (-1, 0.338, 0.039)),
)

# 14 英寸笔电：312.6 × 221.2 × 11.2 mm，屏 302 × 196 mm（2026 年的薄机身比例）
LAPTOP_14 = dict(
    body=(3.126, 2.212, 0.112),
    display=(3.020, 1.964),
    bezel=(0.033, 0.050, 0.090),   # 左右 / 上 / 下
    corner_ratio=0.028,
    lid_thickness=0.040,
    hinge_len=0.86,                # 转轴长度 / 机身宽
    deck=dict(keyboard=(2.620, 0.980),   # 键区宽深
              key_pitch=0.190, key_height=0.016, key_gap=0.024,
              back_margin=0.140, trackpad_gap=0.150,
              trackpad=(1.280, 0.720)),
    notch=dict(width_ratio=0.062, height_ratio=0.019),
)

PHONE_PRESETS = {"6.1": PHONE_6_1}
LAPTOP_PRESETS = {"14": LAPTOP_14}


# ═══════════════════════════ 手机 ═══════════════════════════

def build_phone(preset=PHONE_6_1, screen_texture=None, frames=1,
                face_color=(0.006, 0.006, 0.008),
                rim_color=(0.84, 0.85, 0.87),
                back_color=(0.30, 0.31, 0.34),
                name="Phone"):
    W, H, D = preset["body"]
    r_body = min(preset["corner_ratio"] * W, min(W, H) * 0.5)
    bezel = preset["bezel_ratio"] * W
    w_scr, h_scr = W - bezel * 2, H - bezel * 2
    r_scr = max(0.0, r_body - bezel * 0.92)

    root = empty(name + "Root")
    m_face = mat(name + "_front_glass", face_color, metallic=0.0, roughness=0.20, spec=0.22)
    m_back = mat(name + "_back_glass", back_color, metallic=0.25, roughness=0.28)
    m_rim = mat(name + "_rim", rim_color, metallic=1.0, roughness=0.14)

    body = rounded_slab(name + "Body", W, H, D, r_body, 10,
                        mats=(m_face, m_back, m_rim), chamfer=D * 0.053, plane='XZ')
    body.parent = root

    parts = [body]
    screen = None
    if screen_texture:
        sm = screen_material(screen_texture, frames, name=name + "_screen")
        screen = rounded_face(name + "Screen", w_scr, h_scr, r_scr, 10, sm)
        screen.location = (0, -D * 0.5 - 0.0006, 0)
        screen.parent = root
        parts.append(screen)

    isl = preset.get("island")
    if isl:
        iw = isl["width_ratio"] * w_scr
        ih = isl["height_ratio"] * h_scr
        m_island = mat(name + "_island", (0.006, 0.006, 0.007),
                       metallic=0.0, roughness=0.70, spec=0.0)
        island = rounded_slab(name + "Island", iw, ih, ih * 0.13, ih * 0.5, 8,
                              mats=(m_island, m_island, m_island),
                              chamfer=ih * 0.02, plane='XZ')
        island.location = (0, -D * 0.5 - ih * 0.072,
                           h_scr * 0.5 - isl["gap_ratio"] * h_scr - ih * 0.5)
        island.parent = root
        parts.append(island)

    m_btn = mat(name + "_btn", rim_color, metallic=1.0, roughness=0.34)
    for (side, zr, hr) in preset.get("buttons", ()):
        z = (zr - 0.5) * H
        h = hr * H
        b = box(name + "Btn", (side * (W * 0.5 - 0.0055), 0, z),
                (D * 0.126, D * 0.253, h), m_btn, bevel=h * 0.05, seg=3)
        b.parent = root
        parts.append(b)

    return dict(root=root, body=body, screen=screen, parts=parts,
                size=(W, H, D), screen_size=(w_scr, h_scr))


# ═══════════════════════════ 笔记本 ═══════════════════════════

def _key_rows():
    """标准 14.5u 键位：(标签, 宽度u)。标签为空 = 不印字（方向键/空格这类只画符号的键）。"""
    rows = [
        [(c, 1.0) for c in "`1234567890-="] + [("delete", 1.5)],
        [("tab", 1.5)] + [(c, 1.0) for c in "qwertyuiop"] + [("[", 1.0), ("]", 1.0), ("\\", 1.0)],
        [("caps", 1.75)] + [(c, 1.0) for c in "asdfghjkl"] + [(";", 1.0), ("'", 1.0), ("return", 1.75)],
        [("shift", 2.25)] + [(c, 1.0) for c in "zxcvbnm"] + [(",", 1.0), (".", 1.0), ("/", 1.0), ("shift", 2.25)],
        [("fn", 1.0), ("ctrl", 1.0), ("opt", 1.0), ("cmd", 1.25), ("", 5.0),
         ("cmd", 1.25), ("opt", 1.0), ("", 0.75), ("", 0.75), ("", 0.75), ("", 0.75)],
    ]
    return rows


def key_legend(label, x, y, z, key_w, material):
    """键帽上的字符：贴着一个朝 +Z 的文字对象，字号按可用宽度自适应。"""
    if not label:
        return None
    bpy.ops.object.text_add(location=(x, y, z))
    o = bpy.context.active_object
    o.name = "Legend"
    d = o.data
    d.body = label
    d.align_x = 'CENTER'
    d.align_y = 'CENTER'
    d.extrude = 0.0
    # 字宽 ≈ 0.62×字号；真机字符约占键宽 14%，这里略微放大到 ~18% 以保证 1080p 下可辨
    d.size = min(0.040, key_w * 0.80 / (len(label) * 0.62))
    o.data.materials.append(material)
    return o


def build_laptop(preset=LAPTOP_14, screen_texture=None, frames=1,
                 open_deg=108.0,
                 alu_color=(0.72, 0.73, 0.76),
                 alu_metallic=0.9, alu_roughness=0.38,
                 key_color=(0.045, 0.045, 0.05),
                 name="Laptop"):
    W, D, T = preset["body"]
    dw, dh = preset["display"]
    b_side, b_top, b_bot = preset["bezel"]
    lid_t = preset["lid_thickness"]
    r = min(preset["corner_ratio"] * W, min(W, D) * 0.5)
    lid_h = dh + b_top + b_bot

    m_alu = mat(name + "_alu", alu_color, metallic=alu_metallic, roughness=alu_roughness)
    m_alu_dark = mat(name + "_alu_dark", tuple(c * 0.82 for c in alu_color),
                     metallic=alu_metallic, roughness=alu_roughness + 0.04)
    m_black = mat(name + "_black_glass", (0.005, 0.005, 0.006),
                  metallic=0.0, roughness=0.20, spec=0.22)
    m_key = mat(name + "_key", key_color, metallic=0.0, roughness=0.52, spec=0.3)
    m_leg = mat(name + "_legend", (0.88, 0.89, 0.91), metallic=0.0, roughness=0.55)
    _lb = m_leg.node_tree.nodes["Principled BSDF"]
    set_in(_lb, "Emission Color", (1.0, 1.0, 1.0, 1.0))
    set_in(_lb, "Emission Strength", 0.45)
    m_well = mat(name + "_keywell", (0.02, 0.02, 0.022), metallic=0.0, roughness=0.7)
    m_pad = mat(name + "_trackpad", (0.30, 0.31, 0.33),
                metallic=0.6, roughness=0.30)

    root = empty(name + "Root")

    # ── 底座：底面/顶面铝，侧面铝 ──
    base = rounded_slab(name + "Base", W, D, T, r, 10,
                        mats=(m_alu_dark, m_alu, m_alu), chamfer=T * 0.13, plane='XY')
    base.location = (0, -D * 0.5, T * 0.5)
    base.parent = root

    # ── 键盘面（刻槽 + 键帽）──
    deck = preset["deck"]
    kw, kd = deck["keyboard"]
    kh = deck["key_height"]
    ky0 = -deck.get("back_margin", 0.14)
    well = flat_rect(name + "KeyWell", kw + 0.04, kd + 0.04, m_well, plane='XY')
    well.location = (0, ky0 - kd * 0.5, T + 0.0002)
    well.parent = root

    rows = _key_rows()
    total_u = max(sum(u for _, u in row) for row in rows)
    unit = kw / total_u
    row_h = kd / len(rows)
    for row in rows:
        row_u = sum(u for _, u in row)
        x = -kw * 0.5 + (kw - row_u * unit) * 0.5
        for label, u in row:
            w = u * unit - deck["key_gap"]
            k = box(name + "Key",
                    (x + u * unit * 0.5, ky0 - row_h * 0.5, T + kh * 0.34),
                    (w, row_h - deck["key_gap"], kh), m_key,
                    bevel=kh * 0.22, seg=2)
            k.parent = root
            lg = key_legend(label, x + u * unit * 0.5, ky0 - row_h * 0.5,
                            T + kh * 0.84 + 0.0008, w, m_leg)
            if lg:
                lg.parent = root
            x += u * unit
        ky0 -= row_h

    tw, td = deck["trackpad"]
    pad = rounded_slab(name + "Trackpad", tw, td, 0.004, 0.030, 8,
                       mats=(m_pad, m_pad, m_pad), chamfer=0.0012, plane='XY')
    pad.location = (0, ky0 - deck.get("trackpad_gap", 0.14) - td * 0.5, T - 0.0016)
    pad.parent = root

    # ── 转轴 + 屏盖 ──
    # 屏盖局部 +Z 向上、屏幕朝 -Y；关盖=+90°，立起=0°，后仰越多角度越大。
    # 转轴放在"盖厚度的中面"高度：开盖时盖底贴着键盘面，关盖时也不至于陷进底座。
    hinge = empty(name + "Hinge", (0, 0, T + lid_t * 0.5), parent=root)
    hinge.rotation_euler = (math.radians(90.0 - open_deg), 0, 0)

    lid = rounded_slab(name + "Lid", W, lid_h, lid_t, r, 10,
                       mats=(m_black, m_alu, m_alu), chamfer=lid_t * 0.16, plane='XZ')
    lid.location = (0, -lid_t * 0.5, lid_h * 0.5)
    lid.parent = hinge

    hl = preset.get("hinge_len", 0.86) * W
    hg = rounded_slab(name + "HingeBar", hl, 0.045, 0.045, 0.022, 8,
                      mats=(m_alu_dark, m_alu_dark, m_alu_dark),
                      chamfer=0.004, plane='XZ')
    hg.location = (0, 0.010, T * 0.9)
    hg.parent = root

    parts = [base, well, pad, lid, hg]

    # ── 屏幕 ──
    screen = None
    if screen_texture:
        sm = screen_material(screen_texture, frames, name=name + "_screen")
        screen = rounded_face(name + "Screen", dw, dh, 0.016, 10, sm)
        screen.location = (0, -lid_t - 0.0012, b_bot + dh * 0.5)
        screen.parent = hinge
        parts.append(screen)

    # ── 刘海（可选）──
    nt = preset.get("notch")
    if nt:
        nw = nt["width_ratio"] * dw
        nh = nt["height_ratio"] * dh
        notch = rounded_face(name + "Notch", nw, nh, nw * 0.16, 8, m_black)
        notch.location = (0, -lid_t - 0.0022, b_bot + dh - nh * 0.5)
        notch.parent = hinge
        parts.append(notch)

    return dict(root=root, base=base, lid=lid, hinge=hinge, screen=screen,
                parts=parts, size=(W, D, T), lid_height=lid_h)
