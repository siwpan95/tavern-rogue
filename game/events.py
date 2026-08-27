"""
事件系统 - 处理随机事件和选择
支持奇遇节点的文本事件和选项后果
"""
import json
import random


class EventSystem:
    """事件系统"""
    
    def __init__(self, data_loader, ai_generator=None):
        """
        初始化事件系统
        data_loader: 数据加载器函数
        ai_generator: 可选的 AI 内容生成器，用于增强事件文案
        """
        self.data_loader = data_loader
        self.ai_generator = ai_generator
        self.events_data = None
        self.current_event = None
        self.event_history = []  # 事件历史
        
    def load_events(self):
        """加载事件数据"""
        try:
            self.events_data = self.data_loader('events.json')
            return True
        except Exception as e:
            print(f"加载事件数据失败: {e}")
            return False
    
    def select_random_event(self):
        """随机选择一个事件（如启用 AI 则增强文案）"""
        if not self.events_data:
            self.load_events()
        
        if not self.events_data:
            return None
        
        # 避免重复事件（可选）
        available_events = [e for e in self.events_data 
                          if e['id'] not in self.event_history]
        
        if not available_events:
            # 如果所有事件都经历过了，重置历史
            self.event_history.clear()
            available_events = self.events_data
        
        picked = random.choice(available_events)
        self.event_history.append(picked['id'])
        
        # AI 增强文案
        if self.ai_generator and self.ai_generator.is_available():
            self.current_event = self.ai_generator.enhance_event(picked)
        else:
            self.current_event = picked
        
        return self.current_event
    
    def select_event_by_id(self, event_id):
        """根据ID选择事件"""
        if not self.events_data:
            self.load_events()
        
        for event in self.events_data:
            if event['id'] == event_id:
                self.current_event = event
                return event
        
        return None
    
    def get_current_event(self):
        """获取当前事件"""
        return self.current_event
    
    def execute_option(self, option_index, game_state):
        """
        执行事件选项
        option_index: 选项索引
        game_state: 游戏状态字典，包含英雄、手牌、场上单位等
        返回: (成功?, 结果描述, 更新的游戏状态)
        """
        if not self.current_event:
            return False, "没有进行中的事件", game_state
        
        options = self.current_event.get('options', [])
        
        if option_index < 0 or option_index >= len(options):
            return False, "无效的选项", game_state
        
        option = options[option_index]
        effects = option.get('effects', {})
        
        # 执行效果
        result = self._apply_effects(effects, game_state)
        
        return True, option.get('outcome', '完成了选择。'), result
    
    def _apply_effects(self, effects, game_state):
        """应用事件效果"""
        hero = game_state.get('hero')
        hand = game_state.get('hand', [])
        board = game_state.get('board', [])
        relics = game_state.get('relics', [])
        gold = game_state.get('gold', 0)
        
        # 造成伤害
        if 'damage' in effects:
            if hero:
                hero.take_damage(effects['damage'])
        
        if 'damage_hero' in effects:
            if hero:
                hero.take_damage(effects['damage_hero'])
        
        # 治疗
        if 'heal' in effects:
            if hero:
                hero.heal(effects['heal'])
        
        if 'heal_hero' in effects:
            if hero:
                hero.heal(effects['heal_hero'])
        
        # 获得铸币
        if 'gain_gold' in effects:
            gold += effects['gain_gold']
            game_state['gold'] = gold
        
        # 花费铸币
        if 'cost_gold' in effects:
            if gold >= effects['cost_gold']:
                gold -= effects['cost_gold']
                game_state['gold'] = gold
            else:
                return game_state  # 铸币不足，不执行
        
        # 获得冒险者
        if 'gain_adventurer' in effects:
            adventurer_info = effects['gain_adventurer']
            tier = adventurer_info.get('tier', 1)
            random_choice = adventurer_info.get('random', False)
            
            if random_choice:
                # 随机选择冒险者
                adventurers_data = self.data_loader('adventurers.json')
                available = [a for a in adventurers_data if a['tier'] == tier]
                if available and len(hand) < 10:
                    adventurer = random.choice(available).copy()
                    hand.append(adventurer)
                    game_state['hand'] = hand
        
        # 失去宝物
        if 'lose_relic' in effects:
            count = effects['lose_relic']
            if len(relics) >= count:
                for _ in range(count):
                    relics.pop(0)
                game_state['relics'] = relics
        
        # 获得宝物
        if 'gain_relic' in effects:
            relic_info = effects['gain_relic']
            random_choice = relic_info.get('random', False)
            
            if random_choice:
                relics_data = self.data_loader('relics.json')
                if relics_data and len(relics) < 6:
                    relic = random.choice(relics_data).copy()
                    relics.append(relic)
                    game_state['relics'] = relics
        
        # 场上单位强化
        if 'upgrade_board' in effects:
            stat = effects['upgrade_board'].get('stat', 'attack')
            value = effects['upgrade_board'].get('value', 1)
            for unit in board:
                unit[stat] = unit.get(stat, 0) + value
            game_state['board'] = board
        
        # 净化场上单位
        if effects.get('purify_board', False):
            negative = {'POISON'}
            for unit in board:
                unit['keywords'] = [k for k in unit.get('keywords', []) if k not in negative]
            game_state['board'] = board
        
        # 为场上单位附魔关键词
        if 'enchant_board' in effects:
            enchant = effects['enchant_board']
            keyword = enchant.get('keyword')
            apply_all = enchant.get('all', False)
            if keyword:
                targets = board if apply_all else ([random.choice(board)] if board else [])
                for unit in targets:
                    keywords = unit.setdefault('keywords', [])
                    if keyword not in keywords:
                        keywords.append(keyword)
                game_state['board'] = board
        
        # 投硬币（随机正负效果）
        if effects.get('coin_flip', False):
            if random.choice([True, False]):
                # 正面：获得增益
                if hero:
                    hero.heal(5)
            else:
                # 反面：获得减益
                if hero:
                    hero.take_damage(3)
        
        # 开始战斗
        if 'start_battle' in effects:
            battle_info = effects['start_battle']
            # 这里需要触发战斗，简化处理
            game_state['trigger_battle'] = battle_info
        
        # 献祭冒险者
        if effects.get('sacrifice_adventurer', False):
            if hand:
                hand.pop(0)
                game_state['hand'] = hand
                if 'heal_hero' in effects:
                    if hero:
                        hero.heal(effects['heal_hero'])
        
        # 重塑地图
        if effects.get('regenerate_map', False):
            game_state['regenerate_map'] = True
        
        return game_state
    
    def get_event_display(self, event=None):
        """获取事件显示文本"""
        if not event:
            event = self.current_event
        
        if not event:
            return "没有进行中的事件"
        
        display = []
        display.append(f"=== {event['name']} ===")
        display.append(event['description'])
        display.append("\n选项:")
        
        for i, option in enumerate(event.get('options', [])):
            display.append(f"  {i}. {option['text']}")
        
        return "\n".join(display)


def cli_event_interface(event_system, game_state):
    """命令行事件界面"""
    print("=== 事件系统 ===")
    
    event = event_system.select_random_event()
    
    if not event:
        print("没有可用的事件")
        return game_state
    
    while True:
        print(f"\n{event_system.get_event_display()}")
        
        try:
            choice = input("\n选择选项 (输入数字或 q 退出): ").strip()
            
            if choice.lower() == 'q':
                break
            
            option_index = int(choice)
            success, outcome, game_state = event_system.execute_option(option_index, game_state)
            
            if success:
                print(f"\n结果: {outcome}")
                
                # 检查英雄是否死亡
                hero = game_state.get('hero')
                if hero and not hero.is_alive():
                    print("英雄死亡！游戏结束！")
                    break
                
                input("\n按回车键继续...")
                break
            else:
                print(f"\n错误: {outcome}")
        
        except ValueError:
            print("无效输入！请输入数字。")
    
    return game_state


# 测试代码
if __name__ == '__main__':
    # 模拟数据加载器
    def mock_data_loader(filename):
        if filename == 'events.json':
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
                        },
                        {
                            "text": "选项2",
                            "effects": {"damage": 3},
                            "outcome": "你失去了3点生命值"
                        }
                    ]
                }
            ]
        return []
    
    # 创建事件系统
    event_system = EventSystem(mock_data_loader)
    
    # 创建模拟游戏状态
    class MockHero:
        def __init__(self):
            self.health = 30
            self.max_health = 30
        
        def is_alive(self):
            return self.health > 0
        
        def heal(self, amount):
            self.health = min(self.health + amount, self.max_health)
        
        def take_damage(self, damage):
            self.health -= damage
    
    game_state = {
        'hero': MockHero(),
        'hand': [],
        'board': [],
        'relics': [],
        'gold': 10
    }
    
    # 运行命令行界面
    # cli_event_interface(event_system, game_state)
    
    print("事件系统模块加载成功！")
