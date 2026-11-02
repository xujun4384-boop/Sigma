# -*- coding: utf-8 -*-
"""TSX 交付契约的公共校验：具名导出判定。

组件既可以写 `export const Shot9 = ...`，也可以写 `export function Shot9()`，
还可以在文件末尾 `export {Shot9}`；这些对 `import {Shot9}` 都合法，
校验不能只认第一种写法，否则会把正确代码判成“没导出”。
"""
import re


def has_named_export(code: str, name: str) -> bool:
    n = re.escape(name)
    if re.search(rf"export\s+(?:const|let|var|function|class)\s+{n}\b", code):
        return True
    # export {Shot9} / export {Shot9, BG}；排除 export {Shot9 as X}（别名后具名导入拿不到）
    if re.search(rf"export\s*\{{[^}}]*\b{n}\b\s*(?:,|\}})", code):
        return True
    return False
