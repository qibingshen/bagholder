"""检查项目自编写文档、注释和文档字符串是否含有简体中文说明。"""

from __future__ import annotations

import ast
import io
from pathlib import Path
import re
import sys
import tokenize


中文字符模式 = re.compile(r"[\u4e00-\u9fff]")
英文字符模式 = re.compile(r"[A-Za-z]")
忽略目录 = {
    ".agents",
    ".git",
    ".specify",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
}


def 包含中文文本(value: str) -> bool:
    """判断文本是否包含至少一个中文字符，作为项目说明的最低可检查约束。"""

    return bool(中文字符模式.search(value))


def 检查文档(path: Path) -> list[str]:
    """要求项目 Markdown 文档至少包含中文解释，避免以整篇英文替代项目说明。"""

    text = path.read_text(encoding="utf-8")
    if 英文字符模式.search(text) and not 包含中文文本(text):
        return [f"{path}: 文档包含英文内容但缺少简体中文解释"]
    return []


def 检查_python_说明(path: Path) -> list[str]:
    """检查 Python 文档字符串和注释中的自然语言说明，忽略代码标识符。"""

    source = path.read_text(encoding="utf-8")
    errors: list[str] = []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        return [f"{path}:{error.lineno}: Python 语法无效，无法检查中文说明"]

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(node, clean=False)
            if docstring and 英文字符模式.search(docstring) and not 包含中文文本(docstring):
                errors.append(f"{path}:{node.lineno}: 文档字符串缺少简体中文解释")

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            comment = token.string.lstrip("#").strip()
            if comment and 英文字符模式.search(comment) and not 包含中文文本(comment):
                errors.append(f"{path}:{token.start[0]}: 注释缺少简体中文解释")
    return errors


def 收集待检查文件(root: Path) -> list[Path]:
    """仅收集项目文档和 Python 源码，跳过第三方、缓存和构建目录。"""

    return [
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part in 忽略目录 for part in path.parts) and path.suffix in {".md", ".py"}
    ]


def main(argv: list[str]) -> int:
    """执行中文说明检查并以非零状态报告可定位的问题。"""

    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    if not root.is_dir():
        print(f"检查目录不存在：{root}")
        return 2

    errors: list[str] = []
    for path in 收集待检查文件(root):
        errors.extend(检查文档(path) if path.suffix == ".md" else 检查_python_说明(path))

    if errors:
        print("中文说明检查失败：")
        print("\n".join(errors))
        return 1
    print(f"中文说明检查通过：{root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
