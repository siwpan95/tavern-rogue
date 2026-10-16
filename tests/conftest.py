"""pytest 公共夹具：路径注入、headless 驱动、确定性随机种子。

注意：SDL 驱动必须在 `import pygame` 之前设置，否则无显示环境下建窗口会失败。
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pytest  # noqa: E402 - 必须在环境变量之后导入

SEED = 20261016


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(autouse=True)
def deterministic_random():
    """每个用例用固定种子；用完恢复全局状态，避免互相污染。"""
    state = random.getstate()
    random.seed(SEED)
    try:
        yield
    finally:
        random.setstate(state)


@pytest.fixture(scope="session")
def game_data() -> dict:
    data_dir = REPO_ROOT / "data"
    loaded = {}
    for name in ("adventurers", "enemies", "relics", "events", "map_templates"):
        with open(data_dir / ("%s.json" % name), "r", encoding="utf-8") as fh:
            loaded[name] = json.load(fh)
    return loaded


@pytest.fixture(scope="session")
def data_loader():
    """与 ui/game_manager.py 同形的数据加载器。"""
    cache = {}

    def load(filename: str):
        if filename not in cache:
            with open(REPO_ROOT / "data" / filename, "r", encoding="utf-8") as fh:
                cache[filename] = json.load(fh)
        return cache[filename]

    return load


@pytest.fixture
def temp_progress_file(tmp_path: Path) -> Path:
    return tmp_path / "progress.json"
