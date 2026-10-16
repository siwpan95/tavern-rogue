"""
游戏状态管理器 — 集中管理所有游戏状态和子系统
作为 Model 层的唯一数据源，所有 Scene 通过 GameManager 读写状态
"""
import os
import json
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from game.hero import create_hero, get_all_hero_classes
from game import run_save
from game.engine import BattleEngine
from game.recruit import RecruitSystem
from game.map_manager import MapManager
from game.events import EventSystem
from game.relics import RelicSystem
from game.rewards import RewardSystem
from game.node_handler import NodeHandler
from game.ai_content import AIContentGenerator
from game.persistence import ProgressManager


class GameManager:
    """中央游戏状态管理器 — 所有 Scene 共享的单例状态源"""

    MAX_HEALTH = 30
    MAX_GOLD = 10
    MAX_CARRY_GOLD = 5
    MAX_HAND = 10
    MAX_BOARD = 7
    MAX_RELICS = 6
    MAX_FLOORS = 9
    # 层数成长：每深入一层，敌人生命 +7%、攻击 +5%（进阶倍率再乘在这上面）
    FLOOR_HEALTH_GROWTH = 0.07
    FLOOR_ATTACK_GROWTH = 0.05

    # ─── 与英雄状态同步的代理属性 ───────────────────

    @property
    def health(self) -> int:
        return self.hero.health if self.hero else self._health

    @health.setter
    def health(self, value: int):
        value = max(0, min(value, self.MAX_HEALTH))
        if self.hero:
            self.hero.health = value
        self._health = value

    @property
    def gold(self) -> int:
        return self.hero.gold if self.hero else self._gold

    @gold.setter
    def gold(self, value: int):
        if self.hero:
            self.hero.gold = value
        self._gold = value

    def __init__(self, progress_manager: ProgressManager = None):
        # ===== 局外成长 =====
        self.progress = progress_manager or ProgressManager()
        self.difficulty_params = None

        # ===== 核心游戏状态 =====
        self.hero = None
        self.hand: list = []
        self.board: list = []
        self.relics: list = []
        self._gold: int = 0
        self._health: int = self.MAX_HEALTH
        self.floor: int = 1
        self.current_node = None
        self._run_class_id: str = None
        self._run_victory: bool = False

        # ===== 游戏子系统 =====
        self.battle_engine: BattleEngine = None
        self.recruit_system: RecruitSystem = None
        self.map_manager: MapManager = None
        self.event_system: EventSystem = None
        self.relic_system: RelicSystem = None
        self.reward_system: RewardSystem = None
        self.node_handler: NodeHandler = None

        # ===== 数据缓存 =====
        self._data_cache = {}
        self._data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

    # ─── 游戏生命周期 ───────────────────────────────

    def new_game(self, hero_class: str):
        """开始新游戏，应用当前职业进阶难度参数"""
        self._run_class_id = hero_class
        self._run_victory = False
        self._boss_defeated = False
        self.hero = create_hero(hero_class)
        self.difficulty_params = self.progress.get_difficulty_params(hero_class)
        # 进阶提供英雄额外生命值
        bonus_hp = self.difficulty_params.get('hero_bonus_hp', 0)
        self.hero.max_health += bonus_hp
        self.hero.health += bonus_hp
        self.gold = 0
        self.health = self.MAX_HEALTH + bonus_hp
        self.floor = 1
        self.hand.clear()
        self.board.clear()
        self.relics.clear()
        self.current_node = None
        self._init_systems()

    def _init_systems(self):
        """初始化所有游戏子系统"""

        def data_loader(filename):
            return self.load_data(filename)

        # 初始化 AI 生成器（可选，失败时事件系统回退到原始文案）
        ai_generator = AIContentGenerator()

        self.battle_engine = BattleEngine(log_callback=print, data_loader=data_loader)
        self.recruit_system = RecruitSystem(self.hero, data_loader)
        self.map_manager = MapManager(data_loader)
        self.event_system = EventSystem(data_loader, ai_generator=ai_generator)
        self.relic_system = RelicSystem(data_loader)
        self.reward_system = RewardSystem(data_loader, self.relic_system)
        self.node_handler = NodeHandler(
            data_loader, self.battle_engine,
            self.event_system, self.relic_system
        )

    # ─── 铸币经济 ──────────────────────────────────

    def award_turn_gold(self) -> int:
        """发放回合铸币: 3 + 层数, 上限 10"""
        turn_gold = 3 + self.floor
        old = self.gold
        self.gold = min(self.gold + turn_gold, self.MAX_GOLD)
        return self.gold - old

    def spend_gold(self, amount: int) -> bool:
        """花费铸币, 返回是否成功"""
        if self.gold >= amount:
            self.gold -= amount
            return True
        return False

    def end_turn_cap_gold(self):
        """回合结束: 最多保留 5 枚"""
        if self.gold > self.MAX_CARRY_GOLD:
            self.gold = self.MAX_CARRY_GOLD

    # ─── 英雄生命 ──────────────────────────────────

    def heal_hero(self, amount: int) -> int:
        """治疗英雄, 返回实际治疗量"""
        old = self.health
        self.health = min(self.health + amount, self.MAX_HEALTH)
        return self.health - old

    def damage_hero(self, amount: int) -> int:
        """对英雄造成伤害, 返回剩余生命；致命时先看凤凰之灰能否救回。"""
        self.health = max(0, self.health - amount)
        if self.health <= 0 and self.relic_system is not None:
            if self.relic_system.try_hero_revive(self.hero):
                print("[TavernRogue] 凤凰之灰生效：英雄复活！")
        return self.health

    def shop_price(self, base_cost: int) -> int:
        """商店价格（宝物「商人祝福」打折，最低 1 金）。"""
        discount = self.relic_system.get_shop_discount() if self.relic_system else 0
        return max(1, int(base_cost) - discount)

    # ─── 局内存档（跑团现场，走自研引擎 SaveLoadManager）────

    def save_run(self) -> bool:
        return run_save.save_run(self)

    def load_run(self) -> bool:
        return run_save.load_run(self)

    def has_saved_run(self) -> bool:
        return run_save.has_saved_run()

    def clear_saved_run(self) -> bool:
        return run_save.clear_run()

    def is_hero_alive(self) -> bool:
        return self.health > 0

    # ─── 招募系统集成 ──────────────────────────────

    def sync_to_recruit(self):
        """同步状态到招募系统"""
        rs = self.recruit_system
        rs.hand = self.hand
        rs.board = self.board
        rs.gold = self.gold

    def sync_from_recruit(self):
        """从招募系统同步状态回来"""
        rs = self.recruit_system
        self.hand = rs.hand
        self.board = rs.board
        self.gold = rs.gold

    def start_recruit_turn(self):
        """开始招募回合 — 发放铸币 + 刷新酒馆"""
        self.sync_to_recruit()
        turn_gold = 3 + self.floor
        self.recruit_system.start_turn(turn_gold)
        self.sync_from_recruit()
        print(f"[TavernRogue] 获得 {turn_gold} 铸币！（当前: {self.gold}）")

    def end_recruit_turn(self):
        """结束招募回合"""
        self.sync_to_recruit()
        self.recruit_system.end_turn()
        self.sync_from_recruit()

    # ─── 地图系统集成 ──────────────────────────────

    def ensure_map(self):
        """确保地图已生成"""
        if not self.map_manager.map_data:
            self.map_manager.generate_map()

    def get_current_layer(self):
        return self.map_manager.get_current_layer()

    def select_map_node(self, node_id):
        """选择节点并记住它 —— current_node 是 Scene._after_node() 结算节点的唯一依据。"""
        selected = self.map_manager.select_node(node_id)
        if selected:
            self.current_node = selected
        return selected

    def complete_node(self, node_id):
        """完成节点, 返回 (ok, layer_completed)"""
        layer = self.get_current_layer()
        if layer is None:
            # 响亮失败：没有当前层（地图未生成或节点不属于本层），不能拿 None 去索引
            print("[TavernRogue] 警告：当前没有可结算的层，节点 %s 未标记完成" % node_id)
            return False, False
        remaining = [n for n in layer['nodes']
                     if not n['completed'] and n['id'] != node_id]
        was_last = len(remaining) == 0
        was_boss = (layer.get('type') == 'boss'
                    and any(n['id'] == node_id and n.get('type') == 'boss'
                            for n in layer['nodes']))

        self.map_manager.complete_node(node_id)
        if was_boss:
            self._boss_defeated = True
            print("[TavernRogue] 最终 Boss 已被击败！")

        # 不在此处更新 self.floor，由 advance_floor() 统一处理
        return True, was_last

    def is_run_won(self) -> bool:
        """通关判据：击败最终 Boss（第 8 层龙穴）；9 层全清作为保险。

        历史缺陷：`current_layer` 到 9 就封顶，`floor > MAX_FLOORS` 永不成立，
        VictoryScene 没有任何可达路径（2026-10-16 由平衡对拍发现）。
        """
        if getattr(self, '_boss_defeated', False):
            return True
        data = getattr(self.map_manager, 'map_data', None)
        layers = (data or {}).get('layers') or []
        return bool(layers) and all(layer.get('completed') for layer in layers)

    def is_layer_completed(self):
        layer = self.get_current_layer()
        return layer and layer['completed']

    def advance_floor(self):
        """推进层数并提升酒馆等级"""
        old = self.floor
        self.floor = self.map_manager.current_layer
        if self.floor > old:
            print(f"[TavernRogue] 完成第 {old} 层！进入第 {self.floor} 层！")
            if self.recruit_system.tavern_level < 6:
                self.recruit_system.upgrade_tavern()
                print(f"[TavernRogue] 酒馆等级提升到 {self.recruit_system.tavern_level}！")
        return self.floor

    # ─── 手牌/战场操作 ─────────────────────────────

    def can_add_to_hand(self) -> bool:
        return len(self.hand) < self.MAX_HAND

    def add_to_hand(self, card: dict) -> bool:
        if self.can_add_to_hand():
            self.hand.append(card)
            return True
        return False

    def remove_from_hand(self, index: int):
        if 0 <= index < len(self.hand):
            return self.hand.pop(index)
        return None

    def can_add_to_board(self) -> bool:
        return len(self.board) < self.MAX_BOARD

    def deploy(self, hand_index: int) -> bool:
        if hand_index < 0 or hand_index >= len(self.hand):
            return False
        if not self.can_add_to_board():
            return False
        card = self.hand.pop(hand_index)
        self.board.append(card)
        return True

    def recall(self, board_index: int) -> bool:
        if board_index < 0 or board_index >= len(self.board):
            return False
        if not self.can_add_to_hand():
            return False
        card = self.board.pop(board_index)
        self.hand.append(card)
        return True

    # ─── 宝物操作 ──────────────────────────────────

    def can_add_relic(self) -> bool:
        return len(self.relics) < self.MAX_RELICS

    def add_relic(self, relic: dict) -> bool:
        if self.can_add_relic():
            self.relics.append(relic)
            return True
        return False

    # ─── 数据加载 ──────────────────────────────────

    def load_data(self, filename: str):
        """加载 JSON 数据文件（带缓存）"""
        if filename not in self._data_cache:
            filepath = os.path.join(self._data_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                self._data_cache[filename] = json.load(f)
        return self._data_cache[filename]

    def get_tier_color(self, tier: int) -> tuple:
        """根据稀有度获取颜色"""
        colors = {
            1: (128, 128, 128),
            2: (0, 255, 0),
            3: (0, 128, 255),
            4: (128, 0, 255),
            5: (255, 128, 0),
        }
        return colors.get(tier, (128, 128, 128))

    def get_node_color(self, node_type: str) -> tuple:
        colors = {
            'monster': (139, 0, 0), 'battle': (139, 0, 0),
            'elite': (255, 68, 0),
            'boss': (255, 0, 0),
            'camp': (0, 68, 0), 'rest': (0, 68, 0),
            'event': (68, 0, 68),
            'shop': (68, 68, 0),
            'treasure': (0, 68, 68),
        }
        return colors.get(node_type, (128, 128, 128))

    def get_node_icon(self, node_type: str) -> str:
        icons = {
            'monster': '⚔', 'battle': '⚔',
            'elite': '💀', 'boss': '👹',
            'camp': '🏠', 'rest': '🏠',
            'event': '❓', 'shop': '🏪', 'treasure': '💎',
        }
        return icons.get(node_type, '?')

    # ─── 局外成长对接 ───────────────────────────────

    def encounter_size(self, difficulty: str = 'normal') -> int:
        """本层遭遇的敌人数量（与 MapManager 用同一公式，保证 UI 与 CLI 一致）。"""
        return MapManager.encounter_size(self.floor, difficulty)

    def scale_enemies(self, enemies: list) -> list:
        """按「层数成长 × 进阶难度」缩放敌人属性。

        历史缺陷：缩放只看进阶倍率 —— 进阶 0 时敌人**完全不随层数成长**，
        于是第 8/9 层与第 2 层一样软，平衡对拍显示通关率 89%（2026-10-16）。
        现在改为两层叠加：层数成长给基线曲线，进阶倍率在其上再乘。
        """
        floor = max(1, int(self.floor or 1))
        mult_hp = 1.0 + self.FLOOR_HEALTH_GROWTH * (floor - 1)
        mult_atk = 1.0 + self.FLOOR_ATTACK_GROWTH * (floor - 1)
        if self.difficulty_params:
            mult_hp *= self.difficulty_params.get('enemy_health_mult', 1.0)
            mult_atk *= self.difficulty_params.get('enemy_attack_mult', 1.0)
        scaled = []
        for e in enemies:
            copy = e.copy()
            copy['health'] = max(1, int(round(copy.get('health', 1) * mult_hp)))
            copy['max_health'] = max(copy['health'], int(round(copy.get('max_health', copy['health']) * mult_hp)))
            copy['attack'] = max(1, int(round(copy.get('attack', 1) * mult_atk)))
            scaled.append(copy)
        return scaled

    def record_run(self, victory: bool, floor: int = None):
        """记录本局结果到局外成长"""
        if not self._run_class_id:
            return
        self._run_victory = victory
        relic_ids = [r.get('id') for r in self.relics]
        self.progress.record_run(
            self._run_class_id,
            victory,
            floor or self.floor,
            relic_ids
        )

    def is_victory(self) -> bool:
        return self._run_victory
