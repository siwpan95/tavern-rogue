"""目标选择：优先用自研引擎 allin_engine 的决策树，缺引擎时回退到仓内规则。

为什么只接这一层（SPEC-201「只接同构原语」）：
  · 选目标是**纯决策**（输入战场快照，输出一个目标），与战斗结算完全解耦；
  · 不碰 `battle_log` 的中文文案流（UI 的动画解析依赖它），也不改数值模型；
  · 引擎缺失（干净克隆里没装 allin-engine）时自动降级为仓库自带的旧规则，并且**出声**。

策略（两种模式都保持确定性，便于固定种子对拍）：
  1. 飞行 → 任意目标（随机，保留旧手感）
  2. 有守卫 → 守卫里生命最低的（旧规则是随机挑一个）
  3. 否则 → 能被本次攻击一击必杀的里生命最低的
  4. 再否则 → 生命最低的
"""
from __future__ import annotations

import random as _random
import sys

ENGINE_AVAILABLE = False
ENGINE_ERROR = ""

try:
    from allin_engine.ai.decision import build_decision_tree
    ENGINE_AVAILABLE = True
except ImportError as exc:  # 未安装 allin-engine：降级但不静默
    build_decision_tree = None
    ENGINE_ERROR = str(exc)
    print("[TavernRogue] allin-engine 不可用，目标选择降级为内置规则：%s" % exc,
          file=sys.stderr)


TARGETING_SPEC = {
    "name": "tavern_rogue_targeting",
    "root": {
        "type": "condition",
        "name": "飞行无视守卫",
        "key": "flying",
        "op": "truthy",
        "true": {"type": "action", "name": "free_choice", "label": "任意目标"},
        "false": {
            "type": "condition",
            "name": "场上有守卫",
            "key": "guard_present",
            "op": "truthy",
            "true": {"type": "action", "name": "hit_guard", "label": "血最少的守卫"},
            "false": {
                "type": "condition",
                "name": "存在可一击必杀目标",
                "key": "killable_present",
                "op": "truthy",
                "true": {"type": "action", "name": "secure_kill", "label": "可击杀目标"},
                "false": {"type": "action", "name": "focus_weakest", "label": "最脆弱目标"},
            },
        },
    },
}

_TREE = build_decision_tree(TARGETING_SPEC) if ENGINE_AVAILABLE else None


def _weakest(candidates):
    return min(candidates, key=lambda unit: (unit.get("health", 0), unit.get("pos", 0)))


def legacy_choose(attacker, alive_targets):
    """仓库自带旧规则（无引擎时的回退，也是对拍基线）。"""
    if not alive_targets:
        return None
    if "FLYING" in attacker.get("keywords", []):
        return _random.choice(alive_targets)
    guards = [t for t in alive_targets if "GUARD" in t.get("keywords", [])]
    if guards:
        return _random.choice(guards)
    return _random.choice(alive_targets)


def choose_target(attacker, alive_targets):
    """按决策树选目标；引擎不可用时直接用旧规则。"""
    if not alive_targets:
        return None
    if _TREE is None:
        return legacy_choose(attacker, alive_targets)

    guards = [t for t in alive_targets if "GUARD" in t.get("keywords", [])]
    attack = attacker.get("attack", 0)
    killable = [t for t in alive_targets if t.get("health", 1) <= attack]

    decision = _TREE.decide({
        "flying": "FLYING" in attacker.get("keywords", []),
        "guard_present": bool(guards),
        "killable_present": bool(killable),
    })

    if decision.label == "任意目标":
        return _random.choice(alive_targets)
    if decision.label == "血最少的守卫":
        return _weakest(guards)
    if decision.label == "可击杀目标":
        return _weakest(killable)
    return _weakest(alive_targets)


def explain(attacker, alive_targets):
    """返回 (目标, 决策路径) —— 对拍与调试用。"""
    target = choose_target(attacker, alive_targets)
    if _TREE is None:
        return target, ["legacy"]
    guards = [t for t in alive_targets if "GUARD" in t.get("keywords", [])]
    attack = attacker.get("attack", 0)
    killable = [t for t in alive_targets if t.get("health", 1) <= attack]
    path = _TREE.root.walk_path({
        "flying": "FLYING" in attacker.get("keywords", []),
        "guard_present": bool(guards),
        "killable_present": bool(killable),
    })
    return target, path
