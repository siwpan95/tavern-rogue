"""
TavernRogue 项目测试入口

对当前项目做快速健康检查：
  - 编译所有 .py 文件
  - 解析所有 .json 文件

用法：
    python run_tests.py
"""
import json
import os
import py_compile
import sys
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def run_simple_tests(root):
    """递归编译 .py 并解析 .json"""
    root = Path(root)
    py_errors = []
    json_errors = []
    py_count = 0
    json_count = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path

        if path.suffix == ".py":
            py_count += 1
            try:
                py_compile.compile(str(path), doraise=True)
                print(f"  [OK]  {rel}")
            except Exception as e:
                py_errors.append((str(rel), str(e)))
                print(f"  [FAIL] {rel}: {e}")

        elif path.suffix == ".json":
            json_count += 1
            try:
                with open(path, "r", encoding="utf-8") as f:
                    json.load(f)
                print(f"  [OK]  {rel}")
            except Exception as e:
                json_errors.append((str(rel), str(e)))
                print(f"  [FAIL] {rel}: {e}")

    print()
    print(f"Python 文件: {py_count} 个，失败 {len(py_errors)} 个")
    print(f"JSON 文件:   {json_count} 个，失败 {len(json_errors)} 个")

    if py_errors or json_errors:
        print("❌ 测试未通过")
        return 1
    print("✅ 简单测试通过")
    return 0


if __name__ == '__main__':
    print(f"[TavernRogue] 启动项目测试: {PROJECT_ROOT}")
    sys.exit(run_simple_tests(PROJECT_ROOT))
