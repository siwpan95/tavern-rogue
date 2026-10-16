#!/usr/bin/env python3
"""环境与素材自检（doctor）：回答"这台机器上能正常玩吗、缺什么"。

检查项：
  1. Python 版本 / 关键依赖（pygame-ce、allin-engine）
  2. 数据文件（data/*.json 可解析、数量统计）
  3. 表现层素材（内置字体、音效/BGM）—— 缺失**不算失败**，但要出声说明降级方式
  4. 存档目录可写
  5. 无头模式能否启动（SDL dummy 下 import + 新开局）

退出码：0 无硬问题 · 1 有硬问题（缺依赖/坏数据/目录不可写）
用法：`python tools/doctor.py`（加 `--headless` 时额外做启动冒烟）
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

OK, WARN, FAIL = "OK", "WARN", "FAIL"
results = []


def record(level: str, title: str, detail: str = "") -> None:
    results.append((level, title, detail))
    print("[%s] %s%s" % (level, title, ("：%s" % detail) if detail else ""))


def check_python() -> None:
    version = "%d.%d.%d" % sys.version_info[:3]
    if sys.version_info < (3, 10):
        record(FAIL, "Python 版本 %s" % version, "需要 >= 3.10（本项目在 3.14 上开发）")
    else:
        record(OK, "Python 版本 %s" % version)


def check_dependency(module: str, friendly: str, required: bool, hint: str = "") -> None:
    found = importlib.util.find_spec(module) is not None
    if found:
        record(OK, "%s 可用" % friendly)
    elif required:
        record(FAIL, "缺少 %s" % friendly, hint or "pip install -r requirements.txt")
    else:
        record(WARN, "缺少 %s（可选）" % friendly, hint or "功能会自动降级")


def check_data() -> None:
    data_dir = os.path.join(PROJECT_ROOT, "data")
    expected = ("adventurers.json", "enemies.json", "relics.json", "events.json",
                "map_templates.json")
    for name in expected:
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            record(FAIL, "数据文件缺失：%s" % name)
            continue
        try:
            with io.open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            count = len(payload) if isinstance(payload, list) else len(payload.keys())
            record(OK, "数据 %s" % name, "%d 条" % count)
        except Exception as exc:  # noqa: BLE001 - 自检要把坏文件报出来
            record(FAIL, "数据 %s 解析失败" % name, str(exc))


def check_assets() -> None:
    from ui.renderer import FONT_SEARCH_PATHS

    if any(os.path.exists(path) for path in FONT_SEARCH_PATHS):
        record(OK, "内置字体已就位")
    else:
        record(WARN, "内置字体未下载", "跑 `python tools/fetch_font.py`；否则回退系统 CJK 字体")

    try:
        from tools.gen_audio_assets import check_assets
        missing = check_assets()
    except Exception as exc:  # noqa: BLE001
        record(WARN, "音频素材自检失败", str(exc))
        return
    if not missing:
        record(OK, "音频素材齐备")
    else:
        record(WARN, "音频素材缺 %d 项" % len(missing),
               "跑 `python tools/gen_audio_assets.py`；否则静音")


def check_saves() -> None:
    saves = os.path.join(PROJECT_ROOT, "saves")
    try:
        os.makedirs(saves, exist_ok=True)
        probe = os.path.join(saves, ".doctor_probe")
        with io.open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        record(OK, "存档目录可写", saves)
    except OSError as exc:
        record(FAIL, "存档目录不可写", str(exc))


def check_headless() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    try:
        from ui.game_manager import GameManager
        from game.persistence import ProgressManager

        game = GameManager(progress_manager=ProgressManager(
            save_file=os.path.join(PROJECT_ROOT, "saves", ".doctor_progress.json")))
        game.new_game("warrior")
        game.ensure_map()
        layers = len(game.map_manager.map_data["layers"])
        record(OK, "无头启动冒烟", "新开局成功，地图 %d 层，英雄 HP %d" % (layers, game.hero.health))
        try:
            os.remove(os.path.join(PROJECT_ROOT, "saves", ".doctor_progress.json"))
        except OSError:
            pass
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "无头启动冒烟失败", "%s: %s" % (type(exc).__name__, exc))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TavernRogue 环境与素材自检")
    parser.add_argument("--headless", action="store_true", help="额外做无头启动冒烟")
    args = parser.parse_args(argv)

    print("TavernRogue doctor · %s" % PROJECT_ROOT)
    check_python()
    check_dependency("pygame", "pygame-ce", required=True)
    check_dependency("allin_engine", "allin-engine（自研引擎）", required=False,
                     hint="pip install allin-engine；缺失时用仓内等价实现并出声提示")
    check_dependency("pyflakes", "pyflakes（静态检查）", required=False,
                     hint="pip install -r requirements-dev.txt")
    check_data()
    check_assets()
    check_saves()
    if args.headless or os.environ.get("TAVERN_ROGUE_DOCTOR_HEADLESS") == "1":
        check_headless()

    failures = [row for row in results if row[0] == FAIL]
    warnings = [row for row in results if row[0] == WARN]
    print("\n合计：%d 项通过、%d 项警告、%d 项失败" % (
        len(results) - len(failures) - len(warnings), len(warnings), len(failures)))
    if warnings:
        print("警告不影响运行（会降级），但会影响观感/难度体验。")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
