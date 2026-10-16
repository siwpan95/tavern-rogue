"""地图与节点生成：Boss 配置、兜底行为、通关判据。"""
from __future__ import annotations

from game.map_manager import MapManager


def make_node(layer, node_type, index=0):
    return {"id": "probe_%d_%d" % (layer, index), "layer": layer, "index": index,
            "type": node_type, "name": node_type, "description": "probe",
            "revealed": True, "completed": False, "content": None}


def test_final_boss_layer_declares_its_boss_pool(data_loader):
    """最终 Boss 层必须是「池化」的（内容复用），且包含 README 里的经典红龙。"""
    manager = MapManager(data_loader)
    final_layers = [layer for layer in manager.map_templates["layers"] if layer["type"] == "boss"]
    assert final_layers, "地图模板必须有一层固定 Boss 层"
    pool = final_layers[0].get("boss_pool") or []
    assert len(pool) >= 2, "Boss 池至少 2 个（固定单 Boss 每局都一样）"
    assert "ancient_red_dragon" in pool, "经典红龙应保留在池中"
    for boss_id in pool:
        assert manager._load_enemy(boss_id), "池里的 Boss 必须在 enemies.json 里存在：%s" % boss_id


def test_random_boss_node_without_config_uses_boss_pool(data_loader):
    """回归：第 7 层的随机 boss 没配 boss id，旧版兜底成了 1 级哥布林斥候。"""
    manager = MapManager(data_loader)
    manager.map_data = manager.generate_map()
    content = manager._generate_node_content(make_node(7, "boss"))
    enemies = content["enemies"]
    assert len(enemies) == 1
    assert enemies[0].get("is_boss") is True, "没配 boss id 时也必须从 is_boss 池里取"


def test_layer_boss_pools_are_used(data_loader):
    """第 7 层与第 8 层的 Boss 都应来自各自的池。"""
    manager = MapManager(data_loader)
    manager.map_data = manager.generate_map()
    layer7 = manager.map_templates["layers"][6].get("boss_pool")
    layer8 = manager.map_templates["layers"][7].get("boss_pool")
    for _ in range(10):
        assert manager._generate_node_content(make_node(7, "boss"))["enemies"][0]["id"] in layer7
        assert manager._generate_node_content(make_node(8, "boss"))["enemies"][0]["id"] in layer8


def test_bosses_have_counter_tags_and_budget(data_loader):
    """每个 Boss 必须标 `counter_tag`（它要求玩家改变什么），且数值预算不通胀。"""
    tagged = [e for e in data_loader("enemies.json") if e.get("counter_tag")]
    assert len(tagged) >= 6, "至少 6 个 Boss 带 counter_tag"
    for boss in tagged:
        assert boss.get("is_boss") is True
        total = boss["attack"] + boss["health"]
        assert 18 <= total <= 26, "%s 的 atk+hp=%d 超出 18-26 预算" % (boss["id"], total)


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

    manager.affix_bonus = 1  # 进阶 5：额外一条词缀
    boosted = manager._generate_node_content(make_node(8, "boss"))
    assert len(boosted["affixes"]) == 3


def test_affix_boosts_stats(data_loader):
    """词缀必须真的改数值（用同一个敌人对比，避免随机敌人造成的假比较）。"""
    manager = MapManager(data_loader)
    manager.map_templates = dict(manager.map_templates)
    manager.map_templates["affixes"] = [
        {"id": "giant", "name": "巨型", "keywords": [], "health_mult": 2.0, "attack_mult": 1.0}]
    enemy = {"name": "靶子", "health": 10, "max_health": 10, "attack": 4, "keywords": []}
    applied = manager._apply_affixes([enemy], layer=7)
    assert applied == ["giant"]
    assert enemy["health"] == 20 and enemy["max_health"] == 20
    assert "巨型" in enemy["name"]
