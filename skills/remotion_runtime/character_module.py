"""同一份定妆参数 → 各 Remotion 工程里的角色组件。

应用画布与 lyric_mv / director 共用这里的模块模板；改接口只改这一处。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RIG_ROOT = Path(__file__).resolve().parents[1] / "remotion_runtime" / "src"


def role_slug(raw: Any, fallback: str = "hero") -> str:
    """角色 key：文件名与导出名都从它派生，保证同一个角色在各处叫法一致。"""
    s = re.sub(r"[^0-9a-zA-Z_-]+", "-", str(raw or "").strip()).strip("-").lower()
    return s or fallback


def component_name(role: str) -> str:
    """角色 key → 组件名：hero → Hero，friend-a → FriendA。"""
    parts = [p for p in re.split(r"[-_]+", role) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Character"


def character_module(spec: dict[str, Any], rig_import: str) -> str:
    """只给同一份参数换视角，不在镜头代码里另画一个人。"""
    return (
        "// 由 character_sheet 的定妆参数生成：几何在 RigCharacter，改角色请改参数\n"
        "import React from 'react';\n"
        f"import {{RigCharacter}} from '{rig_import}';\n\n"
        f"const SPEC: any = {json.dumps(spec, ensure_ascii=False, indent=2)};\n\n"
        "export const Character: React.FC<any> = (p) => <RigCharacter spec={SPEC} view=\"front\" {...p} />;\n"
        "export const CharacterSide: React.FC<any> = (p) => <RigCharacter spec={SPEC} view=\"side\" {...p} />;\n"
        "export const CharacterBack: React.FC<any> = (p) => <RigCharacter spec={SPEC} view=\"back\" {...p} />;\n"
    )


def install_character(project_src: Path, spec: dict[str, Any], filename: str = "Character.tsx") -> Path:
    """把骨架与角色适配器装进目标 Remotion 工程，返回组件路径。

    组件放在 scenes/generated/ 这类子目录时，import 的层级要按目录深度算，
    否则 webpack 会去 generated/ui 下找 RigCharacter。
    """
    project_src = Path(project_src)
    for name in ("types.ts", "rig.ts"):
        target_dir = project_src / "character"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / name).write_text((RIG_ROOT / "character" / name).read_text(encoding="utf-8"), encoding="utf-8")
    ui_dir = project_src / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)
    (ui_dir / "RigCharacter.tsx").write_text((RIG_ROOT / "ui" / "RigCharacter.tsx").read_text(encoding="utf-8"), encoding="utf-8")
    depth = len([part for part in Path(filename).parent.parts if part not in ("", ".")])
    rig_import = "../" * depth + "ui/RigCharacter"
    target = project_src / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(character_module(spec, rig_import), encoding="utf-8")
    return target


# 镜头代码里只认这三个名字；缺哪个就不注册哪个，避免编译失败
CHAR_EXPORTS = ("Character", "CharacterSide", "CharacterBack")


def cast_module(roles: list[str]) -> str:
    """把所有角色合成一个统一入口：镜头只 import 这一个模块。

    hero 仍然同时导出 Character / CharacterSide / CharacterBack，兼容旧镜头。
    """
    lines = ["// 由定妆参数自动生成：一个角色一个模块，这里统一改名导出", ""]
    for role in roles:
        name = component_name(role)
        base = f"./char-{role}"
        if role == "hero":
            # 老镜头 import 的是 Character / CharacterSide / CharacterBack，这里一并保留
            lines.append(
                f"export {{\n"
                f"  Character,\n  CharacterSide,\n  CharacterBack,\n"
                f"  Character as Hero,\n"
                f"  CharacterSide as HeroSide,\n"
                f"  CharacterBack as HeroBack,\n"
                f"}} from '{base}';"
            )
        else:
            lines.append(
                f"export {{\n"
                f"  Character as {name},\n"
                f"  CharacterSide as {name}Side,\n"
                f"  CharacterBack as {name}Back,\n"
                f"}} from '{base}';"
            )
    lines.append("")
    return "\n".join(lines)


def sync_char_registry(runtime_src: Path) -> list[str]:
    """按 scenes/generated/char-*.tsx 重写 charRegistry.tsx，返回注册的 key 列表。

    lyric_mv 与 styled 共用同一份已确认角色；多角色时每个角色都注册
    `role / role-side / role-back` 三个 key，定妆预览图按 key 取组件。
    """
    runtime_src = Path(runtime_src)
    scene_dir = runtime_src / "scenes"
    entries, imports, keys = [], [], []
    for f in sorted((scene_dir / "generated").glob("char-*.tsx")):
        role = f.stem[len("char-"):]
        if role == "cast" or not role:
            continue
        code = f.read_text(encoding="utf-8")
        have = [n for n in CHAR_EXPORTS
                if f"export const {n}" in code or f"export function {n}" in code]
        if not have:
            continue
        name = component_name(role)
        local = {n: f"{name}{n[len('Character'):]}" for n in have}
        imports.append(
            f"import {{{', '.join(f'{n} as {local[n]}' for n in have)}}} from './generated/{f.stem}';")
        for n in have:
            key = role if n == "Character" else f"{role}-{n[len('Character'):].lower()}"
            entries.append(f"'{key}': {local[n]}")
            keys.append(key)
    body = "import React from 'react';\n"
    body += ("\n".join(imports) + "\n\n" if imports else "")
    body += f"export const CHAR_REGISTRY: Record<string, React.FC> = {{{', '.join(entries)}}};\n"
    (scene_dir / "charRegistry.tsx").write_text(body, encoding="utf-8")
    return keys
