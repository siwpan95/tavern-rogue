"""种族共鸣的**档位差异化**：2/4/6 必须给玩家不同的东西。

改前：人类/矮人/半兽人的 2/4/6 档完全同效（等于"凑够就完事"），
玩家没有"要不要凑 4 档"的决策 —— 这是重复可玩性最伤的形态。
"""
from __future__ import annotations

import random

import pytest

from game.engine import HALF_ORC_CRIT, BattleEngine
from game.recruit import RecruitSystem
from game.hero import create_hero
from game.persistence import ProgressManager
from ui.game_manager import GameManager


def unit(name, health, attack=1, tribe=None, keywords=(), pos=0):
    data = {"name": name, "health": health, "max_health": health, "attack": attack,
            "keywords": list(keywords), "pos": pos, "initiative": 10}
    if tribe:
        data["tribe"] = tribe
    return data


def make_engine():
    return BattleEngine(log_callback=lambda _m: None)


def attack(engine, attacker, defender, turn=0):
    engine._last_battle_state = {
        "allies": [attacker], "enemies": [defender], "hero": None, "turn": turn,
    }
    attacker["_side"] = "ally"
    defender["_side"] = "enemy"
    engine.add_event({"type": "attack", "attacker": attacker, "defender": defender,
                      "defender_side": "enemy"})
    engine.process_events()


# ─── 档位表不变量 ─────────────────────────────────────────

def test_half_orc_expected_multiplier_is_within_design_band():
    """期望倍率 1.125 / 1.32 / 1.72；暴击几率的相对增幅递减、6 档收益有上限。

    注意：**期望倍率**本身是递增的（几率和倍率同时涨），所以能约束的是
    「几率的相对增幅递减」与「6 档 / 4 档 ≤ 1.4」——避免 6 档成为唯一正解。
    """
    chances = []
    expected = []
    for level in (1, 2, 3):
        chance, multiplier = HALF_ORC_CRIT[level]
        chances.append(chance)
        expected.append(1 + chance * (multiplier - 1))
    assert expected == pytest.approx([1.125, 1.32, 1.72], abs=0.01)
    assert (chances[1] / chances[0]) > (chances[2] / chances[1]), \
        "暴击几率的相对增幅应递减：%s" % chances
    assert expected[2] / expected[1] <= 1.35, "6 档相对 4 档的收益必须封顶"


# ─── 半兽人：几率与倍率都随档位 ────────────────────────────

@pytest.mark.parametrize("count,level", [(2, 1), (4, 2), (6, 3)])
def test_half_orc_resonance_profile_scales(count, level):
    engine = make_engine()
    orcs = [unit("兽%d" % i, 5, 4, tribe="half_orc") for i in range(count)]
    engine.apply_tribe_effects(orcs, None, enemies=[])
    chance, multiplier = HALF_ORC_CRIT[level]
    assert engine._tribe_resonance["half_orc_double_chance"] == pytest.approx(chance)
    assert engine._tribe_resonance["half_orc_multiplier"] == pytest.approx(multiplier)


@pytest.mark.parametrize("count,level", [(2, 1), (6, 3)])
def test_half_orc_crit_damage_uses_multiplier(count, level, monkeypatch):
    engine = make_engine()
    orcs = [unit("兽%d" % i, 5, 4, tribe="half_orc") for i in range(count)]
    engine.apply_tribe_effects(orcs, None, enemies=[])
    monkeypatch.setattr(random, "random", lambda: 0.0)  # 必定暴击
    attacker = orcs[0]
    defender = unit("靶子", 30, 1)
    attack(engine, attacker, defender)
    _chance, multiplier = HALF_ORC_CRIT[level]
    assert defender["health"] == 30 - int(round(4 * multiplier))


# ─── 矮人：首个回合减伤随档位 ──────────────────────────────

@pytest.mark.parametrize("count,reduction", [(2, 2), (4, 3), (6, 4)])
def test_dwarf_first_round_reduction_scales(count, reduction):
    engine = make_engine()
    dwarves = [unit("矮%d" % i, 10, 2, tribe="dwarf") for i in range(count)]
    engine.apply_tribe_effects(dwarves, None, enemies=[])
    assert engine._tribe_resonance["dwarf_first_round_reduction"] == reduction


def test_dwarf_reduction_only_applies_in_first_round():
    """矮人共鸣的减伤与 ARMOR **叠加**（都是抗爆发设计），但只在首个战斗回合生效。"""
    engine = make_engine()
    dwarves = [unit("矮%d" % i, 10, 2, tribe="dwarf") for i in range(4)]
    engine.apply_tribe_effects(dwarves, None, enemies=[])
    defender = dwarves[0]
    assert "ARMOR" in defender["keywords"]
    attacker = unit("敌人", 10, 6)

    # 首回合：6 攻 → ARMOR 减 1 → 5 → 矮人共鸣再减 3 → 实伤 2
    attack(engine, attacker, defender, turn=0)
    assert defender["health"] == 8

    # 第二回合起只有 ARMOR：6 - 1 = 5
    attack(engine, attacker, defender, turn=1)
    assert defender["health"] == 3


# ─── 人类：每回合额外铸币随档位 ────────────────────────────

@pytest.mark.parametrize("humans,bonus", [(0, 0), (1, 0), (2, 1), (3, 1), (4, 2), (6, 3), (8, 3)])
def test_human_gold_bonus_by_board_count(tmp_path, humans, bonus):
    progress = ProgressManager(save_file=str(tmp_path / "p.json"))
    game = GameManager(progress_manager=progress)
    game.new_game("warrior")
    game.board[:] = [unit("人%d" % i, 5, 2, tribe="human") for i in range(humans)]
    assert game.tribe_gold_bonus() == bonus


def test_human_bonus_is_included_in_turn_gold(tmp_path):
    progress = ProgressManager(save_file=str(tmp_path / "p.json"))
    game = GameManager(progress_manager=progress)
    game.new_game("warrior")
    game.gold = 0
    baseline = game.award_turn_gold()
    game.gold = 0
    game.board[:] = [unit("人%d" % i, 5, 2, tribe="human") for i in range(4)]
    boosted = game.award_turn_gold()
    assert boosted == baseline + 2


def test_human_resonance_also_sets_engine_flag():
    engine = make_engine()
    humans = [unit("人%d" % i, 5, 2, tribe="human") for i in range(2)]
    engine.apply_tribe_effects(humans, None, enemies=[])
    assert engine._tribe_resonance["human_free_refresh"] is True
    assert engine._tribe_resonance["human_gold_per_turn"] == 1


# ─── 人类免费刷新需要真的共鸣（≥2 个）────────────────────

def test_free_refresh_requires_two_humans(data_loader):
    system = RecruitSystem(create_hero("warrior"), data_loader)
    system.start_turn(5)
    system.board = [unit("人类新兵", 2, 1, tribe="human")]
    system.gold = 5
    message = system.refresh()
    assert "免费" not in message, "只有 1 个人类不算共鸣，刷新应当收费"
    assert system.gold == 4


def test_free_refresh_with_two_humans(data_loader):
    system = RecruitSystem(create_hero("warrior"), data_loader)
    system.start_turn(5)
    system.board = [unit("人类新兵", 2, 1, tribe="human"),
                    unit("人类老兵", 3, 2, tribe="human")]
    system.gold = 5
    message = system.refresh()
    assert "免费" in message
    assert system.gold == 5, "共鸣触发时不应扣铸币"
