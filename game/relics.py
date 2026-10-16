"""
宝物系统 - 管理魔法物品的被动效果
支持7种魔法物品，包括触发时机（战斗开始、购买时、亡语等）
"""
import json
import random
from game.relic_effects import build_battle_mods


class RelicSystem:
    """宝物管理系统"""
    
    def __init__(self, data_loader):
        """
        初始化宝物系统
        data_loader: 数据加载器函数
        """
        self.data_loader = data_loader
        self.relics = []  # 当前携带的宝物
        self.relics_data = None
        self.max_relics = 6
        
        # 加载宝物数据
        self._load_relics_data()
    
    def _load_relics_data(self):
        """加载宝物数据"""
        try:
            self.relics_data = self.data_loader('relics.json')
        except Exception as e:
            print(f"加载宝物数据失败: {e}")
            self.relics_data = []
    
    def add_relic(self, relic):
        """
        添加宝物
        relic: 宝物数据字典 或 宝物ID
        返回: (成功?, 消息)
        """
        if len(self.relics) >= self.max_relics:
            return False, f"宝物已满！最多携带 {self.max_relics} 件"
        
        # 如果传入的是ID，查找宝物数据
        if isinstance(relic, str):
            relic = self._find_relic_by_id(relic)
            if not relic:
                return False, "找不到指定的宝物"
        
        # 检查是否已拥有（某些宝物可以重复）
        # 简化处理：允许重复
        self.relics.append(relic.copy())
        
        return True, f"获得宝物: {relic['name']}"
    
    def remove_relic(self, index):
        """
        移除宝物
        index: 宝物索引
        返回: (成功?, 消息)
        """
        if index < 0 or index >= len(self.relics):
            return False, "无效的宝物索引"
        
        relic = self.relics.pop(index)
        return True, f"失去宝物: {relic['name']}"
    
    def get_relics(self):
        """获取所有宝物"""
        return self.relics
    
    def clear_relics(self):
        """清空所有宝物（用于新游戏）"""
        self.relics.clear()
    
    def _find_relic_by_id(self, relic_id):
        """根据ID查找宝物数据"""
        for relic in self.relics_data:
            if relic['id'] == relic_id:
                return relic
        return None
    
    def get_combined_effects(self):
        """获取所有宝物的组合效果"""
        effects = {}
        
        for relic in self.relics:
            effect = relic.get('effect', {})
            effect_type = effect.get('type')
            value = effect.get('value', 0)
            
            if effect_type in effects:
                # 叠加效果
                if isinstance(effects[effect_type], (int, float)):
                    effects[effect_type] += value
                elif isinstance(effects[effect_type], list):
                    effects[effect_type].append(value)
            else:
                effects[effect_type] = value
        
        return effects
    
    def apply_battle_start_effects(self, allies, enemies, hero=None):
        """
        应用战斗开始时的宝物效果
        allies: 友军列表
        enemies: 敌军列表
        hero: 英雄对象（可选；吸血类宝物需要它才能真正回血）
        """
        log = []
        
        for relic in self.relics:
            effect = relic.get('effect', {})
            effect_type = effect.get('type')
            
            if effect_type == 'battle_start_damage':
                # 战斗开始时对随机敌人造成伤害
                damage = effect.get('value', 0)
                target_count = effect.get('targets', 1)
                
                for _ in range(target_count):
                    if enemies:
                        target = random.choice(enemies)
                        if target['health'] > 0:
                            target['health'] -= damage
                            log.append(f"{relic['name']}: 对 {target['name']} 造成 {damage} 点伤害")
                            
                            # 检查死亡
                            if target['health'] <= 0:
                                log.append(f"{target['name']} 被宝物效果消灭！")
            
            elif effect_type == 'battle_start_buff':
                # 战斗开始时强化所有友军
                stat = effect.get('stat', 'attack')
                value = effect.get('value', 1)
                for ally in allies:
                    if ally['health'] > 0:
                        ally[stat] = ally.get(stat, 0) + value
                        if 'max_health' not in ally:
                            ally['max_health'] = ally.get('health', 0)
                        if stat == 'health':
                            ally['max_health'] += value
                log.append(f"{relic['name']}: 所有友军 {stat}+{value}")
            
            elif effect_type == 'battle_start_lifesteal':
                # 战斗开始时造成伤害并治疗英雄
                if enemies:
                    alive = [e for e in enemies if e['health'] > 0]
                    if alive:
                        target = random.choice(alive)
                        damage = effect.get('value', 0)
                        target['health'] -= damage
                        log.append(f"{relic['name']}: 对 {target['name']} 造成 {damage} 点伤害")
                        # 吸血：必须真的回血（旧版只写日志，回血那句没人执行）
                        if hero is not None:
                            before = hero.health
                            hero.heal(damage)
                            healed = hero.health - before
                            log.append(f"{relic['name']}: 恢复英雄 {healed} 点生命值")
                        if target['health'] <= 0:
                            log.append(f"{target['name']} 被宝物效果消灭！")
            
            elif effect_type == 'battle_shield_once':
                # 战斗开始时给一个友军施加护盾
                if allies:
                    target = random.choice(allies)
                    if 'keywords' not in target:
                        target['keywords'] = []
                    if 'SHIELD' not in target['keywords']:
                        target['keywords'].append('SHIELD')
                        log.append(f"{relic['name']}: {target['name']} 获得力场护盾")

            elif effect_type == 'battle_start_shield_all':
                # 战斗开始时给所有友军施加护盾（守护图腾）
                for ally in allies:
                    if ally.get('health', 0) <= 0:
                        continue
                    keywords = ally.setdefault('keywords', [])
                    if 'SHIELD' not in keywords:
                        keywords.append('SHIELD')
                log.append(f"{relic['name']}: 所有友军获得力场护盾")

            elif effect_type == 'battle_start_random_guard':
                # 战斗开始时随机一名友军获得守卫（远古盾牌）
                alive = [a for a in allies if a.get('health', 0) > 0]
                if alive:
                    target = random.choice(alive)
                    keywords = target.setdefault('keywords', [])
                    if 'GUARD' not in keywords:
                        keywords.append('GUARD')
                    log.append(f"{relic['name']}: {target['name']} 获得守卫")

            elif effect_type == 'battle_start_debuff':
                # 战斗开始时削弱所有敌人（深渊之刃）
                stat = effect.get('stat', 'attack')
                value = effect.get('value', -1)
                for enemy in enemies:
                    if enemy.get('health', 0) <= 0:
                        continue
                    enemy[stat] = max(0, enemy.get(stat, 0) + value)
                log.append(f"{relic['name']}: 所有敌人 {stat}{value:+d}")

            elif effect_type == 'tribe_buff':
                # 指定种族获得属性或关键词（矮人护甲 / 半兽人战斧）
                tribe = effect.get('tribe')
                stat = effect.get('stat', 'attack')
                value = effect.get('value', 1)
                hit = 0
                for ally in allies:
                    if ally.get('tribe') != tribe or ally.get('health', 0) <= 0:
                        continue
                    if stat in ('attack', 'health'):
                        ally[stat] = ally.get(stat, 0) + value
                        if stat == 'health':
                            ally['max_health'] = ally.get('max_health', 0) + value
                    else:
                        keywords = ally.setdefault('keywords', [])
                        if stat not in keywords:
                            keywords.append(stat)
                    hit += 1
                log.append(f"{relic['name']}: {hit} 名 {tribe} 冒险者获得 {stat}{value:+d}"
                           if stat in ('attack', 'health')
                           else f"{relic['name']}: {hit} 名 {tribe} 冒险者获得 {stat}")

            elif effect_type == 'tribe_dodge':
                # 指定种族获得额外闪避（精灵长弓）
                tribe = effect.get('tribe')
                value = float(effect.get('value', 0.0) or 0.0)
                hit = 0
                for ally in allies:
                    if ally.get('tribe') != tribe or ally.get('health', 0) <= 0:
                        continue
                    ally['dodge_chance'] = ally.get('dodge_chance', 0.0) + value
                    hit += 1
                log.append(f"{relic['name']}: {hit} 名 {tribe} 冒险者闪避 +{value:.0%}")

        return log

    # ─── 战斗修正 / 局外效果 ──────────────────────────────

    def get_battle_mods(self):
        """战斗引擎需要的宝物修正（纯数值，见 game/relic_effects.py）。"""
        return build_battle_mods(self.relics)

    def get_battle_gold_bonus(self):
        """每场战斗后额外铸币（聚宝袋）。"""
        return int(self.get_battle_mods().get('extra_gold', 0) or 0)

    def get_relic_drop_bonus(self):
        """宝物掉落率加成（幸运币）。"""
        return float(self.get_battle_mods().get('relic_drop_bonus', 0.0) or 0.0)

    def get_shop_discount(self):
        """商店折扣（商人祝福）。"""
        return int(self.get_battle_mods().get('shop_discount', 0) or 0)

    def reset_battle_flags(self):
        """每场战斗开始前重置「每场一次」类宝物的使用标记。"""
        self._revive_used = False

    def try_hero_revive(self, hero):
        """英雄本应死亡时用凤凰之灰救回一次；返回是否救回。

        「每场战斗一次」由 reset_battle_flags() 在开战时重置。
        """
        if hero is None or getattr(self, '_revive_used', False):
            return False
        value = int(self.get_battle_mods().get('revive_on_death', 0) or 0)
        if value <= 0:
            return False
        self._revive_used = True
        hero.health = min(getattr(hero, 'max_health', value), value)
        return True
    
    def apply_heal_per_turn(self, hero):
        """应用每回合治疗效果"""
        log = []
        
        for relic in self.relics:
            effect = relic.get('effect', {})
            if effect.get('type') == 'heal_per_turn':
                heal_amount = effect.get('value', 0)
                if hero:
                    hero.heal(heal_amount)
                    log.append(f"{relic['name']}: 恢复 {heal_amount} 点生命值")
        
        return log
    
    def apply_global_attack_bonus(self):
        """获取全局攻击力加成"""
        bonus = 0
        
        for relic in self.relics:
            effect = relic.get('effect', {})
            if effect.get('type') == 'global_attack_bonus':
                bonus += effect.get('value', 0)
        
        return bonus
    
    def get_dodge_chance(self):
        """获取闪避几率"""
        chance = 0.0
        
        for relic in self.relics:
            effect = relic.get('effect', {})
            if effect.get('type') == 'dodge_chance':
                chance += effect.get('value', 0)
        
        return min(chance, 1.0)  # 最高100%
    
    def get_double_attack_chance(self):
        """获取先攻（连击）几率"""
        chance = 0.0
        
        for relic in self.relics:
            effect = relic.get('effect', {})
            if effect.get('type') == 'double_attack_chance':
                chance += effect.get('value', 0)
        
        return min(chance, 1.0)
    
    def apply_deathrattle_double(self, unit):
        """应用亡语双倍效果"""
        log = []
        
        for relic in self.relics:
            effect = relic.get('effect', {})
            if effect.get('type') == 'deathrattle_double':
                # 触发两次亡语
                if 'script' in unit and 'deathrattle' in unit['script']:
                    log.append(f"{relic['name']}: {unit['name']} 的亡语触发两次！")
                    # 实际触发逻辑需要在战斗引擎中处理
        
        return log
    
    def get_relic_display(self):
        """获取宝物显示信息"""
        if not self.relics:
            return "没有携带宝物"
        
        display = ["=== 携带的宝物 ==="]
        for i, relic in enumerate(self.relics):
            display.append(f"{i}. {relic['name']} ({relic['rarity']})")
            display.append(f"   {relic['description']}")
        
        return "\n".join(display)


class RelicManager:
    """宝物管理器 - 用于处理宝物的获取和使用"""
    
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.relic_system = RelicSystem(data_loader)
    
    def discover_relic(self, rarity=None):
        """
        发现一个随机宝物
        rarity: 稀有度过滤（None表示所有）
        返回: 宝物数据
        """
        reics_data = self.relic_system.relics_data
        
        if not reics_data:
            return None
        
        # 过滤稀有度
        if rarity:
            available = [r for r in reics_data if r['rarity'] == rarity]
        else:
            available = reics_data
        
        if not available:
            return None
        
        return random.choice(available).copy()
    
    def award_relic(self, relic=None, rarity=None):
        """
        奖励宝物
        relic: 指定宝物（None表示随机）
        rarity: 稀有度（当relic为None时有效）
        返回: (成功?, 消息)
        """
        if not relic:
            relic = self.discover_relic(rarity)
        
        if not relic:
            return False, "没有可用的宝物"
        
        return self.relic_system.add_relic(relic)


def cli_relic_interface(relic_manager):
    """命令行宝物界面"""
    print("=== 宝物系统 ===")
    
    while True:
        print(f"\n{relic_manager.relic_system.get_relic_display()}")
        print("\n操作:")
        print("1. 获取随机宝物")
        print("2. 移除宝物")
        print("3. 查看效果")
        print("q. 退出")
        
        choice = input("选择: ").strip()
        
        if choice.lower() == 'q':
            break
        
        elif choice == '1':
            success, msg = relic_manager.award_relic()
            print(msg)
        
        elif choice == '2':
            index = input("输入要移除的宝物索引: ").strip()
            try:
                idx = int(index)
                success, msg = relic_manager.relic_system.remove_relic(idx)
                print(msg)
            except ValueError:
                print("无效输入！")
        
        elif choice == '3':
            effects = relic_manager.relic_system.get_combined_effects()
            print("\n=== 组合效果 ===")
            for effect_type, value in effects.items():
                print(f"{effect_type}: {value}")
        
        else:
            print("无效选择！")
    
    return relic_manager.relic_system


# 测试代码
if __name__ == '__main__':
    # 模拟数据加载器
    def mock_data_loader(filename):
        if filename == 'relics.json':
            return [
                {
                    "id": "test_amulet",
                    "name": "测试护符",
                    "description": "每回合恢复 2 点生命值",
                    "rarity": "common",
                    "effect": {
                        "type": "heal_per_turn",
                        "value": 2
                    }
                }
            ]
        return []
    
    # 创建宝物系统
    relic_system = RelicSystem(mock_data_loader)
    
    # 测试添加宝物
    success, msg = relic_system.add_relic('test_amulet')
    print(msg)
    
    # 显示宝物
    print(relic_system.get_relic_display())
    
    print("\n宝物系统模块加载成功！")
