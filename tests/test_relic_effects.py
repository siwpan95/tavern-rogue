"""宝物效果：25 件宝物的每个效果都必须真的参与结算（旧版 4 个效果无人调用）。"""
from __future__ import annotations

import random

import pytest

from game.engine import BattleEngine
from game.hero import create_hero
from game.relic_effects import SUPPORTED_RELIC_EFFECT_TYPES, build_battle_mods
from game.relics import RelicSystem


def relic(effect):
    return {"id": "test_relic", "name": "测试宝物", "rarity": "common", "effect": effect}


def make_engine(mods=None):
    engine = BattleEngine(log_callback=lambda _m: None)
    engine._relic_mods = dict(mods or {})
    return engine


def unit(name, health, attack, **extra):
    data = {"name": name, "health": health, "max_health": health, "attack": attack,
            "keywords": [], "initiative": 10}
    data.update(extra)
    return data


def test_all_data_effects_are_registered(game_data):
    declared = {r["effect"]["type"] for r in game_data["relics"]}
    assert declared <= SUPPORTED_RELIC_EFFECT_TYPES, sorted(declared - SUPPORTED_RELIC_EFFECT_TYPES)


def test_build_battle_mods_sums_and_groups():
    mods = build_battle_mods([
        relic({"type": "global_attack_bonus", "value": 1}),
        relic({"type": "dodge_chance", "value": 0.15}),
        relic({"type": "global_dodge", "value": 0.05}),
        relic({"type": "double_attack_chance", "value": 0.1}),
        relic({"type": "tribe_buff", "tribe": "dwarf", "stat": "ARMOR", "value": 1}),
        relic({"type": "tribe_dodge", "tribe": "elf", "value": 0.1}),
    ])
    assert mods["global_attack_bonus"] == 1
    assert mods["dodge_chance"] == pytest.approx(0.20)
    assert mods["double_attack_chance"] == pytest.approx(0.1)
    assert mods["tribe_buffs"][0]["tribe"] == "dwarf"
    assert mods["tribe_dodges"][0]["tribe"] == "elf"


def test_global_attack_bonus_applies_at_battle_start():
    engine = make_engine({"global_attack_bonus": 1})
    allies = [unit("勇者", 5, 2)]
    engine._apply_relic_battle_start(allies)
    assert allies[0]["attack"] == 3


def test_tribe_buff_applies_only_to_that_tribe():
    engine = make_engine({"tribe_buffs": [{"tribe": "dwarf", "stat": "ARMOR", "value": 1}]})
    allies = [unit("矮人", 5, 2, tribe="dwarf"), unit("精灵", 5, 2, tribe="elf")]
    engine._apply_relic_battle_start(allies)
    assert "ARMOR" in allies[0]["keywords"]
    assert allies[1]["keywords"] == []


def test_dodge_relic_works_without_dodge_keyword(monkeypatch):
    """回归：旧版 _try_dodge 在单位没有 DODGE 时直接返回 False，宝物闪避完全无效。"""
    engine = make_engine({"dodge_chance": 0.5})
    monkeypatch.setattr(random, "random", lambda: 0.4)
    assert engine._try_dodge(unit("攻击者", 5, 2), unit("无闪避单位", 5, 2)) is True


def test_double_damage_once_per_battle():
    engine = make_engine({"double_damage_once": 1})
    attacker = unit("狂战", 10, 3)
    attacker["_side"] = "ally"
    defender = unit("靶子", 20, 1)
    defender["_side"] = "enemy"
    engine._last_battle_state = {"allies": [attacker], "enemies": [defender], "hero": None, "turn": 0}
    engine.add_event({"type": "attack", "attacker": attacker, "defender": defender,
                      "defender_side": "enemy"})
    engine.process_events()
    assert defender["health"] == 14, "第一次攻击应双倍"
    engine.add_event({"type": "attack", "attacker": attacker, "defender": defender,
                      "defender_side": "enemy"})
    engine.process_events()
    assert defender["health"] == 11, "第二次攻击恢复普通伤害"


def test_heal_on_kill_heals_attacker():
    engine = make_engine({"heal_on_kill": 2})
    attacker = unit("吸血鬼", 5, 9)
    attacker["_side"] = "ally"
    attacker["health"] = 3
    defender = unit("脆皮", 2, 1)
    defender["_side"] = "enemy"
    engine._last_battle_state = {"allies": [attacker], "enemies": [defender], "hero": None, "turn": 0}
    engine.add_event({"type": "attack", "attacker": attacker, "defender": defender,
                      "defender_side": "enemy"})
    engine.process_events()
    assert attacker["health"] == 5


def test_deathrattle_double_triggers_twice():
    engine = make_engine({"deathrattle_double": 1})
    martyr = unit("殉道者", 1, 1,
                  script={"deathrattle": {"type": "damage_random", "value": 3}})
    martyr["_side"] = "ally"
    enemy = unit("敌人", 20, 1)
    enemy["_side"] = "enemy"
    engine._last_battle_state = {"allies": [martyr], "enemies": [enemy], "hero": None, "turn": 0}
    engine.add_event({"type": "death", "unit": martyr, "side": "ally"})
    engine.process_events()
    assert enemy["health"] == 14


def test_tribe_death_damage_only_for_that_tribe():
    engine = make_engine({"tribe_death_damage": 2})
    tiefling = unit("提夫林", 1, 1, tribe="tiefling")
    tiefling["_side"] = "ally"
    human = unit("人类", 1, 1, tribe="human")
    human["_side"] = "ally"
    enemy = unit("敌人", 20, 1)
    enemy["_side"] = "enemy"
    engine._last_battle_state = {
        "allies": [tiefling, human], "enemies": [enemy], "hero": None, "turn": 0}
    engine.add_event({"type": "death", "unit": human, "side": "ally"})
    engine.process_events()
    assert enemy["health"] == 20
    engine.add_event({"type": "death", "unit": tiefling, "side": "ally"})
    engine.process_events()
    assert enemy["health"] == 18


def test_heal_per_turn_heals_hero():
    hero = create_hero("warrior")
    hero.take_damage(10)
    engine = make_engine({"heal_per_turn": 2})
    engine._apply_heal_per_turn(hero)
    assert hero.health == hero.max_health - 8


def test_tribe_fire_bonus_increases_dragonborn_resonance():
    engine = make_engine({"tribe_fire_bonus": 1})
    allies = [unit("龙%d" % i, 5, 2, tribe="dragonborn") for i in range(2)]
    enemy = unit("怪", 20, 1)
    engine.apply_tribe_effects(allies, None, enemies=[enemy])
    engine.add_event({"type": "battle_start", "allies": allies, "enemies": [enemy]})
    engine.process_events()
    assert enemy["health"] == 18, "1 级共鸣 1 点 + 宝物 1 点 = 2 点"


# ─── RelicSystem 侧的 battle_start_* 家族 ─────────────────

@pytest.fixture
def relic_system(data_loader):
    return RelicSystem(data_loader)


def test_shield_all_and_random_guard(relic_system):
    relic_system.add_relic(relic({"type": "battle_start_shield_all", "value": 1}))
    relic_system.add_relic(relic({"type": "battle_start_random_guard", "value": 1}))
    allies = [unit("甲", 5, 2), unit("乙", 5, 2)]
    relic_system.apply_battle_start_effects(allies, [unit("敌", 5, 2)])
    assert all("SHIELD" in a["keywords"] for a in allies)
    assert sum("GUARD" in a["keywords"] for a in allies) == 1


def test_battle_start_debuff_weakens_enemies(relic_system):
    relic_system.add_relic(relic({"type": "battle_start_debuff", "stat": "attack", "value": -1}))
    enemies = [unit("敌", 5, 3)]
    relic_system.apply_battle_start_effects([unit("甲", 5, 2)], enemies)
    assert enemies[0]["attack"] == 2


def test_battle_start_lifesteal_really_heals(relic_system):
    hero = create_hero("warrior")
    hero.take_damage(10)
    relic_system.add_relic(relic({"type": "battle_start_lifesteal", "value": 2}))
    relic_system.apply_battle_start_effects([unit("甲", 5, 2)], [unit("敌", 9, 2)], hero=hero)
    assert hero.health == hero.max_health - 8, "吸血必须真的回血，不能只写日志"


def test_tribe_buff_and_tribe_dodge_from_relic_system(relic_system):
    relic_system.add_relic(relic({"type": "tribe_buff", "tribe": "half_orc", "stat": "attack", "value": 1}))
    relic_system.add_relic(relic({"type": "tribe_dodge", "tribe": "elf", "value": 0.1}))
    orc = unit("兽人", 5, 3, tribe="half_orc")
    elf = unit("精灵", 5, 2, tribe="elf")
    relic_system.apply_battle_start_effects([orc, elf], [unit("敌", 5, 2)])
    assert orc["attack"] == 4
    assert elf["dodge_chance"] == pytest.approx(0.1)


def test_economy_helpers(relic_system):
    assert relic_system.get_battle_gold_bonus() == 0
    relic_system.add_relic(relic({"type": "extra_gold", "value": 1}))
    relic_system.add_relic(relic({"type": "shop_discount", "value": 1}))
    relic_system.add_relic(relic({"type": "relic_drop_bonus", "value": 0.2}))
    assert relic_system.get_battle_gold_bonus() == 1
    assert relic_system.get_shop_discount() == 1
    assert relic_system.get_relic_drop_bonus() == pytest.approx(0.2)


def test_phoenix_ash_revives_once_per_battle(relic_system):
    hero = create_hero("warrior")
    hero.health = 0
    relic_system.add_relic(relic({"type": "revive_on_death", "value": 5}))
    relic_system.reset_battle_flags()
    assert relic_system.try_hero_revive(hero) is True
    assert hero.health == 5
    assert relic_system.try_hero_revive(hero) is False, "每场战斗只能救一次"

    relic_system.reset_battle_flags()
    assert relic_system.try_hero_revive(hero) is True
