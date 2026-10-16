"""
battle.py — 自动战斗场景（调用 BattleEngine）
"""
import random
import copy
import re
import pygame
from ui.scenes.base import Scene
from ui.renderer import (
    fill_bg, draw_status_bar, draw_unit_card, fonts, COLORS, WIDTH
)


class BattleScene(Scene):
    """自动战斗场景：酒馆战棋阵容自动战斗，带逐帧动画回放"""

    # 动画参数
    _ANIM_DURATION = 0.65      # 单个事件播放时长（秒）
    _ATTACK_OFFSET = 35        # 攻击者向前位移幅度
    _SHAKE_AMPLITUDE = 6       # 受击抖动幅度
    _FLOAT_SPEED = 40          # 伤害数字飘动速度（像素/秒）

    def enter(self, node=None, event_battle=None, **kwargs):
        super().enter(**kwargs)

        self._node = node
        # 事件战斗（事件选项里的「战斗！」）：敌人由事件指定，胜利奖励也由事件给
        self._event_battle = event_battle or None
        self._event_reward_gold = int((event_battle or {}).get('reward_gold', 0) or 0)
        ntype = node['type'] if node else 'monster'
        is_boss = (ntype == 'boss')
        is_elite = (ntype == 'elite')

        self._title = "BOSS战斗" if is_boss else ("精英战斗" if is_elite else "战斗")

        # 生成敌人（按当前层数过滤等级）
        enemies_data = self.gm.load_data('enemies.json')
        floor = self.gm.floor if self.gm else 1
        if is_boss:
            candidates = [e for e in enemies_data if e.get('is_boss', False) and e.get('tier', 1) <= floor + 2]
            if not candidates:
                candidates = [e for e in enemies_data if e.get('is_boss', False)] or enemies_data
            raw = random.sample(candidates, min(1, len(candidates)))
        elif is_elite:
            candidates = [e for e in enemies_data if e.get('is_elite', False) and e.get('tier', 1) <= floor + 2]
            if not candidates:
                candidates = [e for e in enemies_data if e.get('is_elite', False)] or enemies_data
            raw = random.sample(candidates, min(self.gm.encounter_size('elite'), len(candidates)))
        else:
            candidates = [e for e in enemies_data
                          if not e.get('is_elite', False) and not e.get('is_boss', False)
                          and e.get('tier', 1) <= floor + 1]
            if not candidates:
                candidates = [e for e in enemies_data
                              if not e.get('is_elite', False) and not e.get('is_boss', False)]
            raw = random.sample(candidates, min(self.gm.encounter_size('normal'), len(candidates)))

        self.enemies = self.gm.scale_enemies(copy.deepcopy(raw))

        # 事件战斗：用事件指定的敌人替换按层随机抽取的结果
        if self._event_battle:
            template = self._find_enemy_template(self._event_battle.get('enemy'))
            if template is None:
                print("[TavernRogue] 事件引用了不存在的敌人 %s，已改为普通遭遇"
                      % self._event_battle.get('enemy'))
            else:
                self._title = "事件战斗"
                self.enemies = self.gm.scale_enemies(copy.deepcopy([template]))

        self.allies = copy.deepcopy(self.gm.board)
        self.messages = ["⚔ 战斗准备中……"]
        self.phase = 'prepare'
        self.turn = 0

        if self.gm.hero:
            self.gm.hero.reset_skill()

        # 应用战斗准备效果（种族共鸣 + 宝物战斗开始效果）
        self._apply_pre_battle_effects()

        # 动画系统
        self._anim_events = []
        self._anim_index = 0
        self._anim_timer = 0.0
        self._anim_result = None
        self._floating_texts = []   # [(x, y, text, color, life)]
        self._unit_offsets = {}     # {unit_id: (dx, dy)}
        self._dead_units = set()    # 已播放死亡动画的单位 id
        self._hidden_units = set()  # 已经完全淡出的单位 id
        self._card_w_enemy = 180    # 敌人卡片动态宽度
        self._card_w_ally = 180     # 友军卡片动态宽度

    def _apply_pre_battle_effects(self):
        """战斗前应用种族共鸣和宝物效果"""
        if not self.gm.battle_engine or not self.allies:
            return

        relic_mods = self.gm.relic_system.get_battle_mods() if self.gm.relic_system else {}
        self.gm.battle_engine.apply_tribe_effects(
            self.allies, None, enemies=self.enemies, relic_mods=relic_mods)

        if self.gm.relic_system and self.enemies:
            # 每场战斗重置「每场一次」类宝物（凤凰之灰）
            self.gm.relic_system.reset_battle_flags()
            relic_logs = self.gm.relic_system.apply_battle_start_effects(
                self.allies, self.enemies, hero=self.gm.hero)
            for log in relic_logs:
                self.messages.append(log)

    # ─── 单位位置与查找 ───────────────────────────

    def _unit_positions(self):
        """返回每个单位在屏幕上的基础位置 {unit_id: (x, y)}，自适应居中"""
        positions = {}
        margin = 60
        available = WIDTH - 2 * margin
        base_cw = 180
        gap = 20
        min_cw = 110

        def _calc_row(units, y):
            count = len(units)
            if count == 0:
                return base_cw, 0, margin
            total_w = count * base_cw + (count - 1) * gap
            if total_w <= available:
                cw = base_cw
                actual_gap = (available - count * cw) / max(count - 1, 1) if count > 1 else 0
                start_x = margin
            else:
                cw = max(min_cw, (available - (count - 1) * gap) / count)
                actual_gap = gap
                actual_total = count * cw + (count - 1) * actual_gap
                start_x = margin + (available - actual_total) / 2
            return cw, actual_gap, start_x

        # 敌人行
        if self.enemies:
            cw_e, gap_e, sx_e = _calc_row(self.enemies, 100)
            self._card_w_enemy = cw_e
            for i, e in enumerate(self.enemies):
                uid = e.get('id')
                if uid in self._hidden_units:
                    continue
                x = sx_e + i * (cw_e + gap_e)
                positions[uid] = (x, 100)

        # 友军行
        if self.allies:
            cw_a, gap_a, sx_a = _calc_row(self.allies, 400)
            self._card_w_ally = cw_a
            for i, a in enumerate(self.allies):
                uid = a.get('id')
                if uid in self._hidden_units:
                    continue
                x = sx_a + i * (cw_a + gap_a)
                positions[uid] = (x, 400)

        return positions

    def _find_unit_by_name(self, name, side=None):
        """按名称查找单位（优先活着的）"""
        candidates = []
        if side in (None, 'ally'):
            candidates.extend(self.allies)
        if side in (None, 'enemy'):
            candidates.extend(self.enemies)
        for u in candidates:
            if u.get('name') == name:
                return u
        return None

    def _find_unit_id(self, unit):
        return unit.get('id') if unit else None

    # ─── 技能 ─────────────────────────────────────

    def _skill_name(self):
        names = {'warrior': '战争咆哮', 'rogue': '暗影突袭',
                 'cleric': '治疗祷言', 'wizard': '魔法飞弹', 'warlock': '生命分流'}
        return names.get(self.gm.hero.hero_class, '未知技能')

    def _use_skill(self):
        if not self.gm.hero or self.gm.hero.skill_used or self.phase != 'prepare':
            return
        result = self.gm.hero.use_skill({'allies': self.allies, 'enemies': self.enemies})
        if result:
            self.messages.append(f"[技能] {result}")

    # ─── 自动战斗与动画 ───────────────────────────

    def _start_battle(self):
        if self.phase != 'prepare':
            return

        if not self.gm.battle_engine:
            self.messages.append("战斗引擎未初始化！")
            return

        self.messages.append("=== 自动战斗开始 ===")
        # Boss 战换曲（普通战斗用 scenes.switch_to 里播的 battle BGM）
        audio = getattr(self.app, 'audio', None)
        if audio is not None and (self._node or {}).get('type') == 'boss':
            audio.play_bgm('boss_fight')
        # 宝物修正统一走 relic_mods（闪避/攻击/先攻/吸血/亡语双倍…），
        # 不要再单传 extra_dodge_chance —— 那条路会让同一个宝物效果被算两遍。
        relic_mods = self.gm.relic_system.get_battle_mods() if self.gm.relic_system else {}
        self._anim_result, logs = self.gm.battle_engine.simulate_battle(
            self.allies, self.enemies, self.gm.hero, relic_mods=relic_mods
        )

        # 解析日志为动画事件（跳过纯标记行）
        self._anim_events = self._parse_battle_logs(logs)
        self._anim_index = 0
        self._anim_timer = 0.0
        self._floating_texts.clear()
        self._unit_offsets.clear()

        if self._anim_events:
            self.phase = 'animating'
        else:
            # 没有可播放的事件，直接结算
            self._set_battle_result(self._anim_result)

    def _parse_battle_logs(self, logs):
        """把 BattleEngine 日志解析为动画事件列表"""
        events = []
        for log in logs:
            # 攻击：A 对 B 造成 N 点伤害 (剩余HP: M)
            m = re.match(r'(.+?) 对 (.+?) 造成 (\d+) 点伤害 \(剩余HP: (-?\d+)\)', log)
            if m:
                a_name, t_name, dmg, _ = m.groups()
                attacker = self._find_unit_by_name(a_name)
                target = self._find_unit_by_name(t_name)
                if attacker and target:
                    events.append({
                        'type': 'attack',
                        'attacker': attacker,
                        'target': target,
                        'damage': int(dmg),
                        'message': log
                    })
                continue

            # 闪避：X 闪避了 Y 的攻击！
            m = re.match(r'(.+?) 闪避了 (.+?) 的攻击！', log)
            if m:
                t_name, a_name = m.groups()
                target = self._find_unit_by_name(t_name)
                attacker = self._find_unit_by_name(a_name)
                if target:
                    events.append({
                        'type': 'dodge',
                        'target': target,
                        'attacker': attacker,
                        'message': log
                    })
                continue

            # 治疗：A 的战吼/技能 治疗 B N 点生命
            m = re.match(r'(.+?) 治疗 (.+?) (\d+) 点生命', log)
            if m:
                src, targets, amount = m.groups()
                # targets 可能是多个名字用逗号分隔，取第一个可识别的
                t_name = targets.split('，')[0].strip()
                target = self._find_unit_by_name(t_name)
                if target:
                    events.append({
                        'type': 'heal',
                        'target': target,
                        'amount': int(amount),
                        'message': log
                    })
                continue

            # 治疗（简化）：X 恢复 N 点生命
            m = re.match(r'(.+?) 恢复 (\d+) 点生命', log)
            if m:
                t_name, amount = m.groups()
                target = self._find_unit_by_name(t_name)
                if target:
                    events.append({
                        'type': 'heal',
                        'target': target,
                        'amount': int(amount),
                        'message': log
                    })
                continue

            # 复活：X 的治疗祷言复活了 Y（HP: N）
            m = re.match(r'(.+?) 的治疗祷言复活了 (.+?)（HP: (\d+)）', log)
            if m:
                _, t_name, hp = m.groups()
                target = self._find_unit_by_name(t_name)
                if target:
                    events.append({
                        'type': 'resurrect',
                        'target': target,
                        'amount': int(hp),
                        'message': log
                    })
                continue

            # 增益：X 的战吼使所有友军 stat+N  或  X 的牧师技能使 Y stat+N
            m = re.match(r'(.+?) 的(?:战吼|牧师技能)使 (.+?) (\w+)\+(\d+)', log)
            if m:
                src, targets, stat, value = m.groups()
                t_name = targets.split('，')[0].strip()
                target = self._find_unit_by_name(t_name)
                if target:
                    events.append({
                        'type': 'buff',
                        'target': target,
                        'stat': stat,
                        'value': int(value),
                        'message': log
                    })
                continue

            # 召唤：X 召唤了 N 个 Y
            m = re.match(r'(.+?) 召唤了 (\d+) 个 (.+?) \(', log)
            if m:
                a_name, count, summon_id = m.groups()
                attacker = self._find_unit_by_name(a_name)
                if attacker:
                    events.append({
                        'type': 'summon',
                        'attacker': attacker,
                        'count': int(count),
                        'summon_id': summon_id,
                        'message': log
                    })
                continue

            # 护盾
            if '力场护盾抵消了伤害' in log:
                name = log.split(' 的')[0]
                target = self._find_unit_by_name(name)
                if target:
                    events.append({'type': 'shield', 'target': target, 'message': log})
                continue

            # 剧毒
            if '被剧毒杀死' in log:
                name = log.split(' 被')[0]
                target = self._find_unit_by_name(name)
                if target:
                    events.append({'type': 'poison', 'target': target, 'message': log})
                continue

            # 连击
            if '发动连击' in log:
                name = log.split(' 发动')[0]
                attacker = self._find_unit_by_name(name)
                if attacker:
                    events.append({'type': 'frenzy', 'attacker': attacker, 'message': log})
                continue

            # 阵亡
            if '阵亡' in log:
                name = log.split(' 阵亡')[0]
                unit = self._find_unit_by_name(name)
                if unit:
                    events.append({'type': 'death', 'unit': unit, 'message': log})
                continue

        return events

    def _set_battle_result(self, result):
        """设置战斗结算阶段"""
        self.gm.record_battle(result, (self._node or {}).get('type'))
        # 战斗结束钩子（牧师被动回血等）；CLI 路径在 node_handler 里同样调用
        hero = self.gm.hero
        if hero is not None and hasattr(hero, 'on_battle_end'):
            healed = hero.on_battle_end()
            if healed:
                self.messages.append(f"[被动] 战斗后恢复 {healed} 点生命")
        if result == 'ally':
            self.phase = 'victory'
            self.messages.append("=== 战斗胜利！ ===")
        elif result == 'enemy':
            self.phase = 'defeat'
            self.messages.append("=== 战斗失败... ===")
        else:
            self.phase = 'defeat'
            self.messages.append("=== 战斗平局（按失败处理） ===")

    def _update_floating_texts(self, dt):
        """更新飘字位置"""
        new_texts = []
        for x, y, text, color, life in self._floating_texts:
            life -= dt
            if life > 0:
                new_texts.append((x, y - self._FLOAT_SPEED * dt, text, color, life))
        self._floating_texts = new_texts

    def _spawn_floating_text(self, unit, text, color):
        """在单位上方生成飘字"""
        uid = self._find_unit_id(unit)
        pos = self._unit_positions().get(uid)
        if pos:
            cw = self._card_w_enemy if any(e.get('id') == uid for e in self.enemies) else self._card_w_ally
            x = pos[0] + cw / 2
            y = pos[1] + 20
            self._floating_texts.append((x, y, text, color, 3.0))

    # ─── 绘制 ─────────────────────────────────────

    def draw(self):
        fill_bg(self.screen)
        draw_status_bar(self.screen, self.gm)

        t = fonts.get('large').render(self._title, True, COLORS['text_primary'])
        self.screen.blit(t, t.get_rect(center=(WIDTH // 2, 55)))

        self.buttons.clear()

        # 获取当前动画事件
        current_event = None
        if self.phase == 'animating' and self._anim_index < len(self._anim_events):
            current_event = self._anim_events[self._anim_index]

        progress = self._anim_timer / self._ANIM_DURATION if current_event else 0.0

        # 计算动画偏移
        offsets = {}
        flash_targets = set()
        shield_targets = set()
        poison_targets = set()
        frenzy_attackers = set()
        dodge_targets = set()
        heal_targets = set()
        buff_targets = set()
        resurrect_targets = set()
        summon_attackers = set()

        if current_event:
            etype = current_event['type']
            if etype == 'attack':
                attacker = current_event['attacker']
                target = current_event['target']
                a_pos = self._unit_positions().get(self._find_unit_id(attacker))
                t_pos = self._unit_positions().get(self._find_unit_id(target))
                if a_pos and t_pos:
                    # 攻击者向前冲，前半段冲出去，后半段回来
                    if progress < 0.5:
                        k = progress / 0.5
                        dx = (t_pos[0] - a_pos[0]) * k * 0.25
                        dy = (t_pos[1] - a_pos[1]) * k * 0.25
                        offsets[self._find_unit_id(attacker)] = (dx, dy)
                    else:
                        k = (progress - 0.5) / 0.5
                        dx = (t_pos[0] - a_pos[0]) * 0.25 * (1 - k)
                        dy = (t_pos[1] - a_pos[1]) * 0.25 * (1 - k)
                        offsets[self._find_unit_id(attacker)] = (dx, dy)
                # 受击抖动在中间一段
                if 0.25 <= progress <= 0.6:
                    flash_targets.add(self._find_unit_id(target))

            elif etype == 'dodge':
                dodge_targets.add(self._find_unit_id(current_event['target']))
                if 0.2 <= progress <= 0.8:
                    flash_targets.add(self._find_unit_id(current_event['target']))

            elif etype == 'heal':
                heal_targets.add(self._find_unit_id(current_event['target']))
                if 0.2 <= progress <= 0.8:
                    flash_targets.add(self._find_unit_id(current_event['target']))

            elif etype == 'buff':
                buff_targets.add(self._find_unit_id(current_event['target']))
                if 0.2 <= progress <= 0.8:
                    flash_targets.add(self._find_unit_id(current_event['target']))

            elif etype == 'resurrect':
                uid = self._find_unit_id(current_event['target'])
                resurrect_targets.add(uid)
                self._dead_units.discard(uid)
                self._hidden_units.discard(uid)
                if 0.2 <= progress <= 0.8:
                    flash_targets.add(uid)

            elif etype == 'summon':
                summon_attackers.add(self._find_unit_id(current_event['attacker']))
                if 0.2 <= progress <= 0.8:
                    flash_targets.add(self._find_unit_id(current_event['attacker']))

            elif etype == 'shield':
                shield_targets.add(self._find_unit_id(current_event['target']))

            elif etype == 'poison':
                poison_targets.add(self._find_unit_id(current_event['target']))
                if 0.2 <= progress <= 0.8:
                    flash_targets.add(self._find_unit_id(current_event['target']))

            elif etype == 'frenzy':
                frenzy_attackers.add(self._find_unit_id(current_event['attacker']))

            elif etype == 'death':
                # 死亡事件直接记录到死亡集合，draw 时淡出
                self._dead_units.add(self._find_unit_id(current_event['unit']))

        # 敌人
        for i, e in enumerate(self.enemies):
            uid = e.get('id')
            if e.get('health', 0) <= 0 and uid in self._dead_units:
                alpha = max(0, int(255 * (1 - progress)))
                if alpha <= 20:
                    self._hidden_units.add(uid)
                    continue
                self._draw_animated_unit(e, is_enemy=True, offset=offsets.get(uid, (0, 0)),
                                         flash=uid in flash_targets, alpha=alpha,
                                         shield=uid in shield_targets, poison=uid in poison_targets,
                                         frenzy=uid in frenzy_attackers,
                                         dodge=uid in dodge_targets, heal=uid in heal_targets,
                                         buff=uid in buff_targets, resurrect=uid in resurrect_targets,
                                         summon=uid in summon_attackers)
            else:
                self._draw_animated_unit(e, is_enemy=True, offset=offsets.get(uid, (0, 0)),
                                         flash=uid in flash_targets,
                                         shield=uid in shield_targets, poison=uid in poison_targets,
                                         frenzy=uid in frenzy_attackers,
                                         dodge=uid in dodge_targets, heal=uid in heal_targets,
                                         buff=uid in buff_targets, resurrect=uid in resurrect_targets,
                                         summon=uid in summon_attackers)

        # 分隔线
        pygame.draw.line(self.screen, COLORS['accent'], (50, 380), (1150, 380), 1)

        # 友军
        for i, a in enumerate(self.allies):
            uid = a.get('id')
            if a.get('health', 0) <= 0 and uid in self._dead_units:
                alpha = max(0, int(255 * (1 - progress)))
                if alpha <= 20:
                    self._hidden_units.add(uid)
                    continue
                self._draw_animated_unit(a, is_enemy=False, offset=offsets.get(uid, (0, 0)),
                                         flash=uid in flash_targets, alpha=alpha,
                                         shield=uid in shield_targets, poison=uid in poison_targets,
                                         frenzy=uid in frenzy_attackers,
                                         dodge=uid in dodge_targets, heal=uid in heal_targets,
                                         buff=uid in buff_targets, resurrect=uid in resurrect_targets,
                                         summon=uid in summon_attackers)
            else:
                self._draw_animated_unit(a, is_enemy=False, offset=offsets.get(uid, (0, 0)),
                                         flash=uid in flash_targets,
                                         shield=uid in shield_targets, poison=uid in poison_targets,
                                         frenzy=uid in frenzy_attackers,
                                         dodge=uid in dodge_targets, heal=uid in heal_targets,
                                         buff=uid in buff_targets, resurrect=uid in resurrect_targets,
                                         summon=uid in summon_attackers)

        # 伤害/效果飘字
        for x, y, text, color, life in self._floating_texts:
            alpha = max(0, int(255 * life))
            surf = fonts.get('medium').render(text, True, color)
            surf.set_alpha(alpha)
            self.screen.blit(surf, surf.get_rect(center=(int(x), int(y))))

        # 当前动画事件提示
        if current_event:
            msg = current_event.get('message', '')
            hint = fonts.get('small').render(msg, True, COLORS['warning'])
            self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 580)))

        # 消息日志
        for j, msg in enumerate(self.messages[-8:]):
            ms = fonts.get('small').render(msg, True, COLORS['text_secondary'])
            self.screen.blit(ms, (50, 620 + j * 24))

        # 阶段按钮
        if self.phase == 'prepare':
            if self.gm.hero and not self.gm.hero.skill_used:
                sn = self._skill_name()
                self.buttons.add(280, 740, 200, 40, f"[技能] {sn}", self._use_skill)
            self.buttons.add(500, 740, 200, 40, "开始战斗", self._start_battle)
        elif self.phase == 'victory':
            self.buttons.add(450, 680, 300, 50, "领取奖励", self._victory)
        elif self.phase == 'defeat':
            self.buttons.add(450, 680, 300, 50, "继续", self._defeat)

        self.buttons.add(50, 740, 150, 40, "撤退 (-10HP)", self._retreat)

        self.buttons.draw_all(self.screen)

    def _draw_animated_unit(self, unit, is_enemy, offset=(0, 0), flash=False,
                            alpha=255, shield=False, poison=False, frenzy=False,
                            dodge=False, heal=False, buff=False, resurrect=False,
                            summon=False):
        """绘制带动画效果的单位卡片"""
        uid = self._find_unit_id(unit)
        positions = self._unit_positions()
        base_x, base_y = positions.get(uid, (0, 0))
        x = base_x + offset[0]
        y = base_y + offset[1]

        w = self._card_w_enemy if is_enemy else self._card_w_ally
        h = 120
        border_color = COLORS['health'] if is_enemy else COLORS['success']
        if flash:
            border_color = (255, 255, 255)
        if poison:
            border_color = (0, 200, 0)
        if dodge:
            border_color = (0, 200, 255)
        if heal:
            border_color = (0, 255, 150)
        if buff:
            border_color = (100, 150, 255)
        if resurrect:
            border_color = (255, 215, 0)
        if summon:
            border_color = (255, 100, 255)

        # 绘制卡片（支持 alpha）
        bg = COLORS['enemy_bg'] if is_enemy else COLORS['ally_bg']
        card_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        card_surf.fill((*bg, alpha))
        pygame.draw.rect(card_surf, (*border_color, alpha), (0, 0, w, h), 3)
        self.screen.blit(card_surf, (x, y))

        # 连击光环
        if frenzy:
            pygame.draw.circle(self.screen, (255, 170, 0), (int(x + w / 2), int(y + h / 2)), 70, 3)

        # 护盾光环
        if shield:
            pygame.draw.circle(self.screen, (0, 200, 255), (int(x + w / 2), int(y + h / 2)), 65, 3)

        fm = fonts.get('medium')
        fs = fonts.get('small')

        text_color = (*COLORS['text_secondary'], alpha)
        name_surf = fm.render(unit['name'], True, COLORS['text_secondary'])
        name_surf.set_alpha(alpha)
        self.screen.blit(name_surf, (x + 8, y + 8))

        atk_surf = fs.render(f"ATK:{unit['attack']}", True, COLORS['text_secondary'])
        atk_surf.set_alpha(alpha)
        self.screen.blit(atk_surf, (x + 8, y + 38))

        # HP 条
        max_hp = max(unit.get('max_health', unit['health']), 1)
        ratio = min(unit['health'] / max_hp, 1.0)
        bar_w = w - 20
        pygame.draw.rect(self.screen, (60, 0, 0), (x + 8, y + 60, bar_w, 14))
        hp_c = (0, 200, 0) if ratio > 0.5 else (200, 200, 0) if ratio > 0.25 else (200, 0, 0)
        pygame.draw.rect(self.screen, hp_c, (x + 8, y + 60, int(bar_w * ratio), 14))
        hp_surf = fs.render(f"HP:{unit['health']}", True, COLORS['text_secondary'])
        hp_surf.set_alpha(alpha)
        self.screen.blit(hp_surf, (x + 8, y + 78))

    # ─── 动画触发辅助 ───────────────────────────

    def _trigger_attack_effect(self, event):
        """攻击事件发生时，生成伤害飘字"""
        target = event['target']
        damage = event['damage']
        self._spawn_floating_text(target, f"-{damage}", COLORS['health'])

    def _trigger_shield_effect(self, event):
        """护盾事件发生时，生成飘字"""
        self._spawn_floating_text(event['target'], "护盾", (0, 200, 255))

    def _trigger_poison_effect(self, event):
        """剧毒事件发生时，生成飘字"""
        self._spawn_floating_text(event['target'], "剧毒", (0, 255, 0))

    def _trigger_frenzy_effect(self, event):
        """连击事件发生时，生成飘字"""
        self._spawn_floating_text(event['attacker'], "连击", (255, 170, 0))

    def _trigger_dodge_effect(self, event):
        """闪避事件发生时，生成飘字"""
        self._spawn_floating_text(event['target'], "闪避", (0, 200, 255))

    def _trigger_heal_effect(self, event):
        """治疗事件发生时，生成飘字"""
        self._spawn_floating_text(event['target'], f"+{event['amount']}", (0, 255, 150))

    def _trigger_buff_effect(self, event):
        """增益事件发生时，生成飘字"""
        self._spawn_floating_text(event['target'], f"{event['stat']}+{event['value']}", (100, 150, 255))

    def _trigger_resurrect_effect(self, event):
        """复活事件发生时，生成飘字"""
        uid = self._find_unit_id(event['target'])
        self._dead_units.discard(uid)
        self._hidden_units.discard(uid)
        self._spawn_floating_text(event['target'], "复活", (255, 215, 0))

    def _trigger_summon_effect(self, event):
        """召唤事件发生时，生成飘字"""
        self._spawn_floating_text(event['attacker'], "召唤", (255, 100, 255))

    def _trigger_death_effect(self, event):
        """死亡事件发生时，生成飘字"""
        self._spawn_floating_text(event['unit'], "阵亡", (150, 150, 150))

    def update(self, dt: float):
        """推进战斗动画"""
        # 动画事件切换时触发效果飘字
        if self.phase == 'animating':
            # 检测是否刚进入当前事件（timer 在上一帧还是 0，这一帧开始增加）
            if self._anim_timer == 0.0 and self._anim_index < len(self._anim_events):
                ev = self._anim_events[self._anim_index]
                etype = ev['type']
                # 音效挂在动画事件分派点上：零侵入，不碰战斗逻辑
                audio = getattr(self.app, 'audio', None)
                if audio is not None:
                    audio.play_event(etype)
                if etype == 'attack':
                    self._trigger_attack_effect(ev)
                elif etype == 'dodge':
                    self._trigger_dodge_effect(ev)
                elif etype == 'heal':
                    self._trigger_heal_effect(ev)
                elif etype == 'buff':
                    self._trigger_buff_effect(ev)
                elif etype == 'resurrect':
                    self._trigger_resurrect_effect(ev)
                elif etype == 'summon':
                    self._trigger_summon_effect(ev)
                elif etype == 'shield':
                    self._trigger_shield_effect(ev)
                elif etype == 'poison':
                    self._trigger_poison_effect(ev)
                elif etype == 'frenzy':
                    self._trigger_frenzy_effect(ev)
                elif etype == 'death':
                    self._trigger_death_effect(ev)
                    self._dead_units.add(self._find_unit_id(ev['unit']))

            self._anim_timer += dt
            if self._anim_timer >= self._ANIM_DURATION:
                self._anim_timer = 0.0
                self._anim_index += 1
                self._unit_offsets.clear()
                if self._anim_index >= len(self._anim_events):
                    self._set_battle_result(self._anim_result)

        self._update_floating_texts(dt)

    # ─── 结果处理 ─────────────────────────────────

    def _retreat(self):
        self.gm.damage_hero(10)
        print("[TavernRogue] 撤退！损失10生命值")
        if not self.gm.is_hero_alive():
            self.switch_to('game_over')
        else:
            self._after_node()

    def _victory(self):
        bonus = self.gm.relic_system.get_battle_gold_bonus() if self.gm.relic_system else 0
        # 事件战斗：奖励由事件给定，不进战斗奖励场景
        if self._event_battle:
            gold = int(self._event_reward_gold or 0) + bonus
            if gold:
                self.gm.gold += gold
                self.messages.append(f"事件奖励：+{gold} 铸币")
                print(f"[TavernRogue] 事件奖励 +{gold} 铸币")
            self._after_node()
            return
        if bonus:
            self.gm.gold += bonus
            self.messages.append(f"宝物加成：+{bonus} 铸币")
        self.switch_to('reward', messages=self.messages)

    def _find_enemy_template(self, enemy_id):
        """按 id 在 enemies.json 里找模板；找不到返回 None（由调用方响亮处理）。"""
        if not enemy_id:
            return None
        for enemy in (self.gm.load_data('enemies.json') or []):
            if enemy.get('id') == enemy_id:
                return enemy
        return None

    def _defeat(self):
        # 失败伤害：剩余敌人攻击力之和，最低3点
        remaining_attack = sum(e.get('attack', 0) for e in self.enemies if e.get('health', 0) > 0)
        damage = max(3, remaining_attack)
        self.gm.damage_hero(damage)
        self.messages.append(f"英雄受到 {damage} 点伤害！")
        if not self.gm.is_hero_alive():
            self.switch_to('game_over')
        else:
            self._after_node()
