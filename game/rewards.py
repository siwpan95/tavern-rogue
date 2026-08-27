"""
奖励系统 - 处理战斗和事件的奖励分发
支持铸币、宝物、冒险者发现等奖励类型
"""
import json
import random


class RewardSystem:
    """奖励系统"""
    
    def __init__(self, data_loader, relic_system=None):
        """
        初始化奖励系统
        data_loader: 数据加载器函数
        relic_system: 宝物系统引用（用于奖励宝物）
        """
        self.data_loader = data_loader
        self.relic_system = relic_system
        
        # 加载数据
        self.adventurers_data = None
        self.relics_data = None
        self._load_data()
    
    def _load_data(self):
        """加载数据"""
        try:
            self.adventurers_data = self.data_loader('adventurers.json')
        except:
            self.adventurers_data = []
        
        try:
            self.relics_data = self.data_loader('relics.json')
        except:
            self.relics_data = []
    
    def generate_battle_rewards(self, enemies, is_elite=False, is_boss=False):
        """
        生成战斗奖励
        enemies: 敌人列表
        is_elite: 是否是精英战斗
        is_boss: 是否是Boss战斗
        返回: 奖励字典
        """
        rewards = {
            'gold': 0,
            'discover': False,  # 发现机会
            'relic': None,        # 宝物奖励
            'adventurer': None    # 冒险者奖励
        }
        
        # 计算铸币奖励
        for enemy in enemies:
            rewards['gold'] += enemy.get('reward_gold', 0)
        
        # 精英战斗额外奖励
        if is_elite:
            rewards['gold'] += 5
            rewards['relic'] = self._random_relic()
        
        # Boss战斗额外奖励
        if is_boss:
            rewards['gold'] += 10
            rewards['relic'] = self._random_relic(rarity='rare')
            rewards['discover'] = True
        
        # 普通战斗有几率获得发现机会
        if not is_elite and not is_boss:
            rewards['discover'] = random.random() < 0.3  # 30%几率
        
        return rewards
    
    def _random_relic(self, rarity=None):
        """随机选择一个宝物"""
        if not self.relics_data:
            return None
        
        # 过滤稀有度
        if rarity:
            available = [r for r in self.relics_data if r['rarity'] == rarity]
        else:
            available = self.relics_data
        
        if not available:
            return None
        
        return random.choice(available).copy()
    
    def _random_adventurer(self, tier=None):
        """随机选择一个冒险者"""
        if not self.adventurers_data:
            return None
        
        if tier:
            available = [a for a in self.adventurers_data if a['tier'] == tier]
        else:
            available = self.adventurers_data
        
        if not available:
            return None
        
        return random.choice(available).copy()
    
    def apply_rewards(self, rewards, game_state):
        """
        应用奖励到游戏状态
        rewards: 奖励字典
        game_state: 游戏状态
        返回: 奖励描述列表
        """
        descriptions = []
        
        # 铸币
        if rewards.get('gold', 0) > 0:
            gold = game_state.get('gold', 0)
            gold += rewards['gold']
            game_state['gold'] = gold
            descriptions.append(f"获得 {rewards['gold']} 枚铸币")
        
        # 发现机会
        if rewards.get('discover', False):
            adventurer = self._random_adventurer()
            if adventurer and len(game_state.get('hand', [])) < 10:
                game_state['hand'].append(adventurer)
                descriptions.append(f"发现冒险者: {adventurer['name']}")
        
        # 宝物奖励
        if rewards.get('relic'):
            relic = rewards['relic']
            if self.relic_system:
                success, msg = self.relic_system.add_relic(relic)
                descriptions.append(msg)
        
        # 冒险者奖励
        if rewards.get('adventurer'):
            adventurer = rewards['adventurer']
            if len(game_state.get('hand', [])) < 10:
                game_state['hand'].append(adventurer)
                descriptions.append(f"获得冒险者: {adventurer['name']}")
        
        return descriptions
    
    def generate_event_rewards(self, event_id):
        """
        生成事件奖励（根据事件ID）
        返回: 奖励字典
        """
        # 简化：随机奖励
        rewards = {}
        
        reward_type = random.choice(['gold', 'adventurer', 'relic', 'heal'])
        
        if reward_type == 'gold':
            rewards['gold'] = random.randint(3, 10)
        elif reward_type == 'adventurer':
            rewards['adventurer'] = self._random_adventurer()
        elif reward_type == 'relic':
            rewards['relic'] = self._random_relic()
        elif reward_type == 'heal':
            rewards['heal'] = random.randint(5, 15)
        
        return rewards
    
    def generate_shop_items(self, layer, gold):
        """
        生成商店物品
        layer: 当前层数
        gold: 玩家铸币
        返回: 商店物品字典
        """
        items = {
            'adventurers': [],
            'relics': [],
            'refresh_cost': 1
        }
        
        # 冒险者（3个）
        available = [a for a in self.adventurers_data 
                     if a['tier'] <= min(layer, 6)]
        
        if available:
            items['adventurers'] = random.sample(available, 
                                                min(3, len(available)))
        
        # 宝物（2个）
        if self.relics_data:
            items['relics'] = random.sample(self.relics_data, 
                                           min(2, len(self.relics_data)))
        
        return items
    
    def sell_adventurer_value(self, adventurer):
        """计算出售冒险者的价值"""
        base_value = adventurer.get('cost', 3)
        return max(1, base_value // 2)  # 半价出售


def cli_reward_interface(reward_system, game_state):
    """命令行奖励界面"""
    print("=== 奖励系统 ===")
    
    # 模拟战斗奖励
    mock_enemies = [
        {'name': '哥布林', 'reward_gold': 3},
        {'name': '兽人', 'reward_gold': 4}
    ]
    
    print("\n战斗胜利！生成奖励...")
    rewards = reward_system.generate_battle_rewards(mock_enemies, is_elite=False)
    
    print("\n奖励:")
    for key, value in rewards.items():
        if value:
            print(f"  {key}: {value}")
    
    print("\n应用奖励...")
    descriptions = reward_system.apply_rewards(rewards, game_state)
    for desc in descriptions:
        print(f"  {desc}")
    
    print("\n奖励系统模块测试完成！")
    return game_state


# 测试代码
if __name__ == '__main__':
    # 模拟数据加载器
    def mock_data_loader(filename):
        if filename == 'adventurers.json':
            return [
                {
                    "id": "test_adv",
                    "name": "测试冒险者",
                    "tier": 1,
                    "attack": 1,
                    "health": 2,
                    "cost": 3
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
        return []
    
    # 创建奖励系统
    reward_system = RewardSystem(mock_data_loader)
    
    # 模拟游戏状态
    game_state = {
        'gold': 5,
        'hand': [],
        'board': []
    }
    
    # 运行命令行界面
    # cli_reward_interface(reward_system, game_state)
    
    print("奖励系统模块加载成功！")
    print(f"游戏状态: {game_state}")
