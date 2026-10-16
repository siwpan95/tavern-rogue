"""档 3 落地的机制：宝物稀有度权重、三件"改变玩法"史诗宝物、进阶阶梯。"""
from __future__ import annotations

import random

import pytest

from game.engine import BattleEngine
from game.map_manager import MapManager
from game.persistence import ADVANCEMENT_DIFFICULTY, MAX_ADVANCEMENT, ProgressManager
from game.relic_effects import RELIC_RARITY_WEIGHTS, pick_relic
from ui.game_manager import GameManager


def unit(health=10, attack=2, tribe=None, keywords=(), pos=0):
    data = {"name": "单位", "health": health, "max_health": health, "attack": attack,
            "keywords": list(keywords), "pos": pos, "initiative": 10}
    if tribe:
        data["tribe"] = tribe
    return data


def make_engine(mods=None):
    engine = BattleEngine(log_callback=lambda _m: None)
    engine._relic_mods = dict(mods or {})
    return engine


# ─── P1-3 宝物稀有度权重 ──────────────────────────────────

def test_rarity_weights_sum_to_one():
    assert sum(RELIC_RARITY_WEIGHTS.values()) == pytest.approx(1.0)


def test_relic_draws_follow_rarity_weights():
    """改前是等概率抽取，epic 实际掉率 16%；现在应按 60/30/10 抽。"""
    pool = ([{"id": "c%d" % i, "rarity": "common"} for i in range(10)]
            + [{"id": "r%d" % i, "rarity": "rare"} for i in range(10)]
            + [{"id": "e%d" % i, "rarity": "epic"} for i in range(10)])
    rng = random.Random(20261016)
    counts = {"common": 0, "rare": 0, "epic": 0}
    for _ in range(20000):
        counts[pick_relic(pool, rng=rng)["rarity"]] += 1
    total = sum(counts.values())
    assert counts["common"] / total == pytest.approx(0.60, abs=0.02)
    assert counts["rare"] / total == pytest.approx(0.30, abs=0.02)
    assert counts["epic"] / total == pytest.approx(0.10, abs=0.02)


def test_pick_relic_with_explicit_rarity():
    pool = [{"id": "c", "rarity": "common"}, {"id": "e", "rarity": "epic"}]
    assert pick_relic(pool, rarity="epic")["id"] == "e"
    assert pick_relic([], rarity="epic") is None


def test_real_pool_epic_share_is_rare(game_data):
    """真实池子里 epic 的权重占比应该明显低于等概率。"""
    rng = random.Random(7)
    pool = game_data["relics"]
    epic = sum(1 for _ in range(4000) if pick_relic(pool, rng=rng)["rarity"] == "epic")
    share = epic / 4000
    equal_share = sum(1 for r in pool if r["rarity"] == "epic") / len(pool)
    assert share == pytest.approx(RELIC_RARITY_WEIGHTS["epic"], abs=0.03)
    assert share < equal_share, "加权后 epic 掉率必须低于等概率（%.2f < %.2f）" % (share, equal_share)


# ─── P1-4 三件"改变玩法"的史诗宝物 ────────────────────────

def test_mirror_of_roles_boosts_most_common_tribe_count():
    engine = make_engine({"duplicate_tribe_resonance": 1})
    dwarves = [unit(tribe="dwarf") for _ in range(5)]
    engine.apply_tribe_effects(dwarves, None, enemies=[], relic_mods=engine._relic_mods)
    # 5 个矮人 + 棱镜 1 = 6 计数 → 等级 3 → 首回合减伤 4
    assert engine._tribe_resonance["dwarf_first_round_reduction"] == 4


def test_mirror_of_roles_without_relic_keeps_base_count():
    engine = make_engine()
    dwarves = [unit(tribe="dwarf") for _ in range(5)]
    engine.apply_tribe_effects(dwarves, None, enemies=[], relic_mods={})
    assert engine._tribe_resonance["dwarf_first_round_reduction"] == 3


def test_pact_of_ruin_grants_frenzy_at_health_cost():
    engine = make_engine({"keyword_grants": [
        {"grant": "FRENZY", "penalty_stat": "health", "penalty_pct": 0.2}]})
    allies = [unit(health=10, attack=2)]
    engine._apply_relic_battle_start(allies)
    assert "FRENZY" in allies[0]["keywords"]
    assert allies[0]["max_health"] == 8
    assert allies[0]["health"] == 8, "当前生命也要跟着降，不能靠扣上限变相回血"


def test_hourglass_escalates_attack_with_cap():
    engine = make_engine({"escalating_attack": 1, "escalating_cap": 2})
    allies = [unit(attack=2)]
    for _ in range(5):
        engine._apply_escalating_attack(allies)
    assert allies[0]["attack"] == 4, "上限 +2"


def test_new_playstyle_relics_are_in_the_pool(game_data):
    ids = {r["id"] for r in game_data["relics"]}
    assert {"mirror_of_roles", "pact_of_ruin", "hourglass_of_patience"} <= ids
    for relic in game_data["relics"]:
        if relic["id"] in ("mirror_of_roles", "pact_of_ruin", "hourglass_of_patience"):
            assert relic["rarity"] == "epic"


# ─── P1-6 进阶阶梯 ────────────────────────────────────────

def test_ladder_is_monotonic_and_layered():
    for level in range(1, MAX_ADVANCEMENT + 1):
        prev, cur = ADVANCEMENT_DIFFICULTY[level - 1], ADVANCEMENT_DIFFICULTY[level]
        for key in ("enemy_health_mult", "enemy_attack_mult", "elite_node_weight"):
            assert cur[key] >= prev[key], "第 %d 级的 %s 不该回落" % (level, key)
    # A1 是供给侧改动，A4/A5 才是"改变决策质量"的层级
    assert ADVANCEMENT_DIFFICULTY[1]["elite_node_weight"] > 1.0
    assert ADVANCEMENT_DIFFICULTY[4]["camp_heal_mult"] < 1.0
    assert ADVANCEMENT_DIFFICULTY[5]["affix_bonus"] == 1
    assert ADVANCEMENT_DIFFICULTY[5]["start_gold_penalty"] > 0


def make_game(tmp_path, advancement):
    progress = ProgressManager(save_file=str(tmp_path / "progress.json"))
    progress.set_class_advancement("warrior", advancement)
    game = GameManager(progress_manager=progress)
    game.new_game("warrior")
    return game


def test_advancement_wires_into_systems(tmp_path):
    base = make_game(tmp_path, 0)
    hard = make_game(tmp_path, 5)
    assert base.map_manager.elite_node_weight == 1.0
    assert hard.map_manager.elite_node_weight > 1.0
    assert hard.map_manager.affix_bonus == 1
    assert hard.shop_price(10) > base.shop_price(10)
    assert hard.camp_heal_mult < 1.0


def test_start_gold_penalty_applies_once(tmp_path):
    game = make_game(tmp_path, 5)
    game.gold = 0
    first = game.award_turn_gold()
    game.gold = 0
    second = game.award_turn_gold()
    assert second - first == ADVANCEMENT_DIFFICULTY[5]["start_gold_penalty"]


def test_elite_weight_changes_map_generation(data_loader):
    """精英权重必须真的影响节点生成（A1 的"精英 +60%"）。"""

    def count_elites(weight):
        manager = MapManager(data_loader)
        manager.elite_node_weight = weight
        rng_state = random.getstate()
        random.seed(4242)
        try:
            data = manager.generate_map()
        finally:
            random.setstate(rng_state)
        return sum(1 for layer in data["layers"] for node in layer["nodes"]
                   if node["type"] == "elite")

    assert count_elites(3.0) > count_elites(1.0)
