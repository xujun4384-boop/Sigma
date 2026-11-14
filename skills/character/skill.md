# character - 角色定妆（参数化骨架）

## 这是什么
角色不是一张画，是一组参数。体型系数 + 配色 + 发型 + 服装决定「长什么样」，
几何由前端骨架展开，所以同一个角色在任何视角、姿态、表情、画风下都是同一个人。

定妆 = 让用户先认这个人，再拿去拍镜头。

## 用法
```
# 只有主角
character_sheet(spec={...}, title="MV 主角 · 阿岚", note="为什么这样定", project="<项目名>")

# 主角 + 配角：一次确认整组
character_sheet(
  spec={...},                                    # 主角
  cast=[{"role": "friend-a", "spec": {...}},
        {"role": "friend-b", "spec": {...}}],    # 配角，最多 6 个
  project="<项目名>")
```

调用后画布会出对照图：**只有主角**时是五格参数网格（正面站 / 侧面站 / 背面站 / 坐姿伸手 / 倾斜惊讶）；
**带配角**时每个角色一格正面站姿，一屏看完谁是谁。
**工具会阻塞到你（用户）点「确认这版」或「要求调整」为止。**

返回值里的 `verdict`：
- `confirmed` — 用户认可，`spec` 就是定稿，后续画面都用这一份
- `revise` — 用户提了修改要求，按 `note` 改参数后**重新调用**，不要跳过确认
- `timeout` — 15 分钟内没确认，按待定稿处理并如实告知用户

## 参数
```json
{
  "name": "角色名",
  "proportions": {
    "headRatio": 0.24,
    "legRatio": 0.32,
    "shoulderRatio": 0.92,
    "hipRatio": 1.04,
    "belly": 0.5,
    "armRatio": 1.0
  },
  "colors": {
    "skin": "#f6d3b8", "hair": "#4a3a33", "cloth": "#8fa4bd",
    "apron": "#f1e7d4", "ink": "#4a4038"
  },
  "hair": "short",
  "outfit": "shirt",
  "glasses": false,
  "wrinkle": 0
}
```

- `proportions` 全是相对总高的系数：头越高越幼态，腿越长越成熟，`belly` 控制体宽。
- `colors` 给主色即可，`*Shade` 不填会按主色自动压暗。
- `hair`：`bun` 盘发 / `short` 短发 / `long` 长发 / `baldTop` 谢顶只剩两鬓。
- `outfit`：`apron` 围裙 / `dress` 连衣裙 / `shirt` 衬衫。
- `wrinkle`：老年角色的皱纹强度 0~1。

## 配角（cast）
- 每项 `{role, spec}`：`role` 是小写英文/连字符的角色 key（`friend-a`、`mom`…），**不能用 hero**，不能重复；
  `spec` 与主角参数同构。
- 角色靠**发型 / 服装 / 配色 / 体型 / 眼镜 / 皱纹**区分（骨架没有独立五官参数，换脸做不到）。
- 上限 6 个；超过会被忽略并在返回值里提示。

## 和其他技能的关系
- `lyric_mv` / `director` 涉及人物的段落，**先定妆、用户确认后再开拍**。
- 确认后的整组参数存在 `video_work/<project>/characters.json`
  （主角同时保留 `character.json`，供只认单角色的老流程使用），
  镜头里的 `Hero / FriendA …` 读的就是这一份，不要另画一个人。
- 只改颜色/发型这类小调整，也走这个工具重出一版让用户看，不要口头描述改动。
