"""
战斗引擎 - 实现基于事件队列的自动战斗系统
支持守卫、力场护盾、亡者遗赠、连击、闪避、先攻、召唤、牧师技能等关键词
"""
import json
import random
from collections import deque

from game import ai_targeting

# 半兽人共鸣档位表：等级 -> (暴击几率, 伤害倍率)
# 期望倍率 1.125 / 1.32 / 1.72 —— 每档倍率 1.17 / 1.30（深档递减，避免 6 档成为唯一正解）
HALF_ORC_CRIT = {
    1: (0.25, 1.5),
    2: (0.40, 1.8),
    3: (0.60, 2.2),
}


class BattleEngine:
    """战斗引擎 - 使用事件队列处理后进先出逻辑"""
    
    def __init__(self, log_callback=None, data_loader=None):
        """
        初始化战斗引擎
        log_callback: 日志记录回调函数
        data_loader: 数据加载函数，用于召唤时查找单位模板
        """
        self.event_queue = deque()
        self.battle_log = []
        self.log_callback = log_callback or self._default_log
        self.data_loader = data_loader
        self._tribe_resonance = {}  # 种族共鸣数据，跨方法共享
        self._relic_mods = {}       # 本场战斗的宝物修正（simulate_battle 注入）
        self._double_damage_used = False  # 「每场战斗一次」类宝物的使用标记
        self.use_ai_targeting = True      # 目标选择走决策树；False = 历史随机规则（对拍用）
        
    def _default_log(self, message):
        """默认日志函数：仅输出到控制台"""
        print(message)
    
    def _log(self, message):
        """记录战斗日志：内部始终保存，并可选调用外部回调"""
        self.battle_log.append(message)
        if self.log_callback:
            self.log_callback(message)
    
    def reset(self):
        """重置战斗引擎状态（保留种族共鸣数据，由 apply_tribe_effects 管理）"""
        self.event_queue.clear()
        self.battle_log.clear()
        # 注意：不清空 _tribe_resonance，因为 apply_tribe_effects 在 simulate_battle 之前调用
    
    def add_event(self, event):
        """添加事件到队列（后进先出）"""
        self.event_queue.append(event)
    
    def process_events(self):
        """处理所有事件（后进先出）"""
        while self.event_queue:
            event = self.event_queue.pop()
            self._handle_event(event)
    
    def _handle_event(self, event):
        """处理单个事件"""
        event_type = event.get('type')
        
        if event_type == 'attack':
            self._handle_attack(event)
        elif event_type == 'death':
            self._handle_death(event)
        elif event_type == 'trigger_keyword':
            self._handle_keyword_trigger(event)
        elif event_type == 'battle_start':
            self._handle_battle_start(event)
        elif event_type == 'turn_start':
            self._handle_turn_start(event)
        elif event_type == 'heal':
            self._handle_heal_event(event)
        elif event_type == 'summon':
            self._handle_summon_event(event)
        else:
            self._log(f"未知事件类型: {event_type}")
    
    # ============================================================
    # 战斗开始
    # ============================================================
    
    def _handle_battle_start(self, event):
        """处理战斗开始事件"""
        allies = event.get('allies', [])
        enemies = event.get('enemies', [])
        
        # 记录 max_health（用于治疗、复活、召唤时缩放）
        for unit in allies + enemies:
            if 'max_health' not in unit or unit['max_health'] <= 0:
                unit['max_health'] = unit.get('health', 1)
        
        # 触发友军战吼
        for ally in allies:
            if 'battle_cry' in ally.get('script', {}):
                self._trigger_battle_cry(ally, allies, enemies)
        
        # 触发敌军战斗开始效果（Boss/精英）
        for enemy in enemies:
            start_script = enemy.get('script', {}).get('battle_start')
            if start_script:
                self._trigger_enemy_battle_start(enemy, start_script, allies, enemies)

        # 龙裔种族共鸣：战斗开始时对随机敌人造成火焰伤害（宝物「龙裔鳞片」再 +N）
        fire_damage = self._tribe_resonance.get('dragonborn_fire_damage', 0)
        fire_damage += int((getattr(self, '_relic_mods', {}) or {}).get('tribe_fire_bonus', 0) or 0)
        if fire_damage > 0 and enemies:
            alive_enemies = [e for e in enemies if e['health'] > 0]
            if alive_enemies:
                target = random.choice(alive_enemies)
                target['health'] -= fire_damage
                self._log(f"龙裔共鸣：火焰吐息对 {target['name']} 造成 {fire_damage} 点伤害")
                if target['health'] <= 0:
                    self.add_event({
                        'type': 'death',
                        'unit': target,
                        'side': 'enemy'
                    })
        
        # 触发火焰吐息（FIRE_BREATH）
        for unit in allies + enemies:
            if 'FIRE_BREATH' in unit.get('keywords', []):
                # 确定对手
                opponents = enemies if unit in allies else allies
                if not opponents:
                    continue
                # 伤害 = 攻击力的一半（向上取整），最低 1；龙裔受「龙裔鳞片」加成
                damage = max(1, (unit.get('attack', 0) + 1) // 2)
                if unit.get('tribe') == 'dragonborn':
                    damage += int((getattr(self, '_relic_mods', {}) or {}).get('tribe_fire_bonus', 0) or 0)
                for target in opponents:
                    if target['health'] > 0:
                        target['health'] -= damage
                        self._log(f"{unit['name']} 的火焰吐息对 {target['name']} 造成 {damage} 点伤害")
                        if target['health'] <= 0:
                            self.add_event({
                                'type': 'death',
                                'unit': target,
                                'side': 'enemy' if unit in allies else 'ally'
                            })
    
    def _trigger_enemy_battle_start(self, enemy, script, allies, enemies):
        """触发敌军战斗开始效果"""
        effect_type = script.get('type')
        value = script.get('value', 0)
        
        if effect_type == 'damage_all':
            for ally in allies:
                if ally['health'] > 0:
                    ally['health'] -= value
                    self._log(f"{enemy['name']} 的战斗开始效果对 {ally['name']} 造成 {value} 点伤害")
                    if ally['health'] <= 0:
                        self.add_event({
                            'type': 'death',
                            'unit': ally,
                            'side': 'ally'
                        })
        
        elif effect_type == 'heal_all':
            for e in enemies:
                if e['health'] > 0:
                    max_hp = e.get('max_health', e['health'] + value)
                    e['health'] = min(e['health'] + value, max_hp)
                    self._log(f"{enemy['name']} 的战斗开始效果治疗 {e['name']} {value} 点生命")
        
        elif effect_type == 'summon':
            self._execute_summon(enemy, script, enemies, is_ally=False)
    
    def _trigger_battle_cry(self, unit, allies, enemies):
        """触发战吼效果"""
        script = unit.get('script', {})
        battle_cry = script.get('battle_cry', {})
        effect_type = battle_cry.get('type')
        value = battle_cry.get('value', 0)

        if effect_type == 'damage_random':
            if enemies:
                alive = [e for e in enemies if e['health'] > 0]
                if alive:
                    target = random.choice(alive)
                    damage = self._calculate_damage(value, target)
                    target['health'] -= damage
                    self._log(f"{unit['name']} 的战吼对 {target['name']} 造成 {damage} 点伤害")
                    if target['health'] <= 0:
                        self.add_event({
                            'type': 'death',
                            'unit': target,
                            'side': 'enemy'
                        })

        elif effect_type == 'damage_all':
            if enemies:
                for target in enemies:
                    if target['health'] > 0:
                        damage = self._calculate_damage(value, target)
                        target['health'] -= damage
                        self._log(f"{unit['name']} 的战吼对 {target['name']} 造成 {damage} 点伤害")
                        if target['health'] <= 0:
                            self.add_event({
                                'type': 'death',
                                'unit': target,
                                'side': 'enemy'
                            })

        elif effect_type == 'heal_all':
            healed = []
            for ally in allies:
                if ally['health'] > 0:
                    max_hp = ally.get('max_health', ally['health'] + value)
                    ally['health'] = min(ally['health'] + value, max_hp)
                    healed.append(ally['name'])
            if healed:
                self._log(f"{unit['name']} 的战吼治疗 {', '.join(healed)} 各 {value} 点生命")

        elif effect_type == 'buff_all':
            stat = battle_cry.get('stat', 'attack')
            for ally in allies:
                if ally['health'] > 0:
                    ally[stat] = ally.get(stat, 0) + value
            self._log(f"{unit['name']} 的战吼使所有友军 {stat}+{value}")
    
    # ============================================================
    # 攻击与伤害
    # ============================================================
    
    def _handle_attack(self, event):
        """处理攻击事件"""
        attacker = event.get('attacker')
        defender = event.get('defender')
        
        if not attacker or not defender:
            return
        
        # 检查攻击者是否还活着
        if attacker.get('health', 0) <= 0:
            return
        
        # 检查力场护盾
        if 'SHIELD' in defender.get('keywords', []):
            defender['keywords'].remove('SHIELD')
            self._log(f"{defender['name']} 的力场护盾抵消了伤害！")
            return
        
        # 检查闪避（DODGE）
        if self._try_dodge(attacker, defender):
            self._log(f"{defender['name']} 闪避了 {attacker['name']} 的攻击！")
            return
        
        # 计算伤害
        damage = self._calculate_damage(attacker['attack'], defender)

        # 宝物：每场战斗一次的下一次攻击双倍（狂战士药剂）
        mods = getattr(self, '_relic_mods', {}) or {}
        is_ally_attacker = attacker.get('_side') == 'ally'
        if (is_ally_attacker and int(mods.get('double_damage_once', 0) or 0) > 0
                and not self._double_damage_used):
            self._double_damage_used = True
            damage *= 2
            self._log(f"{attacker['name']} 的狂战士药剂生效！本次伤害翻倍")

        # 半兽人种族共鸣：按档位缩放暴击几率与倍率
        half_orc_chance = self._tribe_resonance.get('half_orc_double_chance', 0)
        if half_orc_chance > 0 and random.random() < half_orc_chance:
            multiplier = float(self._tribe_resonance.get('half_orc_multiplier', 2.0))
            damage = int(round(damage * multiplier))
            self._log(f"{attacker['name']} 的半兽人共鸣触发！造成 {multiplier} 倍伤害！")

        # 矮人种族共鸣：首个战斗回合减伤（抗爆发起手）
        turn_index = (getattr(self, '_last_battle_state', None) or {}).get('turn', 0)
        if turn_index == 0 and defender.get('tribe') == 'dwarf':
            reduction = int(self._tribe_resonance.get('dwarf_first_round_reduction', 0) or 0)
            if reduction > 0:
                reduced = min(damage, reduction)
                damage -= reduced
                if reduced:
                    self._log(f"{defender['name']} 的矮人共鸣减免了 {reduced} 点伤害")

        # 应用伤害
        defender['health'] -= damage
        self._log(f"{attacker['name']} 对 {defender['name']} 造成 {damage} 点伤害 (剩余HP: {defender['health']})")

        # 检查横扫（SWEEP 与 CLEAVE 是同一件事：引擎历史实现叫 SWEEP，数据/设计稿用 CLEAVE）
        if {'SWEEP', 'CLEAVE'} & set(attacker.get('keywords', [])):
            defender_list = self._get_unit_list(defender)
            if defender_list:
                idx = None
                for i, u in enumerate(defender_list):
                    if u is defender:
                        idx = i
                        break
                if idx is not None:
                    sweep_targets = []
                    if idx > 0 and defender_list[idx - 1].get('health', 0) > 0:
                        sweep_targets.append(defender_list[idx - 1])
                    if idx < len(defender_list) - 1 and defender_list[idx + 1].get('health', 0) > 0:
                        sweep_targets.append(defender_list[idx + 1])
                    for st in sweep_targets:
                        sweep_damage = self._calculate_damage(1, st)
                        st['health'] -= sweep_damage
                        self._log(f"{attacker['name']} 的横扫对 {st['name']} 造成 {sweep_damage} 点伤害 (剩余HP: {st['health']})")
                        if st['health'] <= 0:
                            self.add_event({
                                'type': 'death',
                                'unit': st,
                                'side': event.get('defender_side', 'enemy'),
                                'killer': attacker
                            })

        # 检查剧毒
        if 'POISON' in attacker.get('keywords', []):
            defender['health'] = 0
            self._log(f"{defender['name']} 被剧毒杀死！")
        
        # 检查死亡
        if defender['health'] <= 0:
            self.add_event({
                'type': 'death',
                'unit': defender,
                'side': event.get('defender_side', 'enemy'),
                'killer': attacker
            })

        # 检查过杀（OVERKILL）— 超额伤害溅射到随机敌人
        if 'OVERKILL' in attacker.get('keywords', []) and defender['health'] < 0:
            excess = -defender['health']
            opponents = self._get_opponents(attacker)
            alive_opponents = [o for o in opponents if o['health'] > 0 and o is not defender]
            if alive_opponents and excess > 0:
                overkill_target = random.choice(alive_opponents)
                overkill_damage = self._calculate_damage(excess, overkill_target)
                overkill_target['health'] -= overkill_damage
                self._log(f"{attacker['name']} 的过杀对 {overkill_target['name']} 造成 {overkill_damage} 点溅射伤害")
                if overkill_target['health'] <= 0:
                    self.add_event({
                        'type': 'death',
                        'unit': overkill_target,
                        'side': self._get_side(overkill_target),
                        'killer': attacker
                    })
        
        # 宝物：击杀回血（吸血护符）
        if (is_ally_attacker and int(mods.get('heal_on_kill', 0) or 0) > 0
                and defender.get('health', 0) <= 0):
            amount = int(mods.get('heal_on_kill', 0) or 0)
            max_hp = attacker.get('max_health', attacker.get('health', 0) + amount)
            before = attacker.get('health', 0)
            attacker['health'] = min(before + amount, max_hp)
            if attacker['health'] > before:
                self._log(f"{attacker['name']} 的吸血护符恢复 {attacker['health'] - before} 点生命")

        # 检查连击（风怒）- 每回合可以攻击两次
        if 'FRENZY' in attacker.get('keywords', []) and not attacker.get('has_attacked_twice'):
            attacker['has_attacked_twice'] = True
            self._log(f"{attacker['name']} 发动连击！")
            # 再次攻击（重新选择目标，因为战场可能已变化）
            new_target = self._select_target(attacker,
                                              self._get_opponents(attacker))
            if new_target:
                self.add_event({
                    'type': 'attack',
                    'attacker': attacker,
                    'defender': new_target,
                    'defender_side': self._get_side(new_target)
                })

        # 宝物：先攻（速度之靴）—— 与连击共用 has_attacked_twice，每回合最多打两次
        double_chance = float(mods.get('double_attack_chance', 0.0) or 0.0)
        if (is_ally_attacker and double_chance > 0
                and not attacker.get('has_attacked_twice')
                and random.random() < min(1.0, double_chance)):
            attacker['has_attacked_twice'] = True
            self._log(f"{attacker['name']} 的速度之靴触发先攻！")
            new_target = self._select_target(attacker, self._get_opponents(attacker))
            if new_target:
                self.add_event({
                    'type': 'attack',
                    'attacker': attacker,
                    'defender': new_target,
                    'defender_side': self._get_side(new_target)
                })
    
    def _calculate_damage(self, base_attack, defender):
        """计算实际伤害（考虑护甲）"""
        damage = base_attack
        
        # 检查护甲
        if 'ARMOR' in defender.get('keywords', []):
            damage = max(1, damage - 1)  # 护甲减1伤害，最低1点
        
        return damage
    
    def _try_dodge(self, attacker, defender):
        """尝试闪避，成功返回 True。

        闪避来源：单位自带 DODGE（基础 25%）+ 单位 dodge_chance 字段 +
        宝物额外闪避 + 宝物种族闪避。
        旧版在单位没有 DODGE 关键词时直接 return False —— 于是「移位斗篷 / 暗影斗篷」
        给的闪避对没有 DODGE 的单位**完全无效**，而宝物描述并没有这个前提。
        """
        has_dodge = 'DODGE' in defender.get('keywords', [])
        chance = float(defender.get('dodge_chance', 0.0) or 0.0)
        if has_dodge:
            chance = max(chance, 0.25)
        chance += getattr(self, '_extra_dodge_chance', 0.0)

        mods = getattr(self, '_relic_mods', {}) or {}
        chance += float(mods.get('dodge_chance', 0.0) or 0.0)
        for entry in mods.get('tribe_dodges', []) or []:
            if defender.get('tribe') == entry.get('tribe'):
                chance += float(entry.get('value', 0.0) or 0.0)

        if chance <= 0:
            return False
        return random.random() < min(1.0, chance)

    # ============================================================
    # 宝物修正
    # ============================================================

    def _apply_relic_battle_start(self, allies):
        """开战时把「全局攻击加成 / 种族专属加成」落到友军身上。

        只改本次战斗用的副本（UI 与 NodeHandler 都传 deepcopy），不污染常驻阵容。
        """
        mods = getattr(self, '_relic_mods', {}) or {}

        bonus = int(mods.get('global_attack_bonus', 0) or 0)
        if bonus:
            for ally in allies:
                if ally.get('health', 0) > 0:
                    ally['attack'] = ally.get('attack', 0) + bonus
            self._log(f"宝物加成：所有友军攻击力 +{bonus}")

        for entry in mods.get('tribe_buffs', []) or []:
            tribe = entry.get('tribe')
            stat = entry.get('stat', 'attack')
            value = entry.get('value', 0)
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
            if hit:
                self._log(f"宝物加成：{hit} 名 {tribe} 冒险者获得 {stat}{value:+d}"
                          if stat in ('attack', 'health')
                          else f"宝物加成：{hit} 名 {tribe} 冒险者获得 {stat}")

    def _apply_hero_passives(self, allies, hero):
        """英雄被动里能落到战斗上的部分。

        · 游荡者「敏捷+3」→ 全队先攻 +2
        · 术士「以血为契」→ 全队攻击 +1（代价是最大生命 −3）
        """
        if hero is None:
            return
        initiative = int(getattr(hero, 'PASSIVE_INITIATIVE_BONUS', 0) or 0)
        if initiative > 0:
            for ally in allies:
                ally['initiative'] = ally.get('initiative', 10) + initiative
            self._log(f"{hero.name} 的敏捷让全队先攻 +{initiative}")

        attack = int(getattr(hero, 'PASSIVE_ATTACK_BONUS', 0) or 0)
        if attack > 0:
            for ally in allies:
                if ally.get('health', 0) > 0:
                    ally['attack'] = ally.get('attack', 0) + attack
            self._log(f"{hero.name} 的以血为契让全队攻击 +{attack}")

    def _apply_heal_per_turn(self, hero):
        """宝物：每回合结束恢复英雄生命（再生护符）。"""
        if hero is None:
            return
        amount = int((getattr(self, '_relic_mods', {}) or {}).get('heal_per_turn', 0) or 0)
        if amount <= 0:
            return
        before = hero.health
        hero.heal(amount)
        healed = hero.health - before
        if healed > 0:
            self._log(f"再生护符：恢复英雄 {healed} 点生命值")
    
    # ============================================================
    # 死亡与亡语
    # ============================================================
    
    def _handle_death(self, event):
        """处理单位死亡事件"""
        unit = event.get('unit')
        side = event.get('side', 'unknown')
        killer = event.get('killer')
        
        # 牧师治疗祷言：友方死亡时复活（保留在战场中）
        if side == 'ally' and self._try_cleric_resurrect(unit):
            return
        
        self._log(f"{unit['name']} 阵亡！")
        
        # 触发亡者遗赠（亡语）
        script = unit.get('script', {})
        mods = getattr(self, '_relic_mods', {}) or {}
        if 'deathrattle' in script:
            triggers = 1
            if side == 'ally' and int(mods.get('deathrattle_double', 0) or 0) > 0:
                triggers = 2
                self._log(f"亡灵法书：{unit['name']} 的亡语触发两次")
            for _ in range(triggers):
                self.add_event({
                    'type': 'trigger_keyword',
                    'keyword': 'deathrattle',
                    'unit': unit,
                    'side': side,
                    'effect': script['deathrattle']
                })
        
        # 触发血怒（复仇）- 友方死亡后触发
        self._trigger_blood_fury(unit, side)

        # 提夫林种族共鸣：友军死亡时对随机敌人造成暗影伤害
        tiefling_damage = self._tribe_resonance.get('tiefling_death_damage', 0)
        if tiefling_damage > 0 and side == 'ally':
            if hasattr(self, '_last_battle_state'):
                enemies = self._last_battle_state.get('enemies', [])
                alive_enemies = [e for e in enemies if e['health'] > 0]
                if alive_enemies:
                    target = random.choice(alive_enemies)
                    target['health'] -= tiefling_damage
                    self._log(f"提夫林共鸣：暗影之力对 {target['name']} 造成 {tiefling_damage} 点伤害")
                    if target['health'] <= 0:
                        self.add_event({
                            'type': 'death',
                            'unit': target,
                            'side': 'enemy'
                        })

        # 宝物：提夫林之球 —— 提夫林冒险者阵亡时额外造成暗影伤害
        relic_shadow = int(mods.get('tribe_death_damage', 0) or 0)
        if relic_shadow > 0 and side == 'ally' and unit.get('tribe') == 'tiefling':
            if hasattr(self, '_last_battle_state'):
                enemies = self._last_battle_state.get('enemies', [])
                alive_enemies = [e for e in enemies if e['health'] > 0]
                if alive_enemies:
                    target = random.choice(alive_enemies)
                    target['health'] -= relic_shadow
                    self._log(f"提夫林之球：暗影之力对 {target['name']} 造成 {relic_shadow} 点伤害")
                    if target['health'] <= 0:
                        self.add_event({
                            'type': 'death',
                            'unit': target,
                            'side': 'enemy'
                        })

    def _try_cleric_resurrect(self, unit):
        """尝试用牧师技能复活单位"""
        battle_state = getattr(self, '_last_battle_state', None)
        if not battle_state:
            return False
        
        hero = battle_state.get('hero')
        if not hero or hero.hero_class != 'cleric':
            return False
        if not getattr(hero, 'has_healing_word', False):
            return False
        
        # 消耗治疗祷言
        hero.has_healing_word = False
        # 只恢复 50% 生命 + 以 2 点英雄生命为引
        # （平衡实测：每场一次的"白送单位"让牧师通关率高出其他职业 10-19pp；
        #   满血复活更高。代价落在英雄血线上，正好与"牧师最耐打"互相抵消。）
        ratio = float(getattr(hero, 'REVIVE_HEALTH_RATIO', 0.5) or 0.5)
        cost = int(getattr(hero, 'REVIVE_HEALTH_COST', 0) or 0)
        max_hp = unit.get('max_health', unit.get('health', 1))
        unit['health'] = max(1, int(round(max_hp * ratio)))
        if cost:
            hero.take_damage(cost)
        self._log(f"{hero.name} 的治疗祷言救回了 {unit['name']}"
                  f"（HP: {unit['health']}/{max_hp}，自身 -{cost}）")
        return True
    
    def _trigger_blood_fury(self, dead_unit, dead_side):
        """触发血怒效果：友方死亡时，所有带血怒关键词的友军获得+2攻击力"""
        if not hasattr(self, '_last_battle_state'):
            return

        # 找到亡者同侧的存活单位
        if dead_side == 'ally':
            allies = self._last_battle_state.get('allies', [])
        else:
            allies = self._last_battle_state.get('enemies', [])

        for unit in allies:
            if unit is dead_unit or unit.get('health', 0) <= 0:
                continue
            if 'BLOOD_FURY' in unit.get('keywords', []):
                unit['attack'] = unit.get('attack', 0) + 2
                self._log(f"{unit['name']} 的血怒触发！攻击力 +2")
    
    def _handle_keyword_trigger(self, event):
        """处理关键词触发效果"""
        keyword = event.get('keyword')
        unit = event.get('unit')
        effect = event.get('effect', {})
        
        if keyword == 'deathrattle':
            self._handle_deathrattle(unit, effect)
    
    def _handle_deathrattle(self, unit, effect):
        """处理亡者遗赠效果"""
        effect_type = effect.get('type')
        value = effect.get('value', 0)
        
        # 从最后一次战斗状态获取敌我列表
        allies = []
        enemies = []
        if hasattr(self, '_last_battle_state'):
            allies = self._last_battle_state.get('allies', [])
            enemies = self._last_battle_state.get('enemies', [])
        
        if effect_type == 'damage_random':
            if enemies:
                alive = [e for e in enemies if e['health'] > 0]
                if alive:
                    target = random.choice(alive)
                    target['health'] -= value
                    self._log(f"{unit['name']} 的亡语对 {target['name']} 造成 {value} 点伤害")
                    if target['health'] <= 0:
                        self.add_event({
                            'type': 'death',
                            'unit': target,
                            'side': 'enemy'
                        })
        
        elif effect_type == 'damage_all':
            if enemies:
                for target in enemies:
                    if target['health'] > 0:
                        target['health'] -= value
                        self._log(f"{unit['name']} 的亡语对 {target['name']} 造成 {value} 点伤害")
                        if target['health'] <= 0:
                            self.add_event({
                                'type': 'death',
                                'unit': target,
                                'side': 'enemy'
                            })
        
        elif effect_type == 'summon':
            side = unit.get('_side', 'enemy')
            recipients = enemies if side == 'enemy' else allies
            self._execute_summon(unit, effect, recipients, is_ally=(side == 'ally'))
    
    # ============================================================
    # 召唤
    # ============================================================
    
    def _execute_summon(self, summoner, script, recipients, is_ally=False):
        """执行召唤，将新单位加入战场"""
        summon_id = script.get('summon_id', '')
        count = script.get('count', 1)
        
        if not self.data_loader:
            self._log(f"{summoner['name']} 召唤了 {count} 个 {summon_id}（无法加载数据，未实际加入战场）")
            return
        
        templates = []
        try:
            enemies_data = self.data_loader('enemies.json') or []
            adventurers_data = self.data_loader('adventurers.json') or []
            templates = enemies_data + adventurers_data
        except Exception as e:
            self._log(f"召唤失败：无法加载单位数据（{e}）")
            return
        
        template = None
        for t in templates:
            if t.get('id') == summon_id:
                template = t
                break
        
        if not template:
            self._log(f"{summoner['name']} 召唤了 {count} 个 {summon_id}（找不到模板）")
            return
        
        summoned = []
        for _ in range(count):
            new_unit = template.copy()
            new_unit['max_health'] = new_unit.get('health', 1)
            new_unit['_summoned'] = True
            new_unit['_side'] = 'ally' if is_ally else 'enemy'
            # 生成唯一 id，避免与同名单位冲突
            new_unit['id'] = f"{summon_id}_{random.randint(1000, 9999)}"
            recipients.append(new_unit)
            summoned.append(new_unit['name'])
        
        if summoned:
            self._log(f"{summoner['name']} 召唤了 {count} 个 {summon_id} ({', '.join(summoned)})")
    
    def _handle_summon_event(self, event):
        """处理召唤事件（外部触发）"""
        summoner = event.get('summoner')
        script = event.get('script', {})
        recipients = event.get('recipients', [])
        is_ally = event.get('is_ally', False)
        self._execute_summon(summoner, script, recipients, is_ally)
    
    # ============================================================
    # 治疗 / 回合开始技能
    # ============================================================
    
    def _handle_turn_start(self, event):
        """处理单位回合开始事件"""
        unit = event.get('unit')
        allies = event.get('allies', [])
        enemies = event.get('enemies', [])
        
        if not unit or unit.get('health', 0) <= 0:
            return
        
        # 处理再生（REGENERATION）：回合开始时恢复 2 点生命
        if 'REGENERATION' in unit.get('keywords', []):
            heal_amount = 2
            max_hp = unit.get('max_health', unit['health'] + heal_amount)
            old_hp = unit['health']
            unit['health'] = min(unit['health'] + heal_amount, max_hp)
            healed = unit['health'] - old_hp
            if healed > 0:
                self._log(f"{unit['name']} 的再生恢复了 {healed} 点生命")
        
        script = unit.get('script', {})
        turn_start = script.get('turn_start')
        if not turn_start:
            return
        
        effect_type = turn_start.get('type')
        value = turn_start.get('value', 0)
        
        if effect_type == 'heal_lowest':
            alive_allies = [a for a in allies if a['health'] > 0 and a != unit]
            if not alive_allies:
                return
            target = min(alive_allies, key=lambda a: a['health'] / max(a.get('max_health', 1), 1))
            max_hp = target.get('max_health', target['health'] + value)
            target['health'] = min(target['health'] + value, max_hp)
            self._log(f"{unit['name']} 的牧师技能治疗 {target['name']} {value} 点生命")
        
        elif effect_type == 'buff_random':
            alive_allies = [a for a in allies if a['health'] > 0 and a != unit]
            if alive_allies:
                target = random.choice(alive_allies)
                stat = turn_start.get('stat', 'attack')
                target[stat] = target.get(stat, 0) + value
                self._log(f"{unit['name']} 的牧师技能使 {target['name']} {stat}+{value}")
        
        elif effect_type == 'damage_random':
            alive_enemies = [e for e in enemies if e['health'] > 0]
            if alive_enemies:
                target = random.choice(alive_enemies)
                target['health'] -= value
                self._log(f"{unit['name']} 的技能对 {target['name']} 造成 {value} 点伤害")
                if target['health'] <= 0:
                    self.add_event({
                        'type': 'death',
                        'unit': target,
                        'side': 'enemy'
                    })
    
    def _handle_heal_event(self, event):
        """处理治疗事件"""
        target = event.get('target')
        amount = event.get('amount', 0)
        if target and target.get('health', 0) > 0:
            max_hp = target.get('max_health', target['health'] + amount)
            target['health'] = min(target['health'] + amount, max_hp)
            self._log(f"{target['name']} 恢复 {amount} 点生命")
    
    # ============================================================
    # 战斗主循环
    # ============================================================
    
    def simulate_battle(self, allies, enemies, hero=None, extra_dodge_chance=0.0,
                        relic_mods=None):
        """
        模拟完整战斗
        allies: 友军单位列表
        enemies: 敌军单位列表
        hero: 英雄对象（可选）
        extra_dodge_chance: 额外闪避几率（外部来源）
        relic_mods: 宝物战斗修正字典（见 game/relic_effects.build_battle_mods）
        返回: (胜利方, 战斗日志)
        """
        self.reset()
        self._relic_mods = dict(relic_mods or {})
        self._double_damage_used = False
        
        # 初始化战斗状态
        battle_state = {
            'allies': allies,
            'enemies': enemies,
            'hero': hero,
            'turn': 0
        }
        self._last_battle_state = battle_state
        self._extra_dodge_chance = extra_dodge_chance

        # 牧师自动激活治疗祷言（被动技能，无需手动触发）
        if hero and hero.hero_class == 'cleric':
            hero.has_healing_word = True
        
        # 确保所有单位有 max_health
        for unit in allies + enemies:
            if 'max_health' not in unit or unit['max_health'] <= 0:
                unit['max_health'] = unit.get('health', 1)

        # 宝物：全局攻击加成 + 种族专属加成（只作用于本次战斗的副本）
        self._apply_relic_battle_start(allies)
        # 英雄被动：游荡者的「敏捷」= 全队先攻加成
        self._apply_hero_passives(allies, hero)
        
        self._log("=== 战斗开始 ===")
        
        # 触发战斗开始效果
        self.add_event({
            'type': 'battle_start',
            'allies': allies,
            'enemies': enemies
        })
        self.process_events()
        
        # 战斗循环
        max_turns = 100  # 防止无限循环
        while battle_state['turn'] < max_turns:
            # 检查战斗是否结束
            if self._check_battle_end(battle_state):
                break
            
            # 处理所有单位的攻击（按先攻排序）
            self._process_attack_phase(battle_state)
            
            # 处理事件队列
            self.process_events()
            
            battle_state['turn'] += 1
            self._apply_heal_per_turn(hero)
        
        # 判断胜负
        allies_alive = any(a['health'] > 0 for a in allies)
        enemies_alive = any(e['health'] > 0 for e in enemies)
        
        if allies_alive and not enemies_alive:
            self._log("=== 战斗胜利！ ===")
            return ('ally', self.battle_log)
        elif enemies_alive and not allies_alive:
            self._log("=== 战斗失败... ===")
            return ('enemy', self.battle_log)
        else:
            self._log("=== 战斗平局 ===")
            return ('draw', self.battle_log)
    
    def _check_battle_end(self, battle_state):
        """检查战斗是否结束"""
        allies_alive = any(a['health'] > 0 for a in battle_state['allies'])
        enemies_alive = any(e['health'] > 0 for e in battle_state['enemies'])
        
        return not allies_alive or not enemies_alive
    
    def _process_attack_phase(self, battle_state):
        """处理攻击阶段（按先攻 initiative 排序）"""
        allies = battle_state['allies']
        enemies = battle_state['enemies']
        
        # 合并所有存活单位，按 initiative 降序排列
        all_units = []
        for a in allies:
            if a['health'] > 0:
                a['_side'] = 'ally'
                all_units.append(a)
        for e in enemies:
            if e['health'] > 0:
                e['_side'] = 'enemy'
                all_units.append(e)
        
        all_units.sort(key=lambda u: u.get('initiative', 10), reverse=True)
        
        # 重置连击标记
        for u in all_units:
            u['has_attacked_twice'] = False
        
        for unit in all_units:
            if unit.get('health', 0) <= 0:
                continue
            
            # 回合开始技能
            self.add_event({
                'type': 'turn_start',
                'unit': unit,
                'allies': allies,
                'enemies': enemies
            })
            self.process_events()
            
            if unit.get('health', 0) <= 0:
                continue
            
            # 选择目标（敌方）
            opponents = enemies if unit['_side'] == 'ally' else allies
            target = self._select_target(unit, opponents)
            if target:
                self.add_event({
                    'type': 'attack',
                    'attacker': unit,
                    'defender': target,
                    'defender_side': 'enemy' if unit['_side'] == 'ally' else 'ally'
                })
                self.process_events()
    
    def _select_target(self, attacker, potential_targets):
        """选择攻击目标。

        默认走 game/ai_targeting.py 的决策树（复用自研引擎 allin_engine 的决策树原语）：
        飞行无视守卫 → 守卫里血最少 → 可一击必杀者 → 最脆弱者。
        `use_ai_targeting = False` 时退化为历史随机规则，供固定种子对拍与回滚。
        """
        alive_targets = [t for t in potential_targets if t['health'] > 0]
        
        if not alive_targets:
            return None

        if getattr(self, 'use_ai_targeting', True):
            target = ai_targeting.choose_target(attacker, alive_targets)
            if target is not None:
                return target
        
        # 历史规则（对拍基线）
        if 'FLYING' in attacker.get('keywords', []):
            return random.choice(alive_targets)
        
        guard_targets = [t for t in alive_targets if 'GUARD' in t.get('keywords', [])]
        if guard_targets:
            return random.choice(guard_targets)
        
        return random.choice(alive_targets)
    
    def _get_opponents(self, unit):
        """获取单位的对手列表"""
        if not hasattr(self, '_last_battle_state'):
            return []
        state = self._last_battle_state
        if unit.get('_side') == 'ally':
            return state.get('enemies', [])
        return state.get('allies', [])
    
    def _get_side(self, unit):
        """获取单位 side"""
        return unit.get('_side', 'enemy')

    def _get_unit_list(self, unit):
        """获取单位所在的列表（友军或敌军），用于横扫等位置相关效果"""
        if not hasattr(self, '_last_battle_state'):
            return []
        state = self._last_battle_state
        if unit.get('_side') == 'ally':
            return state.get('allies', [])
        return state.get('enemies', [])
    
    # ============================================================
    # 种族共鸣
    # ============================================================
    
    def apply_tribe_effects(self, units, tribe, enemies=None):
        """应用种族共鸣效果 — 统计种族数量并存储共鸣等级，供战斗中触发"""
        self._tribe_resonance.clear()

        tribe_counts = {}
        for unit in units:
            unit_tribe = unit.get('tribe')
            if unit_tribe:
                tribe_counts[unit_tribe] = tribe_counts.get(unit_tribe, 0) + 1

        # 检查每个种族的共鸣（2/4/6 个 → 等级 1/2/3）
        for t, count in tribe_counts.items():
            if count >= 2:
                level = min(count // 2, 3)
                self._apply_tribe_resonance(t, units, level, enemies)

    def _apply_tribe_resonance(self, tribe, units, level, enemies=None):
        """应用种族共鸣效果 — 立即生效的修改单位属性，延迟效果存入 _tribe_resonance

        **档位必须可感知**：人类/矮人/半兽人此前 2/4/6 档完全同效（等于"凑够就完事"，
        玩家没有"要不要凑 4 档"的决策）。现在这三个种族按档位线性/表驱动缩放。
        """
        if tribe == 'human':
            # 人类：每回合第一次刷新酒馆免费 + 每回合额外铸币（1/2/3）
            self._tribe_resonance['human_free_refresh'] = True
            self._tribe_resonance['human_gold_per_turn'] = level
            self._log(f"人类共鸣 (等级 {level}): 每回合额外 +{level} 铸币，首次刷新免费")

        elif tribe == 'elf':
            # 精灵：冒险者获得敏捷（20%闪避）+ 额外闪避几率
            for unit in units:
                if unit.get('tribe') == 'elf':
                    if 'DODGE' not in unit.get('keywords', []):
                        unit.setdefault('keywords', []).append('DODGE')
                    # 精灵共鸣额外提供闪避几率
                    unit['dodge_chance'] = unit.get('dodge_chance', 0.0) + 0.05 * level
            self._log(f"精灵共鸣 (等级 {level}): 精灵冒险者获得敏捷")

        elif tribe == 'dwarf':
            # 矮人：冒险者获得护甲 + 首个战斗回合减伤（2/3/4，抗爆发起手）
            for unit in units:
                if unit.get('tribe') == 'dwarf':
                    if 'ARMOR' not in unit.get('keywords', []):
                        unit.setdefault('keywords', []).append('ARMOR')
            self._tribe_resonance['dwarf_first_round_reduction'] = level + 1
            self._log(f"矮人共鸣 (等级 {level}): 矮人获得护甲，首个回合受伤 -{level + 1}")

        elif tribe == 'dragonborn':
            # 龙裔：战斗开始时对随机敌人造成火焰伤害
            self._tribe_resonance['dragonborn_fire_damage'] = level
            self._log(f"龙裔共鸣 (等级 {level}): 战斗开始时造成 {level} 点火焰伤害")

        elif tribe == 'half_orc':
            # 半兽人：暴击几率与倍率都随档位提升（1/2/3 档 → 见 HALF_ORC_CRIT）
            chance, multiplier = HALF_ORC_CRIT.get(level, HALF_ORC_CRIT[1])
            self._tribe_resonance['half_orc_double_chance'] = chance
            self._tribe_resonance['half_orc_multiplier'] = multiplier
            self._log(f"半兽人共鸣 (等级 {level}): {chance:.0%} 几率造成 {multiplier} 倍伤害")

        elif tribe == 'tiefling':
            # 提夫林：友军死亡时对敌人造成暗影伤害
            self._tribe_resonance['tiefling_death_damage'] = level
            self._log(f"提夫林共鸣 (等级 {level}): 友军死亡时造成 {level} 点暗影伤害")
