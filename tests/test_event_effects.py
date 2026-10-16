"""事件效果解析器：每种效果都要真的落地（旧版有 6 种是纯数据、点了没反应）。"""
from __future__ import annotations

import pytest

from game.event_effects import SUPPORTED_EFFECT_KEYS, EventEffectResolver
from game.hero import create_hero


class FakeMapManager:
    def __init__(self):
        self.regenerated = 0
        self.revealed = []
        self.node_ids = ["layer1_node0", "layer1_node1"]

    def generate_map(self):
        self.regenerated += 1
        return {"layers": []}

    def get_current_layer(self):
        return {"nodes": [{"id": nid, "revealed": nid in self.revealed} for nid in self.node_ids]}

    def reveal_node(self, node_id):
        if node_id not in self.revealed:
            self.revealed.append(node_id)
        return True


@pytest.fixture
def resolver_factory(data_loader):
    def build(**overrides):
        state = {
            "hero": create_hero("warrior"),
            "hand": [],
            "board": [],
            "relics": [],
            "data_loader": data_loader,
            "map_manager": FakeMapManager(),
            "gold": 20,
        }
        state.update(overrides)
        return EventEffectResolver(**state)

    return build


def test_supported_keys_cover_data(game_data):
    declared = set()
    for event in game_data["events"]:
        for option in event.get("options", []):
            declared |= set((option.get("effects") or {}).keys())
    assert declared <= SUPPORTED_EFFECT_KEYS, sorted(declared - SUPPORTED_EFFECT_KEYS)


def test_heal_and_damage_hero(resolver_factory):
    resolver = resolver_factory()
    resolver.hero.take_damage(5)
    hp = resolver.hero.health
    resolver.apply({"heal": 3})
    assert resolver.hero.health == hp + 3
    resolver.apply({"damage_hero": 2})
    assert resolver.hero.health == hp + 1


def test_gain_and_cost_gold(resolver_factory):
    resolver = resolver_factory(gold=10)
    resolver.apply({"gain_gold": 5})
    assert resolver.gold == 15
    resolver.apply({"cost_gold": 4, "gain_relic": {"random": True}})
    assert resolver.gold == 11
    assert len(resolver.relics) == 1


def test_cost_gold_shortfall_blocks_the_option(resolver_factory):
    resolver = resolver_factory(gold=1)
    resolver.apply({"cost_gold": 5, "gain_relic": {"random": True}})
    assert resolver.gold == 1
    assert resolver.relics == [], "铸币不足时后续效果不应生效"
    assert any("铸币不足" in line for line in resolver.logs)


def test_gain_adventurer_pulls_from_data(resolver_factory):
    resolver = resolver_factory()
    resolver.apply({"gain_adventurer": {"tier": 3, "random": True}})
    assert len(resolver.hand) == 1
    assert resolver.hand[0]["tier"] == 3


def test_discover_adventurer_is_not_a_dead_key(resolver_factory):
    resolver = resolver_factory()
    resolver.apply({"discover_adventurer": {"tier": 3}})
    assert len(resolver.hand) == 1


def test_sacrifice_adventurer_heals_when_asked(resolver_factory):
    resolver = resolver_factory()
    resolver.hand.append({"id": "x", "name": "替罪羊"})
    resolver.hero.take_damage(8)
    hp = resolver.hero.health
    resolver.apply({"sacrifice_adventurer": True, "heal_hero": 5})
    assert resolver.hand == []
    assert resolver.hero.health == hp + 5


def test_damage_all_floors_at_one_hp(resolver_factory):
    board = [{"name": "甲", "health": 3, "max_health": 3}, {"name": "乙", "health": 1, "max_health": 3}]
    resolver = resolver_factory(board=board)
    resolver.apply({"damage_all": 2})
    assert [u["health"] for u in board] == [1, 1], "事件不该把队伍直接打到 0 血"


def test_upgrade_board_and_buff_board(resolver_factory):
    board = [{"name": "甲", "attack": 2, "health": 2, "max_health": 2, "keywords": []}]
    resolver = resolver_factory(board=board)
    resolver.apply({"upgrade_board": {"stat": "attack", "value": 1}})
    assert board[0]["attack"] == 3
    resolver.apply({"buff_board": {"keyword": "FRENZY"}})
    assert "FRENZY" in board[0]["keywords"]


def test_enchant_and_purify(resolver_factory):
    board = [{"name": "甲", "keywords": ["POISON"]}, {"name": "乙", "keywords": []}]
    resolver = resolver_factory(board=board)
    resolver.apply({"enchant_board": {"keyword": "SHIELD", "all": True}})
    assert all("SHIELD" in u["keywords"] for u in board)
    resolver.apply({"purify_board": True})
    assert all("POISON" not in u["keywords"] for u in board)


def test_reveal_and_regenerate_map(resolver_factory):
    map_manager = FakeMapManager()
    resolver = resolver_factory(map_manager=map_manager)
    resolver.apply({"reveal_map": True})
    assert len(map_manager.revealed) == 2
    resolver.apply({"regenerate_map": True})
    assert map_manager.regenerated == 1


def test_start_battle_becomes_pending_battle(resolver_factory):
    resolver = resolver_factory()
    resolver.apply({"start_battle": {"enemy": "mimic", "reward_gold": 15}})
    assert resolver.pending_battle == {"enemy": "mimic", "reward_gold": 15}


def test_avoid_combat_suppresses_battle(resolver_factory):
    resolver = resolver_factory()
    resolver.apply({"cost_gold": 5, "avoid_combat": True, "start_battle": {"enemy": "mimic"}})
    assert resolver.avoided_battle is True
    assert resolver.pending_battle is None


def test_unknown_effect_is_loud(resolver_factory):
    resolver = resolver_factory()
    resolver.apply({"teleport_to_final_boss": True})
    assert any("未实现的事件效果" in line for line in resolver.logs)


def test_empty_effects_is_a_noop(resolver_factory):
    resolver = resolver_factory()
    before = (resolver.gold, list(resolver.hand), list(resolver.relics))
    resolver.apply({})
    assert (resolver.gold, resolver.hand, resolver.relics) == before
