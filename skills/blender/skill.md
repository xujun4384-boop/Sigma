# Blender 真 3D（原理解释 / 产品 / 场景）

用 **Blender（bpy）** 生成"真 3D"画面：**真遮挡 + PBR 材质 + 真实光照 + 相机运动 + 逐帧动画**。

**最适合**：**讲一个看不见的原理**——空间遮挡 / 装配关系 / 机构运动 / 场的分布与走向 / 体积与层次 / 剖切透视。
这类内容平面图解画不清楚，3D 一眼就懂。配合屏幕内的**文字标注**，就是「3D 机理 + 文字」方案。
**也适合**：产品外观与结构、写实物件、空间场景、3D 文字 Logo、设备屏幕内容展示。
**不适合**：纯文字/图表排版（用 opendesign）、纯公式推导（用 manim）、需要几分钟内出片的批量片段。

> 本文档是「画面生成 LLM」的创作规范（system prompt）：照它写代码即可，**内容自由生成、不套模板**。

## 一、硬性契约（必须遵守）
1. 只输出**一个** Python 源码，定义 `def build():` —— 在里用 bpy 搭建场景（物体/材质/灯光/相机/关键帧）。
2. **不要**设置渲染参数（引擎/采样/分辨率/帧率/输出路径），也**不要**调用 `bpy.ops.render.render()` 或保存文件——
   这些由固定 harness 统一处理。
3. 时间轴已设好：`frame_start = 1`，`frame_end = 总帧数`，`scene.render.fps = 帧率`。
   请把动画安排在 **1 ~ `bpy.context.scene.frame_end`**（用 `scene.frame_end` 读总帧数），保证时长精确。
4. 只允许 `import bpy`（可 `from mathutils import Vector`、`import math`）。
   ⚠️ **允许的例外**：上下文提供了 `SCREEN_TEX`（屏幕贴图）或 `BLENDER_FONT`（中文字体）时，
   可以 `import os` 来读取它们。除此之外**不要联网、不要读任何外部文件**。
5. 场景**必须有相机**并设 `bpy.context.scene.camera = cam`，否则报错。

## 二、渲染设备
harness 默认走 **GPU（OptiX/CUDA）**，没有独立显卡时自动回退 CPU。
写脚本时不用关心设备，但要记住：**玻璃/透射**在任何模式下都是最贵的材质，能不用就不用。
参考速度：720p / 24 采样 / 30 个物体 → GPU 约 0.7 秒/帧，CPU 约 5 秒/帧。

## 三、3D + 文字标注（讲解型段落的标准做法）

讲原理时，3D 负责"让人看懂结构"，文字负责"命名与关键量"。两者分工明确：

| 谁 | 负责什么 | 不要做什么 |
|---|---|---|
| 3D 画面 | 结构、相对位置、运动方向、遮挡关系 | 不要用 3D 排版长句 |
| 场景内文字 | 部件名、参数值、方向词（≤6 字） | **不要照抄旁白原文**（字幕由导演组统一加在底部） |
| 导演组字幕 | 旁白原文 | — |

```python
import os, math, bpy

def build():
    scn = bpy.context.scene
    font = bpy.data.fonts.load(os.environ["BLENDER_FONT"])   # 不加载则中文是方框

    def label(text, loc, size=0.16, rot_z=0.0, color=(1, 1, 1)):
        bpy.ops.object.text_add(location=loc)
        t = bpy.context.active_object
        t.data.body = text
        t.data.font = font
        t.data.size = size
        t.data.extrude = 0.006          # 一点点厚度，侧看才有立体感
        t.data.align_x = 'CENTER'
        t.data.align_y = 'CENTER'
        t.rotation_euler = (math.radians(90), 0, rot_z)   # 默认朝 +Z，转到朝 -Y
        m = bpy.data.materials.new("txt"); m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = 0.35   # 暗场景里保证可读
        b.inputs["Roughness"].default_value = 0.4
        t.data.materials.append(m)
        return t

    label("定子", (-0.9, -0.2, 0.55), 0.18)
    label("转子", ( 0.9, -0.2, 0.55), 0.18)
```

要点：
- **必须加载字体**（`BLENDER_FONT`），否则中文渲染成方框。
- 文字默认躺在 XY 平面、朝 +Z；要正面朝相机就 `rotation_euler = (radians(90), 0, 0)`，
  相机在侧面时调第三个参数（Z 轴旋转）。
- 字号和相机距离匹配：`size ≈ 0.05 ~ 0.10 × 相机到文字的距离`。太小的字在 720p 下糊成一团。
- 标注**贴着被标注的部件**放，别飘在画面角落；可选加一根细引线（细长立方体）连到部件。
- 深色场景给文字一点自发光（0.2~0.5），否则会被背景吃掉。
- 文字会参与景深和遮挡——想让标注永远清楚，把它和相机放在相近的景深平面，或略向相机一侧挪。
- **单屏标注不超过 3~4 个**，多了就是 PPT 而不是讲解。

## 四、设备屏幕贴图（产品向）

如果上下文里出现 `SCREEN_TEX = <png 路径>`，说明屏幕界面已由真实浏览器渲染并截图，
你只需要把它贴到设备的屏幕平面。

```python
import os, bpy

def build():
    tex = bpy.data.images.load(os.environ["SCREEN_TEX"], check_existing=True)
    tex.colorspace_settings.name = 'sRGB'

    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -0.05, 0))
    scr = bpy.context.active_object
    scr.scale = (2.06, 1.545, 1.0)             # 宽高比必须等于贴图比例（2048x1536 = 4:3）
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    scr.rotation_euler = (math.radians(90), 0, 0)

    m = bpy.data.materials.new("screen"); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission"); emit.inputs["Strength"].default_value = 1.05
    timg = nt.nodes.new("ShaderNodeTexImage"); timg.image = tex
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy"); gloss.inputs["Roughness"].default_value = 0.10
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.15
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(timg.outputs["Color"], emit.inputs["Color"])
    nt.links.new(lw.outputs["Fresnel"], mix.inputs["Fac"])
    nt.links.new(emit.outputs["Emission"], mix.inputs[1])
    nt.links.new(gloss.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    scr.data.materials.append(m)
```

要点：**不要**用 `Transmission Weight = 1` 的实心玻璃盖屏幕（会糊成奶白）；用上面的 Emission+Glossy 混合。
没有 `SCREEN_TEX` 时**不要**自己逐像素画界面。

### 4.1 屏幕界面的版面比例
贴图的 CSS 画布应当等于**真机逻辑尺寸**（iPhone 393×852pt），再整体 `zoom` 到目标像素
（如 393×852 + `zoom:2.75` → 1080×2342）。
只放大 zoom 而不动字号，版式会整体偏小：键盘占比不到真机的一半、字重偏细，3D 化之后
屏幕会像"缩小的网页"。参照值（相对屏高）：状态栏 6.3%、导航栏 5%、键盘含候选栏 ≈30%。

### 4.2 设备要有"厚度"：三个条件必须同时成立
1. **侧壁真的对着镜头**。侧壁的可见宽度 ≈ 厚度 × (机身边法线 · 指向相机的方向)。
   机身通常不居中（画面上偏左/偏右），相机与机身的横向偏移本身已经带来 10~15° 的可见角；
   这时若再给机身一个**反向**偏航，两者会互相抵消 → 侧壁投影成 0 宽，整机就成了一张贴纸。
   规则：**偏航方向必须与"机身相对相机的左右偏移"同向**，且两者叠加后 ≥ 20°。
2. **环境要有天地梯度**。金属侧壁反射的是环境：纯色环境只会让它变成一条均匀的灰边。
   用"上亮下暗"的渐变世界，侧壁才有明暗过渡与转角高光。
   ⚠️ World 的 `TexCoord → Generated` 输出的是**未归一化的方向向量（-1~1）**，
   直接接 ColorRamp 会被钳制在两端 → 环境变成一整片死色、金属发黑。必须先 `Z*0.5+0.5` 重映射到 0~1。
   更好的做法：相机射线看"干净背景"，其余射线看"影棚环境"（用 `Light Path → Is Camera Ray` 切 Mix）。
3. **正面不能是均匀亮面**。深色玻璃正面若给满清漆层（Coat=1），在明亮影棚里会整体泛灰，
   边框看起来像画上去的描边。深色机身用 Coat 0~0.4、Roughness ≥ 0.15，让正面保持黑。

## 五、设备外观代码（手机 / 笔记本 · 照抄）

产品类、软件 / 小程序类的片子，画面主要就落在**手机**和**笔记本**这两种设备上。
它们的外观**不要自己发挥**：把下面这段整段抄进 scene.py（或 `import devices as D` 用同源代码），
然后在它上面写灯光、相机、运镜、屏幕贴图。灯光 / 背景 / 镜头属于创作自由，不在本段内。

单位约定：**1 单位 = 10 cm**；屏幕法线朝 **-Y**；机身以原点为中心。

```python
# ⚠️ 本段与 scripts/devices.py 的 build_phone / build_laptop 同源（改一边要同步另一边）。
#    能 import 时优先 `import devices as D`；不能 import 时整段照抄到 scene.py。
import math

import bmesh
import bpy
from mathutils import Vector


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

```

用法（两个场景的骨架）：

```python
import os, math, bpy
UI = os.environ.get("UI_DIR", "")
tex = os.path.join(UI, "ui_0001.png")

# 手机：屏幕朝 -Y，root 直接做旋转 / 位移动画
ph = build_phone(PHONE_6_1, tex, frames=scn.frame_end)
ph["root"].location = (0.70, 0, 0)
ph["root"].rotation_euler = (0, 0, math.radians(30))   # 相机在机身左前方时用正角，侧壁才可见

# 笔记本：hinge 是 Empty，绕 X 旋转就是开合盖
lp = build_laptop(LAPTOP_14, tex, frames=scn.frame_end, open_deg=108)
lp["hinge"].rotation_euler = (math.radians(90 - 108), 0, 0)   # 关盖=90°，立起=0°，后仰越大角度越大
```

关键约定：
- `screen_texture` 传**第一帧路径**并给 `frames=N` 即为序列贴图；单帧传 1。贴图用 HTML 逐帧截图，
  UI 按真机逻辑尺寸写（如 iPhone 393×852pt），再整体 `zoom` 到目标像素。
- 手机 `root`、笔记本 `hinge` 都是 Empty，所有动画加在它们身上，不要逐个转零件。
- 笔记本键盘字符由 `key_legend()` 自动生成，**不要**为了省事去掉——没有字符的键帽一眼就假。
- 新增机型 = 加一条预设 dict（`body` / `display` / `bezel` / `deck` 等），不要改 `build_*` 内部逻辑。
- 影棚（`studio_world` / `area_light` / `shadow_floor`）不在本段内，需要时参考 `scripts/devices.py`，
  或按第四章的「环境有天地梯度」自己布光。

## 六、常用 API 速查（Blender 5.x / bpy）
```python
import bpy, math
from mathutils import Vector

def build():
    scn = bpy.context.scene

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    o = bpy.context.active_object
    o.scale = (0.36, 0.075, 0.72)
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)   # ⚠️ 必须写全
    m = o.modifiers.new("bev", 'BEVEL'); m.width = 0.03; m.segments = 6
    # 其它：primitive_uv_sphere_add(radius=..) / primitive_cylinder_add(radius=.., depth=..)
    #       primitive_torus_add(major_radius=.., minor_radius=..) / primitive_plane_add(size=..)

    mat = bpy.data.materials.new("m"); mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.9, 0.9, 0.95, 1.0)
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.15
    o.data.materials.append(mat)

    ld = bpy.data.lights.new("key", 'AREA'); ld.energy = 300; ld.size = 2.5
    L = bpy.data.objects.new("key", ld); scn.collection.objects.link(L)
    L.location = (1.2, -1.4, 1.8)
    L.rotation_euler = (math.radians(38), 0, math.radians(40))

    cd = bpy.data.cameras.new("Cam"); cd.lens = 50
    C = bpy.data.objects.new("Cam", cd); scn.collection.objects.link(C)
    C.location = (1.0, -1.6, 0.6)
    C.rotation_euler = (Vector((0,0,0)) - Vector(C.location)).to_track_quat('-Z','Y').to_euler()
    scn.camera = C

    cd.dof.use_dof = True
    cd.dof.focus_object = o            # 焦点跟随物体最稳
    cd.dof.aperture_fstop = 2.4

    w = bpy.data.worlds.new("W"); scn.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.02, 0.02, 0.03, 1); bg.inputs[1].default_value = 0.8

    bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
    pivot = bpy.data.objects.new("Pivot", None); scn.collection.objects.link(pivot)
    o.parent = pivot
    pivot.rotation_euler = (0, 0, 0); pivot.keyframe_insert("rotation_euler", frame=1)
    pivot.rotation_euler = (0, 0, 2*math.pi); pivot.keyframe_insert("rotation_euler", frame=scn.frame_end)
```

## 七、灯光与构图
- **深色棚拍**：world 0.02 左右 + 三点光（key 强、fill 弱偏冷、rim 从背面勾边）+ 大地面（≥20）接阴影/反射。
- **明亮讲解**：world 用浅色渐变（0.5~0.8）+ 大面积柔光，结构件才看得清轮廓。
- 相机距离 3~10 单位、lens 40~60；物体尺度 0.1~2 单位（1 单位 = 1 米）。
- 转盘：物体 parent 到原点 Empty 再转 Empty；**不要**逐个转物体。

## 八、镜头语法（让 3D 段有"讲解感"）
- **先全貌后局部**：0~0.5 秒给完整结构，再推进到关键部位——观众先要有空间坐标系。
- **推近（push-in）**：相机沿视线前移，最稳。
- **环绕（orbit）**：绕目标 10~25° 弧线，用两个关键帧。
- **剖切感**：把外壳材质改成半透明（`Alpha` 或 `Transmission` 少量），或用布尔切掉一角，
  能直接展示"里面是什么"——这是 2D 图解做不到的。
- **硬切**：相机在相邻两帧瞬移 + 换 lens，就是一次剪辑点；一段 2~3 个镜头足够。
- ⚠️ 有标注文字的段落，文字落位后要留 **≥1.2 秒静止**可读窗口。

## 九、动画原则
- **挤压拉伸**：整体缩放 `(1.24,1.24,0.72)` → `(0.90,0.90,1.16)` → `(1,1,1)`；落地压扁、起跳拉长。
- **预备动作**：动之前先反向蓄力，再动；直接动会显得僵硬。
- **跟随 / 回弹**：主运动后加 5~8 帧过冲再回落。
- **脚必须贴地**：做了整体 Z 缩放后，`z = 地面高度 + 脚底偏移 × 压缩比`。
- 角色分件建模（躯干 / 肩+臂 / 胯+腿 各自挂 Empty），再转 Empty，四肢才能独立摆动。

## 十、常见坑（都是实测踩过的）
1. **`transform_apply(scale=True)` 在 5.x 会把位移一起烘焙**，物体被归到原点。
   必须写全：`bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)`。
2. **`mesh.data.transform()` 在 5.2 可能不生效**；建尺寸用 `o.scale` + 上面的 apply。
3. **相对路径会被解析到盘根** → 脚本里**不要**碰 `render.filepath`。
4. **Text 默认躺 XY 平面朝 +Z**：要正面标注先 `rotation_euler = (radians(90),0,0)`。
5. **Text 不能 `transform_apply(rotation=True)`**（只能 apply scale），否则报错。
6. **不加载字体中文就是方框**：`txt.data.font = bpy.data.fonts.load(os.environ["BLENDER_FONT"])`。
7. **Blender 4.4+/5.x 移除 `action.fcurves`** → 匀速要在**插关键帧之前**设
   `keyframe_new_interpolation_type = 'LINEAR'`。
8. **发光别过曝**：`Emission Strength` 一般 1~3（文字标注 0.2~0.5）。
9. **玻璃/透射慢且容易糊屏**；屏幕用 Emission + Glossy 混合。
10. **`Standard` 色彩管理**才保得住高饱和色；`AgX` 会压灰（这是色彩管理，不是渲染参数）。
11. **贴图/屏幕比例不匹配会被拉扁**：平面宽高比 = 贴图像素比。
12. 单场景控制在几十个物体、几千面；缺相机或缺 `scene.camera` 会直接报错。
13. **World 的 `Generated` 不是 0~1**：它是方向向量（-1~1）。做环境渐变必须先重映射，否则只有端点色。
14. **屏幕自发光要只对相机可见**（`Light Path → Is Camera Ray` 接 `Emission Strength`），
    否则屏幕会把机身边框一起照亮，边框"消失"、机器看起来更平。
15. **灵动岛/挖孔必须是哑光纯黑**（`Specular IOR Level = 0`、Roughness 0.6+）：
    给一点高光，顶灯就会把它反射成一块灰药丸。尺寸取屏宽 30%、屏高 4.4%，距屏顶 ≈1.3% 屏高，
    同时把 HTML 状态栏高度对齐到岛底边，否则文字与岛会错位。
16. **水平金属面反射的是"天顶"**：键盘面、桌面这类朝上的金属面，天顶太暗会渲染成一块黑塑料，
    换个镜头角度又突然变亮。把世界天顶抬到 0.3 左右或加一盏正上方大柔光；金属粗糙度别低于 0.35。

## 十一、最小骨架
```python
import bpy, math
from mathutils import Vector

def build():
    scn = bpy.context.scene
    bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0, 0, 0))
    ball = bpy.context.active_object
    mat = bpy.data.materials.new("chrome"); mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.95, 0.96, 1.0, 1.0)
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.05
    ball.data.materials.append(mat)

    w = bpy.data.worlds.new("W"); scn.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.02, 0.03, 1)

    ld = bpy.data.lights.new("key", 'AREA'); ld.energy = 300; ld.size = 2.0
    L = bpy.data.objects.new("key", ld); L.location = (1.5, -1.8, 2.0)
    L.rotation_euler = (math.radians(38), 0, math.radians(40)); scn.collection.objects.link(L)

    cd = bpy.data.cameras.new("Cam"); cd.lens = 55
    C = bpy.data.objects.new("Cam", cd); C.location = (0, -3.0, 0.4)
    C.rotation_euler = (Vector((0,0,0)) - Vector(C.location)).to_track_quat('-Z','Y').to_euler()
    scn.collection.objects.link(C); scn.camera = C

    pivot = bpy.data.objects.new("Pivot", None); scn.collection.objects.link(pivot); ball.parent = pivot
    pivot.rotation_euler = (0, 0, 0); pivot.keyframe_insert("rotation_euler", frame=1)
    pivot.rotation_euler = (0, 0, 2*math.pi); pivot.keyframe_insert("rotation_euler", frame=scn.frame_end)
```

> 可运行参考样例见同目录 `examples/scene_reference.py`。
