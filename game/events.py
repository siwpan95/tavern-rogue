"""
事件系统 - 处理随机事件和选择
支持奇遇节点的文本事件和选项后果
"""
import random
from game.event_effects import EventEffectResolver


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
            # 事件池抽干了才重置 —— 出声（否则玩家/开发者都看不出"这一局开始重复了"）
            print("[TavernRogue] 事件池已抽完 %d 个事件，重置后可重复抽取" % len(self.events_data))
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
        """应用事件效果 —— 实现只在 game/event_effects.py 一处，这里只做状态搬运。

        game_state: {'hero', 'hand', 'board', 'relics', 'gold', ...}
        返回: 更新后的 game_state（含 trigger_battle，供上层决定是否开战）
        """
        resolver = EventEffectResolver(
            hero=game_state.get('hero'),
            hand=game_state.get('hand'),
            board=game_state.get('board'),
            relics=game_state.get('relics'),
            data_loader=self.data_loader,
            map_manager=game_state.get('map_manager'),
            gold=game_state.get('gold', 0),
            max_hand=game_state.get('max_hand', 10),
        ).apply(effects)

        game_state['gold'] = resolver.gold
        game_state['hand'] = resolver.hand
        game_state['board'] = resolver.board
        game_state['relics'] = resolver.relics
        game_state.setdefault('event_logs', []).extend(resolver.logs)
        if resolver.pending_battle:
            game_state['trigger_battle'] = resolver.pending_battle
        if resolver.regenerated_map:
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
