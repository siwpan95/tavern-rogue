"""
event_scene.py — 随机事件场景
"""
import random
import pygame
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_status_bar, fonts, COLORS, WIDTH


class EventScene(Scene):
    """随机事件"""

    def enter(self, node=None, **kwargs):
        super().enter(**kwargs)
        self._node = node
        self._event = self.gm.event_system.select_random_event()
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
        effects = option.get('effects', {})
        outcome = option.get('outcome', '')

        if 'heal' in effects:
            a = self.gm.heal_hero(effects['heal'])
            print(f"[TavernRogue] 恢复了 {a} 点生命值")
        if 'damage' in effects or 'damage_hero' in effects:
            dmg = effects.get('damage', effects.get('damage_hero', 0))
            self.gm.damage_hero(dmg)
            print(f"[TavernRogue] 受到了 {dmg} 点伤害")
        if 'gain_gold' in effects:
            self.gm.gold += effects['gain_gold']
            print(f"[TavernRogue] 获得 {effects['gain_gold']} 金币")
        if 'cost_gold' in effects and self.gm.gold >= effects['cost_gold']:
            self.gm.gold -= effects['cost_gold']
            print(f"[TavernRogue] 花费 {effects['cost_gold']} 金币")
        if 'gain_adventurer' in effects:
            ti = effects['gain_adventurer'].get('tier', 1)
            adv_data = self.gm.load_data('adventurers.json')
            available = [a for a in adv_data if a['tier'] == ti]
            if available and self.gm.can_add_to_hand():
                card = random.choice(available).copy()
                self.gm.add_to_hand(card)
                print(f"[TavernRogue] 获得冒险者 {card['name']}！")
        if 'gain_relic' in effects and self.gm.can_add_relic():
            relics_data = self.gm.load_data('relics.json')
            if relics_data:
                relic = random.choice(relics_data).copy()
                self.gm.add_relic(relic)
                print(f"[TavernRogue] 获得宝物 {relic['name']}！")
        if 'lose_relic' in effects and self.gm.relics:
            lost = self.gm.relics.pop(0)
            print(f"[TavernRogue] 失去了宝物 {lost['name']}")
        if 'coin_flip' in effects:
            if random.choice([True, False]):
                self.gm.heal_hero(5)
                print("[TavernRogue] 硬币正面！恢复了 5 点生命值")
            else:
                self.gm.damage_hero(3)
                print("[TavernRogue] 硬币反面！受到了 3 点伤害")
        if 'sacrifice_adventurer' in effects and self.gm.hand:
            lost = self.gm.hand.pop(0)
            print(f"[TavernRogue] 献祭了 {lost['name']}")
            if 'heal_hero' in effects:
                self.gm.heal_hero(effects['heal_hero'])
        if 'heal_hero' in effects and 'sacrifice_adventurer' not in effects:
            self.gm.heal_hero(effects['heal_hero'])
        if 'upgrade_board' in effects:
            stat = effects['upgrade_board'].get('stat', 'attack')
            value = effects['upgrade_board'].get('value', 1)
            for unit in self.gm.board:
                unit[stat] = unit.get(stat, 0) + value
            print(f"[TavernRogue] 所有场上单位 {stat}+{value}")
        if effects.get('purify_board', False):
            negative = {'POISON'}
            for unit in self.gm.board:
                unit['keywords'] = [k for k in unit.get('keywords', []) if k not in negative]
            print("[TavernRogue] 净化了场上单位的负面状态")
        if 'enchant_board' in effects:
            keyword = effects['enchant_board'].get('keyword')
            apply_all = effects['enchant_board'].get('all', False)
            if keyword and self.gm.board:
                targets = self.gm.board if apply_all else [random.choice(self.gm.board)]
                for unit in targets:
                    keywords = unit.setdefault('keywords', [])
                    if keyword not in keywords:
                        keywords.append(keyword)
                print(f"[TavernRogue] 为场上单位附加 {keyword}")
        if effects.get('regenerate_map', False):
            if self.gm.map_manager:
                self.gm.map_manager.generate_map()
                print("[TavernRogue] 地图已重塑")
        if outcome:
            print(f"[TavernRogue] {outcome}")

        if not self.gm.is_hero_alive():
            self.switch_to('game_over')
        else:
            self._after_node()
