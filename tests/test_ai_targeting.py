"""目标选择：决策树策略 + 回退规则 + 对拍开关。"""
from __future__ import annotations

import random

import pytest

from game import ai_targeting
from game.engine import BattleEngine


def unit(name, health, attack=1, keywords=(), pos=0):
    return {"name": name, "health": health, "max_health": health, "attack": attack,
            "keywords": list(keywords), "pos": pos}


def test_prefers_weakest_guard():
    attacker = unit("攻击者", 10, 3)
    guards = [unit("硬守卫", 10, 2, ["GUARD"], pos=0), unit("软守卫", 3, 2, ["GUARD"], pos=1)]
    picked = ai_targeting.choose_target(attacker, guards)
    assert picked["name"] == "软守卫", "守卫里应优先打血最少的"


def test_secures_kill_over_raw_weakest():
    attacker = unit("攻击者", 10, 4)
    targets = [unit("能杀", 4, 1, pos=0), unit("血更少但已死", 0, 1, pos=1)]
    alive = [t for t in targets if t["health"] > 0]
    assert ai_targeting.choose_target(attacker, alive)["name"] == "能杀"


def test_focuses_weakest_when_nothing_killable():
    attacker = unit("弱者", 10, 1)
    targets = [unit("厚甲", 9, 1, pos=0), unit("残血", 5, 1, pos=1)]
    assert ai_targeting.choose_target(attacker, targets)["name"] == "残血"


def test_returns_none_for_empty_board():
    assert ai_targeting.choose_target(unit("攻击者", 10, 3), []) is None


def test_explain_returns_decision_path():
    attacker = unit("攻击者", 10, 3)
    target, path = ai_targeting.explain(attacker, [unit("守卫", 5, 1, ["GUARD"])])
    assert target["name"] == "守卫"
    assert path, "必须能说清走了哪条分支"


def test_engine_flag_switches_between_tree_and_legacy():
    engine = BattleEngine(log_callback=lambda _m: None)
    attacker = unit("攻击者", 10, 3)
    guards = [unit("硬守卫", 10, 2, ["GUARD"], pos=0), unit("软守卫", 3, 2, ["GUARD"], pos=1)]

    engine.use_ai_targeting = True
    assert engine._select_target(attacker, guards)["name"] == "软守卫"

    engine.use_ai_targeting = False
    random.seed(1)
    picks = {engine._select_target(attacker, guards)["name"] for _ in range(20)}
    assert picks == {"硬守卫", "软守卫"}, "回退模式必须是历史的随机规则"


def test_targeting_is_deterministic_under_fixed_seed():
    attacker = unit("攻击者", 10, 3)
    targets = [unit("甲", 5, 1, pos=0), unit("乙", 5, 1, pos=1)]

    def run():
        random.seed(99)
        engine = BattleEngine(log_callback=lambda _m: None)
        return [engine._select_target(attacker, targets)["name"] for _ in range(5)]

    assert run() == run()


def test_engine_availability_is_reported():
    """引擎装了就是 True；没装则必须留下可读的降级原因（不能静默）。"""
    assert isinstance(ai_targeting.ENGINE_AVAILABLE, bool)
    if not ai_targeting.ENGINE_AVAILABLE:
        assert ai_targeting.ENGINE_ERROR


@pytest.mark.skipif(not ai_targeting.ENGINE_AVAILABLE, reason="未安装 allin-engine")
def test_decision_tree_comes_from_self_developed_engine():
    assert ai_targeting._TREE is not None
    assert ai_targeting._TREE.decide(
        {"flying": False, "guard_present": True, "killable_present": False}
    ).label == "血最少的守卫"
