"""
docx_editor skill - 编辑 Word 文档 (.docx)

提供 edit_docx 工具，采用"读取-分析-修改-验证"四步工作流精确修改文档。
"""
import os
import re
import shutil
from typing import Any
from skills.base import BaseTool, ToolParameter, ToolResult
from skills.utils.docx_text import get_paragraph_full_text, get_cell_full_text, accept_all_revisions


class EditDocxTool(BaseTool):
    name = "edit_docx"
    description = (
        "精确编辑 Word (.docx) 文档。支持替换、插入、删除段落和表格内容，"
        "以及修改文本样式。采用四步工作流（读取→分析→修改→验证）确保修改安全。"
    )
    parameters = [
        ToolParameter("file_path", "string", "要编辑的 Word 文档路径"),
        ToolParameter("edit_instructions", "array", (
            "修改指令列表，每项包含: target(paragraph|table|heading), "
            "match_type(index|content|regex|style|level), match_value, "
            "action(replace|insert|delete|modify_style), new_content, "
            "old_content(可选验证), style_changes(可选), cell_location(可选)"
        )),
        ToolParameter("output_path", "string", "输出路径（不指定则覆盖原文件）", required=False),
        ToolParameter("dry_run", "boolean", "预览模式：只分析不实际修改", required=False, default=False),
    ]

    def __init__(self, cwd: str = ".", backup_enabled: bool = True):
        super().__init__(cwd)
        self.backup_enabled = backup_enabled

    def execute(self, file_path: str, edit_instructions: list, output_path: str = "",
                dry_run: bool = False, **kwargs) -> ToolResult:
        backup = self.backup_enabled
        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.cwd, file_path)

        if not os.path.exists(full_path):
            return ToolResult.fail(f"文件不存在: {full_path}")
        if not full_path.lower().endswith('.docx'):
            return ToolResult.fail("仅支持 .docx 格式文件")

        backup_path = ""
        try:
            from docx import Document
        except ImportError:
            return ToolResult.fail("缺少 python-docx 库，请运行: pip install python-docx")

        try:
            if backup and not dry_run:
                backup_path = full_path + '.backup'
                shutil.copy(full_path, backup_path)

            doc, structure = self._read_document(full_path)
            analysis = self._analyze(structure, edit_instructions)
            modifications = self._execute(doc, analysis, dry_run)

            if not dry_run:
                verification = self._verify(doc, structure, modifications)
            else:
                verification = {"passed": True, "checks": [], "is_preview": True}

            save_path = output_path or full_path
            if save_path and not os.path.isabs(save_path):
                save_path = os.path.join(self.cwd, save_path)

            if not dry_run and verification["passed"]:
                out_dir = os.path.dirname(save_path)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                doc.save(save_path)
            else:
                save_path = ""

            applied = sum(1 for m in modifications if m.get("status") == "applied" or m.get("status") == "preview")
            failed = len(modifications) - applied

            lines = [
                f"编辑{'预览' if dry_run else '完成'}: {full_path}",
                f"修改指令: {len(edit_instructions)} 条",
                f"成功: {applied}, 失败: {failed}",
            ]
            if verification.get("checks"):
                for c in verification["checks"]:
                    icon = "OK" if c.get("passed") else "!!"
                    lines.append(f"  [{icon}] {c.get('message', '')}")

            return ToolResult.ok(
                "\n".join(lines),
                dry_run=dry_run,
                modifications_count=len(modifications),
                applied=applied,
                failed=failed,
                output_path=save_path or None,
                backup_path=backup_path or None,
            )
        except Exception as e:
            return ToolResult.fail(f"编辑文档失败: {e}")

    def _read_document(self, file_path: str):
        from docx import Document
        doc = Document(file_path)
        # 编辑前先接受所有修订，避免 w:ins/w:del 干扰文本定位与替换
        accept_all_revisions(doc)
        structure = {"paragraphs": [], "tables": [], "headings": []}

        for idx, para in enumerate(doc.paragraphs):
            para_text = get_paragraph_full_text(para)
            info = {
                "index": idx, "text": para_text, "style": para.style.name,
                "is_heading": para.style.name.startswith('Heading'), "runs_count": len(para.runs),
            }
            structure["paragraphs"].append(info)
            if info["is_heading"]:
                structure["headings"].append(info)

        for idx, table in enumerate(doc.tables):
            tinfo = {"index": idx, "rows": len(table.rows), "cols": len(table.columns), "cells": []}
            for r, row in enumerate(table.rows):
                for c, cell in enumerate(row.cells):
                    tinfo["cells"].append({"row": r, "col": c, "text": get_cell_full_text(cell)})
            structure["tables"].append(tinfo)

        return doc, structure

    def _analyze(self, structure, instructions):
        results = []
        for inst in instructions:
            target = inst.get("target", "paragraph")
            mt = inst.get("match_type", "content")
            mv = inst.get("match_value", "")

            if target == "paragraph":
                loc = self._find_para(structure["paragraphs"], mt, mv)
            elif target == "table":
                loc = self._find_table(structure["tables"], mt, mv)
            elif target == "heading":
                loc = self._find_heading(structure["headings"], mt, mv)
            else:
                loc = None

            results.append({
                "instruction": inst,
                "location": loc,
                "original_content": loc.get("text", "") if loc else "",
                "found": loc is not None,
            })
        return results

    def _find_para(self, paragraphs, mt, mv):
        if mt == "index":
            i = int(mv)
            return paragraphs[i] if 0 <= i < len(paragraphs) else None
        if mt == "content":
            return next((p for p in paragraphs if mv in p["text"]), None)
        if mt == "regex":
            return next((p for p in paragraphs if re.search(mv, p["text"])), None)
        if mt == "style":
            return next((p for p in paragraphs if p["style"] == mv), None)
        return None

    def _find_table(self, tables, mt, mv):
        if mt == "index":
            i = int(mv)
            return tables[i] if 0 <= i < len(tables) else None
        if mt == "content":
            for t in tables:
                for c in t["cells"]:
                    if mv in c["text"]:
                        return {"table": t, "cell": c}
        return None

    def _find_heading(self, headings, mt, mv):
        if mt == "index":
            i = int(mv)
            return headings[i] if 0 <= i < len(headings) else None
        if mt == "content":
            return next((h for h in headings if mv in h["text"]), None)
        if mt == "level":
            return next((h for h in headings if f"Heading {mv}" == h["style"]), None)
        return None

    def _execute(self, doc, analysis, dry_run):
        modifications = []
        for result in analysis:
            inst = result["instruction"]
            loc = result["location"]

            if not loc:
                modifications.append({"success": False, "error": "未找到目标", "instruction": inst, "status": "failed"})
                continue

            if dry_run:
                new = self._preview_content(result.get("original_content", ""), inst)
                modifications.append({"success": True, "location": loc, "original": result.get("original_content", ""),
                                     "new": new, "action": inst.get("action"), "status": "preview"})
            else:
                try:
                    new = self._apply(doc, loc, inst)
                    modifications.append({"success": True, "location": loc, "original": result.get("original_content", ""),
                                         "new": new, "action": inst.get("action"), "status": "applied"})
                except Exception as e:
                    modifications.append({"success": False, "error": str(e), "instruction": inst, "status": "failed"})
        return modifications

    def _preview_content(self, original, inst):
        action = inst.get("action", "replace")
        if action == "replace":
            return inst.get("new_content", original)
        if action == "insert":
            return original + "\n" + inst.get("new_content", "")
        if action == "delete":
            return "[已删除]"
        if action == "modify_style":
            return original + " [样式已修改]"
        return original

    def _apply(self, doc, loc, inst):
        target = inst.get("target", "paragraph")
        if target in ("paragraph", "heading"):
            return self._mod_para(doc, loc, inst)
        if target == "table":
            return self._mod_table(doc, loc, inst)
        return ""

    def _mod_para(self, doc, loc, inst):
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn

        idx = loc.get("index", 0)
        if idx >= len(doc.paragraphs):
            raise IndexError(f"段落 {idx} 超出范围")
        para = doc.paragraphs[idx]
        action = inst.get("action", "replace")

        if action == "replace":
            new = inst.get("new_content", "")
            old = inst.get("old_content", "")
            if old and old not in para.text:
                raise ValueError(f"未找到: {old[:50]}")
            para.clear()
            run = para.add_run(new)
            self._apply_style(run, para.style.name, inst.get("style_changes"))
            return new

        if action == "insert":
            new = inst.get("new_content", "")
            run = para.add_run(new)
            self._apply_style(run, para.style.name)
            return para.text

        if action == "delete":
            para.clear()
            return ""

        if action == "modify_style":
            sc = inst.get("style_changes", {})
            for run in para.runs:
                self._apply_style(run, para.style.name, sc)
            return para.text

        return para.text

    def _mod_table(self, doc, loc, inst):
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn

        if "table" in loc and "cell" in loc:
            ti = loc["table"]["index"]
            row, col = loc["cell"]["row"], loc["cell"]["col"]
        else:
            ti = loc.get("index", 0)
            cl = inst.get("cell_location", {})
            row, col = cl.get("row", 0), cl.get("col", 0)

        if ti >= len(doc.tables):
            raise IndexError(f"表格 {ti} 超出范围")
        table = doc.tables[ti]
        if row >= len(table.rows) or col >= len(table.columns):
            raise IndexError(f"单元格 [{row},{col}] 超出范围")

        cell = table.rows[row].cells[col]
        action = inst.get("action", "replace")

        if action == "replace":
            new = inst.get("new_content", "")
            old = inst.get("old_content", "")
            if old and old not in cell.text:
                raise ValueError(f"未找到: {old}")
            cell.text = ""
            run = cell.paragraphs[0].add_run(new)
            run.font.name = '仿宋'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')
            run.font.size = Pt(12)
            run.font.color.rgb = RGBColor(0, 0, 0)
            return new

        return cell.text

    def _apply_style(self, run, style_name, changes=None):
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn

        if style_name.startswith('Heading'):
            run.font.name = '黑体'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
            run.font.bold = True
            sz = 16 if '1' in style_name else (15 if '2' in style_name else 14)
            run.font.size = Pt(sz)
        else:
            run.font.name = '仿宋'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')
            run.font.size = Pt(14)
        run.font.color.rgb = RGBColor(0, 0, 0)

        if changes:
            if 'font_name' in changes:
                run.font.name = changes['font_name']
                run._element.rPr.rFonts.set(qn('w:eastAsia'), changes['font_name'])
            if 'font_size' in changes:
                run.font.size = Pt(changes['font_size'])
            if 'bold' in changes:
                run.font.bold = changes['bold']
            if 'color' in changes:
                c = changes['color']
                if isinstance(c, (list, tuple)):
                    run.font.color.rgb = RGBColor(*c)

    def _verify(self, doc, orig_structure, modifications):
        ver = {"passed": True, "checks": []}
        cp = len(doc.paragraphs)
        op = len(orig_structure["paragraphs"])
        ver["checks"].append({"check": "paragraph_count", "passed": True, "message": f"段落: {op} → {cp}"})

        headings = [p for p in doc.paragraphs if p.style.name.startswith('Heading')]
        oh = len(orig_structure["headings"])
        ok = len(headings) >= oh
        ver["checks"].append({"check": "headings", "passed": ok, "message": f"标题: {len(headings)}"})
        if not ok:
            ver["passed"] = False

        successful = sum(1 for m in modifications if m.get("success"))
        total = len(modifications)
        ver["checks"].append({"check": "success_rate", "passed": successful == total,
                              "message": f"成功率: {successful}/{total}"})
        if successful < total:
            ver["passed"] = False
        return ver
