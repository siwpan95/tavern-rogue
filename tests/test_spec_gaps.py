"""规格（`be like.txt`）里此前未落地条目的验收：

  · §9 冒险日志：最佳通关阵容 / 最高伤害 / 最爱种族
  · §6 第 9 层宝藏密室：携带特定物品才能进入（否则跳过）
  · §8 示例事件「幽灵的恳求」
  · §11 游戏内帮助文本
"""
from __future__ import annotations

import pytest

from game.map_manager import MapManager
from game.persistence import ProgressManager
from ui.game_manager import GameManager
from ui.scenes.help_scene import build_pages


@pytest.fixture
def progress(tmp_path):
    return ProgressManager(save_file=str(tmp_path / "progress.json"))


def unit(unit_id, name, tribe, tier=2):
    return {"id": unit_id, "name": name, "tribe": tribe, "tier": tier}


def make_game(tmp_path, hero_class="warrior"):
    game = GameManager(progress_manager=ProgressManager(save_file=str(tmp_path / "p.json")))
    game.new_game(hero_class)
    return game


# ─── §9 冒险日志 ─────────────────────────────────────────

def test_journal_records_best_lineup_damage_and_favorite_tribe(progress):
    progress.record_run("warrior", False, 5, ["boots_of_speed"],
                        stats={"damage_best": 12}, lineup=[unit("human_a", "人类新兵", "human")])
    progress.data["journal"]["tribe_counts"] = {"human": 3, "elf": 1}
    progress.save()

    journal = progress.get_journal()
    assert journal["max_damage"] == 12
    assert journal["favorite_tribe"] == "human"
    assert journal["favorite_tribe_count"] == 3
    assert len(journal["best_lineup"]) == 1

    lines = progress.journal_lines()
    assert any("最佳阵容" in line for line in lines)
    assert any("最高单场伤害：12" in line for line in lines)
    assert any("最爱种族：人类" in line for line in lines)


def test_journal_prefers_victory_then_floor(progress):
    progress.record_run("warrior", False, 7, [], stats={"damage_best": 30},
                        lineup=[unit("a", "甲", "human")])
    progress.record_run("cleric", True, 8, [], stats={"damage_best": 5},
                        lineup=[unit("b", "乙", "dwarf")])
    progress.record_run("rogue", False, 3, [], stats={"damage_best": 99},
                        lineup=[unit("c", "丙", "elf")])
    journal = progress.get_journal()
    assert journal["best_lineup"][0]["id"] == "b", "通关的局优先成为最佳阵容（即使伤害更低）"
    assert journal["max_damage"] == 99, "最高伤害与阵容独立统计"
    assert "通关" in journal["best_lineup_note"]


def test_game_manager_reports_damage_and_lineup(tmp_path):
    game = make_game(tmp_path)
    game.battle_engine.last_battle_damage = 17
    game.record_battle("ally", "monster")
    assert game.run_stats["damage_best"] == 17
    assert game.run_stats["damage_total"] == 17

    game.board[:] = [unit("human_a", "人类新兵", "human"), unit("elf_a", "精灵弓手", "elf")]
    game.record_run(False, 4)
    record = game.progress.data["run_history"][-1]
    assert {u["tribe"] for u in record["lineup"]} == {"human", "elf"}
    assert any("最佳阵容" in line for line in game.run_summary_lines())


def test_journal_lines_are_used_by_the_summary(tmp_path):
    game = make_game(tmp_path)
    game.record_run(True, 8)
    lines = game.run_summary_lines()
    assert any("最爱种族" in line for line in lines)


# ─── §6 第 9 层：携带特定物品才能进入 ─────────────────────

def test_layer9_requires_the_vault_key(data_loader):
    manager = MapManager(data_loader)
    assert manager.is_layer_accessible(9, []) is False
    assert manager.is_layer_accessible(9, ["vault_key"]) is True
    assert manager.is_layer_accessible(7, []) is True, "其余层无进入条件"
    assert "密室钥匙" in manager.locked_layer_reason(9)
    assert manager.locked_layer_reason(7) == ""


def test_clearing_layer8_without_key_skips_layer9(data_loader):
    manager = MapManager(data_loader)
    manager.map_data = manager.generate_map()
    assert manager._accessible_next_layer(8, []) >= 9
    assert manager._accessible_next_layer(8, ["vault_key"]) == 9


def test_locked_layer_refuses_node_selection(tmp_path, data_loader):
    game = make_game(tmp_path)
    game.ensure_map()
    game.map_manager.current_layer = 9
    game.floor = 9
    node = game.get_current_layer()["nodes"][0]
    assert game.select_map_node(node["id"]) is None, "没钥匙时选点必须被拒绝"
    assert game.current_node is None
    assert game.layer_lock_reason(9)

    game.add_relic({"id": "vault_key", "name": "密室钥匙", "rarity": "rare", "effect": {}})
    assert game.select_map_node(node["id"]) is not None, "有钥匙后可以进入"


def test_vault_key_is_obtainable_and_registered(game_data):
    relics = {r["id"]: r for r in game_data["relics"]}
    assert "vault_key" in relics
    from game.relic_effects import SUPPORTED_RELIC_EFFECT_TYPES
    assert relics["vault_key"]["effect"]["type"] in SUPPORTED_RELIC_EFFECT_TYPES


# ─── §8 示例事件「幽灵的恳求」────────────────────────────

def test_ghost_plea_event_exists_with_spec_options(game_data):
    events = {e["id"]: e for e in game_data["events"]}
    assert "ghost_plea" in events, "规格 §8 的三个示例事件必须都在"
    assert {"magic_fountain", "greedy_mimic"} <= set(events)
    ghost = events["ghost_plea"]
    assert len(ghost["options"]) == 2
    effects = ghost["options"][0]["effects"]
    assert "lose_relic" in effects and "gain_adventurer" in effects


# ─── §11 游戏内帮助 ──────────────────────────────────────

def test_help_pages_cover_every_keyword_in_the_data(game_data):
    """帮助文本必须覆盖数据里出现的**每一个**关键词（新增关键词时这里会红）。"""
    from ui.scenes.help_scene import KEYWORD_HELP

    keywords = sorted({k for a in game_data["adventurers"] for k in a.get("keywords", [])} |
                      {k for e in game_data["enemies"] for k in e.get("keywords", [])})
    missing = [k for k in keywords if k not in KEYWORD_HELP]
    assert not missing, "帮助文本缺少关键词说明：%s" % missing


def test_help_pages_cover_core_systems():
    pages = build_pages()
    assert len(pages) >= 8
    titles = [title for title, _lines in pages]
    assert "核心循环" in titles and "种族共鸣" in titles and "进阶与自定义规则" in titles
    text = "\n".join("\n".join(lines) for _title, lines in pages)
    for token in ("铸币", "三连", "密室钥匙", "自定义规则", "图鉴", "种子"):
        assert token in text, "帮助文本缺少 %s" % token


def test_help_scene_renders():
    from ui.app import TavernRogueApp

    app = TavernRogueApp()
    app.scenes.switch_to("help")
    app.scenes.update(0.016)
    app.scenes.draw()
    assert app.scenes.current.__class__.__name__ == "HelpScene"
    app.scenes.switch_to("help", page=99)  # 越界页码要被夹住
    app.scenes.draw()
