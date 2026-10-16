"""局内存档（跑团现场）：用自研引擎 allin_engine 的 SaveLoadManager 落盘。

分工：
  · **局外进度**（职业解锁 / 进阶 / 战绩）→ `saves/progress.json`，由 `ProgressManager` 管；
  · **局内存档**（当前这一局的现场）→ `saves/runs/`，由本模块管。
两者分目录，互不覆盖。

引擎缺失时降级为仓内 JSON 直写（功能不失效，且出声提示一次）。
"""
from __future__ import annotations

import io
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(REPO_ROOT, "saves", "runs")
SLOT = 0
FALLBACK_FILE = os.path.join(SAVE_DIR, "run_slot%d.json" % SLOT)

ENGINE_AVAILABLE = False
ENGINE_ERROR = ""

try:
    from allin_engine.systems.save_load import SaveLoadManager
    ENGINE_AVAILABLE = True
except ImportError as exc:
    SaveLoadManager = None
    ENGINE_ERROR = str(exc)


class RunSnapshot:
    """SaveLoadManager 要求存档对象实现 to_dict()。"""

    def __init__(self, data: dict):
        self.data = dict(data)

    def to_dict(self) -> dict:
        return dict(self.data)


def _manager():
    if not ENGINE_AVAILABLE:
        return None
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        return SaveLoadManager(save_dir=SAVE_DIR)
    except Exception as exc:  # noqa: BLE001 - 存档不可用不该让游戏崩
        print("[TavernRogue] SaveLoadManager 不可用，局内存档降级为 JSON 直写：%s" % exc,
              file=sys.stderr)
        return None


def snapshot_from(game_manager) -> dict:
    """把当前局的状态抽成可序列化的快照。"""
    hero = game_manager.hero
    recruit = getattr(game_manager, "recruit_system", None)
    map_manager = getattr(game_manager, "map_manager", None)
    return {
        "hero_class": getattr(hero, "hero_class", None),
        "hero_health": getattr(hero, "health", 0),
        "hero_max_health": getattr(hero, "max_health", 0),
        "hero_skill_used": getattr(hero, "skill_used", False),
        "gold": game_manager.gold,
        "floor": game_manager.floor,
        "hand": list(game_manager.hand),
        "board": list(game_manager.board),
        "relics": list(game_manager.relics),
        "map_data": getattr(map_manager, "map_data", None),
        "current_node": getattr(getattr(game_manager, "current_node", None), "id", None),
        "tavern_level": getattr(recruit, "tavern_level", 1),
        "tavern_pool": list(getattr(recruit, "tavern_pool", []) or []),
    }


def apply_snapshot(game_manager, data: dict) -> bool:
    """把快照写回 GameManager（会重建英雄与地图游标）。"""

    if not data or not data.get("hero_class"):
        return False

    game_manager.new_game(data["hero_class"])
    hero = game_manager.hero
    hero.max_health = int(data.get("hero_max_health", hero.max_health))
    hero.health = int(data.get("hero_health", hero.health))
    hero.skill_used = bool(data.get("hero_skill_used", False))

    game_manager.gold = int(data.get("gold", 0))
    game_manager.floor = int(data.get("floor", 1))
    game_manager.hand[:] = list(data.get("hand", []))
    game_manager.board[:] = list(data.get("board", []))
    game_manager.relics[:] = list(data.get("relics", []))

    if data.get("map_data") and game_manager.map_manager is not None:
        game_manager.map_manager.map_data = data["map_data"]
        game_manager.map_manager.current_layer = game_manager.floor
        node_id = data.get("current_node")
        if node_id:
            for layer in data["map_data"].get("layers", []):
                for node in layer.get("nodes", []):
                    if node.get("id") == node_id:
                        game_manager.current_node = node

    recruit = getattr(game_manager, "recruit_system", None)
    if recruit is not None:
        recruit.tavern_level = int(data.get("tavern_level", recruit.tavern_level))
        recruit.tavern_pool = list(data.get("tavern_pool", []) or [])
    game_manager.sync_to_recruit()
    return True


def save_run(game_manager) -> bool:
    """保存当前局；返回是否成功。"""
    snapshot = RunSnapshot(snapshot_from(game_manager))
    manager = _manager()
    if manager is not None:
        try:
            ok = bool(manager.save(snapshot, slot=SLOT))
            if ok:
                return True
            print("[TavernRogue] SaveLoadManager 保存失败，改用 JSON 直写", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print("[TavernRogue] SaveLoadManager 异常，改用 JSON 直写：%s" % exc, file=sys.stderr)

    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        with io.open(FALLBACK_FILE, "w", encoding="utf-8") as handle:
            json.dump(snapshot.to_dict(), handle, ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        print("[TavernRogue] 局内存档写入失败：%s" % exc, file=sys.stderr)
        return False


def load_run(game_manager) -> bool:
    """读取最新局内存档；返回是否成功。"""
    data = None
    manager = _manager()
    if manager is not None:
        try:
            loaded = manager.load(slot=SLOT)
            if isinstance(loaded, dict) and "state_data" in loaded:
                loaded = loaded["state_data"]
            if isinstance(loaded, dict):
                data = loaded.get("data") if "hero_class" not in loaded else loaded
        except Exception as exc:  # noqa: BLE001
            print("[TavernRogue] SaveLoadManager 读取异常：%s" % exc, file=sys.stderr)

    if data is None and os.path.exists(FALLBACK_FILE):
        try:
            with io.open(FALLBACK_FILE, "r", encoding="utf-8") as handle:
                fallback = json.load(handle)
            data = fallback.get("data") if "hero_class" not in fallback else fallback
        except (OSError, json.JSONDecodeError) as exc:
            print("[TavernRogue] 局内存档读取失败：%s" % exc, file=sys.stderr)
            return False

    if not isinstance(data, dict):
        return False
    return apply_snapshot(game_manager, data)


def has_saved_run() -> bool:
    if os.path.exists(FALLBACK_FILE):
        return True
    manager = _manager()
    if manager is None:
        return False
    try:
        return bool(manager.has_saves())
    except Exception:  # noqa: BLE001
        return False


def clear_run() -> bool:
    """清档（新开一局时调用）。"""
    removed = False
    manager = _manager()
    if manager is not None:
        try:
            removed = bool(manager.delete(slot=SLOT)) or removed
        except Exception:  # noqa: BLE001
            pass
    if os.path.exists(FALLBACK_FILE):
        try:
            os.remove(FALLBACK_FILE)
            removed = True
        except OSError:
            pass
    return removed
