"""数据完整性：JSON 之间的交叉引用必须成立（旧版只在验证脚本里查了敌人一处）。"""
from __future__ import annotations

import pytest

# 数据里允许出现的关键词（新增关键词时必须同步这里 + 引擎实现 + 设计稿）
KNOWN_KEYWORDS = {
    "GUARD", "SHIELD", "ARMOR", "POISON", "FRENZY", "DODGE", "FLYING",
    "REGENERATION", "FIRE_BREATH", "BLOOD_FURY", "CLEAVE", "OVERKILL",
}
KNOWN_TRIBES = {"human", "elf", "dwarf", "dragonborn", "half_orc", "tiefling"}
KNOWN_SCRIPT_TYPES = {
    "damage_random", "damage_all", "heal_lowest", "heal_all", "buff_random",
    "buff_all", "summon", "debuff_all", "shield_all",
}
KNOWN_EVENT_EFFECTS = {
    "heal", "damage", "damage_hero", "heal_hero", "gain_gold", "cost_gold",
    "gain_adventurer", "discover_adventurer", "gain_relic", "lose_relic",
    "sacrifice_adventurer", "coin_flip", "upgrade_board", "buff_board",
    "enchant_board", "purify_board", "regenerate_map", "reveal_map",
    "avoid_combat", "damage_all", "start_battle",
}
REQUIRED_UNIT_FIELDS = ("id", "name", "tier", "attack", "health", "keywords", "initiative")


def _units(game_data):
    return game_data["adventurers"] + game_data["enemies"]


def test_unique_ids(game_data):
    for key in ("adventurers", "enemies", "relics", "events"):
        ids = [row["id"] for row in game_data[key]]
        assert len(ids) == len(set(ids)), "%s.json 存在重复 id" % key


def test_units_have_required_fields(game_data):
    for unit in _units(game_data):
        for field in REQUIRED_UNIT_FIELDS:
            assert field in unit, "%s 缺少字段 %s" % (unit.get("id"), field)
        assert unit["tier"] >= 1, unit["id"]
        assert unit["attack"] >= 0 and unit["health"] >= 1, unit["id"]
        assert unit.get("max_health", unit["health"]) == unit["health"], \
            "%s 的 max_health 与 health 不一致" % unit["id"]


def test_adventurers_tribe_and_cost(game_data):
    for adv in game_data["adventurers"]:
        assert adv["tribe"] in KNOWN_TRIBES, "%s 种族未知: %s" % (adv["id"], adv.get("tribe"))
        assert adv.get("cost", 0) > 0, "%s 缺少 cost" % adv["id"]
        assert adv["tier"] <= 6, adv["id"]


def test_keywords_are_known(game_data):
    for unit in _units(game_data):
        for kw in unit.get("keywords", []):
            assert kw in KNOWN_KEYWORDS, "%s 出现未登记关键词 %s" % (unit["id"], kw)


def test_scripts_have_known_types(game_data):
    for unit in _units(game_data):
        for slot, script in (unit.get("script") or {}).items():
            if not isinstance(script, dict):
                continue
            assert script.get("type") in KNOWN_SCRIPT_TYPES, \
                "%s.%s 效果类型未知: %s" % (unit["id"], slot, script.get("type"))


def test_enemy_pools_have_elite_and_boss(game_data):
    enemies = game_data["enemies"]
    assert any(e.get("is_elite") for e in enemies), "精英池为空"
    assert any(e.get("is_boss") for e in enemies), "Boss 池为空"
    for enemy in enemies:
        assert enemy.get("reward_gold", 0) > 0, "%s 缺 reward_gold" % enemy["id"]


def test_relic_effects_are_declared(game_data):
    rarities = {"common", "rare", "epic"}
    for relic in game_data["relics"]:
        assert relic.get("rarity") in rarities, "%s 稀有度未知" % relic["id"]
        assert relic.get("effect", {}).get("type"), "%s 缺 effect.type" % relic["id"]


def test_relic_effect_types_are_wired(game_data):
    """宝物效果必须能被引擎/宝物系统真正消费，不能只是数据里的一个字符串。

    `game.relic_effects.SUPPORTED_RELIC_EFFECT_TYPES` 是「已接线」的唯一登记处；
    新增宝物效果时必须同时加实现并登记，否则这里报红。
    """
    from game.relic_effects import SUPPORTED_RELIC_EFFECT_TYPES

    declared = {r["effect"]["type"] for r in game_data["relics"]}
    missing = sorted(declared - set(SUPPORTED_RELIC_EFFECT_TYPES))
    assert not missing, "以下宝物效果没有实现：%s" % missing


def test_events_are_well_formed(game_data):
    for event in game_data["events"]:
        assert event.get("name"), event.get("id")
        options = event.get("options") or []
        assert options, "%s 没有选项" % event["id"]
        for option in options:
            assert option.get("text"), event["id"]
            assert "effects" in option, "%s 的选项 %s 缺 effects 字段" % (event["id"], option["text"])
            effects = option.get("effects") or {}
            unknown = sorted(set(effects) - KNOWN_EVENT_EFFECTS)
            assert not unknown, "%s 出现未登记事件效果 %s" % (event["id"], unknown)


def test_event_battle_targets_exist(game_data):
    """回归：曾经 events.json 引用了不存在的敌人 `mimic`，事件战斗直接断链。"""
    enemy_ids = {e["id"] for e in game_data["enemies"]}
    for event in game_data["events"]:
        for option in event.get("options", []):
            battle = (option.get("effects") or {}).get("start_battle")
            if not battle:
                continue
            assert "enemy" in battle, "%s 的 start_battle 缺 enemy" % event["id"]
            assert battle["enemy"] in enemy_ids, \
                "%s 引用了不存在的敌人 %s" % (event["id"], battle["enemy"])


def test_event_effects_have_handlers(game_data):
    """每种事件效果都必须有实现（旧版有 6 种效果是死数据，玩家选了没反应）。"""
    from game.event_effects import SUPPORTED_EFFECT_KEYS

    declared = set()
    for event in game_data["events"]:
        for option in event.get("options", []):
            declared |= set((option.get("effects") or {}).keys())
    missing = sorted(declared - set(SUPPORTED_EFFECT_KEYS))
    assert not missing, "以下事件效果没有实现：%s" % missing


def test_map_templates_cover_nine_layers(game_data):
    template = game_data["map_templates"]
    layers = template["layers"]
    assert [layer["layer"] for layer in layers] == list(range(1, len(layers) + 1)), \
        "层号必须从 1 开始连续"
    node_types = template["node_types"]
    for layer in layers:
        assert layer["nodes"] >= 1, layer["name"]
        if layer["type"] == "fixed":
            assert layer["type"] in node_types or layer.get("fixed_type"), layer["name"]
        else:
            for node_type in layer.get("possible_types", []):
                assert node_type in node_types, "层 %s 出现未知节点类型 %s" % (layer["name"], node_type)


def test_adventurer_tier_coverage(game_data):
    """每档星级都要有可选单位，否则酒馆等级提升后池子会空。"""
    tiers = {adv["tier"] for adv in game_data["adventurers"]}
    assert tiers == set(range(1, 7)), "冒险者星级覆盖不全: %s" % sorted(tiers)


def test_every_tribe_has_two_units_per_tier(game_data):
    """每个种族在每个星级至少 2 个单位 —— 否则玩家凑不出 2/4/6 档共鸣。

    这是 2026-10-16 内容补洞的验收判据（矮人/龙裔的 2/4/6 星、半兽人/提夫林的 1/3/5 星
    原本各只有 1 个，共鸣只能靠运气凑）。
    """
    counts = {}
    for adv in game_data["adventurers"]:
        counts[(adv["tribe"], adv["tier"])] = counts.get((adv["tribe"], adv["tier"]), 0) + 1
    thin = sorted(key for key, value in counts.items() if value < 2)
    assert not thin, "以下 种族×星级 少于 2 个单位：%s" % thin


def test_every_keyword_has_enough_carriers(game_data):
    """关键词至少 4 个承载单位，才值得作为一个"名词"存在（Brode 判据）。

    低于 4 个的关键词玩家一辈子见不到几次，等于白占一个词表位。
    """
    import collections

    carriers = collections.Counter()
    for adv in game_data["adventurers"]:
        for keyword in set(adv.get("keywords", [])):
            carriers[keyword] += 1
    thin = sorted(keyword for keyword, count in carriers.items() if count < 4)
    assert not thin, "以下关键词的承载单位少于 4 个：%s（计数：%s）" % (thin, dict(carriers))


@pytest.mark.parametrize("tribe", sorted(KNOWN_TRIBES))
def test_every_tribe_has_mid_tier_units(game_data, tribe):
    units = [a for a in game_data["adventurers"] if a["tribe"] == tribe]
    assert len(units) >= 4, "%s 种族可用单位过少（%d）" % (tribe, len(units))
