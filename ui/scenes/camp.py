"""
camp.py — 安全营地场景（休息 + 训练）
"""
import pygame
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_status_bar, fonts, COLORS


class CampScene(Scene):
    """安全营地"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self._training = False

    def draw(self):
        fill_bg(self.screen)
        draw_status_bar(self.screen, self.gm)

        t = fonts.get('xlarge').render("🏠 安全营地", True, COLORS['success'])
        self.screen.blit(t, t.get_rect(center=(600, 50)))

        self.buttons.clear()

        if not self._training:
            desc = fonts.get('large').render(
                "你找到了一个安全的营地，可以在此休息或训练", True, COLORS['text_secondary'])
            self.screen.blit(desc, desc.get_rect(center=(600, 120)))

            heal_amt = min(15, self.gm.MAX_HEALTH - self.gm.health)
            fs = fonts.get('medium')
            self.screen.blit(fs.render(
                f"恢复 {heal_amt} 点生命值 (当前: {self.gm.health}/{self.gm.MAX_HEALTH})",
                True, COLORS['health']), (300, 200))

            self.buttons.add(350, 270, 500, 50,
                             f"休息恢复 (+{heal_amt} HP)", lambda: self._rest(heal_amt))

            train_count = len(self.gm.board) + len(self.gm.hand)
            if train_count > 0:
                self.buttons.add(350, 340, 500, 50,
                                 f"训练冒险者 (+1/+1) — {train_count} 名可选",
                                 lambda: setattr(self, '_training', True))
            else:
                hint = fonts.get('medium').render("（没有冒险者可以训练）", True, (128, 128, 128))
                self.screen.blit(hint, (350, 350))

            self.buttons.add(350, 410, 500, 50, "继续前进（离开）", self._leave)
        else:
            t2 = fonts.get('large').render(
                "选择一名冒险者进行训练 (+1 ATK / +1 HP)", True, COLORS['gold'])
            self.screen.blit(t2, t2.get_rect(center=(600, 120)))

            # 场上
            if self.gm.board:
                lb = fonts.get('medium').render("— 场上单位 —", True, COLORS['success'])
                self.screen.blit(lb, (80, 160))
                for i, card in enumerate(self.gm.board):
                    x = 80 + i * 220
                    y = 200
                    self._draw_train_card(x, y, card, i, True)

            # 手牌
            if self.gm.hand:
                hy = 340 if self.gm.board else 200
                lb = fonts.get('medium').render("— 手牌 —", True, COLORS['text_primary'])
                self.screen.blit(lb, (80, hy - 30))
                for i, card in enumerate(self.gm.hand):
                    x = 80 + i * 220
                    y = hy
                    self._draw_train_card(x, y, card, i, False)

            self.buttons.add(450, 720, 300, 50, "取消训练",
                             lambda: setattr(self, '_training', False))

        self.buttons.draw_all(self.screen)

    def _draw_train_card(self, x, y, card, index, from_board):
        color = self.gm.get_tier_color(card.get('tier', 1))
        rect = pygame.Rect(x, y, 200, 120)
        pygame.draw.rect(self.screen, color, rect)
        pygame.draw.rect(self.screen, COLORS['gold'], rect, 3)

        fm = fonts.get('medium')
        fs = fonts.get('small')
        self.screen.blit(fm.render(card['name'], True, COLORS['text_secondary']), (x + 10, y + 8))
        self.screen.blit(fs.render(f"ATK:{card['attack']} HP:{card['health']}",
                                   True, COLORS['text_secondary']), (x + 10, y + 35))
        self.screen.blit(fs.render(f"→ ATK:{card['attack']+1} HP:{card['health']+1}",
                                   True, COLORS['success']), (x + 10, y + 55))
        if card.get('keywords'):
            self.screen.blit(fs.render(','.join(card['keywords']),
                                       True, COLORS['accent']), (x + 10, y + 75))

        self.buttons.add(x + 10, y + 95, 180, 25, "训练！",
                         lambda idx=index, fb=from_board: self._train(idx, fb))

    def _train(self, index, from_board):
        source = self.gm.board if from_board else self.gm.hand
        if 0 <= index < len(source):
            card = source[index]
            card['attack'] += 1
            card['health'] += 1
            print(f"[TavernRogue] {card['name']} 训练完成: ATK+1, HP+1!")
        self._leave()

    def _rest(self, amount):
        # 进阶 4 起营地治疗打折（"铁石心肠"）
        mult = float(getattr(self.gm, 'camp_heal_mult', 1.0) or 1.0)
        healed = self.gm.heal_hero(max(1, int(round(amount * mult))))
        print(f"[TavernRogue] 在营地恢复了 {healed} 点生命值")
        self._leave()

    def _leave(self):
        self._after_node()
