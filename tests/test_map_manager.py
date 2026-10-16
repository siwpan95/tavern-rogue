"""地图与节点生成：Boss 配置、兜底行为、通关判据。"""
from __future__ import annotations

from game.map_manager import MapManager


def make_node(layer, node_type, index=0):
    return {"id": "probe_%d_%d" % (layer, index), "layer": layer, "index": index,
            "type": node_type, "name": node_type, "description": "probe",
            "revealed": True, "completed": False, "content": None}


def test_final_boss_layer_declares_its_boss(data_loader):
    manager = MapManager(data_loader)
    final_layers = [layer for layer in manager.map_templates["layers"] if layer["type"] == "boss"]
    assert final_layers, "地图模板必须有一层固定 Boss 层"
    assert final_layers[0].get("boss"), "最终 Boss 层必须配 boss id（README：远古红龙）"


def test_random_boss_node_without_config_uses_boss_pool(data_loader):
    """回归：第 7 层的随机 boss 没配 boss id，旧版兜底成了 1 级哥布林斥候。"""
    manager = MapManager(data_loader)
    manager.map_data = manager.generate_map()
    content = manager._generate_node_content(make_node(7, "boss"))
    enemies = content["enemies"]
    assert len(enemies) == 1
    assert enemies[0].get("is_boss") is True, "没配 boss id 时也必须从 is_boss 池里取"


def test_configured_boss_is_used(data_loader):
    manager = MapManager(data_loader)
    manager.map_data = manager.generate_map()
    content = manager._generate_node_content(make_node(8, "boss"))
    assert content["enemies"][0]["id"] == "ancient_red_dragon"


def test_load_enemy_is_loud_instead_of_silent(data_loader):
    manager = MapManager(data_loader)
    assert manager._load_enemy(None) is None
    assert manager._load_enemy("no_such_enemy") is None


def test_generated_map_has_nine_layers(data_loader):
    manager = MapManager(data_loader)
    data = manager.generate_map()
    assert len(data["layers"]) == 9
    assert all(layer["nodes"] for layer in data["layers"])
    for layer in data["layers"]:
        for node in layer["nodes"]:
            assert node["type"] in manager.map_templates["node_types"]


def test_fixed_layers_keep_their_declared_type(data_loader):
    """回归：旧版判 `type == 'fixed'`（模板里没有这个值）→ 九层全走随机分支，
    于是第 1 层不是营地、第 8 层的最终 Boss 变成普通小怪、第 9 层宝藏密室不存在。"""
    manager = MapManager(data_loader)
    data = manager.generate_map()
    by_layer = {layer["layer"]: layer for layer in data["layers"]}
    assert by_layer[1]["nodes"][0]["type"] == "camp"
    assert by_layer[8]["nodes"][0]["type"] == "boss"
    assert by_layer[9]["nodes"][0]["type"] == "treasure"


def test_random_layer_only_uses_declared_types(data_loader):
    """随机层只能用**本局抽中的那种层变体**里声明的节点类型。"""
    manager = MapManager(data_loader)
    data = manager.generate_map()
    for layer in data["layers"]:
        allowed = layer.get("possible_types")
        if not allowed:
            continue
        for node in layer["nodes"]:
            assert node["type"] in allowed, "%s 出现未声明的节点类型 %s" % (layer["name"], node["type"])


def test_layer_variants_come_from_template(data_loader):
    manager = MapManager(data_loader)
    data = manager.generate_map()
    variants = manager.map_templates.get("layer_variants") or {}
    for layer in data["layers"]:
        declared = variants.get(str(layer["layer"]))
        if not declared:
            continue
        assert layer["possible_types"] in declared, \
            "第 %d 层的节点组合必须来自 layer_variants" % layer["layer"]


def test_elite_affixes_start_at_layer_five(data_loader):
    manager = MapManager(data_loader)
    manager.map_data = manager.generate_map()
    early = manager._generate_node_content(make_node(3, "elite"))
    assert early["affixes"] == [], "前期精英不该带词缀"

    late = manager._generate_node_content(make_node(7, "elite"))
    assert late["affixes"], "第 5 层起精英必须带词缀"
    enemy = late["enemies"][0]
    assert any(keyword in enemy.get("keywords", [])
               for keyword in ("FRENZY", "ARMOR", "POISON", "DODGE", "REGENERATION")), enemy


def test_boss_takes_two_affixes_and_advancement_adds_one(data_loader):
    manager = MapManager(data_loader)
    manager.map_data = manager.generate_map()
    content = manager._generate_node_content(make_node(8, "boss"))
    assert len(content["affixes"]) == 2
    assert content["enemies"][0]["id"] == "ancient_red_dragon"

    manager.affix_bonus = 1  # 进阶≥3
    boosted = manager._generate_node_content(make_node(8, "boss"))
    assert len(boosted["affixes"]) == 3


def test_affix_boosts_stats(data_loader):
    manager = MapManager(data_loader)
    manager.map_data = manager.generate_map()
    base = manager._generate_node_content(make_node(7, "elite"))["enemies"][0]
    manager.map_templates = dict(manager.map_templates)
    manager.map_templates["affixes"] = [
        {"id": "giant", "name": "巨型", "keywords": [], "health_mult": 2.0, "attack_mult": 1.0}]
    boosted = manager._generate_node_content(make_node(7, "elite"))["enemies"][0]
    assert boosted["health"] > base["health"]
    assert "巨型" in boosted["name"]
