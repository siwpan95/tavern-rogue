"""
shop.py — 旅行商人场景
"""
import random
import pygame
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_status_bar, fonts, COLORS


class ShopScene(Scene):
    """旅行商人"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        adv_data = self.gm.load_data('adventurers.json')
        try:
            relics_data = self.gm.load_data('relics.json')
        except Exception:
            relics_data = []

        layer = self.gm.get_current_layer()
        layer_num = layer['layer'] if layer else 1

        self.adventurers = random.sample(
            [a for a in adv_data if a['tier'] <= layer_num],
            min(3, len(adv_data))
        )
        self.relics_list = random.sample(relics_data, min(2, len(relics_data))) if relics_data else []

    def draw(self):
        fill_bg(self.screen)
        draw_status_bar(self.screen, self.gm)

        t = fonts.get('xlarge').render("🏪 旅行商人", True, COLORS['gold'])
        self.screen.blit(t, t.get_rect(center=(600, 100)))

        self.buttons.clear()

        # 冒险者
        st = fonts.get('large').render("— 招募冒险者 —", True, COLORS['text_primary'])
        self.screen.blit(st, (80, 160))

        for i, adv in enumerate(self.adventurers):
            x = 80 + i * 250
            y = 200
            color = self.gm.get_tier_color(adv['tier'])

            card = pygame.Rect(x, y, 220, 130)
            pygame.draw.rect(self.screen, color, card)
            pygame.draw.rect(self.screen, COLORS['accent'], card, 2)

            fs = fonts.get('small')
            fm = fonts.get('medium')
            self.screen.blit(fm.render(adv['name'], True, COLORS['text_secondary']), (x + 10, y + 8))
            self.screen.blit(fs.render(
                f"ATK:{adv['attack']} HP:{adv['health']} 费用:{adv['cost']}金",
                True, COLORS['text_secondary']), (x + 10, y + 38))
            if adv.get('keywords'):
                self.screen.blit(fs.render(f"技能: {', '.join(adv['keywords'])}",
                                           True, COLORS['gold']), (x + 10, y + 60))

            can = self.gm.gold >= adv['cost'] and len(self.gm.hand) < self.gm.MAX_HAND
            btn_text = f"购买 ({adv['cost']}金)"
            if not can:
                btn_text = "金币不足" if self.gm.gold < adv['cost'] else "手牌已满"
            self.buttons.add(x + 10, y + 90, 200, 30, btn_text,
                             lambda a=adv, idx=i: self._buy_adv(a, idx), enabled=can)

        # 宝物
        if self.relics_list:
            st2 = fonts.get('large').render("— 宝物 —", True, COLORS['accent'])
            self.screen.blit(st2, (80, 370))

            for i, relic in enumerate(self.relics_list):
                x = 80 + i * 250
                y = 410
                card = pygame.Rect(x, y, 220, 100)
                pygame.draw.rect(self.screen, COLORS['bg_card'], card)
                pygame.draw.rect(self.screen, COLORS['accent'], card, 2)

                fm = fonts.get('medium')
                fs = fonts.get('small')
                self.screen.blit(fm.render(relic['name'], True, COLORS['gold']), (x + 10, y + 8))
                self.screen.blit(fs.render(relic.get('description', ''),
                                           True, COLORS['text_secondary']), (x + 10, y + 38))

                rarity_cost = {'common': 5, 'rare': 8, 'epic': 12}
                cost = relic.get('cost', rarity_cost.get(relic.get('rarity', 'common'), 5))
                can = self.gm.gold >= cost and len(self.gm.relics) < self.gm.MAX_RELICS
                btn_text = f"购买 ({cost}金)" if can else (
                    "金币不足" if self.gm.gold < cost else "宝物已满")
                self.buttons.add(x + 10, y + 65, 200, 25, btn_text,
                                 lambda r=relic: self._buy_relic(r), enabled=can)

        self.buttons.add(450, 720, 300, 50, "离开商店", self._leave)
        self.buttons.draw_all(self.screen)

    def _buy_adv(self, adv, idx):
        if self.gm.gold >= adv['cost'] and self.gm.can_add_to_hand():
            self.gm.spend_gold(adv['cost'])
            self.gm.add_to_hand(adv.copy())
            self.adventurers.pop(idx)
            print(f"[TavernRogue] 购买了 {adv['name']}！")

    def _buy_relic(self, relic):
        rarity_cost = {'common': 5, 'rare': 8, 'epic': 12}
        cost = relic.get('cost', rarity_cost.get(relic.get('rarity', 'common'), 5))
        if self.gm.gold >= cost and self.gm.can_add_relic():
            self.gm.spend_gold(cost)
            self.gm.add_relic(relic.copy())
            self.relics_list.remove(relic)
            print(f"[TavernRogue] 购买了宝物 {relic['name']}！")

    def _leave(self):
        self._after_node()
