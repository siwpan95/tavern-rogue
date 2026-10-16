"""战斗引擎：关键词、种族共鸣、自动战斗契约。

旧版 `test_final_verification.py` 用了错误的构造签名（`BattleEngine(None, Hero(...))`）、
不存在的职业名（`mage`/`ranger`）和过期的私有方法签名，既抓不到缺陷也证明不了正确性。
本文件按**当前真实 API** 编写，并覆盖此前完全没有测试的路径。
"""
from __future__ import annotations

import random

import pytest

from game.engine import BattleEngine
from game.hero import create_hero


def make_unit(name, health, attack, keywords=(), tribe=None, **extra):
    unit = {
        "name": name,
        "health": health,
        "max_health": health,
        "attack": attack,
        "keywords": list(keywords),
        "initiative": extra.pop("initiative", 10),
    }
    if tribe:
        unit["tribe"] = tribe
    unit.update(extra)
    return unit


def make_engine(data_loader=None, hero=None):
    engine = BattleEngine(log_callback=lambda _message: None, data_loader=data_loader)
    if hero is not None:
        engine._last_battle_state = {"allies": [], "enemies": [], "hero": hero, "turn": 0}
    return engine


def attach(engine, allies, enemies, hero=None, turn=0):
    engine._last_battle_state = {"allies": allies, "enemies": enemies, "hero": hero, "turn": turn}
    for index, unit in enumerate(allies):
        unit.setdefault("_side", "ally")
        unit.setdefault("pos", index)
    for index, unit in enumerate(enemies):
        unit.setdefault("_side", "enemy")
        unit.setdefault("pos", index)
    return engine._last_battle_state


def attack(engine, attacker, defender, defender_side="enemy"):
    engine.add_event({
        "type": "attack", "attacker": attacker,
        "defender": defender, "defender_side": defender_side,
    })
    engine.process_events()


# ─── 关键词 ───────────────────────────────────────────────

def test_regeneration_heals_and_caps_at_max_health():
    engine = make_engine()
    unit = make_unit("再生兵", 3, 1, ["REGENERATION"])
    unit["max_health"] = 8
    engine.add_event({"type": "turn_start", "unit": unit, "allies": [unit], "enemies": []})
    engine.process_events()
    assert unit["health"] == 5

    unit["health"] = 7
    engine.add_event({"type": "turn_start", "unit": unit, "allies": [unit], "enemies": []})
    engine.process_events()
    assert unit["health"] == 8, "再生不能超过 max_health"


def test_guard_is_preferred_target():
    engine = make_engine()
    attacker = make_unit("攻击者", 5, 2)
    guard = make_unit("守卫", 5, 1, ["GUARD"])
    plain = make_unit("杂兵", 5, 1)
    assert engine._select_target(attacker, [plain, guard]) is guard


def test_flying_ignores_guard():
    engine = make_engine()
    flyer = make_unit("飞侠", 5, 2, ["FLYING"])
    guard = make_unit("守卫", 5, 1, ["GUARD"])
    picked = {engine._select_target(flyer, [guard])["name"] for _ in range(20)}
    assert picked == {"守卫"}, "只有一个候选时飞行也只能选它（不因守卫而跳过）"


def test_shield_absorbs_exactly_one_hit():
    engine = make_engine()
    defender = make_unit("护盾兵", 10, 1, ["SHIELD"])
    attacker = make_unit("攻击者", 10, 3)
    attach(engine, [attacker], [defender])

    attack(engine, attacker, defender)
    assert defender["health"] == 10 and "SHIELD" not in defender["keywords"]

    attack(engine, attacker, defender)
    assert defender["health"] == 7


def test_armor_reduces_damage_but_not_below_one():
    engine = make_engine()
    defender = make_unit("铁卫", 10, 1, ["ARMOR"])
    attacker = make_unit("攻击者", 10, 3)
    attach(engine, [attacker], [defender])
    attack(engine, attacker, defender)
    assert defender["health"] == 8

    weak = make_unit("弱者", 10, 1)
    attach(engine, [weak], [defender])
    attack(engine, weak, defender)
    assert defender["health"] == 7, "护甲减伤后的最低伤害应为 1"


def test_poison_kills_outright():
    engine = make_engine()
    defender = make_unit("巨兽", 99, 1)
    attacker = make_unit("刺客", 10, 1, ["POISON"])
    attach(engine, [attacker], [defender])
    attack(engine, attacker, defender)
    assert defender["health"] <= 0


def test_dodge_avoids_attack(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(random, "random", lambda: 0.0)  # 必定小于任何闪避率
    defender = make_unit("游侠", 10, 1, ["DODGE"])
    attacker = make_unit("攻击者", 10, 3)
    attach(engine, [attacker], [defender])
    attack(engine, attacker, defender)
    assert defender["health"] == 10


def test_relic_dodge_chance_is_applied(monkeypatch):
    engine = make_engine()
    engine._extra_dodge_chance = 0.5
    monkeypatch.setattr(random, "random", lambda: 0.3)
    defender = make_unit("无闪避单位", 10, 1)
    attacker = make_unit("攻击者", 10, 3)
    attach(engine, [attacker], [defender])
    attack(engine, attacker, defender)
    assert defender["health"] == 10, "宝物提供的额外闪避必须参与判定"


def test_frenzy_attacks_twice():
    engine = make_engine()
    attacker = make_unit("狂战士", 10, 3, ["FRENZY"])
    defender = make_unit("靶子", 20, 1)
    attach(engine, [attacker], [defender])
    attack(engine, attacker, defender)
    assert defender["health"] == 14, "连击应在同一次结算里再打一次"


def test_blood_fury_buffs_surviving_allies():
    engine = make_engine()
    survivor = make_unit("血怒战士", 5, 2, ["BLOOD_FURY"])
    dead = make_unit("阵亡者", 1, 1)
    attach(engine, [survivor, dead], [make_unit("敌人", 10, 1)])
    engine.add_event({"type": "death", "unit": dead, "side": "ally"})
    engine.process_events()
    assert survivor["attack"] == 4


@pytest.mark.parametrize("keyword", ["SWEEP", "CLEAVE"])
def test_cleave_hits_both_neighbours(keyword):
    """横扫：设计稿用 CLEAVE，引擎历史实现叫 SWEEP —— 两个名字都必须生效。"""
    engine = make_engine()
    attacker = make_unit("横扫者", 10, 3, [keyword])
    left = make_unit("左", 10, 1)
    middle = make_unit("中", 10, 1)
    right = make_unit("右", 10, 1)
    attach(engine, [attacker], [left, middle, right])
    attack(engine, attacker, middle)
    assert middle["health"] == 7
    assert left["health"] == 9 and right["health"] == 9


def test_overkill_splashes_excess_damage():
    engine = make_engine()
    attacker = make_unit("过杀者", 10, 8, ["OVERKILL"])
    victim = make_unit("脆皮", 2, 1)
    bystander = make_unit("旁观者", 10, 1)
    attach(engine, [attacker], [victim, bystander])
    attack(engine, attacker, victim)
    assert bystander["health"] < 10


def test_deathrattle_damage_random():
    engine = make_engine()
    martyr = make_unit("殉道者", 1, 1, script={"deathrattle": {"type": "damage_random", "value": 3}})
    enemy = make_unit("敌人", 10, 1)
    attach(engine, [martyr], [enemy])
    engine.add_event({"type": "death", "unit": martyr, "side": "ally"})
    engine.process_events()
    assert enemy["health"] == 7


def test_deathrattle_damage_all():
    engine = make_engine()
    martyr = make_unit("殉道者", 1, 1, script={"deathrattle": {"type": "damage_all", "value": 2}})
    enemies = [make_unit("甲", 10, 1), make_unit("乙", 10, 1)]
    attach(engine, [martyr], enemies)
    engine.add_event({"type": "death", "unit": martyr, "side": "ally"})
    engine.process_events()
    assert [e["health"] for e in enemies] == [8, 8]


def test_deathrattle_summon_uses_data_loader(data_loader):
    engine = make_engine(data_loader)
    summoner = make_unit(
        "召唤者", 1, 1,
        script={"deathrattle": {"type": "summon", "summon_id": "dwarf_warrior", "count": 2}},
    )
    allies = [summoner]
    attach(engine, allies, [make_unit("敌人", 10, 1)])
    engine.add_event({"type": "death", "unit": summoner, "side": "ally"})
    engine.process_events()
    summoned = [u for u in allies if u.get("_summoned")]
    assert len(summoned) == 2
    assert all(u["name"] == "矮人战士" for u in summoned)


def test_fire_breath_hits_all_opponents():
    engine = make_engine()
    dragons = [make_unit("龙A", 10, 5, ["FIRE_BREATH"]), make_unit("龙B", 10, 5, ["FIRE_BREATH"])]
    heroes = [make_unit("勇者1", 20, 3), make_unit("勇者2", 20, 3)]
    attach(engine, heroes, dragons)
    engine.add_event({"type": "battle_start", "allies": heroes, "enemies": dragons})
    engine.process_events()
    assert [h["health"] for h in heroes] == [14, 14]


def test_enemy_battle_start_heal_all():
    engine = make_engine()
    healer = make_unit("萨满", 10, 1, script={"battle_start": {"type": "heal_all", "value": 2}})
    hurt = make_unit("巨魔", 5, 1)
    hurt["health"] = 3
    ally = make_unit("勇者", 10, 1)
    attach(engine, [ally], [healer, hurt])
    engine.add_event({"type": "battle_start", "allies": [ally], "enemies": [healer, hurt]})
    engine.process_events()
    assert hurt["health"] == 5


def test_cleric_resurrects_once_per_battle():
    """牧师复活：每场一次，且只恢复 50% 生命（平衡实测：满血复活 = 白送一个单位）。"""
    hero = create_hero("cleric")
    hero.has_healing_word = True
    engine = make_engine(hero=hero)
    fallen = make_unit("友军", 4, 1)
    engine._last_battle_state = {
        "allies": [fallen], "enemies": [make_unit("敌人", 10, 1)], "hero": hero, "turn": 0,
    }
    engine.add_event({"type": "death", "unit": fallen, "side": "ally"})
    engine.process_events()
    assert fallen["health"] == 4, "牧师把阵亡友军救回满血（代价是 1 点英雄生命）"
    assert hero.has_healing_word is False, "治疗祷言每场战斗只能用一次"

    fallen["health"] = 0
    engine.add_event({"type": "death", "unit": fallen, "side": "ally"})
    engine.process_events()
    assert fallen["health"] == 0


def test_rogue_passive_grants_initiative():
    """游荡者被动「敏捷+3」→ 全队先攻 +1（此前被动只写在界面上，代码里没有）。"""
    hero = create_hero("rogue")
    engine = make_engine(hero=hero)
    allies = [make_unit("甲", 5, 2, initiative=10), make_unit("乙", 5, 2, initiative=8)]
    enemies = [make_unit("敌", 5, 2, initiative=9)]
    engine.simulate_battle(allies, enemies, hero)
    assert [a["initiative"] for a in allies] == [11, 9]


def test_class_passives_are_implemented():
    """五个职业的被动必须真的存在（界面文案曾与代码不符）。"""
    assert create_hero("warrior").max_health == 33
    assert create_hero("rogue").PASSIVE_INITIATIVE_BONUS == 1
    assert create_hero("cleric").max_health == 33
    assert create_hero("cleric").PASSIVE_TEAM_HEALTH_BONUS == 1
    assert create_hero("wizard").MISSILE_DAMAGE == 4
    warlock = create_hero("warlock")
    assert warlock.max_health == 28
    assert warlock.PASSIVE_ATTACK_BONUS == 1


def test_warlock_passive_buffs_team_attack():
    """术士以 −3 生命为代价换全队 +1 攻击（改前它战斗面零贡献，是最弱职业）。"""
    hero = create_hero("warlock")
    engine = make_engine(hero=hero)
    allies = [make_unit("甲", 5, 2), make_unit("乙", 5, 3)]
    enemies = [make_unit("敌", 5, 2)]
    engine.simulate_battle(allies, enemies, hero)
    assert [a["attack"] for a in allies] == [3, 4]


def test_wizard_missile_damage_scales_with_passive():
    hero = create_hero("wizard")
    enemies = [make_unit("敌A", 10, 1), make_unit("敌B", 10, 1)]
    hero.use_skill({"allies": [], "enemies": enemies})
    assert sum(10 - e["health"] for e in enemies) == hero.MISSILE_DAMAGE


# ─── 种族共鸣 ─────────────────────────────────────────────

@pytest.mark.parametrize("count,level", [(2, 1), (3, 1), (4, 2), (6, 3), (7, 3)])
def test_dragonborn_resonance_level_scales_with_count(count, level):
    engine = make_engine()
    units = [make_unit("龙%d" % i, 5, 2, tribe="dragonborn") for i in range(count)]
    engine.apply_tribe_effects(units, None, enemies=[])
    assert engine._tribe_resonance["dragonborn_fire_damage"] == level


@pytest.mark.parametrize("count,level", [(2, 1), (4, 2), (6, 3)])
def test_tiefling_resonance_level_scales_with_count(count, level):
    engine = make_engine()
    units = [make_unit("魔%d" % i, 5, 2, tribe="tiefling") for i in range(count)]
    engine.apply_tribe_effects(units, None, enemies=[])
    assert engine._tribe_resonance["tiefling_death_damage"] == level


def test_dragonborn_resonance_deals_damage_at_battle_start():
    engine = make_engine()
    allies = [make_unit("龙%d" % i, 5, 2, tribe="dragonborn") for i in range(4)]
    enemy = make_unit("怪", 20, 1)
    engine.apply_tribe_effects(allies, None, enemies=[enemy])
    engine.add_event({"type": "battle_start", "allies": allies, "enemies": [enemy]})
    engine.process_events()
    assert enemy["health"] == 18, "4 个龙裔 = 2 级共鸣 = 2 点火焰伤害"


def test_tiefling_resonance_triggers_on_ally_death():
    engine = make_engine()
    tieflings = [make_unit("魔%d" % i, 5, 2, tribe="tiefling") for i in range(2)]
    enemy = make_unit("敌人", 20, 1)
    engine.apply_tribe_effects(tieflings, None, enemies=[enemy])
    engine._last_battle_state = {"allies": tieflings, "enemies": [enemy], "hero": None, "turn": 0}
    engine.add_event({"type": "death", "unit": tieflings[0], "side": "ally"})
    engine.process_events()
    assert enemy["health"] == 19


def test_elf_resonance_grants_dodge_and_dwarf_grants_armor():
    engine = make_engine()
    elves = [make_unit("精灵%d" % i, 5, 2, tribe="elf") for i in range(2)]
    dwarves = [make_unit("矮人%d" % i, 5, 2, tribe="dwarf") for i in range(2)]
    engine.apply_tribe_effects(elves + dwarves, None, enemies=[])
    assert all("DODGE" in u["keywords"] for u in elves)
    assert all(u["dodge_chance"] > 0 for u in elves)
    assert all("ARMOR" in u["keywords"] for u in dwarves)


def test_human_resonance_marks_free_refresh():
    engine = make_engine()
    humans = [make_unit("人%d" % i, 5, 2, tribe="human") for i in range(2)]
    engine.apply_tribe_effects(humans, None, enemies=[])
    assert engine._tribe_resonance.get("human_free_refresh") is True


def test_tribe_resonance_is_reset_between_battles():
    engine = make_engine()
    dragonborns = [make_unit("龙%d" % i, 5, 2, tribe="dragonborn") for i in range(2)]
    engine.apply_tribe_effects(dragonborns, None, enemies=[])
    assert engine._tribe_resonance
    engine.apply_tribe_effects([make_unit("散兵", 5, 2)], None, enemies=[])
    assert engine._tribe_resonance == {}


# ─── 自动战斗整体契约 ──────────────────────────────────────

def make_skirmish():
    allies = [
        make_unit("勇者1", 10, 3, initiative=10),
        make_unit("勇者2", 8, 2, ["GUARD"], initiative=5),
    ]
    enemies = [
        make_unit("哥布林", 6, 2, initiative=9),
        make_unit("兽人", 9, 3, initiative=7),
    ]
    for index, unit in enumerate(allies):
        unit["pos"] = index
    return allies, enemies


def test_simulate_battle_returns_side_and_log():
    engine = make_engine()
    allies, enemies = make_skirmish()
    result, logs = engine.simulate_battle(allies, enemies, create_hero("warrior"))
    assert result in ("ally", "enemy", "draw")
    assert logs and isinstance(logs[0], str)
    for unit in allies + enemies:
        assert "_side" in unit, "结算后每个单位都应带 _side，供位置相关效果使用"


def test_simulate_battle_terminates_and_has_no_negative_health():
    engine = make_engine()
    allies, enemies = make_skirmish()
    engine.simulate_battle(allies, enemies, create_hero("warrior"))
    assert len(engine.battle_log) < 2000, "战斗不应无限循环"
    assert all(u["health"] <= u["max_health"] for u in allies + enemies)


def test_simulate_battle_is_deterministic_for_same_seed():
    def run():
        random.seed(777)
        engine = make_engine()
        allies, enemies = make_skirmish()
        result, _logs = engine.simulate_battle(allies, enemies, create_hero("warrior"))
        return result, [u["health"] for u in allies + enemies]

    assert run() == run()


def test_tribe_effects_survive_simulate_battle_reset():
    """apply_tribe_effects 在 simulate_battle 之前调用，reset() 不能把它清掉。"""
    engine = make_engine()
    allies, enemies = make_skirmish()
    dragonborns = [make_unit("龙%d" % i, 6, 2, tribe="dragonborn") for i in range(2)]
    engine.apply_tribe_effects(allies, None, enemies=enemies)
    engine.apply_tribe_effects(dragonborns, None, enemies=enemies)
    engine.simulate_battle(dragonborns, enemies, create_hero("warrior"))
    assert engine._tribe_resonance.get("dragonborn_fire_damage") == 1


# ─── 2026-10-16 新增的 6 个关键词 ──────────────────────────

def test_aegis_absorbs_before_health():
    """神盾：吸收值 = min(3, 20% 最大生命)，先吃吸收、不溢出到生命。"""
    engine = make_engine()
    defender = make_unit("神盾兵", 20, 1, ["AEGIS"])
    attacker = make_unit("攻击者", 10, 5)
    attach(engine, [attacker], [defender])
    engine.add_event({"type": "battle_start", "allies": [attacker], "enemies": [defender]})
    engine.process_events()
    assert defender["_aegis"] == 3

    attack(engine, attacker, defender)
    assert defender["health"] == 18, "5 点伤害中 3 点被吸收"
    assert defender["_aegis"] == 0


def test_aegis_caps_at_three_and_does_not_stack_with_shield():
    engine = make_engine()
    defender = make_unit("神盾巨人", 40, 1, ["AEGIS", "SHIELD"])
    engine.add_event({"type": "battle_start", "allies": [], "enemies": [defender]})
    engine.process_events()
    assert defender["_aegis"] == 3, "吸收上限 3"

    attacker = make_unit("攻击者", 10, 5)
    attach(engine, [attacker], [defender])
    attack(engine, attacker, defender)
    assert defender["health"] == 40, "力场护盾优先，神盾不该被消费"
    assert defender["_aegis"] == 3


def test_thorns_reflects_half_of_damage_taken():
    engine = make_engine()
    defender = make_unit("荆棘卫", 20, 1, ["THORNS"])
    attacker = make_unit("攻击者", 10, 4)
    attach(engine, [attacker], [defender])
    attack(engine, attacker, defender)
    assert defender["health"] == 16
    assert attacker["health"] == 8, "反弹 4 // 2 = 2 点"


def test_thorns_does_not_recurse():
    """两个荆棘单位互打不能无限递归。"""
    engine = make_engine()
    a = make_unit("荆棘甲", 20, 4, ["THORNS"])
    b = make_unit("荆棘乙", 20, 4, ["THORNS"])
    attach(engine, [a], [b])
    attack(engine, a, b)
    assert a["health"] == 18 and b["health"] == 16


def test_intimidate_weakens_attacker_up_to_three_stacks():
    engine = make_engine()
    defender = make_unit("威吓者", 30, 1, ["INTIMIDATE"])
    attacker = make_unit("攻击者", 30, 5)
    attach(engine, [attacker], [defender])

    attack(engine, attacker, defender)
    assert attacker["_intimidate_debuff"] == 1

    attack(engine, attacker, defender)
    attack(engine, attacker, defender)
    attack(engine, attacker, defender)
    assert attacker["_intimidate_debuff"] == 3, "上限 3 层"
    assert defender["health"] == 30 - 4 - 4 - 3 - 3, "削弱后的伤害递减"


def test_aura_buffs_only_adjacent_allies():
    engine = make_engine()
    banner = make_unit("旗手", 10, 1, ["AURA"], pos=0)
    neighbor = make_unit("邻兵", 10, 3, pos=1)
    far = make_unit("远兵", 10, 3, pos=3)
    enemy = make_unit("敌人", 10, 1, pos=0)
    for index, unit_ in enumerate([banner, neighbor, far]):
        unit_["_side"] = "ally"
    engine._last_battle_state = {"allies": [banner, neighbor, far], "enemies": [enemy], "hero": None, "turn": 0}
    engine.add_event({"type": "battle_start", "allies": [banner, neighbor, far], "enemies": [enemy]})
    engine.process_events()
    assert (neighbor["attack"], neighbor["max_health"]) == (4, 11)
    assert (far["attack"], far["max_health"]) == (3, 10), "不相邻不受益"


def test_warrior_spirit_grows_every_two_kills():
    engine = make_engine()
    killer = make_unit("战魂兵", 30, 9, ["WARRIOR_SPIRIT"])
    victims = [make_unit("靶%d" % i, 2, 1, pos=i) for i in range(4)]
    attach(engine, [killer], victims)
    for victim in victims:
        attack(engine, killer, victim)
    assert killer["attack"] == 11, "4 次击杀 = +2 攻击"
    assert killer["_ws_bonus"] == 2


def test_martyr_grants_shields_on_death():
    engine = make_engine()
    martyr = make_unit("殉道者", 1, 1, ["MARTYR"])
    friends = [make_unit("友%d" % i, 5, 2, pos=i) for i in range(3)]
    enemy = make_unit("敌人", 10, 1)
    allies = [martyr] + friends
    attach(engine, allies, [enemy])
    engine.add_event({"type": "death", "unit": martyr, "side": "ally"})
    engine.process_events()
    shielded = [f for f in friends if "SHIELD" in f["keywords"]]
    assert len(shielded) == 2, "随机 2 名存活友军获得护盾"
