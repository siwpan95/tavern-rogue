"""自定义规则（mutators）：把 N 个修饰符变成 2^N 种玩法。

设计依据（调研）：小体量游戏最便宜的内容放大器 —— 玩家"自己给自己加难度"和
"游戏告诉你该打进阶 5 了"是两种完全不同的心理体验（StS 的 Custom Mode / Hades 的 Heat）。

用法：
    · 游戏内：`python run_gui.py --mutator one_hp --mutator midas`
    · 代码内：`GameManager.new_game('warrior', mutators=['midas'])`
    · 未登记的规则名会**响亮报错**（不静默忽略）

每条规则的 `effects` 是纯数据，由 GameManager/systems 消费：
    hero_max_hp        英雄最大生命（绝对值）
    start_gold         开局铸币（叠加在常规起始之上）
    board_limit        场上单位上限
    enemy_health_mult  敌人生命倍率
    enemy_attack_mult  敌人攻击倍率
    gold_mult          战斗铸币倍率
    shop_price_mult    商店价格倍率
    camp_heal_mult     营地治疗倍率
    relic_drop_bonus   宝物掉落率加成
    ally_attack        全队攻击加成（战斗开始时）
    ally_initiative    全队先攻加成
    post_battle_heal   每场战斗后英雄恢复
"""
from __future__ import annotations

MUTATORS = {
    "one_hp": {
        "name": "一击必死", "type": "neg",
        "description": "英雄最大生命变为 5（其余不变）。",
        "effects": {"hero_max_hp": 5},
    },
    "lethality": {
        "name": "致命", "type": "mix",
        "description": "你的队伍攻击 +3，敌人攻击也 +25%。",
        "effects": {"ally_attack": 3, "enemy_attack_mult": 1.25},
    },
    "midas": {
        "name": "点金", "type": "mix",
        "description": "战斗铸币翻倍，但敌人生命 +30%。",
        "effects": {"gold_mult": 2.0, "enemy_health_mult": 1.3},
    },
    "binary": {
        "name": "二元", "type": "neg",
        "description": "敌人生命 -20%，但你的场上上限只有 4。",
        "effects": {"enemy_health_mult": 0.8, "board_limit": 4},
    },
    "allstar": {
        "name": "全明星", "type": "pos",
        "description": "开局多 10 铸币，但敌人攻击 +20%。",
        "effects": {"start_gold": 10, "enemy_attack_mult": 1.2},
    },
    "ironman": {
        "name": "铁人", "type": "neg",
        "description": "营地治疗完全无效，改为每场战斗后恢复 3 点生命。",
        "effects": {"camp_heal_mult": 0.0, "post_battle_heal": 3},
    },
    "swift": {
        "name": "疾风", "type": "pos",
        "description": "全队先攻 +3，但敌人生命 +15%。",
        "effects": {"ally_initiative": 3, "enemy_health_mult": 1.15},
    },
    "greedy": {
        "name": "贪婪", "type": "neg",
        "description": "宝物掉落率 +50%，但商店价格 +50%。",
        "effects": {"relic_drop_bonus": 0.5, "shop_price_mult": 1.5},
    },
}

EFFECT_KEYS = frozenset({
    "hero_max_hp", "start_gold", "board_limit", "enemy_health_mult", "enemy_attack_mult",
    "gold_mult", "shop_price_mult", "camp_heal_mult", "relic_drop_bonus",
    "ally_attack", "ally_initiative", "post_battle_heal",
})


def list_mutators() -> list:
    """给 UI/帮助文本用的清单。"""
    return [{"id": key, **value} for key, value in sorted(MUTATORS.items())]


def parse_mutators(names) -> list:
    """把命令行/存档里的名字解析成 id 列表；未登记的名字**响亮失败**。"""
    resolved, unknown = [], []
    for name in names or []:
        key = str(name).strip().lower()
        if not key:
            continue
        if key in MUTATORS:
            if key not in resolved:
                resolved.append(key)
        else:
            unknown.append(name)
    if unknown:
        raise ValueError("未登记的自定义规则：%s（可用：%s）"
                         % ("、".join(map(str, unknown)), "、".join(sorted(MUTATORS))))
    return resolved


def describe(names) -> str:
    """一行人类可读描述（结算屏/主菜单用）。"""
    parts = []
    for key in names or []:
        entry = MUTATORS.get(key)
        if entry:
            parts.append("%s（%s）" % (entry["name"], entry["description"]))
    return " · ".join(parts) if parts else "无"


def build_mods(names) -> dict:
    """把多条规则的 effects 合并成一份修正表（同类数值相加、'限制/倍率'类相乘）。"""
    mods = {key: 0 for key in EFFECT_KEYS}
    mult_keys = ("enemy_health_mult", "enemy_attack_mult", "gold_mult",
                 "shop_price_mult", "camp_heal_mult")
    for key in mult_keys:
        mods[key] = 1.0
    mods["hero_max_hp"] = 0        # 0 = 不改
    mods["board_limit"] = 0        # 0 = 不改
    mods["relic_drop_bonus"] = 0.0

    for name in names or []:
        effects = MUTATORS.get(name, {}).get("effects", {})
        for key, value in effects.items():
            if key not in EFFECT_KEYS:
                raise ValueError("规则 %s 里的 effects 键未登记：%s" % (name, key))
            if key in mult_keys:
                mods[key] *= value
            else:
                mods[key] += value
    return mods
