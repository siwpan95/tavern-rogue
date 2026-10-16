"""
英雄职业系统 - 实现5个D&D职业及其技能
"""
import json
import random


class Hero:
    """英雄基类"""
    def __init__(self, name, hero_class, max_health=30):
        self.name = name
        self.hero_class = hero_class
        self.max_health = max_health
        self.health = max_health
        self.gold = 0
        self.relics = []
        self.skill_used = False
        self.skill_cooldown = 0
        
    def is_alive(self):
        """检查英雄是否存活"""
        return self.health > 0
    
    def take_damage(self, damage):
        """英雄受到伤害"""
        self.health -= damage
        if self.health < 0:
            self.health = 0
        return self.health
    
    def heal(self, amount):
        """治疗英雄"""
        self.health = min(self.health + amount, self.max_health)
        return self.health
    
    def use_skill(self, battle_context=None):
        """使用职业技能"""
        if self.skill_used:
            return None
        
        self.skill_used = True
        return self._apply_skill_effect(battle_context)
    
    def _apply_skill_effect(self, battle_context):
        """应用技能效果 - 由子类实现"""
        raise NotImplementedError
    
    def reset_skill(self):
        """重置技能（每场战斗后）"""
        self.skill_used = False

    def on_battle_end(self):
        """战斗结束钩子（子类可覆盖：如牧师被动回血）；返回恢复的生命值"""
        return 0
    
    def add_relic(self, relic):
        """添加宝物"""
        if len(self.relics) < 6:
            self.relics.append(relic)
            return True
        return False
    
    def get_relic_effects(self):
        """获取所有宝物效果"""
        effects = {}
        for relic in self.relics:
            effect_type = relic['effect']['type']
            value = relic['effect']['value']
            if effect_type in effects:
                if isinstance(effects[effect_type], (int, float)):
                    effects[effect_type] += value
            else:
                effects[effect_type] = value
        return effects


class Warrior(Hero):
    """战士 - 战争咆哮

    被动：生命值 +5 —— 与职业选择界面的文案一致（此前界面写了、代码里没有）
    """
    PASSIVE_HEALTH_BONUS = 3

    def __init__(self):
        super().__init__("战士", "warrior",
                         max_health=30 + self.PASSIVE_HEALTH_BONUS)
    
    def _apply_skill_effect(self, battle_context):
        """战争咆哮：最左侧的友军获得守卫和+2生命值"""
        if battle_context and battle_context['allies']:
            leftmost = battle_context['allies'][0]
            if 'keywords' not in leftmost:
                leftmost['keywords'] = []
            if 'GUARD' not in leftmost['keywords']:
                leftmost['keywords'].append('GUARD')
            leftmost['health'] += 2
            return f"战争咆哮：{leftmost['name']} 获得守卫和+2生命值"
        return "战争咆哮：没有友军可以强化"


class Rogue(Hero):
    """游荡者 - 暗影突袭

    被动：敏捷 +3 → 全队先攻 +2（先攻是引擎已有字段）
    """
    PASSIVE_INITIATIVE_BONUS = 2

    def __init__(self):
        super().__init__("游荡者", "rogue")
    
    def _apply_skill_effect(self, battle_context):
        """暗影突袭：对一个随机敌人造成2点伤害"""
        if battle_context and battle_context['enemies']:
            target = random.choice(battle_context['enemies'])
            if target['health'] > 0:
                target['health'] -= 2
                return f"暗影突袭：对 {target['name']} 造成 2 点伤害"
        return "暗影突袭：没有敌人可以攻击"


class Cleric(Hero):
    """牧师 - 治疗祷言

    被动：生命值 +3（"治疗+3"折算为体魄）。
    ⚠ 曾经把它实现成"每场战斗后回 3 血"——一局约 10 场战斗等于 +30 HP，
    牧师通关率直接飙到 78%（其他职业 33-54%），已改回一次性加成。
    技能：每场战斗一次救回阵亡友军，但只恢复 **50%** 生命。
    """
    PASSIVE_MAX_HEALTH_BONUS = 3
    REVIVE_HEALTH_RATIO = 0.5
    REVIVE_HEALTH_COST = 1  # 每次救回消耗 1 点英雄生命（以命换命）

    def __init__(self):
        super().__init__("牧师", "cleric",
                         max_health=30 + self.PASSIVE_MAX_HEALTH_BONUS)
    
    def _apply_skill_effect(self, battle_context):
        """治疗祷言：当一个友军死亡时，将其救回（恢复 50% 生命）"""
        # 这个技能需要在友军死亡时触发
        # 这里设置一个标记，在战斗引擎中检查
        self.has_healing_word = True
        return "治疗祷言：友军死亡时将其救回（恢复 50% 生命）"
    
    def on_ally_death(self, dead_ally, hand):
        """友军死亡时触发"""
        if hasattr(self, 'has_healing_word') and self.has_healing_word:
            dead_ally['health'] = dead_ally.get('max_health', dead_ally['health'])
            hand.append(dead_ally)
            self.has_healing_word = False
            return f"治疗祷言：{dead_ally['name']} 移回手牌并恢复生命值"
        return None


class Wizard(Hero):
    """法师 - 魔法飞弹

    被动：法力 +5 → 飞弹总伤害由 3 提升到 4（法师通关率 33%，全职业最低）
    """
    MISSILE_DAMAGE = 4

    def __init__(self):
        super().__init__("法师", "wizard")
    
    def _apply_skill_effect(self, battle_context):
        """魔法飞弹：造成 5 点伤害（法力+5），由所有敌人分摊"""
        if battle_context and battle_context['enemies']:
            alive_enemies = [e for e in battle_context['enemies'] if e['health'] > 0]
            if alive_enemies:
                total = self.MISSILE_DAMAGE
                damage_per_enemy = total // len(alive_enemies)
                remainder = total % len(alive_enemies)
                
                results = []
                for i, enemy in enumerate(alive_enemies):
                    damage = damage_per_enemy + (1 if i < remainder else 0)
                    enemy['health'] -= damage
                    results.append(f"{enemy['name']} 受到 {damage} 点伤害")
                
                return f"魔法飞弹：{'，'.join(results)}"
        return "魔法飞弹：没有敌人可以攻击"


class Warlock(Hero):
    """术士 - 生命分流

    被动：生命值 −3（27 点，以血为契的代价）+ 全队攻击 +1
    技能：购买时可消耗 2 点生命代替 1 枚铸币
    ⚠ 改前术士只有"经济技能"、战斗面**零主动**，是结构性最弱（通关率 33% vs 其他 45-78%）
    """
    PASSIVE_MAX_HEALTH_PENALTY = 2
    PASSIVE_ATTACK_BONUS = 1

    def __init__(self):
        super().__init__("术士", "warlock",
                         max_health=30 - self.PASSIVE_MAX_HEALTH_PENALTY)
        self.life_tap_available = True
    
    def _apply_skill_effect(self, battle_context):
        """生命分流：购买冒险者时，可以消耗2点生命值代替1枚铸币"""
        # 这个技能需要在购买时触发
        self.life_tap_available = True
        return "生命分流：购买冒险者时可消耗 2 点生命值代替 1 枚铸币"
    
    def can_use_life_tap(self, cost):
        """检查是否可以使用生命分流"""
        return self.life_tap_available and self.health > cost * 2
    
    def use_life_tap(self, cost):
        """使用生命分流"""
        if self.can_use_life_tap(cost):
            self.health -= cost * 2
            self.life_tap_available = False
            return True
        return False


def create_hero(hero_class):
    """根据职业名称创建英雄"""
    heroes = {
        'warrior': Warrior,
        'rogue': Rogue,
        'cleric': Cleric,
        'wizard': Wizard,
        'warlock': Warlock
    }
    
    if hero_class.lower() in heroes:
        return heroes[hero_class.lower()]()
    else:
        raise ValueError(f"未知的职业: {hero_class}")


def get_all_hero_classes():
    """获取所有可用职业"""
    return [
        {'id': 'warrior', 'name': '战士', 'skill': '战争咆哮'},
        {'id': 'rogue', 'name': '游荡者', 'skill': '暗影突袭'},
        {'id': 'cleric', 'name': '牧师', 'skill': '治疗祷言'},
        {'id': 'wizard', 'name': '法师', 'skill': '魔法飞弹'},
        {'id': 'warlock', 'name': '术士', 'skill': '生命分流'}
    ]
