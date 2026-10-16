"""宝物效果的登记表与战斗修正构建。

本模块回答两个问题：
  1. **数据里每个宝物效果有没有实现** —— `SUPPORTED_RELIC_EFFECT_TYPES` 是唯一登记处，
     测试与设计稿按它校验（历史问题：25 件宝物里有 4 个效果的方法全仓没有调用者）。
  2. **开战前要把哪些数值交给战斗引擎** —— `build_battle_mods()` 把宝物列表折成
     引擎消费的修正字典，避免引擎反向依赖 RelicSystem。
"""
from __future__ import annotations

# 效果类型 -> 实现落点（新增类型时必须同时补实现、补登记、补用例）
RELIC_EFFECT_HANDLERS = {
    "heal_per_turn": "engine.simulate_battle（每回合结束治疗英雄）",
    "double_attack_chance": "engine._handle_attack（先攻）",
    "double_damage_once": "engine._handle_attack（每场战斗一次双倍）",
    "heal_on_kill": "engine._handle_attack（击杀回血）",
    "deathrattle_double": "engine._handle_death（亡语触发两次）",
    "global_attack_bonus": "engine._apply_relic_battle_start",
    "dodge_chance": "engine._try_dodge",
    "global_dodge": "engine._try_dodge",
    "tribe_dodge": "engine._try_dodge",
    "tribe_buff": "engine._apply_relic_battle_start",
    "tribe_fire_bonus": "engine._handle_battle_start（火焰吐息/龙裔共鸣 +N）",
    "tribe_death_damage": "engine._handle_death（提夫林阵亡暗影伤害）",
    "battle_shield_once": "relics.apply_battle_start_effects",
    "battle_start_damage": "relics.apply_battle_start_effects",
    "battle_start_buff": "relics.apply_battle_start_effects",
    "battle_start_lifesteal": "relics.apply_battle_start_effects",
    "battle_start_debuff": "relics.apply_battle_start_effects",
    "battle_start_shield_all": "relics.apply_battle_start_effects",
    "battle_start_random_guard": "relics.apply_battle_start_effects",
    "extra_gold": "BattleScene._victory / node_handler._apply_battle_rewards",
    "shop_discount": "GameManager.shop_price",
    "relic_drop_bonus": "rewards.RewardSystem.generate_battle_rewards",
    "revive_on_death": "GameManager.damage_hero -> RelicSystem.try_hero_revive",
    # 2026-10-16 新增：三件"改变玩法"的史诗宝物
    "duplicate_tribe_resonance": "engine.apply_tribe_effects（最多种族计数 +1）",
    "keyword_for_stat_penalty": "engine._apply_relic_battle_start（给全队关键词，代价是最大生命）",
    "escalating_attack": "engine 每回合结束（全队攻击递增，有上限）",
}

SUPPORTED_RELIC_EFFECT_TYPES = frozenset(RELIC_EFFECT_HANDLERS)

# 稀有度掉落权重：改前 25 件宝物是**等概率**抽取，于是 4 件 epic 各占 4%、
# 合计 16%，"稀有度"名存实亡。对齐 StS 的 50/33/17 与 Balatro 的 70/25/5 之间。
RELIC_RARITY_WEIGHTS = {"common": 0.60, "rare": 0.30, "epic": 0.10}


def pick_relic(relics, rarity=None, rng=None):
    """按稀有度权重抽一件宝物（rarity 指定时只看该档）。

    这是宝物掉落的**唯一**入口 —— 奖励系统与发现机制都走这里，
    避免"两处各写一套概率"那种漂移。
    """
    import random as _random

    rng = rng or _random
    if not relics:
        return None
    if rarity:
        pool = [r for r in relics if r.get("rarity") == rarity]
        return rng.choice(pool).copy() if pool else None

    rarities = [r.get("rarity", "common") for r in relics]
    weights = [RELIC_RARITY_WEIGHTS.get(r, 0.1) for r in rarities]
    return rng.choices(relics, weights=weights, k=1)[0].copy()

# 直接作用在单位上的 battle_start_* 家族由 RelicSystem 处理，不进引擎修正字典
BATTLE_START_EFFECT_TYPES = frozenset({
    "battle_shield_once", "battle_start_damage", "battle_start_buff",
    "battle_start_lifesteal", "battle_start_debuff", "battle_start_shield_all",
    "battle_start_random_guard",
})


def build_battle_mods(relics) -> dict:
    """把宝物列表折成战斗引擎消费的修正字典（纯函数，不改动入参）。"""
    mods = {
        "global_attack_bonus": 0,
        "dodge_chance": 0.0,
        "double_attack_chance": 0.0,
        "double_damage_once": 0,
        "heal_on_kill": 0,
        "heal_per_turn": 0,
        "deathrattle_double": 0,
        "tribe_fire_bonus": 0,
        "tribe_death_damage": 0,
        "tribe_buffs": [],
        "tribe_dodges": [],
        "extra_gold": 0,
        "relic_drop_bonus": 0.0,
        "shop_discount": 0,
        "revive_on_death": 0,
        # 改变玩法类
        "duplicate_tribe_resonance": 0,
        "escalating_attack": 0,
        "escalating_cap": 0,
        "keyword_grants": [],
    }

    for relic in relics or []:
        effect = (relic or {}).get("effect") or {}
        effect_type = effect.get("type")
        value = effect.get("value", 0) or 0

        if effect_type in ("dodge_chance", "global_dodge"):
            mods["dodge_chance"] += float(value)
        elif effect_type == "tribe_buff":
            mods["tribe_buffs"].append(dict(effect))
        elif effect_type == "tribe_dodge":
            mods["tribe_dodges"].append(dict(effect))
        elif effect_type == "keyword_for_stat_penalty":
            mods["keyword_grants"].append(dict(effect))
        elif effect_type == "escalating_attack":
            mods["escalating_attack"] = max(mods["escalating_attack"], int(value))
            mods["escalating_cap"] = max(mods["escalating_cap"], int(effect.get("cap", 5)))
        elif effect_type in mods and isinstance(mods[effect_type], (int, float)):
            mods[effect_type] += value

    return mods
