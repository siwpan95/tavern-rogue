"""自定义规则（mutators）：解析、合并、以及每条规则真的影响系统。"""
from __future__ import annotations

import pytest

from game.mutators import EFFECT_KEYS, MUTATORS, build_mods, describe, list_mutators, parse_mutators
from game.persistence import ProgressManager
from ui.game_manager import GameManager


@pytest.fixture
def make_game(tmp_path):
    def build(mutators=None, hero_class="warrior", advancement=0):
        progress = ProgressManager(save_file=str(tmp_path / "p.json"))
        if advancement:
            progress.set_class_advancement(hero_class, advancement)
        game = GameManager(progress_manager=progress)
        game.new_game(hero_class, mutators=mutators)
        return game

    return build


def test_registry_is_well_formed():
    assert len(MUTATORS) >= 8
    for key, entry in MUTATORS.items():
        assert entry["name"] and entry["description"]
        assert entry["type"] in ("pos", "neg", "mix")
        for effect_key in entry["effects"]:
            assert effect_key in EFFECT_KEYS, "%s 用了未登记的 effect %s" % (key, effect_key)


def test_parse_rejects_unknown_mutator():
    with pytest.raises(ValueError) as excinfo:
        parse_mutators(["midas", "not_a_real_mutator"])
    assert "not_a_real_mutator" in str(excinfo.value)


def test_parse_deduplicates_and_lowercases():
    assert parse_mutators(["MIDAS", " midas ", "one_hp"]) == ["midas", "one_hp"]
    assert parse_mutators(None) == []


def test_build_mods_merges_multiplicatively_and_additively():
    mods = build_mods(["midas", "greedy"])   # gold_mult 2.0 / shop_price_mult 1.5
    assert mods["gold_mult"] == pytest.approx(2.0)
    assert mods["shop_price_mult"] == pytest.approx(1.5)
    assert mods["enemy_health_mult"] == pytest.approx(1.3)

    mods2 = build_mods(["lethality", "swift"])  # ally_attack 3 / ally_initiative 3
    assert mods2["ally_attack"] == 3
    assert mods2["ally_initiative"] == 3


def test_describe_names_the_active_rules():
    assert "点金" in describe(["midas"])
    assert describe([]) == "无"


def test_list_mutators_is_stable():
    ids = [entry["id"] for entry in list_mutators()]
    assert ids == sorted(ids)


# ─── 每条规则都要真的改动系统 ─────────────────────────────

def test_one_hp_sets_hero_health(make_game):
    game = make_game(["one_hp"])
    assert game.hero.max_health == 5
    assert game.hero.health == 5


def test_midas_doubles_gold_and_toughens_enemies(make_game):
    base = make_game()
    game = make_game(["midas"])
    assert game.gold_mult == pytest.approx(2.0 * base.gold_mult)
    enemy = {"name": "靶子", "health": 10, "max_health": 10, "attack": 4}
    scaled = game.scale_enemies([dict(enemy)])[0]
    assert scaled["health"] > 10, "敌人生命应被 mutator 放大"


def test_binary_limits_board_size(make_game):
    game = make_game(["binary"])
    assert game.MAX_BOARD == 4


def test_ironman_disables_camp_heal_and_adds_post_battle_heal(make_game):
    game = make_game(["ironman"])
    assert game.camp_heal_mult == pytest.approx(0.0)
    game.hero.take_damage(10)
    healed = game.hero.on_battle_end()
    assert healed == 3


def test_greedy_raises_shop_price_and_relic_drop(make_game):
    base = make_game()
    game = make_game(["greedy"])
    assert game.shop_price(10) > base.shop_price(10)
    assert game.relic_system.get_relic_drop_bonus() > 0


def test_allstar_grants_starting_gold(make_game):
    game = make_game(["allstar"])
    game.gold = 0
    game.board.clear()
    assert game.award_turn_gold() == 3 + game.floor + 10


def test_swift_and_lethality_change_battle_start(make_game):

    game = make_game(["swift", "lethality"])
    engine = game.battle_engine
    allies = [{"name": "甲", "health": 5, "max_health": 5, "attack": 2,
               "keywords": [], "initiative": 10, "pos": 0}]
    engine._apply_hero_passives(allies, game.hero)
    assert allies[0]["attack"] == 5, "lethality +3"
    assert allies[0]["initiative"] == 13, "swift +3"


def test_mutators_are_recorded_for_the_summary(make_game):
    game = make_game(["midas", "ironman"])
    assert game.mutators == ["midas", "ironman"]
    lines = game.run_summary_lines()
    assert any("自定义规则" in line for line in lines), lines
