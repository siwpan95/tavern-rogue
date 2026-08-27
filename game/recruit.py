"""
酒馆招募系统 - 实现招募界面和逻辑
支持：购买冒险者、刷新、三连合成、站位调整、铸币管理
"""
import json
import random
from collections import Counter


class RecruitSystem:
    """酒馆招募系统"""
    
    def __init__(self, hero, data_loader):
        """
        初始化招募系统
        hero: 英雄对象
        data_loader: 数据加载器函数
        """
        self.hero = hero
        self.data_loader = data_loader
        self.tavern_level = 1
        self.gold = 0
        self.refresh_cost = 1
        self.recruit_cost = 3
        self.max_gold_reserve = 5  # 最多保留5枚铸币
        
        # 酒馆中的候选冒险者
        self.tavern_pool = []
        self.hand = []  # 手牌
        self.board = []  # 场上单位（最多7个）
        self.max_board_size = 7
        self.max_hand_size = 10
        
        # 刷新次数（用于人类共鸣）
        self.refresh_count = 0
        self.free_refresh_available = False
        
        # 加载冒险者数据
        self.adventurers_data = self.data_loader('adventurers.json')
        
    def start_turn(self, turn_gold):
        """开始新的招募阶段"""
        # 获得铸币
        self.gold += turn_gold
        self.gold = min(self.gold, 10)  # 最多10枚
        
        # 重置免费刷新
        self.refresh_count = 0
        self.free_refresh_available = True
        
        # 刷新酒馆
        self._refresh_tavern_pool()
        
        return f"招募阶段开始！当前铸币: {self.gold}"
    
    def _refresh_tavern_pool(self):
        """刷新酒馆候选者"""
        self.tavern_pool = []
        
        # 根据酒馆等级生成候选者
        available = [a for a in self.adventurers_data 
                    if a['tier'] <= self.tavern_level]
        
        # 随机选择3-5个候选者
        num_candidates = min(random.randint(3, 5), len(available))
        self.tavern_pool = random.sample(available, num_candidates)
    
    def refresh(self):
        """刷新酒馆（花费1铸币）"""
        # 检查人类共鸣（每回合第一次刷新免费）
        if self.free_refresh_available and self._has_tribe_on_board('human'):
            self.free_refresh_available = False
            self._refresh_tavern_pool()
            return "人类共鸣触发！刷新酒馆免费！"
        
        # 正常刷新
        if self.gold >= self.refresh_cost:
            self.gold -= self.refresh_cost
            self.refresh_count += 1
            self.free_refresh_available = False
            self._refresh_tavern_pool()
            return f"刷新成功！剩余铸币: {self.gold}"
        else:
            return f"铸币不足！需要 {self.refresh_cost} 枚，当前 {self.gold} 枚"
    
    def recruit(self, index):
        """
        招募冒险者
        index: 酒馆候选者的索引
        """
        if index < 0 or index >= len(self.tavern_pool):
            return "无效的索引！"
        
        if len(self.hand) >= self.max_hand_size:
            return f"手牌已满！最多 {self.max_hand_size} 个"
        
        adventurer = self.tavern_pool[index]
        cost = adventurer.get('cost', self.recruit_cost)
        
        # 检查术士的生命分流
        if hasattr(self.hero, 'can_use_life_tap') and self.hero.can_use_life_tap(cost):
            # 可以选择使用生命分流
            return "可以使用生命分流（消耗2点生命值代替1枚铸币）"
        
        # 正常购买
        if self.gold >= cost:
            self.gold -= cost
            adventurer_copy = adventurer.copy()
            self.hand.append(adventurer_copy)
            self.tavern_pool.pop(index)
            return f"成功招募 {adventurer['name']}！剩余铸币: {self.gold}"
        else:
            return f"铸币不足！需要 {cost} 枚，当前 {self.gold} 枚"
    
    def use_life_tap(self, index):
        """使用生命分流购买冒险者"""
        if index < 0 or index >= len(self.tavern_pool):
            return "无效的索引！"
        
        if not hasattr(self.hero, 'use_life_tap'):
            return "你的英雄不能使用生命分流！"
        
        adventurer = self.tavern_pool[index]
        cost = adventurer.get('cost', self.recruit_cost)
        
        if self.hero.use_life_tap(cost):
            adventurer_copy = adventurer.copy()
            self.hand.append(adventurer_copy)
            self.tavern_pool.pop(index)
            return f"使用生命分流招募 {adventurer['name']}！剩余生命: {self.hero.health}"
        else:
            return "生命值不足！"
    
    def sell_adventurer(self, index, from_hand=True):
        """
        出售冒险者
        from_hand: True表示从手牌出售，False表示从场上出售
        """
        source = self.hand if from_hand else self.board
        
        if index < 0 or index >= len(source):
            return "无效的索引！"
        
        adventurer = source.pop(index)
        sell_value = 1  # 出售获得1铸币
        self.gold += sell_value
        
        return f"出售 {adventurer['name']}，获得 {sell_value} 铸币！剩余铸币: {self.gold}"
    
    def deploy_to_board(self, hand_index):
        """将手牌部署到场上"""
        if len(self.board) >= self.max_board_size:
            return f"场上已满！最多 {self.max_board_size} 个单位"
        
        if hand_index < 0 or hand_index >= len(self.hand):
            return "无效的手牌索引！"
        
        adventurer = self.hand.pop(hand_index)
        self.board.append(adventurer)
        
        return f"{adventurer['name']} 部署到场上！场上单位: {len(self.board)}"
    
    def recall_to_hand(self, board_index):
        """将场上单位召回手牌"""
        if board_index < 0 or board_index >= len(self.board):
            return "无效的场上索引！"
        
        if len(self.hand) >= self.max_hand_size:
            return f"手牌已满！最多 {self.max_hand_size} 个"
        
        adventurer = self.board.pop(board_index)
        self.hand.append(adventurer)
        
        return f"{adventurer['name']} 召回手牌！"
    
    def swap_positions(self, index1, index2, on_board=True):
        """
        调整站位
        on_board: True表示调整场上，False表示调整手牌
        """
        source = self.board if on_board else self.hand
        
        if index1 < 0 or index1 >= len(source) or index2 < 0 or index2 >= len(source):
            return "无效的索引！"
        
        source[index1], source[index2] = source[index2], source[index1]
        return "站位调整成功！"
    
    def check_triple(self):
        """检查三连（3个相同冒险者）"""
        # 统计手牌和场上的冒险者
        all_adventurers = self.hand + self.board
        adventurer_counts = Counter(a['id'] for a in all_adventurers)
        
        for adv_id, count in adventurer_counts.items():
            if count >= 3:
                # 找到三连！
                return adv_id
        
        return None
    
    def perform_triple(self, adv_id):
        """执行三连合成"""
        # 移除3个相同的冒险者
        removed = 0
        new_hand = []
        
        for adv in self.hand:
            if adv['id'] == adv_id and removed < 3:
                removed += 1
                # 不添加到新列表（即移除）
            else:
                new_hand.append(adv)
        
        self.hand = new_hand
        
        # 场上也移除
        new_board = []
        for adv in self.board:
            if adv['id'] == adv_id and removed < 3:
                removed += 1
            else:
                new_board.append(adv)
        
        self.board = new_board
        
        # 创建精英版（属性翻倍）
        base_adv = next(a for a in self.adventurers_data if a['id'] == adv_id)
        elite_adv = base_adv.copy()
        elite_adv['name'] = "精英 " + elite_adv['name']
        elite_adv['attack'] *= 2
        elite_adv['health'] *= 2
        elite_adv['tier'] += 1
        
        # 添加到手牌
        self.hand.append(elite_adv)
        
        # 发现一张当前酒馆等级的随机冒险者
        available = [a for a in self.adventurers_data 
                    if a['tier'] <= self.tavern_level]
        if available:
            discovery = random.choice(available)
            self.hand.append(discovery.copy())
        
        return f"三连成功！获得精英 {base_adv['name']} 和一张发现卡！"
    
    def _has_tribe_on_board(self, tribe):
        """检查场上是否有指定种族的单位"""
        return any(a.get('tribe') == tribe for a in self.board)
    
    def upgrade_tavern(self):
        """提升酒馆等级"""
        if self.tavern_level < 6:
            self.tavern_level += 1
            return f"酒馆等级提升到 {self.tavern_level} 级！"
        else:
            return "酒馆等级已满！"
    
    def get_status(self):
        """获取当前状态"""
        return {
            'gold': self.gold,
            'tavern_level': self.tavern_level,
            'hand_count': len(self.hand),
            'board_count': len(self.board),
            'tavern_pool': self.tavern_pool,
            'hand': self.hand,
            'board': self.board
        }
    
    def end_turn(self):
        """结束招募阶段"""
        # 未使用的铸币（最多保留5枚）
        if self.gold > self.max_gold_reserve:
            self.gold = self.max_gold_reserve
        
        return f"招募阶段结束！保留铸币: {self.gold}"


def load_adventurers_data(filename):
    """加载冒险者数据的辅助函数"""
    with open(f'data/{filename}', 'r', encoding='utf-8') as f:
        return json.load(f)


# 命令行界面
def cli_recruit_interface(hero, data_loader):
    """命令行招募界面"""
    recruit = RecruitSystem(hero, data_loader)
    
    print("=== 酒馆招募系统 ===")
    print(recruit.start_turn(3))
    
    while True:
        status = recruit.get_status()
        
        print(f"\n--- 当前状态 ---")
        print(f"铸币: {status['gold']}")
        print(f"酒馆等级: {status['tavern_level']}")
        print(f"手牌: {status['hand_count']}/10")
        print(f"场上: {status['board_count']}/7")
        
        print(f"\n--- 酒馆候选者 ---")
        for i, adv in enumerate(status['tavern_pool']):
            print(f"{i}. {adv['name']} (攻击:{adv['attack']} 生命:{adv['health']}) 花费:{adv.get('cost', 3)}")
        
        print(f"\n--- 操作 ---")
        print("1. 招募  2. 刷新  3. 出售  4. 部署  5. 召回  6. 调整站位  7. 结束回合")
        
        choice = input("选择操作: ").strip()
        
        if choice == '1':
            index = int(input("输入候选者索引: "))
            print(recruit.recruit(index))
        
        elif choice == '2':
            print(recruit.refresh())
        
        elif choice == '7':
            print(recruit.end_turn())
            break
        
        else:
            print("功能开发中...")
    
    return recruit
