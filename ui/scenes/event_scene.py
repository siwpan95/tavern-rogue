"""
event_scene.py — 随机事件场景
"""
from game.event_effects import EventEffectResolver
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_status_bar, fonts, COLORS, WIDTH


class EventScene(Scene):
    """随机事件"""

    def enter(self, node=None, **kwargs):
        super().enter(**kwargs)
        self._node = node
        self._event = self.gm.event_system.select_random_event()
        if self._event:
            self.gm.mark_collection('events', [self._event.get('id')])
        if not self._event:
            print("[TavernRogue] 没有可用事件")
            self.switch_to('map')

    def draw(self):
        if not self._event:
            return

        fill_bg(self.screen)
        draw_status_bar(self.screen, self.gm)

        event = self._event
        title = event.get('name', event.get('title', '未知事件'))
        t = fonts.get('large').render(title, True, COLORS['text_primary'])
        self.screen.blit(t, t.get_rect(center=(WIDTH // 2, 80)))

        # 描述
        desc = event.get('description', '')
        words = desc.split()
        lines, cur = [], ""
        for w in words:
            if len(cur + ' ' + w) < 50:
                cur = (cur + ' ' + w) if cur else w
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)

        for i, line in enumerate(lines):
            ds = fonts.get('medium').render(line, True, COLORS['text_secondary'])
            self.screen.blit(ds, (200, 150 + i * 30))

        self.buttons.clear()

        options = event.get('options', [])
        for i, option in enumerate(options):
            self.buttons.add(400, 300 + i * 60, 400, 50, option['text'],
                             lambda opt=option: self._choose(opt))

        self.buttons.draw_all(self.screen)

    def _choose(self, option):
        """结算选项：效果实现只有一处（game/event_effects.py），本场景不再自己写一套。"""
        effects = option.get('effects', {})
        outcome = option.get('outcome', '')

        resolver = EventEffectResolver(
            hero=self.gm.hero,
            hand=self.gm.hand,
            board=self.gm.board,
            relics=self.gm.relics,
            data_loader=self.gm.load_data,
            map_manager=self.gm.map_manager,
            gold=self.gm.gold,
            max_hand=self.gm.MAX_HAND,
            can_add_to_hand=self.gm.can_add_to_hand,
            can_add_relic=self.gm.can_add_relic,
        ).apply(effects)
        self.gm.gold = resolver.gold

        for line in resolver.logs:
            print(f"[TavernRogue] {line}")
        if outcome:
            print(f"[TavernRogue] {outcome}")

        # 事件里的「战斗！」选项走真正的战斗（此前只设了个没人读的 trigger_battle）
        if resolver.pending_battle:
            self._start_event_battle(resolver.pending_battle)
            return

        if not self.gm.is_hero_alive():
            self.switch_to('game_over')
        else:
            self._after_node()

    def _start_event_battle(self, battle_info):
        """按事件指定的敌人开一场战斗；敌人不存在时响亮跳过而不是静默卡住。"""
        enemy_id = battle_info.get('enemy')
        enemies_data = self.gm.load_data('enemies.json') or []
        template = next((e for e in enemies_data if e.get('id') == enemy_id), None)
        if template is None:
            print(f"[TavernRogue] 事件引用了不存在的敌人 {enemy_id}，已跳过战斗")
            self._after_node()
            return
        self.switch_to('battle', node=self._node, event_battle=battle_info)
