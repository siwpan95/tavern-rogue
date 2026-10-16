"""入口与可移植性：测试入口本身要可靠，仓库必须能从干净克隆跑起来。

回归对象（均为实测缺陷）：
  1. `run_tests.py` 在 GBK 控制台打印 ✅ 抛 UnicodeEncodeError，全绿也退出 1；
  2. 旧版递归全仓，把 `.venv` 里 573 个第三方 py 也编译一遍；
  3. `third_party/` 被 .gitignore 忽略，而 `game/ai_content.py` 无条件 import
     → 干净克隆 `import ui.game_manager` 直接 ModuleNotFoundError。
"""
from __future__ import annotations

import builtins
import importlib
import pkgutil
import subprocess
import sys

import pytest

import run_tests


# ─── 入口本身 ─────────────────────────────────────────────

def test_encode_safe_never_raises_on_gbk():
    text = "✅ 全部通过"
    safe = run_tests.encode_safe(text, "gbk")
    safe.encode("gbk")  # 必须能编码，否则控制台又会崩
    assert "通过" in safe


def test_encode_safe_is_identity_for_encodable_text():
    assert run_tests.encode_safe("普通文本", "gbk") == "普通文本"


def test_scan_face_excludes_env_and_third_party(repo_root):
    files = run_tests.iter_python_files(repo_root)
    rels = [str(path.relative_to(repo_root)) for path in files]
    assert rels, "必须扫到自研代码"
    for rel in rels:
        assert not rel.startswith(".venv" + "/"), rel
        assert not rel.startswith("third_party" + "/"), rel
        assert "__pycache__" not in rel, rel


def test_run_simple_tests_passes(repo_root, capsys):
    code = run_tests.run_simple_tests(repo_root, quiet=True, with_pytest=False)
    captured = capsys.readouterr()
    assert code == 0, captured.out
    assert "[PASS] 语法与数据检查通过" in captured.out


def test_pytest_is_installed_and_collectable():
    assert importlib.util.find_spec("pytest") is not None


# ─── 干净克隆可运行性 ──────────────────────────────────────

def test_ai_backend_import_is_optional(monkeypatch):
    """模拟干净克隆：third_party 不可用时，导入仍必须成功且**出声**降级。"""
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "third_party" or name.startswith("third_party."):
            raise ModuleNotFoundError("simulated fresh clone without third_party")
        return real_import(name, *args, **kwargs)

    for module_name in list(sys.modules):
        if module_name.startswith(("game.ai_content", "third_party")):
            del sys.modules[module_name]

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    module = importlib.import_module("game.ai_content")
    assert module.AI_BACKEND_AVAILABLE is False
    assert module.AIContentGenerator().is_available() is False
    assert module.enhance_event({"id": "x", "name": "n"}) is not None, \
        "后端缺失时应回退到原始事件，而不是抛错"


def test_vendored_ai_backend_is_tracked(repo_root):
    """third_party 里的 AI 后端必须入库，否则干净克隆跑不起来。"""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "third_party"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.returncode != 0:
        pytest.skip("git 不可用，跳过入库面检查")
    tracked = result.stdout.split()
    assert "third_party/ollama_generator/core.py" in tracked, tracked


def test_all_first_party_modules_import():
    failures = []
    for package_name in ("game", "ui"):
        package = importlib.import_module(package_name)
        for info in pkgutil.walk_packages(package.__path__, prefix=package_name + "."):
            try:
                importlib.import_module(info.name)
            except Exception as exc:  # noqa: BLE001 - 汇总全部导入失败而不是首个
                failures.append((info.name, repr(exc)))
    assert not failures, failures


def test_game_entry_module_imports_headless():
    module = importlib.import_module("ui.app")
    assert hasattr(module, "TavernRogueApp")
