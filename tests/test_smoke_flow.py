"""headless 全流程冒烟：让游戏真的跑起来（旧套件完全没覆盖 UI/场景层）。

SDL 用 dummy 驱动，不需要显示器与声卡。
"""
from __future__ import annotations

import random

import pytest

from ui.app import TavernRogueApp

SCENE_FOR_NODE = {
    "monster": "battle",
    "elite": "battle",
    "boss": "battle",
    "shop": "shop",
    "camp": "camp",
    "event": "event",
    "treasure": "treasure",
}
HERO_CLASSES = ["warrior", "rogue", "cleric", "wizard", "warlock"]


@pytest.fixture(scope="module")
def app():
    application = TavernRogueApp()
    yield application
    import pygame

    pygame.display.quit()


def fresh_game(app, hero_class="warrior"):
    app.game.new_game(hero_class)
    return app.game


def frame(app, dt=0.016):
    app.scenes.update(dt)
    app.scenes.draw()


def make_node(game, node_type, layer=3):
    """构造一个该类型的节点，并让 MapManager 生成内容。"""
    node = {
        "id": "probe_%s" % node_type,
        "layer": layer,
        "index": 0,
        "type": node_type,
        "name": node_type,
        "description": "probe",
        "revealed": True,
        "completed": False,
        "content": None,
    }
    game.map_manager.current_layer = layer
    node["content"] = game.map_manager._generate_node_content(node)
    return node


def recruit_one(game):
    """买一个买得起的并部署上场；返回是否成功。"""
    game.start_recruit_turn()
    pool = getattr(game.recruit_system, "tavern_pool", [])
    for index in range(len(pool)):
        cost = pool[index].get("cost", 3)
        if cost <= game.gold and game.recruit_system.recruit(index):
            game.recruit_system.deploy_to_board(0)
            return True
    return False


def finish_battle(app, max_frames=4000):
    """点开始战斗，驱动动画到结算，然后走结算分支。"""
    scene = app.scenes.current
    scene._start_battle()
    frames = 0
    while getattr(scene, "phase", None) == "animating" and frames < max_frames:
        frame(app, 0.05)
        frames += 1
    assert scene.phase in ("victory", "defeat"), "战斗必须收敛到胜利/失败，当前 %s" % scene.phase
    phase = scene.phase
    if phase == "victory":
        scene._victory()
    else:
        scene._defeat()
    return phase


def test_app_starts_on_menu_and_draws(app):
    assert type(app.scenes.current).__name__ == "MenuScene"
    for _ in range(3):
        frame(app)


@pytest.mark.parametrize("hero_class", HERO_CLASSES)
def test_every_hero_class_can_start_a_run(app, hero_class):
    game = fresh_game(app, hero_class)
    assert game.hero is not None and game.hero.hero_class == hero_class
    app.scenes.switch_to("recruit")
    frame(app)
    app.scenes.switch_to("map")
    frame(app)


def test_recruit_buy_deploy_and_sell(app):
    game = fresh_game(app)
    app.scenes.switch_to("recruit")
    assert recruit_one(game), "铸币足够时必须能买到并部署一个单位"
    assert len(game.board) == 1
    assert game.recruit_system.recall_to_hand(0)
    assert len(game.board) == 0 and len(game.hand) == 1
    assert game.recruit_system.deploy_to_board(0)
    before = game.gold
    game.recruit_system.sell_adventurer(0, from_hand=False)
    assert game.gold >= before


@pytest.mark.parametrize("node_type", sorted(SCENE_FOR_NODE))
def test_every_node_type_enters_and_draws(app, node_type):
    game = fresh_game(app)
    recruit_one(game)
    node = make_node(game, node_type)
    app.scenes.switch_to(SCENE_FOR_NODE[node_type], node=node)
    frame(app)
    assert type(app.scenes.current).__name__ != "MenuScene"


@pytest.mark.parametrize("node_type", ["monster", "elite", "boss"])
def test_battle_nodes_resolve_both_ways(app, node_type):
    game = fresh_game(app)
    recruit_one(game)
    node = make_node(game, node_type)
    app.scenes.switch_to("battle", node=node)
    phase = finish_battle(app)
    if phase == "victory":
        assert type(app.scenes.current).__name__ == "RewardScene"
    else:
        assert game.health < game.MAX_HEALTH, "战败必须扣英雄血"


def test_event_scene_applies_first_option(app):
    game = fresh_game(app)
    recruit_one(game)
    node = make_node(game, "event")
    app.scenes.switch_to("event", node=node)
    scene = app.scenes.current
    effects = scene._event["options"][0].get("effects", {})
    before_gold = game.gold
    scene._choose(scene._event["options"][0])
    if "gain_gold" in effects:
        assert game.gold >= before_gold
    assert type(app.scenes.current).__name__ in ("MapScene", "RecruitScene", "BattleScene")


def test_treasure_and_camp_scenes_resolve(app):
    for node_type, method in (("treasure", "_take"), ("camp", "_leave")):
        game = fresh_game(app)
        recruit_one(game)
        node = make_node(game, node_type)
        app.scenes.switch_to(SCENE_FOR_NODE[node_type], node=node)
        getattr(app.scenes.current, method)()
        assert type(app.scenes.current).__name__ in ("MapScene", "RecruitScene")


def test_event_battle_option_starts_a_real_battle(app):
    """回归：事件里的「战斗！」曾经只设了个没人读的 trigger_battle（战斗永不发生）。"""
    game = fresh_game(app)
    recruit_one(game)
    game.ensure_map()
    node = next(n for n in game.map_manager.map_data['layers'][1]['nodes'])
    node['type'] = "event"
    node['content'] = game.map_manager._generate_node_content(node)
    game.select_map_node(node['id'])
    app.scenes.switch_to("event", node=node)
    scene = app.scenes.current
    scene._event = game.event_system.select_event_by_id("greedy_mimic")
    assert scene._event is not None, "测试数据里必须有 greedy_mimic 事件"

    option = scene._event["options"][0]
    assert "start_battle" in option["effects"]
    gold_before = game.gold
    scene._choose(option)

    battle = app.scenes.current
    assert type(battle).__name__ == "BattleScene", "事件战斗必须真的进战斗场景"
    assert battle._event_battle["enemy"] == "mimic"
    assert len(battle.enemies) == 1 and battle.enemies[0]["id"] == "mimic", \
        "事件战斗的敌人必须来自事件指定的 id"

    phase = finish_battle(app)
    if phase == "victory":
        assert game.gold == gold_before + option["effects"]["start_battle"]["reward_gold"]


def test_missing_node_does_not_crash_after_node(app):
    """回归：没有 current_node 时 _after_node() 曾经抛 TypeError。"""
    game = fresh_game(app)
    recruit_one(game)
    node = make_node(game, "camp")
    app.scenes.switch_to("camp", node=node)
    game.current_node = None
    app.scenes.current._after_node()
    assert type(app.scenes.current).__name__ == "MapScene"


def test_full_run_playthrough_reaches_an_ending_or_final_layer(app):
    """一局到底的粗粒度冒烟：任何一步抛异常都算失败。"""
    random.seed(4242)
    game = fresh_game(app, "warrior")
    endings = ("GameOverScene", "VictoryScene")

    for _step in range(80):
        current = type(app.scenes.current).__name__
        if current in endings:
            return

        if current == "BattleScene":
            # 事件选项可能直接开战；不把它打完就会卡在半路
            finish_battle(app)
            continue

        if current == "RewardScene":
            app.scenes.current._pick("gold", 10)
            continue

        if current == "RecruitScene":
            recruit_one(game)
            app.scenes.current._end()
            continue

        game.ensure_map()
        layer = game.map_manager.get_current_layer()
        node = next((n for n in layer["nodes"] if not n.get("completed")), None)
        if node is None:
            game.advance_floor()
            app.scenes.switch_to("recruit")
            continue

        game.map_manager.reveal_node(node["id"])
        game.select_map_node(node["id"])
        scene_name = SCENE_FOR_NODE.get(node["type"])
        if scene_name is None:
            game.complete_node(node["id"])
            app.scenes.switch_to("map")
            continue

        app.scenes.switch_to(scene_name, node=node)
        current_scene = app.scenes.current
        if scene_name == "battle":
            finish_battle(app)
        elif scene_name == "event":
            option = current_scene._event["options"][0]
            current_scene._choose(option)
        elif scene_name == "treasure":
            current_scene._take()
        elif scene_name == "camp":
            current_scene._leave()
        elif scene_name == "shop":
            current_scene._leave()
        frame(app)

    raise AssertionError(
        "80 步内没走到结局（当前场景 %s，层 %d）" % (type(app.scenes.current).__name__, game.floor)
    )
