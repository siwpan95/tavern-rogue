"""TavernRogue 项目测试入口

四层检查，逐层都能单独跑：
  1. 编译仓内**自研** Python 文件（跳过 .venv / third_party / __pycache__ 等）
  2. 静态检查：死代码（未使用导入/变量、无占位符 f-string）—— 需要 pyflakes
  3. 解析 data/*.json
  4. 若装了 pytest，再跑 tests/ 套件（`--no-pytest` 可关）

用法：
    python run_tests.py
    python run_tests.py --no-pytest
    python run_tests.py --quiet
    python run_tests.py --no-lint

退出码：0 全部通过 · 1 有失败 · 2 用法错误
注意：控制台被跳过时**出声**（SKIP 不是通过）。

历史：旧的 `test_final_verification.py` 已删除（它用的是过期 API 与不存在的职业名，
5 个 FAIL 里 4 个是脚本自己过期）。功能面 × 接任者：

| 旧脚本的功能面 | 接任者 |
| --- | --- |
| 语法检查 | 本文件的 `check_python_files`（只扫自研代码）+ `tests/test_entrypoints.py` |
| JSON 数据可解析 | 本文件的 `check_json_files` + `tests/test_data_integrity.py` |
| 事件引用敌人 ID 校验 | `tests/test_data_integrity.py::test_event_battle_targets_exist` |
| 关键词逻辑 / 种族共鸣 / 全流程 | `tests/test_battle_engine.py`、`tests/test_smoke_flow.py` |
| 宝物效果类型检查 | `tests/test_relic_effects.py`（按实现登记表校验） |
| 死代码与未定义名 | 本文件的 `run_lint`（pyflakes） |
"""
from __future__ import annotations

import argparse
import json
import py_compile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# 只扫自研代码。旧版递归全仓，会把 .venv 里 573 个第三方 py 也编译一遍。
SCAN_SUBDIRS = ("game", "ui", "tools", "tests")
SCAN_ROOT_FILES = ("run_gui.py", "run_tests.py")
SKIP_DIR_NAMES = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "third_party", "saves", "save", "archive", "build",
    "dist", "node_modules", "assets",
})


def encode_safe(text, encoding) -> str:
    """把文本转成目标编码一定能打印出来的形式（不能编码的字符用 ? 顶替）。

    Windows 控制台常见 GBK（cp936），直接 print("✅") 会抛 UnicodeEncodeError，
    让「全绿」的检查以退出码 1 收场。这里只降级字符，不吞掉结论。
    """
    if not encoding:
        return text
    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        return text.encode(encoding, "replace").decode(encoding, "replace")


def emit(text: str = "") -> None:
    """打印一行；编码能力不够时降级字符，绝不因此崩掉。"""
    stream = sys.stdout
    safe = encode_safe(text, getattr(stream, "encoding", None))
    try:
        print(safe)
    except UnicodeEncodeError:  # 极端环境：连降级后的串也打不出来
        print(safe.encode("ascii", "replace").decode("ascii"))


def iter_python_files(root: Path):
    """产出仓内自研 .py 文件（按路径排序，输出稳定）。"""
    seen = []
    for sub in SCAN_SUBDIRS:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
                continue
            seen.append(path)
    for name in SCAN_ROOT_FILES:
        path = root / name
        if path.is_file():
            seen.append(path)
    return sorted(set(seen))


def iter_json_files(root: Path):
    data_dir = root / "data"
    if not data_dir.is_dir():
        return []
    return sorted(data_dir.rglob("*.json"))


def check_python_files(root: Path, quiet: bool = False):
    errors = []
    files = iter_python_files(root)
    for path in files:
        rel = path.relative_to(root)
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append((str(rel), str(exc).strip().splitlines()[-1]))
            emit("  [FAIL] %s: %s" % (rel, errors[-1][1]))
        else:
            if not quiet:
                emit("  [OK]   %s" % rel)
    return len(files), errors


def check_json_files(root: Path, quiet: bool = False):
    errors = []
    files = iter_json_files(root)
    for path in files:
        rel = path.relative_to(root)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                json.load(fh)
        except Exception as exc:  # noqa: BLE001 - 这里要报出全部坏文件，不能中断
            errors.append((str(rel), str(exc)))
            emit("  [FAIL] %s: %s" % (rel, exc))
        else:
            if not quiet:
                emit("  [OK]   %s" % rel)
    return len(files), errors


def run_pytest_suite(root: Path):
    """跑 tests/ 套件。返回 (exit_code, skipped, note)。"""
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return 0, True, "tests/ 目录不存在"
    try:
        import pytest  # noqa: PLC0415 - 可选依赖，用到了才导入
    except ImportError:
        return 0, True, "未安装 pytest"
    code = int(pytest.main(["-q", str(tests_dir)]))
    if code == 5:  # pytest: no tests collected
        return 0, True, "tests/ 未收集到用例"
    return code, False, ""


def run_lint(root: Path):
    """静态检查（pyflakes）：死代码 / 未定义名 / 无占位符 f-string。

    返回 (exit_code, skipped, note)。pyflakes 是开发期依赖，未安装时**出声跳过**，
    并明确说明"SKIP 不是通过" —— 不许静默当成干净。
    """
    try:
        from pyflakes.api import checkRecursive
        from pyflakes.reporter import Reporter
    except ImportError:
        return 0, True, "未安装 pyflakes（pip install -r requirements-dev.txt）"

    import io

    files = [str(path) for path in iter_python_files(root)]
    out, err = io.StringIO(), io.StringIO()
    warnings = checkRecursive(files, Reporter(out, err))
    report = (out.getvalue() + err.getvalue()).strip()
    return (1 if warnings else 0), False, report


def run_simple_tests(root=None, quiet=True, with_pytest=True, with_lint=True) -> int:
    """给测试与 CI 调用的入口：返回进程退出码。"""
    root = Path(root or PROJECT_ROOT)
    emit("[TavernRogue] 项目测试: %s" % root)

    emit("-- Python 语法检查 " + "-" * 30)
    py_count, py_errors = check_python_files(root, quiet=quiet)
    emit("Python 文件: %d 个，失败 %d 个" % (py_count, len(py_errors)))

    emit("-- JSON 数据检查 " + "-" * 32)
    json_count, json_errors = check_json_files(root, quiet=quiet)
    emit("JSON 文件:   %d 个，失败 %d 个" % (json_count, len(json_errors)))

    failed = bool(py_errors or json_errors)
    if not failed:
        emit("[PASS] 语法与数据检查通过")
    else:
        emit("[FAIL] 语法或数据检查未通过")

    if with_lint:
        emit("-- 静态检查（pyflakes） " + "-" * 24)
        code, skipped, note = run_lint(root)
        if skipped:
            emit("[SKIP] 静态检查未运行：%s（SKIP 不是通过）" % note)
        elif code == 0:
            emit("[PASS] 静态检查通过（无死代码/未定义名）")
        else:
            for line in note.splitlines()[:20]:
                emit("  " + line)
            emit("[FAIL] 静态检查发现 %d 条问题" % len(note.splitlines()))
            failed = True

    if with_pytest:
        emit("-- pytest 套件 " + "-" * 34)
        code, skipped, note = run_pytest_suite(root)
        if skipped:
            emit("[SKIP] pytest 未运行：%s（SKIP 不是通过）" % note)
        elif code == 0:
            emit("[PASS] pytest 套件全绿")
        else:
            emit("[FAIL] pytest 套件退出码 %d" % code)
            failed = True

    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TavernRogue 项目测试入口")
    parser.add_argument("--no-pytest", action="store_true", help="只跑语法/静态/数据检查")
    parser.add_argument("--no-lint", action="store_true", help="跳过 pyflakes 静态检查")
    parser.add_argument("--quiet", action="store_true", help="不逐文件打印")
    args = parser.parse_args(argv)
    return run_simple_tests(PROJECT_ROOT, quiet=args.quiet,
                            with_pytest=not args.no_pytest,
                            with_lint=not args.no_lint)


if __name__ == "__main__":
    sys.exit(main())
