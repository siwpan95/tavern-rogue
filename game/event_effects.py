"""事件效果统一实现 —— 事件效果的**唯一**落点。

历史上有三份互相漂移的实现：
  · `game/events.py::EventSystem._apply_effects`
  · `ui/scenes/event_scene.py::EventScene._choose`
  · `game/node_handler.py::NodeHandler._apply_event_effects`
结果是数据里 21 种效果有 6 种（start_battle / damage_all / buff_board /
reveal_map / discover_adventurer / avoid_combat）在三处**都没有实现** ——
玩家点了选项，界面只打印一句 outcome 就完事。

本模块把它们收成一处：
  · 纯数据进、纯结果出，不持有 UI 引用，CLI 与 pygame 场景共用；
  · `SUPPORTED_EFFECT_KEYS` 是「已实现效果」的登记表，测试与门禁按它校验
    data/events.json 里的每个效果键都有实现（防再造死数据）。
"""
from __future__ import annotations

import copy
import random


# 已实现的事件效果键（新增数据前先在这里登记 + 写实现 + 补用例）
SUPPORTED_EFFECT_KEYS = frozenset({
    "heal", "heal_hero", "damage", "damage_hero", "damage_all",
    "gain_gold", "cost_gold",
    "gain_adventurer", "discover_adventurer", "sacrifice_adventurer",
    "gain_relic", "lose_relic",
    "coin_flip", "upgrade_board", "buff_board", "enchant_board",
    "purify_board", "regenerate_map", "reveal_map", "avoid_combat",
    "start_battle",
})

# 事件把随从打到最低多少血就停手（事件不该直接灭团）
MIN_UNIT_HEALTH_AFTER_EVENT = 1
NEGATIVE_KEYWORDS = frozenset({"POISON"})


class EventEffectResolver:
    """把一次事件选项的 `effects` 落到宿主状态上。

    宿主只需要交出**可写的容器**（hand/board/relics 列表）与几个回调，
    因此 pygame 场景、NodeHandler 与测试都能复用同一份语义。
    """

    def __init__(self, *, hero=None, hand=None, board=None, relics=None,
                 data_loader=None, map_manager=None, gold=0,
                 max_hand=10, max_relics=6,
                 can_add_to_hand=None, can_add_relic=None):
        self.hero = hero
        self.hand = hand if hand is not None else []
        self.board = board if board is not None else []
        self.relics = relics if relics is not None else []
        self.data_loader = data_loader
        self.map_manager = map_manager
        self.gold = gold
        self.max_hand = max_hand
        self.max_relics = max_relics
        self._can_add_to_hand = can_add_to_hand or (lambda: len(self.hand) < self.max_hand)
        self._can_add_relic = can_add_relic or (lambda: len(self.relics) < self.max_relics)

        self.logs: list[str] = []
        self.pending_battle: dict | None = None
        self.avoided_battle = False
        self.regenerated_map = False
        self.revealed_map = False

    # ─── 对外入口 ─────────────────────────────────────────

    def apply(self, effects: dict | None) -> "EventEffectResolver":
        effects = effects or {}
        for key, value in effects.items():
            if key not in SUPPORTED_EFFECT_KEYS:
                # 响亮失败：未实现的效果不能被默默忽略
                self.logs.append(f"[未实现的事件效果: {key}]")
                continue
            handler = getattr(self, "_effect_%s" % key)
            if handler(effects, value) is False:
                # 效果自带前置条件不满足（如铸币不足）→ 中止该选项的后续效果
                break
        return self

    # ─── 资源类 ───────────────────────────────────────────

    def _effect_heal(self, effects, value):
        self._heal_hero(effects.get("heal", 0))

    def _effect_heal_hero(self, effects, value):
        # 献祭选项自带 heal_hero，避免与 _effect_sacrifice_adventurer 重复治疗
        if "sacrifice_adventurer" in effects:
            return
        self._heal_hero(effects.get("heal_hero", 0))

    def _ensure_gold(self, amount):
        return self.gold >= amount

    def _effect_gain_gold(self, effects, value):
        self.gold += int(effects.get("gain_gold", 0))
        self.logs.append("获得 %d 枚铸币" % int(effects.get("gain_gold", 0)))

    def _effect_cost_gold(self, effects, value):
        cost = int(effects.get("cost_gold", 0))
        if not self._ensure_gold(cost):
            self.logs.append("铸币不足（需要 %d，当前 %d），该选项未生效" % (cost, self.gold))
            return False
        self.gold -= cost
        self.logs.append("花费 %d 枚铸币" % cost)
        return True

    # ─── 伤害 / 治疗 ──────────────────────────────────────

    def _heal_hero(self, amount):
        amount = int(amount or 0)
        if amount <= 0 or self.hero is None:
            return
        healed = self.hero.heal(amount)
        healed = amount if healed is None else healed
        self.logs.append("恢复 %d 点生命值" % healed)

    def _effect_damage(self, effects, value):
        self._damage_hero(effects.get("damage", 0))

    def _effect_damage_hero(self, effects, value):
        self._damage_hero(effects.get("damage_hero", 0))

    def _damage_hero(self, amount):
        amount = int(amount or 0)
        if amount <= 0 or self.hero is None:
            return
        self.hero.take_damage(amount)
        self.logs.append("受到 %d 点伤害" % amount)

    def _effect_damage_all(self, effects, value):
        damage = int(effects.get("damage_all", 0))
        if damage <= 0 or not self.board:
            return
        for unit in self.board:
            floor = MIN_UNIT_HEALTH_AFTER_EVENT
            unit["health"] = max(floor, unit.get("health", floor) - damage)
        self.logs.append("队伍全员受到 %d 点伤害（不会低于 %d 点生命）"
                         % (damage, MIN_UNIT_HEALTH_AFTER_EVENT))

    # ─── 单位 ─────────────────────────────────────────────

    def _load_units(self, tier=None):
        if not self.data_loader:
            return []
        try:
            adventurers = self.data_loader("adventurers.json") or []
        except Exception as exc:  # noqa: BLE001 - 数据缺失不该让事件崩掉
            self.logs.append("无法读取冒险者数据：%s" % exc)
            return []
        if tier is None:
            return adventurers
        return [unit for unit in adventurers if unit.get("tier") == tier]

    def _grant_adventurer(self, spec, verb):
        spec = spec if isinstance(spec, dict) else {}
        tier = spec.get("tier")
        pool = self._load_units(tier)
        if not pool:
            self.logs.append("没有可用的 %s 星冒险者" % tier)
            return
        if not self._can_add_to_hand():
            self.logs.append("手牌已满，%s失败" % verb)
            return
        card = copy.deepcopy(random.choice(pool))
        self.hand.append(card)
        self.logs.append("%s%s（%d 星）" % (verb, card["name"], card.get("tier", 0)))

    def _effect_gain_adventurer(self, effects, value):
        self._grant_adventurer(effects.get("gain_adventurer"), "获得冒险者 ")

    def _effect_discover_adventurer(self, effects, value):
        # 简化实现：直接给一名该星级冒险者（三选一 UI 见设计稿 P1 条目）
        self._grant_adventurer(effects.get("discover_adventurer"), "发现冒险者 ")

    def _effect_sacrifice_adventurer(self, effects, value):
        if not effects.get("sacrifice_adventurer"):
            return
        if not self.hand:
            self.logs.append("没有可献祭的冒险者")
            return
        lost = self.hand.pop(0)
        self.logs.append("献祭了 %s" % lost["name"])
        if "heal_hero" in effects:
            self._heal_hero(effects.get("heal_hero", 0))

    def _effect_upgrade_board(self, effects, value):
        spec = effects.get("upgrade_board") or {}
        stat = spec.get("stat", "attack")
        amount = int(spec.get("value", 1))
        if not self.board:
            self.logs.append("场上没有冒险者")
            return
        for unit in self.board:
            unit[stat] = unit.get(stat, 0) + amount
            if stat == "health":
                unit["max_health"] = unit.get("max_health", unit.get("health", 0)) + amount
        self.logs.append("所有场上冒险者 %s+%d" % (stat, amount))

    def _effect_buff_board(self, effects, value):
        spec = effects.get("buff_board") or {}
        keyword = spec.get("keyword")
        if not keyword or not self.board:
            return
        for unit in self.board:
            keywords = unit.setdefault("keywords", [])
            if keyword not in keywords:
                keywords.append(keyword)
        self.logs.append("所有场上冒险者获得 %s" % keyword)

    def _effect_enchant_board(self, effects, value):
        spec = effects.get("enchant_board") or {}
        keyword = spec.get("keyword")
        if not keyword or not self.board:
            return
        targets = self.board if spec.get("all", False) else [random.choice(self.board)]
        for unit in targets:
            keywords = unit.setdefault("keywords", [])
            if keyword not in keywords:
                keywords.append(keyword)
        self.logs.append("为 %d 名冒险者附加 %s" % (len(targets), keyword))

    def _effect_purify_board(self, effects, value):
        if not effects.get("purify_board"):
            return
        for unit in self.board:
            unit["keywords"] = [k for k in unit.get("keywords", []) if k not in NEGATIVE_KEYWORDS]
        self.logs.append("净化了场上单位的负面状态")

    # ─── 宝物 ─────────────────────────────────────────────

    def _effect_gain_relic(self, effects, value):
        spec = effects.get("gain_relic")
        if not spec:
            return
        if not self._can_add_relic():
            self.logs.append("宝物已满，无法获得新宝物")
            return
        relic_id = spec.get("id") if isinstance(spec, dict) else None
        relic = None
        if self.data_loader:
            try:
                relics = self.data_loader("relics.json") or []
            except Exception as exc:  # noqa: BLE001
                self.logs.append("无法读取宝物数据：%s" % exc)
                return
            if relic_id:
                relic = next((r for r in relics if r.get("id") == relic_id), None)
            elif relics:
                relic = random.choice(relics)
        if not relic:
            self.logs.append("没有可获得的宝物")
            return
        self.relics.append(copy.deepcopy(relic))
        self.logs.append("获得宝物 %s" % relic["name"])

    def _effect_lose_relic(self, effects, value):
        count = int(effects.get("lose_relic", 0) or 0)
        if count <= 0:
            return
        if len(self.relics) < count:
            self.logs.append("宝物不足 %d 件，无法失去" % count)
            return
        for _ in range(count):
            lost = self.relics.pop(0)
            self.logs.append("失去了宝物 %s" % lost["name"])

    # ─── 随机与地图 ───────────────────────────────────────

    def _effect_coin_flip(self, effects, value):
        if not effects.get("coin_flip"):
            return
        if random.choice([True, False]):
            self._heal_hero(5)
            self.logs.append("硬币正面！")
        else:
            self._damage_hero(3)
            self.logs.append("硬币反面！")

    def _effect_regenerate_map(self, effects, value):
        if not effects.get("regenerate_map"):
            return
        if self.map_manager is not None:
            self.map_manager.generate_map()
        self.regenerated_map = True
        self.logs.append("地图已重塑")

    def _effect_reveal_map(self, effects, value):
        if not effects.get("reveal_map"):
            return
        self.revealed_map = True
        if self.map_manager is None:
            self.logs.append("获得了地图情报")
            return
        revealed = 0
        layer = self.map_manager.get_current_layer()
        for node in (layer or {}).get("nodes", []):
            if not node.get("revealed"):
                self.map_manager.reveal_node(node["id"])
                revealed += 1
        self.logs.append("揭示本层 %d 个节点" % revealed)

    # ─── 战斗 ─────────────────────────────────────────────

    def _effect_avoid_combat(self, effects, value):
        if effects.get("avoid_combat"):
            self.avoided_battle = True

    def _effect_start_battle(self, effects, value):
        battle = effects.get("start_battle") or {}
        enemy_id = battle.get("enemy")
        if not enemy_id:
            self.logs.append("[事件战斗缺少 enemy 字段]")
            return
        if self.avoided_battle:
            self.logs.append("已避开这场战斗")
            return
        self.pending_battle = {
            "enemy": enemy_id,
            "reward_gold": int(battle.get("reward_gold", 0) or 0),
        }
        self.logs.append("战斗一触即发：%s" % enemy_id)


def resolve_event_effects(effects, **kwargs) -> EventEffectResolver:
    """便捷函数：一次性结算。"""
    return EventEffectResolver(**kwargs).apply(effects)
