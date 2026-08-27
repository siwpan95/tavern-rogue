"""
节点事件处理器 - 分发和处理不同类型的节点事件
支持怪物战斗、商店、营地、奇遇等节点类型
"""
import json
import random
from game.engine import BattleEngine
from game.events import EventSystem
from game.relics import RelicSystem
from game.ai_content import AIContentGenerator


class NodeHandler:
    """节点事件处理器"""
    
    def __init__(self, data_loader, battle_engine=None, event_system=None, relic_system=None):
        """
        初始化节点处理器
        data_loader: 数据加载器函数
        battle_engine: 战斗引擎实例
        event_system: 事件系统实例
        relic_system: 宝物系统实例
        """
        self.data_loader = data_loader
        self.battle_engine = battle_engine or BattleEngine()
        self.ai_generator = AIContentGenerator()
        self.event_system = event_system or EventSystem(data_loader, ai_generator=self.ai_generator)
        self.relic_system = relic_system or RelicSystem(data_loader)
        
        # 游戏状态
        self.hero = None
        self.hand = []
        self.board = []
        self.relics = []
        self.gold = 0
        
    def set_game_state(self, hero, hand, board, relics, gold):
        """设置游戏状态"""
        self.hero = hero
        self.hand = hand
        self.board = board
        self.relics = relics
        self.gold = gold
    
    def get_game_state(self):
        """获取当前游戏状态"""
        return {
            'hero': self.hero,
            'hand': self.hand,
            'board': self.board,
            'relics': self.relics,
            'gold': self.gold
        }
    
    def handle_node(self, node):
        """
        处理节点
        node: 节点数据字典
        返回: (结果字典, 日志列表)
        """
        if not node or 'content' not in node:
            return None, ["节点数据无效"]
        
        node_type = node['type']
        content = node['content']
        logs = []
        
        if node_type == 'monster' or node_type == 'elite' or node_type == 'boss':
            # 战斗节点
            return self._handle_battle_node(content, node_type, logs)
        
        elif node_type == 'shop':
            # 商店节点
            return self._handle_shop_node(content, logs)
        
        elif node_type == 'event':
            # 事件节点
            return self._handle_event_node(content, logs)
        
        elif node_type == 'camp':
            # 营地节点
            return self._handle_camp_node(content, logs)
        
        elif node_type == 'treasure':
            # 宝藏节点
            return self._handle_treasure_node(content, logs)
        
        else:
            logs.append(f"未知节点类型: {node_type}")
            return None, logs
    
    def _handle_battle_node(self, content, node_type, logs):
        """处理战斗节点"""
        enemies = content.get('enemies', [])
        
        if not enemies:
            logs.append("没有敌人可以战斗！")
            return {'type': 'battle', 'result': 'no_enemies'}, logs
        
        logs.append(f"遭遇战斗！敌人: {', '.join([e['name'] for e in enemies])}")
        
        # 触发种族共鸣
        self.battle_engine.apply_tribe_effects(self.board, None, enemies=enemies)
        
        # 触发宝物战斗开始效果
        if self.relic_system:
            relic_logs = self.relic_system.apply_battle_start_effects(self.board, enemies)
            logs.extend(relic_logs)
        
        # 开始战斗
        allies = self.board.copy()
        result, battle_logs = self.battle_engine.simulate_battle(allies, enemies, self.hero)
        
        logs.extend(battle_logs)
        
        # 处理战斗结果
        if result == 'ally':
            logs.append("战斗胜利！")
            
            # 应用奖励
            rewards = content.get('rewards', {})
            reward_result = self._apply_battle_rewards(rewards, logs)
            
            return {
                'type': 'battle',
                'result': 'victory',
                'rewards': reward_result
            }, logs
        
        else:
            logs.append("战斗失败...")
            
            # 英雄受到伤害
            if self.hero:
                # 计算剩余敌人的总攻击力
                total_enemy_attack = sum(e['attack'] for e in enemies if e['health'] > 0)
                self.hero.take_damage(total_enemy_attack)
                logs.append(f"英雄受到 {total_enemy_attack} 点伤害！")
            
            return {
                'type': 'battle',
                'result': 'defeat',
                'hero_damage': self.hero.health if self.hero else 0
            }, logs
    
    def _apply_battle_rewards(self, rewards, logs):
        """应用战斗奖励"""
        result = {}
        
        # 铸币奖励
        if rewards.get('gold', False):
            gold_earned = random.randint(3, 8)
            self.gold += gold_earned
            result['gold'] = gold_earned
            logs.append(f"获得 {gold_earned} 枚铸币！")
        
        # 发现机会
        if rewards.get('discover', False):
            # 随机发现一个冒险者
            adventurers_data = self.data_loader('adventurers.json')
            if adventurers_data and len(self.hand) < 10:
                adventurer = random.choice(adventurers_data).copy()
                self.hand.append(adventurer)
                result['discover'] = adventurer['name']
                logs.append(f"发现冒险者: {adventurer['name']}！")
        
        # 宝物奖励
        if rewards.get('relic', False):
            # 随机获得一个宝物
            relics_data = self.data_loader('relics.json')
            if relics_data and len(self.relics) < 6:
                relic = random.choice(relics_data).copy()
                self.relics.append(relic)
                result['relic'] = relic['name']
                logs.append(f"获得宝物: {relic['name']}！")
        
        return result
    
    def _handle_shop_node(self, content, logs):
        """处理商店节点"""
        logs.append("进入旅行商人营地...")
        
        # 简化：自动购买一个随机冒险者
        items = content.get('items', {})
        adventurers = items.get('adventurers', [])
        
        if adventurers and self.gold >= 3 and len(self.hand) < 10:
            adventurer = random.choice(adventurers).copy()
            self.hand.append(adventurer)
            self.gold -= 3
            logs.append(f"购买了 {adventurer['name']}！剩余铸币: {self.gold}")
            
            return {
                'type': 'shop',
                'purchased': adventurer['name']
            }, logs
        
        else:
            logs.append("铸币不足或手牌已满，无法购买。")
            return {'type': 'shop', 'purchased': None}, logs
    
    def _handle_event_node(self, content, logs):
        """处理事件节点"""
        event_data = content.get('event', {})
        
        if not event_data:
            logs.append("事件数据无效！")
            return None, logs
        
        logs.append(f"遭遇事件: {event_data['name']}")
        logs.append(event_data['description'])
        
        # 简化：随机选择第一个选项
        options = event_data.get('options', [])
        if options:
            option = options[0]
            logs.append(f"选择: {option['text']}")
            logs.append(option['outcome'])
            
            # 应用选项效果
            effects = option.get('effects', {})
            self._apply_event_effects(effects, logs)
            
            return {
                'type': 'event',
                'event_name': event_data['name'],
                'option_chosen': option['text']
            }, logs
        
        return {'type': 'event', 'event_name': event_data['name']}, logs
    
    def _apply_event_effects(self, effects, logs):
        """应用事件效果"""
        # 治疗
        if 'heal' in effects:
            if self.hero:
                self.hero.heal(effects['heal'])
                logs.append(f"恢复了 {effects['heal']} 点生命值！")
        
        # 伤害
        if 'damage' in effects:
            if self.hero:
                self.hero.take_damage(effects['damage'])
                logs.append(f"受到 {effects['damage']} 点伤害！")
        
        # 获得铸币
        if 'gain_gold' in effects:
            self.gold += effects['gain_gold']
            logs.append(f"获得 {effects['gain_gold']} 枚铸币！")
        
        # 获得冒险者
        if 'gain_adventurer' in effects:
            adventurer_info = effects['gain_adventurer']
            # 简化处理
            adventurers_data = self.data_loader('adventurers.json')
            if adventurers_data and len(self.hand) < 10:
                adventurer = random.choice(adventurers_data).copy()
                self.hand.append(adventurer)
                logs.append(f"获得冒险者: {adventurer['name']}！")
    
    def _handle_camp_node(self, content, logs):
        """处理营地节点"""
        logs.append("发现安全营地...")
        
        # 简化：自动恢复生命值
        if self.hero:
            heal_amount = int(self.hero.max_health * 0.3)
            self.hero.heal(heal_amount)
            logs.append(f"恢复了 {heal_amount} 点生命值！")
            
            return {
                'type': 'camp',
                'healed': heal_amount
            }, logs
        
        return {'type': 'camp', 'healed': 0}, logs
    
    def _handle_treasure_node(self, content, logs):
        """处理宝藏节点"""
        logs.append("发现宝藏密室！")
        
        # 获得大量铸币
        gold_earned = content.get('gold', 20)
        self.gold += gold_earned
        logs.append(f"获得 {gold_earned} 枚铸币！")
        
        # 可能获得宝物
        if content.get('relic', False):
            relics_data = self.data_loader('relics.json')
            if relics_data and len(self.relics) < 6:
                relic = random.choice(relics_data).copy()
                self.relics.append(relic)
                logs.append(f"获得宝物: {relic['name']}！")
                
                return {
                    'type': 'treasure',
                    'gold': gold_earned,
                    'relic': relic['name']
                }, logs
        
        return {'type': 'treasure', 'gold': gold_earned}, logs


def cli_node_handler_test():
    """命令行节点处理器测试"""
    print("=== 节点处理器测试 ===")
    
    # 模拟数据加载器
    def mock_data_loader(filename):
        if filename == 'adventurers.json':
            return [
                {
                    "id": "test_adv",
                    "name": "测试冒险者",
                    "tier": 1,
                    "attack": 2,
                    "health": 3,
                    "keywords": [],
                    "script": {},
                    "cost": 3
                }
            ]
        elif filename == 'enemies.json':
            return [
                {
                    "id": "test_enemy",
                    "name": "测试敌人",
                    "tier": 1,
                    "attack": 1,
                    "health": 2,
                    "keywords": [],
                    "script": {},
                    "reward_gold": 3
                }
            ]
        elif filename == 'relics.json':
            return [
                {
                    "id": "test_relic",
                    "name": "测试宝物",
                    "description": "测试效果",
                    "rarity": "common",
                    "effect": {}
                }
            ]
        elif filename == 'events.json':
            return [
                {
                    "id": "test_event",
                    "name": "测试事件",
                    "description": "这是一个测试事件",
                    "options": [
                        {
                            "text": "选项1",
                            "effects": {"heal": 5},
                            "outcome": "你恢复了5点生命值"
                        }
                    ]
                }
            ]
        return []
    
    # 创建节点处理器
    battle_engine = BattleEngine()
    event_system = EventSystem(mock_data_loader)
    node_handler = NodeHandler(mock_data_loader, battle_engine, event_system)
    
    # 创建模拟游戏状态
    class MockHero:
        def __init__(self):
            self.name = "测试英雄"
            self.health = 30
            self.max_health = 30
        
        def is_alive(self):
            return self.health > 0
        
        def heal(self, amount):
            self.health = min(self.health + amount, self.max_health)
        
        def take_damage(self, amount):
            self.health -= amount
        
        def apply_battle_start_effects(self, allies, enemies):
            return []
    
    hero = MockHero()
    hand = []
    board = [
        {
            "id": "test_adv",
            "name": "测试冒险者",
            "tier": 1,
            "attack": 2,
            "health": 3,
            "keywords": [],
            "script": {},
            "cost": 3
        }
    ]
    reics = []
    gold = 10
    
    node_handler.set_game_state(hero, hand, board, reics, gold)
    
    # 测试战斗节点
    print("\n--- 测试战斗节点 ---")
    mock_node = {
        'type': 'monster',
        'content': {
            'enemies': [
                {
                    "id": "test_enemy",
                    "name": "测试敌人",
                    "tier": 1,
                    "attack": 1,
                    "health": 2,
                    "keywords": [],
                    "script": {},
                    "reward_gold": 3
                }
            ],
            'rewards': {
                'gold': True,
                'discover': True
            }
        }
    }
    
    result, logs = node_handler.handle_node(mock_node)
    
    print("日志:")
    for log in logs:
        print(f"  {log}")
    
    print(f"\n结果: {result}")
    
    # 获取更新后的游戏状态
    game_state = node_handler.get_game_state()
    print(f"\n更新后的游戏状态:")
    print(f"  英雄生命值: {game_state['hero'].health}")
    print(f"  铸币: {game_state['gold']}")
    print(f"  手牌数量: {len(game_state['hand'])}")
    
    print("\n=== 测试完成 ===")


if __name__ == '__main__':
    cli_node_handler_test()
