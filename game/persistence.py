"""
局外成长系统 — 持久化玩家进度、职业解锁、进阶与宝物解锁
"""
import json
import os
from datetime import datetime

SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saves')
SAVE_FILE = os.path.join(SAVE_DIR, 'progress.json')

# 职业解锁链：通关一次职业 A 的进阶 N 可解锁下一职业
CLASS_UNLOCK_CHAIN = {
    'warrior': {'rogue': 0},
    'rogue': {'cleric': 0},
    'cleric': {'wizard': 0},
    'wizard': {'warlock': 0}
}

# 初始职业
STARTING_CLASSES = {'warrior'}

# 进阶等级上限
MAX_ADVANCEMENT = 5

# 进阶难度调整（用于下一局开始时的敌人强度）
ADVANCEMENT_DIFFICULTY = {
    0: {'enemy_health_mult': 1.0, 'enemy_attack_mult': 1.0, 'enemy_count_mult': 1.0, 'hero_bonus_hp': 0},
    1: {'enemy_health_mult': 1.15, 'enemy_attack_mult': 1.1, 'enemy_count_mult': 1.0, 'hero_bonus_hp': 0},
    2: {'enemy_health_mult': 1.3, 'enemy_attack_mult': 1.2, 'enemy_count_mult': 1.0, 'hero_bonus_hp': 2},
    3: {'enemy_health_mult': 1.5, 'enemy_attack_mult': 1.3, 'enemy_count_mult': 1.15, 'hero_bonus_hp': 2},
    4: {'enemy_health_mult': 1.75, 'enemy_attack_mult': 1.4, 'enemy_count_mult': 1.15, 'hero_bonus_hp': 4},
    5: {'enemy_health_mult': 2.0, 'enemy_attack_mult': 1.5, 'enemy_count_mult': 1.3, 'hero_bonus_hp': 4}
}


class ProgressManager:
    """管理玩家局外成长进度"""

    def __init__(self, save_file=None):
        self.save_file = save_file or SAVE_FILE
        self.data = self._default_data()
        self.load()

    @staticmethod
    def _default_data():
        return {
            'unlocked_classes': sorted(list(STARTING_CLASSES)),
            'advancements': {'warrior': 0, 'rogue': 0, 'cleric': 0, 'wizard': 0, 'warlock': 0},
            'relic_unlocks': {},
            'best_records': {},  # class_id: {'floor': int, 'victory': bool, 'date': str}
            'total_runs': 0,
            'victories': 0,
            'run_history': [],  # 最近 20 条记录（含 stats/seed）
            'totals': {},       # 累计统计（战斗数/精英数/铸币…）
            'achievements': []
        }

    def load(self):
        """从文件加载进度，不存在则使用默认"""
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                # 合并默认字段，防止旧版本缺失
                for key, default in self._default_data().items():
                    if key not in loaded:
                        loaded[key] = default
                self.data = loaded
                return True
            except (json.JSONDecodeError, IOError) as e:
                print(f"[ProgressManager] 加载进度失败: {e}，使用默认进度")
                self.data = self._default_data()
                return False
        return True

    def save(self):
        """保存进度到文件"""
        os.makedirs(os.path.dirname(self.save_file), exist_ok=True)
        try:
            with open(self.save_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"[ProgressManager] 保存进度失败: {e}")
            return False

    def is_class_unlocked(self, class_id: str) -> bool:
        return class_id in self.data['unlocked_classes']

    def unlock_class(self, class_id: str) -> bool:
        """解锁一个职业，返回是否为新解锁（立即落盘，避免进度丢失）"""
        if class_id not in self.data['unlocked_classes']:
            self.data['unlocked_classes'].append(class_id)
            self.data['unlocked_classes'].sort()
            self.save()
            return True
        return False

    def get_class_advancement(self, class_id: str) -> int:
        return self.data['advancements'].get(class_id, 0)

    def set_class_advancement(self, class_id: str, level: int):
        """设置职业进阶等级，不会超过 MAX_ADVANCEMENT（立即落盘）"""
        self.data['advancements'][class_id] = max(0, min(level, MAX_ADVANCEMENT))
        self.save()

    def advance_class(self, class_id: str) -> bool:
        """提升一个职业的进阶等级，返回是否成功"""
        current = self.get_class_advancement(class_id)
        if current < MAX_ADVANCEMENT:
            self.set_class_advancement(class_id, current + 1)
            # 自动解锁链式职业
            unlocked = CLASS_UNLOCK_CHAIN.get(class_id, {})
            for next_class, required_level in unlocked.items():
                if current + 1 >= required_level:
                    self.unlock_class(next_class)
            self.save()
            return True
        return False

    def get_difficulty_params(self, class_id: str) -> dict:
        """获取当前职业进阶对应的难度参数"""
        level = self.get_class_advancement(class_id)
        return ADVANCEMENT_DIFFICULTY.get(level, ADVANCEMENT_DIFFICULTY[0]).copy()

    def get_unlocked_relics(self) -> set:
        """获取已解锁的宝物 id 集合"""
        return {rid for rid, unlocked in self.data['relic_unlocks'].items() if unlocked}

    def unlock_relic(self, relic_id: str) -> bool:
        if relic_id not in self.data['relic_unlocks'] or not self.data['relic_unlocks'].get(relic_id):
            self.data['relic_unlocks'][relic_id] = True
            self.save()
            return True
        return False

    def record_run(self, class_id: str, victory: bool, floor: int, relics: list = None,
                   stats: dict = None, seed: int = None):
        """记录一局结果（含本局统计与种子；未通关也计入总局数与累计统计）"""
        self.data['total_runs'] += 1
        if victory:
            self.data['victories'] += 1

        record = {
            'class_id': class_id,
            'victory': victory,
            'floor': floor,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'relics': relics or [],
            'stats': stats or {},
            'seed': seed,
        }
        self.data['run_history'].append(record)
        self.data['run_history'] = self.data['run_history'][-20:]

        # 累计统计（用于统计面板与失败屏的"你没白打"）
        totals = self.data.setdefault('totals', {})
        for key, value in (stats or {}).items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value

        # 更新最佳记录
        best = self.data['best_records'].get(class_id, {})
        if victory or (not best.get('victory') and floor > best.get('floor', 0)):
            self.data['best_records'][class_id] = {
                'floor': floor,
                'victory': victory,
                'date': record['date']
            }

        # 胜利时自动进阶并解锁下一职业
        if victory:
            self.advance_class(class_id)

        self.save()

    def get_advancement_label(self, class_id: str) -> str:
        level = self.get_class_advancement(class_id)
        if level == 0:
            return '进阶 0'
        return f'进阶 {level}'

    def get_available_classes(self) -> list:
        """返回已解锁职业列表，包含进阶等级"""
        from game.hero import get_all_hero_classes
        all_classes = get_all_hero_classes()
        return [
            {
                **cls,
                'locked': not self.is_class_unlocked(cls['id']),
                'advancement': self.get_class_advancement(cls['id']),
                'best_record': self.data['best_records'].get(cls['id'], {})
            }
            for cls in all_classes
        ]
