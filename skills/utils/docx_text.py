"""
DOCX 文本提取与修订处理工具

python-docx 默认的 paragraph.text / cell.text 不会读取 Word 修订模式
（Track Changes）下 <w:ins> 标签内的内容，导致搜索、读取、diff 都可能
遗漏实际可见的文字。本模块提供统一方法提取“用户实际看到的完整文本”，
并支持在编辑前接受所有修订。
"""
from docx.oxml.ns import qn


def get_paragraph_full_text(para) -> str:
    """获取段落的完整文本，包括修订插入（w:ins）中的内容。"""
    return "".join(t.text or "" for t in para._p.iter(qn("w:t")))


def get_cell_full_text(cell) -> str:
    """获取表格单元格的完整文本，包括修订插入中的内容。"""
    return "\n".join(get_paragraph_full_text(p) for p in cell.paragraphs)


def _accept_revisions_in_element(element):
    """在指定元素范围内接受所有修订：提升 w:ins，删除 w:del。"""
    # 先处理所有 w:ins：把内部 run 提升到 ins 同级位置
    for ins in list(element.iter(qn("w:ins"))):
        parent = ins.getparent()
        if parent is None:
            continue
        idx = parent.index(ins)
        for child in list(ins):
            parent.insert(idx, child)
            idx += 1
        parent.remove(ins)

    # 再删除所有 w:del
    for del_ in list(element.iter(qn("w:del"))):
        parent = del_.getparent()
        if parent is None:
            continue
        parent.remove(del_)


def accept_all_revisions(doc):
    """接受文档中的所有修订，使 paragraph.text 能反映最终可见内容。

    注意：这会直接修改 doc 的 XML 树，建议在编辑操作前调用，避免修订
    标签干扰文本定位与替换。
    """
    body = doc.element.body
    _accept_revisions_in_element(body)
    # 页眉页脚也可能包含修订，一并处理
    for section in doc.sections:
        for hdr in [section.header, section.first_page_header, section.even_page_header]:
            if hdr is not None:
                _accept_revisions_in_element(hdr._element)
        for ftr in [section.footer, section.first_page_footer, section.even_page_footer]:
            if ftr is not None:
                _accept_revisions_in_element(ftr._element)
