"""显示名与文案格式化：避免"同一个词在三个界面三种写法"。"""
from __future__ import annotations

TRIBE_NAMES = {
    "human": "人类",
    "elf": "精灵",
    "dwarf": "矮人",
    "dragonborn": "龙裔",
    "half_orc": "半兽人",
    "tiefling": "提夫林",
}

CLASS_NAMES = {
    "warrior": "战士",
    "rogue": "游荡者",
    "cleric": "牧师",
    "wizard": "法师",
    "warlock": "术士",
}

TIER_LABELS = {1: "1 星", 2: "2 星", 3: "3 星", 4: "4 星", 5: "5 星", 6: "6 星"}


def lineup_line(lineup, limit: int = 7) -> str:
    """把阵容快照压成一行，如「人类×3 · 矮人×2 · 精灵×1」。

    传入的 lineup 可以是 [{id,name,tribe,tier}, ...]，也可以是纯 id 列表。
    """
    counts = {}
    for unit in lineup or []:
        if isinstance(unit, dict):
            key = TRIBE_NAMES.get(unit.get("tribe"), unit.get("tribe")) or unit.get("name") or "?"
        else:
            key = str(unit)
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    parts = ["%s×%d" % (name, count) for name, count in ordered[:limit]]
    if len(ordered) > limit:
        parts.append("…")
    return " · ".join(parts)
