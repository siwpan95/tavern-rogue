"""
地图管理系统 - 负责生成和管理游戏地图
支持9层地图，每层2-4个节点
"""
import json
import random
from enum import Enum


class NodeType(Enum):
    """节点类型"""
    MONSTER = "monster"      # 怪物巢穴
    ELITE = "elite"          # 精英守卫
    SHOP = "shop"            # 旅行商人
    EVENT = "event"          # 古老祭坛（奇遇）
    CAMP = "camp"            # 安全营地
    BOSS = "boss"            # 首领
    TREASURE = "treasure"    # 宝藏密室


class MapManager:
    """地图管理器"""
    
    def __init__(self, data_loader):
        """
        初始化地图管理器
        data_loader: 数据加载器函数
        """
        self.data_loader = data_loader
        self.current_layer = 1
        self.max_layer = 9
        self.map_data = None
        self.current_node = None
        self.path = []  # 玩家选择的路径
        self.affix_bonus = 0            # 进阶难度带来的额外词缀数
        self.elite_node_weight = 1.0    # 进阶 1 起精英节点权重上调
        self.encounter_size_bonus = 0   # 进阶 5 起每次遭遇多 1 个敌人
        
        # 加载地图模板
        self.map_templates = self.data_loader('map_templates.json')
        
    def generate_map(self):
        """生成完整地图"""
        self.map_data = {
            'layers': [],
            'current_layer': 1,
            'completed_layers': []
        }
        
        # 生成每一层
        for layer_info in self.map_templates['layers']:
            layer = self._generate_layer(layer_info)
            self.map_data['layers'].append(layer)
        
        return self.map_data
    
    def _generate_layer(self, layer_info):
        """生成单层地图"""
        layer_num = layer_info['layer']
        layer_type = layer_info['type']
        node_count = layer_info['nodes']
        
        layer = {
            'layer': layer_num,
            'name': layer_info['name'],
            'type': layer_type,
            'description': layer_info['description'],
            'nodes': [],
            'completed': False
        }
        
        # 根据层类型生成节点
        # 注意：模板里**只有** type == 'random' 的层才是随机节点；其余（camp/boss/treasure…）
        # 是固定层，节点类型就是层类型。旧版判的是 'fixed'，而这个字符串在模板里根本不存在
        # → 九层全走随机分支 → 第 1 层不是营地、第 8 层最终 Boss 变成普通小怪、
        # 第 9 层宝藏密室不存在（2026-10-16 平衡对拍时发现）。
        if layer_type == 'random':
            # 随机节点：优先用层变体（同一层有多种节点组合，提升每局差异）
            variants = (self.map_templates.get('layer_variants') or {}).get(str(layer_num))
            if variants:
                possible_types = random.choice(variants)
            else:
                possible_types = layer_info.get('possible_types', ['monster', 'event'])
            layer['possible_types'] = list(possible_types)
            # 进阶 1 起精英权重上调（抄 StS A1 的「精英 +60%」）
            weights = [self.elite_node_weight if node_type == 'elite' else 1.0
                       for node_type in possible_types]
            for i in range(node_count):
                node_type = random.choices(possible_types, weights=weights, k=1)[0]
                node = self._create_node(node_type, layer_num, i)
                layer['nodes'].append(node)
        else:
            # 固定节点（营地、Boss、宝藏密室…）
            for i in range(node_count):
                node = self._create_node(layer_type, layer_num, i)
                layer['nodes'].append(node)
        
        return layer
    
    def _create_node(self, node_type, layer, index):
        """创建单个节点"""
        node_types = self.map_templates['node_types']
        
        if node_type in node_types:
            type_info = node_types[node_type]
            node = {
                'id': f"layer{layer}_node{index}",
                'layer': layer,
                'index': index,
                'type': node_type,
                'name': type_info['name'],
                'description': type_info['description'],
                'revealed': False,  # 是否已揭示
                'completed': False,
                'content': None  # 节点内容（进入时才生成）
            }
            return node
        else:
            # 默认怪物节点
            return {
                'id': f"layer{layer}_node{index}",
                'layer': layer,
                'index': index,
                'type': 'monster',
                'name': '怪物巢穴',
                'description': '普通的怪物战斗',
                'revealed': False,
                'completed': False,
                'content': None
            }
    
    def get_current_layer(self):
        """获取当前层"""
        if not self.map_data:
            return None
        
        for layer in self.map_data['layers']:
            if layer['layer'] == self.current_layer:
                return layer
        
        return None
    
    def reveal_node(self, node_id):
        """揭示节点内容"""
        if not self.map_data:
            return None
        
        # 查找节点
        for layer in self.map_data['layers']:
            for node in layer['nodes']:
                if node['id'] == node_id:
                    node['revealed'] = True
                    
                    # 生成节点内容
                    if node['content'] is None:
                        node['content'] = self._generate_node_content(node)
                    
                    return node
        
        return None
    
    def _generate_node_content(self, node):
        """生成节点内容"""
        node_type = node['type']
        
        if node_type == 'monster':
            # 生成怪物战斗
            return {
                'type': 'battle',
                'enemies': self._generate_enemies(node['layer'], 'normal'),
                'rewards': {
                    'gold': True,
                    'discover': True
                }
            }
        
        elif node_type == 'elite':
            # 精英战斗（第 5 层起带词缀）
            enemies = self._generate_enemies(node['layer'], 'elite')
            affixes = self._apply_affixes(enemies, node['layer'])
            return {
                'type': 'battle',
                'enemies': enemies,
                'affixes': affixes,
                'rewards': {
                    'gold': True,
                    'relic': True
                }
            }
        
        elif node_type == 'boss':
            # Boss战斗：优先用模板配置的 boss id；没配就从 is_boss 池里按层数挑一个。
            # 旧版 `_load_enemy(None)` 会兜底成 enemies_data[0] —— 于是第 7 层的随机 boss
            # 静默变成一只 1 级哥布林斥候（平衡对拍时发现）。
            layer_info = self.map_templates['layers'][node['layer']-1]
            pool = layer_info.get('boss_pool') or []
            boss_id = layer_info.get('boss') or (random.choice(pool) if pool else None)
            boss = self._load_enemy(boss_id) if boss_id else None
            if boss is None:
                candidates = [e for e in self.data_loader('enemies.json')
                              if e.get('is_boss') and e.get('tier', 1) <= node['layer'] + 2]
                if not candidates:
                    candidates = [e for e in self.data_loader('enemies.json') if e.get('is_boss')]
                boss = random.choice(candidates).copy()
            enemies = [boss]
            affixes = self._apply_affixes(enemies, node['layer'], count=2)
            return {
                'type': 'battle',
                'enemies': enemies,
                'affixes': affixes,
                'rewards': {
                    'gold': True,
                    'relic': True,
                    'upgrade_tavern': True
                }
            }
        
        elif node_type == 'shop':
            # 商店
            return {
                'type': 'shop',
                'items': self._generate_shop_items(node['layer'])
            }
        
        elif node_type == 'event':
            # 随机事件
            return {
                'type': 'event',
                'event': self._select_random_event()
            }
        
        elif node_type == 'camp':
            # 营地
            return {
                'type': 'camp',
                'options': ['heal', 'train']
            }
        
        elif node_type == 'treasure':
            # 宝藏
            return {
                'type': 'treasure',
                'gold': 20,
                'relic': True
            }
        
        return None
    
    AFFIX_MIN_LAYER = 6  # 第 6 层起精英/Boss 带词缀（第 5 层还是玩家的构筑成型期）

    @staticmethod
    def max_enemy_tier(layer, difficulty='normal'):
        """该层能出现的敌人**星级上限**。

        改前是 `tier <= layer`（普通）/`<= layer + 1`（精英）——9 层地图配 6 个星级，
        于是第 5-6 层就能刷出 6 星怪（攻击 5-9），而玩家场上通常还是 2-4 星，
        第 7 层因此成了"墙"（62% 的阵亡堆在那里，2026-10-16 对拍实测）。
        现在改成更缓的曲线：普通 L1-2→2 星、L3-4→3 星、L5-6→4 星、L7-8→5 星、L9→6 星；
        精英整体 +1 星（精英节点本来就该更难）。
        """
        bump = 1 if difficulty == 'elite' else 0
        return min(6, max(1, 1 + (int(layer or 1) + 1) // 2 + bump))

    @staticmethod
    def base_encounter_size(layer, difficulty='normal'):
        """遭遇规模基线（不含进阶/自定义规则的加成）。

        形状：第 1-3 层 2 个（教学期，允许玩家从容成型）→ 4-6 层 3 个 → 7-9 层 4 个；
        精英比普通少 1 个。改前是「前 4 层 3 个」——对拍显示那会让前期也在掉血，
        而真正的难度墙本来就在 6-8 层（2026-10-16 曲线实测）。
        """
        layer = max(1, int(layer or 1))
        if difficulty == 'boss':
            return 1
        if difficulty == 'elite':
            return min(1 + (layer - 1) // 3, 3)
        return min(2 + (layer - 1) // 3, 4)

    def encounter_size(self, layer, difficulty='normal'):
        """遭遇规模（含进阶 A5「孤注一掷」的 +1 敌人）。

        改前固定「普通 1-2 个、精英 1 个」，玩家中后期稳定 7 个单位上场
        → 7 打 2 必胜，通关率 89%（2026-10-16 平衡对拍）。
        现在从第 1 层就上 3 个（前 4 层不再是"零风险教学关"），第 5 层起 4 个。
        """
        base = self.base_encounter_size(layer, difficulty)
        if difficulty == 'boss':
            return base
        return base + max(0, int(getattr(self, 'encounter_size_bonus', 0) or 0))

    def _apply_affixes(self, enemies, layer, count=1):
        """给精英/Boss 敌人叠词缀（狂暴/重甲/淬毒/疾行/巨型/不灭）。

        内容复用技巧：同一批敌人 + 不同词缀 = 新遭遇，用组合数换重复可玩性。
        `self.affix_bonus` 由进阶难度设置（进阶≥3 多一条词缀）。
        """
        pool = self.map_templates.get('affixes') or []
        if not pool or not enemies or layer < self.AFFIX_MIN_LAYER:
            return []
        count = max(1, int(count) + int(getattr(self, 'affix_bonus', 0) or 0))
        chosen = random.sample(pool, min(count, len(pool)))

        for affix in chosen:
            for enemy in enemies:
                keywords = enemy.setdefault('keywords', [])
                for keyword in affix.get('keywords', []):
                    if keyword not in keywords:
                        keywords.append(keyword)
                health_mult = float(affix.get('health_mult', 1.0) or 1.0)
                attack_mult = float(affix.get('attack_mult', 1.0) or 1.0)
                enemy['health'] = max(1, int(round(enemy.get('health', 1) * health_mult)))
                enemy['max_health'] = max(
                    enemy['health'],
                    int(round(enemy.get('max_health', enemy['health']) * health_mult)))
                enemy['attack'] = max(1, int(round(enemy.get('attack', 1) * attack_mult)))
                if len(chosen) == 1:
                    enemy['name'] = "%s·%s" % (enemy.get('name', '敌人'), affix['name'])
        return [affix['id'] for affix in chosen]

    def _generate_enemies(self, layer, difficulty='normal'):
        """生成敌人"""
        enemies_data = self.data_loader('enemies.json')
        
        if difficulty == 'normal':
            # 普通怪物：数量与星级上限都随层数增长（星级曲线见 max_enemy_tier）
            count = self.encounter_size(layer, 'normal')
            available = [e for e in enemies_data
                         if e['tier'] <= self.max_enemy_tier(layer, 'normal')
                         and not e.get('is_boss')]
        elif difficulty == 'elite':
            # 精英：高一级的敌人池，数量随层数增长
            available = [e for e in enemies_data
                         if e['tier'] <= self.max_enemy_tier(layer, 'elite')
                         and not e.get('is_boss')]
            count = self.encounter_size(layer, 'elite')
        else:
            count = 1
            available = enemies_data
        
        if not available:
            # 兜底：使用第一个敌人
            return [enemies_data[0]] * count
        
        enemies = []
        for _ in range(count):
            enemy = random.choice(available)
            enemies.append(enemy.copy())
        
        return enemies
    
    def _load_enemy(self, enemy_id):
        """按 id 加载敌人；找不到返回 None（由调用方决定兜底，不要静默换成别的怪）。"""
        if not enemy_id:
            return None
        enemies_data = self.data_loader('enemies.json')
        for enemy in enemies_data:
            if enemy['id'] == enemy_id:
                return enemy.copy()
        return None
    
    def _generate_shop_items(self, layer):
        """生成商店物品"""
        adventurers_data = self.data_loader('adventurers.json')
        relics_data = self.data_loader('relics.json')
        
        items = {
            'adventurers': random.sample([a for a in adventurers_data if a['tier'] <= layer], 
                                        min(3, len(adventurers_data))),
            'relics': random.sample(relics_data, min(2, len(relics_data)))
        }
        
        return items
    
    def _select_random_event(self):
        """选择随机事件"""
        events_data = self.data_loader('events.json')
        return random.choice(events_data).copy()
    
    def layer_requirement(self, layer_num: int) -> dict:
        """该层的进入条件（规格 §6：第 9 层"若携带特定物品可进入"）。"""
        for layer in (self.map_templates or {}).get('layers', []):
            if layer.get('layer') == layer_num:
                return dict(layer.get('requires') or {})
        return {}

    def is_layer_accessible(self, layer_num: int, relic_ids=()) -> bool:
        """按进入条件判断该层是否可进（无条件 = 可进）。"""
        requirement = self.layer_requirement(layer_num)
        needed = requirement.get('relic')
        if not needed:
            return True
        return needed in set(relic_ids or ())

    def locked_layer_reason(self, layer_num: int) -> str:
        """给 UI 的一句话说明（可进则返回空串）。"""
        requirement = self.layer_requirement(layer_num)
        needed = requirement.get('relic')
        if not needed:
            return ""
        return "需要携带「%s」才能进入" % requirement.get('relic_name', needed)

    def _accessible_next_layer(self, completed_layer: int, relic_ids=()) -> int:
        """推进到下一条**可进**的层；被锁住的层直接跳过（第 9 层是可选层）。"""
        candidate = completed_layer + 1
        while candidate <= self.max_layer and not self.is_layer_accessible(candidate, relic_ids):
            candidate += 1
        return min(candidate, self.max_layer)

    def complete_node(self, node_id, relic_ids=()):
        """完成节点；层完成后推进到下一条可进的层（会跳过未解锁的层）。"""
        if not self.map_data:
            return False
        
        for layer in self.map_data['layers']:
            for node in layer['nodes']:
                if node['id'] == node_id:
                    node['completed'] = True
                    
                    # 检查层是否完成
                    layer_completed = all(n['completed'] for n in layer['nodes'])
                    if layer_completed:
                        layer['completed'] = True
                        self.map_data['completed_layers'].append(layer['layer'])
                        
                        # 进入下一层（跳过进入条件不满足的层）
                        if layer['layer'] < self.max_layer:
                            self.current_layer = self._accessible_next_layer(
                                layer['layer'], relic_ids)
                    
                    return True
        
        return False
    
    def get_map_display(self):
        """获取地图显示信息"""
        if not self.map_data:
            return "地图未生成"
        
        display = []
        for layer in self.map_data['layers']:
            layer_info = f"第 {layer['layer']} 层: {layer['name']}"
            
            if layer['layer'] == self.current_layer:
                layer_info += " [当前]"
            
            nodes_info = []
            for node in layer['nodes']:
                status = "✓" if node['completed'] else "○" if node['revealed'] else "?"
                nodes_info.append(f"{status} {node['name']}")
            
            layer_info += f" | {' / '.join(nodes_info)}"
            display.append(layer_info)
        
        return "\n".join(display)
    
    def select_node(self, node_id):
        """选择节点"""
        node = self.reveal_node(node_id)
        
        if node:
            self.current_node = node
            return node
        
        return None
    
    def has_escaped(self):
        """检查是否可以进入宝藏密室（需要特殊物品）"""
        # 简化：检查是否携带特殊物品
        # 实际应该在hero对象中检查
        return False  # 默认不可进入


def load_map_data(filename):
    """加载地图数据的辅助函数"""
    with open(f'data/{filename}', 'r', encoding='utf-8') as f:
        return json.load(f)


# 命令行界面
def cli_map_interface(map_manager):
    """命令行地图界面"""
    print("=== 地图系统 ===")
    
    map_manager.generate_map()
    
    while True:
        print(f"\n{map_manager.get_map_display()}")
        
        current_layer = map_manager.get_current_layer()
        if not current_layer:
            print("游戏通关！")
            break
        
        print(f"\n当前层: 第 {current_layer['layer']} 层 - {current_layer['name']}")
        print("节点:")
        for i, node in enumerate(current_layer['nodes']):
            status = "✓" if node['completed'] else "○" if node['revealed'] else "?"
            print(f"  {i}. {status} {node['name']} - {node['description']}")
        
        print("\n操作: [索引] 选择节点, [q] 退出")
        choice = input("选择: ").strip()
        
        if choice.lower() == 'q':
            break
        
        try:
            index = int(choice)
            if 0 <= index < len(current_layer['nodes']):
                node = map_manager.select_node(current_layer['nodes'][index]['id'])
                print(f"\n进入 {node['name']}!")
                print(f"类型: {node['type']}")
                if node['content']:
                    print(f"内容: {node['content']}")
                
                # 模拟完成节点
                input("按回车键继续...")
                map_manager.complete_node(node['id'])
        except ValueError:
            print("无效输入！")
    
    return map_manager
