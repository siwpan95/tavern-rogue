"""招募系统：正常购买、术士生命分流、三连。"""
from __future__ import annotations

import pytest

from game.recruit import RecruitSystem
from game.hero import create_hero


@pytest.fixture
def recruit(data_loader):
    system = RecruitSystem(create_hero("warrior"), data_loader)
    system.start_turn(10)
    return system


def first_affordable(system):
    for index, card in enumerate(system.tavern_pool):
        if card.get("cost", 3) <= system.gold:
            return index
    return None


def test_recruit_with_gold(recruit):
    index = first_affordable(recruit)
    assert index is not None
    gold_before = recruit.gold
    message = recruit.recruit(index)
    assert message.startswith("成功招募")
    assert recruit.gold < gold_before
    assert recruit.hand, "购买成功必须进手牌"


def test_recruit_without_gold_is_loud(recruit):
    recruit.gold = 0
    message = recruit.recruit(0)
    assert "铸币不足" in message
    assert recruit.hand == []


def test_warlock_can_still_buy_with_gold(data_loader):
    """回归：旧版术士只要血量够就会被"生命分流"分支拦下，永远买不到东西。"""
    system = RecruitSystem(create_hero("warlock"), data_loader)
    system.start_turn(10)
    index = first_affordable(system)
    assert index is not None
    message = system.recruit(index)
    assert message.startswith("成功招募"), message
    assert system.hand


def test_warlock_life_tap_pays_with_health(data_loader):
    system = RecruitSystem(create_hero("warlock"), data_loader)
    system.start_turn(3)
    cost = system.tavern_pool[0].get("cost", 3)
    system.gold = 0
    hero = system.hero
    hp_before = hero.health
    message = system.use_life_tap(0)
    assert message.startswith("使用生命分流")
    assert hero.health == hp_before - cost * 2
    assert system.hand


def test_non_warlock_cannot_life_tap(recruit):
    assert "不能使用生命分流" in recruit.use_life_tap(0)


def test_triple_merges_three_copies(data_loader):
    system = RecruitSystem(create_hero("warrior"), data_loader)
    system.start_turn(10)
    card = system.tavern_pool[0]
    system.hand = [dict(card), dict(card), dict(card)]
    triple_id = system.check_triple()
    assert triple_id == card["id"]
    message = system.perform_triple(triple_id)
    assert "三连" in message
    # 设计：3 张合成 1 张精英 + 发现 1 张（所以手牌是 2 张，不是 1 张）
    assert len(system.hand) == 2
    assert any(c["name"].startswith("精英") for c in system.hand), system.hand
    elite = next(c for c in system.hand if c["name"].startswith("精英"))
    assert elite["attack"] == card["attack"] * 2
    assert elite["health"] == card["health"] * 2
