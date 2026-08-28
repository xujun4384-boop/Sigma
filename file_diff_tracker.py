"""
文件差异追踪模块
用于追踪文件修改前后的差异，支持 Excel、Word 等文档类型
"""
import os
import difflib
from datetime import datetime
from typing import Dict, Optional, Any
import openpyxl
from openpyxl import load_workbook
from docx import Document
from skills.utils.docx_text import get_paragraph_full_text, get_cell_full_text


class FileSnapshot:
    """文件快照"""
    def __init__(self, file_path: str, content: Any):
        self.file_path = file_path
        self.content = content
        self.timestamp = datetime.now().isoformat()


TEXT_SUFFIXES = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.scss', '.less',
    '.java', '.c', '.cpp', '.h', '.hpp', '.go', '.rs', '.rb', '.php', '.swift',
    '.json', '.yaml', '.yml', '.xml', '.toml', '.ini', '.cfg', '.env', '.properties',
    '.sql', '.sh', '.bat', '.ps1', '.log', '.txt', '.csv',
}

class FileDiffTracker:
    """文件差异追踪器"""

    def __init__(self):
        self.snapshots: Dict[str, FileSnapshot] = {}
        self.active_modifications: set = set()

    def snapshot_file(self, file_path: str) -> bool:
        """
        在修改文件前保存快照

        Args:
            file_path: 文件路径

        Returns:
            是否成功保存快照
        """
        if not os.path.exists(file_path):
            print(f"[FileDiffTracker] 文件不存在: {file_path}")
            return False

        file_ext = os.path.splitext(file_path)[1].lower()

        try:
            if file_ext == '.xlsx':
                content = self._snapshot_excel(file_path)
            elif file_ext == '.docx':
                content = self._snapshot_word(file_path)
            elif file_ext == '.md':
                content = self._snapshot_markdown(file_path)
            elif file_ext in TEXT_SUFFIXES:
                content = self._snapshot_code(file_path)
            else:
                # 其他文件类型：保存原始字节内容
                with open(file_path, 'rb') as f:
                    content = f.read()

            self.snapshots[file_path] = FileSnapshot(file_path, content)
            print(f"[FileDiffTracker] 已保存快照: {file_path}")
            return True

        except Exception as e:
            print(f"[FileDiffTracker] 保存快照失败: {file_path}, 错误: {e}")
            return False

    def _snapshot_excel(self, file_path: str) -> Dict:
        """保存 Excel 文件的结构化数据"""
        wb = load_workbook(file_path, data_only=True)
        snapshot = {
            'sheets': {}
        }

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            sheet_data = {}

            # 只保存有内容的单元格
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        cell_ref = f"{cell.column_letter}{cell.row}"
                        sheet_data[cell_ref] = {
                            'value': str(cell.value),
                            'row': cell.row,
                            'col': cell.column,
                            'col_letter': cell.column_letter
                        }

            snapshot['sheets'][sheet_name] = sheet_data

        wb.close()
        return snapshot

    def _snapshot_word(self, file_path: str) -> Dict:
        """保存 Word 文件的结构化数据"""
        doc = Document(file_path)
        snapshot = {
            'paragraphs': [],
            'tables': []
        }

        # 保存段落（包含修订插入内容）
        for i, para in enumerate(doc.paragraphs):
            snapshot['paragraphs'].append({
                'index': i,
                'text': get_paragraph_full_text(para),
                'style': para.style.name if para.style else None
            })

        # 保存表格（包含修订插入内容）
        for i, table in enumerate(doc.tables):
            table_data = []
            for row in table.rows:
                row_data = [get_cell_full_text(cell) for cell in row.cells]
                table_data.append(row_data)
            snapshot['tables'].append({
                'index': i,
                'data': table_data
            })

        return snapshot

    def _snapshot_markdown(self, file_path: str) -> Dict:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        return {
            'text': text,
            'lines': text.splitlines()
        }

    def _snapshot_code(self, file_path: str) -> Dict:
        """代码文件按文本快照"""
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        return {'text': text, 'lines': text.splitlines()}

    def get_diff(self, file_path: str, snapshot_if_missing: bool = False) -> Optional[Dict]:
        """
        获取文件的差异信息

        Args:
            file_path: 文件路径
            snapshot_if_missing: 无快照时是否先对当前状态补建快照再返回 None
                （供外部文件监听通道调用，使文件的后续修改也能正常产生 diff，
                而非每次都被当作首次出现）

        Returns:
            差异信息字典，如果没有快照或文件不存在则返回 None
        """
        if file_path not in self.snapshots:
            if snapshot_if_missing:
                self.snapshot_file(file_path)
            else:
                print(f"[FileDiffTracker] 没有找到快照: {file_path}")
            return None

        if not os.path.exists(file_path):
            print(f"[FileDiffTracker] 文件不存在: {file_path}")
            return None

        file_ext = os.path.splitext(file_path)[1].lower()

        try:
            if file_ext == '.xlsx':
                return self._diff_excel(file_path)
            elif file_ext == '.docx':
                return self._diff_word(file_path)
            elif file_ext == '.md':
                return self._diff_markdown(file_path)
            elif file_ext in TEXT_SUFFIXES:
                return self._diff_code(file_path)
            else:
                return None

        except Exception as e:
            print(f"[FileDiffTracker] 生成 diff 失败: {file_path}, 错误: {e}")
            return None

    def _diff_excel(self, file_path: str) -> Dict:
        """生成 Excel 文件的差异"""
        old_snapshot = self.snapshots[file_path].content
        new_content = self._snapshot_excel(file_path)

        diff = {
            'file_path': file_path,
            'file_type': 'excel',
            'file_name': os.path.basename(file_path),
            'sheets': {}
        }

        # 对比每个 sheet
        all_sheet_names = set(old_snapshot['sheets'].keys()) | set(new_content['sheets'].keys())

        for sheet_name in all_sheet_names:
            old_sheet = old_snapshot['sheets'].get(sheet_name, {})
            new_sheet = new_content['sheets'].get(sheet_name, {})

            sheet_diff = {
                'added': [],
                'removed': [],
                'modified': []
            }

            # 所有单元格的并集
            all_cells = set(old_sheet.keys()) | set(new_sheet.keys())

            for cell_ref in all_cells:
                old_cell = old_sheet.get(cell_ref)
                new_cell = new_sheet.get(cell_ref)

                if old_cell and new_cell:
                    # 单元格存在于新旧版本，检查是否修改
                    if old_cell['value'] != new_cell['value']:
                        sheet_diff['modified'].append({
                            'cell': cell_ref,
                            'row': new_cell['row'],
                            'col': new_cell['col'],
                            'col_letter': new_cell['col_letter'],
                            'old_value': old_cell['value'],
                            'new_value': new_cell['value']
                        })
                elif new_cell:
                    # 新增的单元格
                    sheet_diff['added'].append({
                        'cell': cell_ref,
                        'row': new_cell['row'],
                        'col': new_cell['col'],
                        'col_letter': new_cell['col_letter'],
                        'value': new_cell['value']
                    })
                elif old_cell:
                    # 删除的单元格
                    sheet_diff['removed'].append({
                        'cell': cell_ref,
                        'row': old_cell['row'],
                        'col': old_cell['col'],
                        'col_letter': old_cell['col_letter'],
                        'value': old_cell['value']
                    })

            # 只记录有变化的 sheet
            if sheet_diff['added'] or sheet_diff['removed'] or sheet_diff['modified']:
                diff['sheets'][sheet_name] = sheet_diff

        return diff

    def _diff_word(self, file_path: str) -> Dict:
        """生成 Word 文件的差异"""
        old_snapshot = self.snapshots[file_path].content
        new_content = self._snapshot_word(file_path)

        diff = {
            'file_path': file_path,
            'file_type': 'word',
            'file_name': os.path.basename(file_path),
            'old_text': '\n'.join(p['text'] for p in old_snapshot['paragraphs']),
            'new_text': '\n'.join(p['text'] for p in new_content['paragraphs']),
            'paragraphs': {
                'added': [],
                'removed': [],
                'modified': []
            }
        }

        old_paras = old_snapshot['paragraphs']
        new_paras = new_content['paragraphs']

        # 简单的段落对比（按索引）
        max_len = max(len(old_paras), len(new_paras))

        for i in range(max_len):
            old_para = old_paras[i] if i < len(old_paras) else None
            new_para = new_paras[i] if i < len(new_paras) else None

            if old_para and new_para:
                # 段落存在于新旧版本，检查是否修改
                if old_para['text'] != new_para['text']:
                    diff['paragraphs']['modified'].append({
                        'index': i,
                        'old_text': old_para['text'],
                        'new_text': new_para['text'],
                        'word_diff': self._word_level_diff(old_para['text'], new_para['text'])
                    })
            elif new_para:
                # 新增的段落
                diff['paragraphs']['added'].append({
                    'index': i,
                    'text': new_para['text']
                })
            elif old_para:
                # 删除的段落
                diff['paragraphs']['removed'].append({
                    'index': i,
                    'text': old_para['text']
                })

        return diff

    def _diff_markdown(self, file_path: str) -> Dict:
        old_snapshot = self.snapshots[file_path].content
        new_content = self._snapshot_markdown(file_path)

        diff = {
            'file_path': file_path,
            'file_type': 'markdown',
            'file_name': os.path.basename(file_path),
            'old_text': old_snapshot['text'],
            'new_text': new_content['text'],
            'lines': {
                'added': [],
                'removed': [],
                'modified': []
            }
        }

        matcher = difflib.SequenceMatcher(None, old_snapshot['lines'], new_content['lines'])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                continue
            if tag == 'insert':
                for offset, line in enumerate(new_content['lines'][j1:j2]):
                    diff['lines']['added'].append({
                        'line': j1 + offset + 1,
                        'text': line
                    })
            elif tag == 'delete':
                for offset, line in enumerate(old_snapshot['lines'][i1:i2]):
                    diff['lines']['removed'].append({
                        'line': i1 + offset + 1,
                        'text': line
                    })
            elif tag == 'replace':
                max_len = max(i2 - i1, j2 - j1)
                for offset in range(max_len):
                    old_line = old_snapshot['lines'][i1 + offset] if i1 + offset < i2 else ''
                    new_line = new_content['lines'][j1 + offset] if j1 + offset < j2 else ''
                    diff['lines']['modified'].append({
                        'old_line': i1 + offset + 1 if old_line else None,
                        'new_line': j1 + offset + 1 if new_line else None,
                        'old_text': old_line,
                        'new_text': new_line,
                        'word_diff': self._word_level_diff(old_line, new_line)
                    })

        return diff

    def _diff_code(self, file_path: str) -> Dict:
        """代码文件 diff：返回原始文本 + 行级统计"""
        old_snapshot = self.snapshots[file_path].content
        new_content = self._snapshot_code(file_path)

        diff = {
            'file_path': file_path,
            'file_type': 'code',
            'file_name': os.path.basename(file_path),
            'old_text': old_snapshot['text'],
            'new_text': new_content['text'],
            'lines': {'added': [], 'removed': [], 'modified': []}
        }

        matcher = difflib.SequenceMatcher(None, old_snapshot['lines'], new_content['lines'])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                continue
            if tag == 'insert':
                for offset, line in enumerate(new_content['lines'][j1:j2]):
                    diff['lines']['added'].append({'line': j1 + offset + 1, 'text': line})
            elif tag == 'delete':
                for offset, line in enumerate(old_snapshot['lines'][i1:i2]):
                    diff['lines']['removed'].append({'line': i1 + offset + 1, 'text': line})
            elif tag == 'replace':
                max_len = max(i2 - i1, j2 - j1)
                for offset in range(max_len):
                    old_line = old_snapshot['lines'][i1 + offset] if i1 + offset < i2 else ''
                    new_line = new_content['lines'][j1 + offset] if j1 + offset < j2 else ''
                    diff['lines']['modified'].append({
                        'old_line': i1 + offset + 1 if old_line else None,
                        'new_line': j1 + offset + 1 if new_line else None,
                        'old_text': old_line, 'new_text': new_line,
                    })
        return diff

    def _word_level_diff(self, old_text: str, new_text: str) -> Dict:
        """词级别的差异对比"""
        import difflib

        old_words = old_text.split()
        new_words = new_text.split()

        matcher = difflib.SequenceMatcher(None, old_words, new_words)

        changes = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                changes.append({
                    'type': 'equal',
                    'text': ' '.join(old_words[i1:i2])
                })
            elif tag == 'insert':
                changes.append({
                    'type': 'insert',
                    'text': ' '.join(new_words[j1:j2])
                })
            elif tag == 'delete':
                changes.append({
                    'type': 'delete',
                    'text': ' '.join(old_words[i1:i2])
                })
            elif tag == 'replace':
                changes.append({
                    'type': 'replace',
                    'old_text': ' '.join(old_words[i1:i2]),
                    'new_text': ' '.join(new_words[j1:j2])
                })

        return {'changes': changes}

    def mark_modification_start(self, file_path: str):
        """标记文件开始修改"""
        self.active_modifications.add(file_path)

    def mark_modification_complete(self, file_path: str):
        """标记文件修改完成"""
        if file_path in self.active_modifications:
            self.active_modifications.remove(file_path)

    def is_modifying(self, file_path: str) -> bool:
        """检查文件是否正在修改中"""
        return file_path in self.active_modifications

    def clear_snapshot(self, file_path: str):
        """清除文件快照"""
        if file_path in self.snapshots:
            del self.snapshots[file_path]


file_diff_tracker = FileDiffTracker()


def _diff_has_changes(diff: dict) -> bool:
    """检查 diff 结果是否包含实际变更"""
    # Word diff: paragraphs.modified/added/removed
    for group in diff.get("paragraphs", {}).values():
        if isinstance(group, list) and len(group) > 0:
            return True
    # Markdown diff: lines.modified/added/removed
    for group in diff.get("lines", {}).values():
        if isinstance(group, list) and len(group) > 0:
            return True
    # Excel diff: sheets
    sheets = diff.get("sheets", {})
    for sheet_name, sheet_diff in sheets.items():
        for group in sheet_diff.values() if isinstance(sheet_diff, dict) else []:
            if isinstance(group, list) and len(group) > 0:
                return True
    return False
