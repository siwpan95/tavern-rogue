#!/usr/bin/env python3
"""
TavernRogue 最终综合验证测试
"""
import sys, os, json, random, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
random.seed(42)

errors = []
warnings = []

def check(msg, condition):
    if condition:
        print(f"  OK {msg}")
    else:
        print(f"  FAIL {msg}")
        errors.append(msg)

def warn(msg):
    print(f"  WARN {msg}")
    warnings.append(msg)

print("=" * 60)
print("TavernRogue 最终综合验证")
print("=" * 60)

# 1. 语法检查
print("\n[1] Python 文件语法检查")
py_files = [
    "game/engine.py", "game/hero.py", "game/recruit.py",
    "game/node_handler.py", "ui/scenes/recruit.py",
]
import py_compile
for f in py_files:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
    if not os.path.exists(path):
        print(f"  SKIP {f} (不存在)")
        continue
    try:
        py_compile.compile(path, doraise=True)
        print(f"  OK {f}")
    except py_compile.PyCompileError as e:
        print(f"  FAIL {f}: {e}")
        errors.append(f"语法错误: {f}")

# 2. JSON 数据文件检查
print("\n[2] JSON 数据文件检查")

def load_json(path):
    full = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    try:
        with open(full, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  FAIL 加载 {path} 失败: {e}")
        errors.append(f"JSON加载失败: {path}")
        return None

enemies = load_json("data/enemies.json")
adventurers = load_json("data/adventurers.json")
relics = load_json("data/relics.json")
events = load_json("data/events.json")

if enemies:
    print(f"  OK enemies.json: {len(enemies)} 个敌人")
    check("敌人数量 >= 25", len(enemies) >= 25)
if adventurers:
    print(f"  OK adventurers.json: {len(adventurers)} 个冒险者")
    check("冒险者数量 >= 50", len(adventurers) >= 50)
if relics:
    print(f"  OK relics.json: {len(relics)} 个圣物")
    check("圣物数量 >= 20", len(relics) >= 20)
if events:
    print(f"  OK events.json: {len(events)} 个事件")
    check("事件数量 >= 15", len(events) >= 15)

# 3. 事件引用敌人ID检查
print("\n[3] 事件引用敌人ID检查")
if enemies and events:
    enemy_ids = {e['id'] for e in enemies}
    referenced = set()
    for ev in events:
        for opt in ev.get('options', []):
            eff = opt.get('effects', {})
            bt = eff.get('start_battle', {})
            if bt and 'enemy' in bt:
                referenced.add(bt['enemy'])
    print(f"  事件引用了 {len(referenced)} 个敌人ID")
    for eid in sorted(referenced):
        ok = eid in enemy_ids
        if ok:
            print(f"  OK 敌人ID '{eid}' 存在")
        else:
            print(f"  FAIL 敌人ID '{eid}' 不存在!")
            errors.append(f"事件引用不存在的敌人: {eid}")

# 4. 导入 engine 并测试
print("\n[4] BattleEngine 关键字逻辑测试")
try:
    from game.engine import BattleEngine
    from game.hero import Hero

    # 4.1 REGENERATION
    print("  -- REGENERATION --")
    engine = BattleEngine(None, Hero("warrior", 1))
    u = dict(name='测试单位', health=3, max_health=8, attack=1,
              keywords=['REGENERATION'], initiative=10, side='ally', pos=0)
    engine._handle_turn_start(u, 1)
    check("REGENERATION: 生命 3->5", u['health'] == 5)
    u['health'] = 7
    engine._handle_turn_start(u, 2)
    check("REGENERATION: 不超过max_health (7+2->8)", u['health'] == 8)

    # 4.2 FLYING 忽略 GUARD
    print("  -- FLYING --")
    allies = [
        dict(name='飞侠', health=5, attack=3, keywords=['FLYING'], initiative=10, side='ally', pos=0),
        dict(name='肉盾', health=10, attack=1, keywords=['GUARD'], initiative=5, side='ally', pos=1),
    ]
    enemies_test = [
        dict(name='普通敌', health=5, attack=1, keywords=[], initiative=8, side='enemy', pos=0),
        dict(name='守卫敌', health=5, attack=1, keywords=['GUARD'], initiative=8, side='enemy', pos=1),
    ]
    engine2 = BattleEngine(None, Hero("warrior", 1))
    target = engine2._select_target(allies[0], enemies_test, allies)
    check("FLYING: 不优先打GUARD", target['name'] == '普通敌')
    target2 = engine2._select_target(allies[1], enemies_test, allies)
    check("GUARD: 无FLYING单位优先打GUARD", target2['name'] == '守卫敌')

    # 4.3 FIRE_BREATH
    print("  -- FIRE_BREATH --")
    allies_fb = [
        dict(name='勇者1', health=20, attack=3, keywords=[], initiative=8, side='ally', pos=0, max_health=20),
        dict(name='勇者2', health=20, attack=3, keywords=[], initiative=7, side='ally', pos=1, max_health=20),
    ]
    enemies_fb = [
        dict(name='龙A', health=10, attack=5, keywords=['FIRE_BREATH'], initiative=10, side='enemy', pos=0, max_health=10),
        dict(name='龙B', health=10, attack=5, keywords=['FIRE_BREATH'], initiative=9, side='enemy', pos=1, max_health=10),
    ]
    eng_fb = BattleEngine(None, Hero("warrior", 1))
    eng_fb.event_queue = []
    eng_fb.battle_log = []
    eng_fb.apply_tribe_effects(allies_fb, enemies_fb, enemies=enemies_fb)
    eng_fb._handle_battle_start(allies_fb, enemies_fb)
    # 2条龙，每条造成2点AOE -> 每个盟友受到4点伤害
    check("FIRE_BREATH: 勇者1受到伤害(20->16)", allies_fb[0]['health'] == 16)
    check("FIRE_BREATH: 勇者2受到伤害(20->16)", allies_fb[1]['health'] == 16)

    # 4.4 SHIELD
    print("  -- SHIELD --")
    shield_unit = dict(name='护盾兵', health=10, attack=1, keywords=['SHIELD'],
                       initiative=5, side='ally', pos=0, max_health=10)
    atk = dict(name='攻击者', attack=3, keywords=[], side='enemy', pos=0)
    engine3 = BattleEngine(None, Hero("warrior", 1))
    engine3._apply_damage(shield_unit, atk, 3, [])
    check("SHIELD: 第一次受击不扣血(10->10)", shield_unit['health'] == 10)
    engine3._apply_damage(shield_unit, atk, 3, [])
    check("SHIELD: 第二次受击扣血(10->7)", shield_unit['health'] == 7)

    # 4.5 FRENZY
    print("  -- FRENZY --")
    frenzy_unit = dict(name='狂战士', health=4, max_health=10, attack=3,
                        keywords=['FRENZY'], initiative=5, side='ally', pos=0)
    dmg = engine3._calculate_damage(frenzy_unit, dict(name='x', keywords=[], side='enemy', pos=0))
    check("FRENZY: 低血量攻击翻倍(3->6)", dmg == 6)
    frenzy_unit['health'] = 6
    dmg2 = engine3._calculate_damage(frenzy_unit, dict(name='x', keywords=[], side='enemy', pos=0))
    check("FRENZY: 血量>=50%攻击正常(3->3)", dmg2 == 3)

    print("  OK 关键字逻辑测试完成")

except Exception as e:
    print(f"  FAIL 测试过程中出错: {e}")
    traceback.print_exc()
    errors.append(f"关键字测试出错: {e}")

# 5. 种族共鸣检查
print("\n[5] 种族共鸣检查")
try:
    from game.engine import BattleEngine
    from game.hero import Hero

    # 龙裔
    dragonborns = [
        dict(name='龙A', health=10, attack=3, keywords=['FLYING'], tribe='dragonborn', tier=4, initiative=10, side='ally', pos=0, max_health=10),
        dict(name='龙B', health=10, attack=3, keywords=['FLYING'], tribe='dragonborn', tier=4, initiative=9, side='ally', pos=1, max_health=10),
        dict(name='龙C', health=10, attack=3, keywords=['FLYING'], tribe='dragonborn', tier=4, initiative=8, side='ally', pos=2, max_health=10),
    ]
    enemies_t = [dict(name='怪', health=20, attack=1, keywords=[], initiative=5, side='enemy', pos=0, max_health=20)]
    eng = BattleEngine(None, Hero("mage", 1))
    eng.event_queue = []
    eng.battle_log = []
    eng.apply_tribe_effects(dragonborns, enemies_t, enemies=enemies_t)
    check("龙裔共鸣: fire_damage 已设置", eng._tribe_resonance.get('dragonborn_fire_damage') == 2)

    # 半兽人
    orcs = [
        dict(name='兽A', health=10, attack=3, keywords=['FRENZY'], tribe='half_orc', tier=2, initiative=10, side='ally', pos=0, max_health=10),
        dict(name='兽B', health=10, attack=3, keywords=['FRENZY'], tribe='half_orc', tier=2, initiative=9, side='ally', pos=1, max_health=10),
    ]
    eng2 = BattleEngine(None, Hero("warrior", 1))
    eng2.apply_tribe_effects(orcs, enemies_t, enemies=enemies_t)
    check("半兽人共鸣: double_chance > 0", eng2._tribe_resonance.get('half_orc_double_chance', 0) > 0)

    # 提夫林
    tieflings = [
        dict(name='提A', health=10, attack=3, keywords=['DODGE'], tribe='tiefling', tier=2, initiative=10, side='ally', pos=0, max_health=10),
        dict(name='提B', health=10, attack=3, keywords=['DODGE'], tribe='tiefling', tier=2, initiative=9, side='ally', pos=1, max_health=10),
        dict(name='提C', health=10, attack=3, keywords=['DODGE'], tribe='tiefling', tier=2, initiative=8, side='ally', pos=2, max_health=10),
    ]
    eng3 = BattleEngine(None, Hero("warlock", 1))
    eng3.apply_tribe_effects(tieflings, enemies_t, enemies=enemies_t)
    check("提夫林共鸣: death_damage = 3", eng3._tribe_resonance.get('tiefling_death_damage') == 3)

    print("  OK 种族共鸣检查完成")

except Exception as e:
    print(f"  FAIL 种族共鸣测试出错: {e}")
    traceback.print_exc()
    errors.append(f"种族共鸣测试出错: {e}")

# 6. simulate_battle 完整流程测试
print("\n[6] simulate_battle 完整流程测试(3局)")
try:
    from game.engine import BattleEngine
    from game.hero import Hero

    for i in range(3):
        hero = Hero(random.choice(['warrior', 'mage', 'ranger', 'cleric', 'warlock']), 1)
        engine = BattleEngine(None, hero)
        board = [
            dict(name='勇者1', health=10, max_health=10, attack=3, keywords=[], tribe='human', tier=1, initiative=10, side='ally', pos=0),
            dict(name='勇者2', health=8, max_health=8, attack=2, keywords=['GUARD'], tribe='human', tier=1, initiative=5, side='ally', pos=1),
        ]
        enemy_list = []
        for idx, e in enumerate(random.sample(enemies, min(2, len(enemies)))):
            en = dict(e)
            en['side'] = 'enemy'
            en['pos'] = idx
            en.setdefault('max_health', en.get('health', 5))
            enemy_list.append(en)

        result = engine.simulate_battle(board, enemy_list, avoid_death=False)
        check(f"第{i+1}局: simulate_battle 返回结果", result is not None)

    print("  OK simulate_battle 流程测试完成")

except Exception as e:
    print(f"  FAIL simulate_battle 测试出错: {e}")
    traceback.print_exc()
    errors.append(f"simulate_battle 测试出错: {e}")

# 7. 圣物效果类型检查
print("\n[7] 圣物效果类型检查")
if relics:
    supported = {'gold', 'max_health', 'attack', 'heal', 'damage',
                  'buff', 'debuff', 'special', 'tribe_buff',
                  'battle_start_buff', 'battle_start_debuff',
                  'death_effect', 'global_buff', 'shop_discount',
                  'heal_on_kill', 'gold_per_turn', 'relic_limit_break',
                  'resurrect_once', 'poison_immune', 'counter_attack'}
    all_types = set()
    for r in relics:
        eff = r.get('effect', {})
        if isinstance(eff, dict):
            t = eff.get('type', '')
            if t:
                all_types.add(t)
    print(f"  圣物效果类型: {all_types}")
    for t in all_types:
        if t not in supported:
            warn(f"效果类型 '{t}' 可能在 engine 中未实现")

# 汇总
print("\n" + "=" * 60)
print("验证汇总")
print("=" * 60)
print(f"  OK 通过")
print(f"  FAIL 失败: {len(errors)} 个")
print(f"  WARN 警告: {len(warnings)} 个")

if errors:
    print("\n失败项:")
    for e in errors:
        print(f"    - {e}")

if warnings:
    print("\n警告项:")
    for w in warnings:
        print(f"    - {w}")

if not errors:
    print("\n  PASS 全部验证通过! TavernRogue 项目已达到可玩状态。")
else:
    print(f"\n  WARN 还有 {len(errors)} 个问题需要修复。")

print("=" * 60)
