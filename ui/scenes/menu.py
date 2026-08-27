"""
menu.py — 主菜单 + 职业选择
"""
import pygame
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_text_centered, fonts, COLORS, WIDTH, HEIGHT
from game.hero import get_all_hero_classes


class MenuScene(Scene):
    """主菜单"""

    def enter(self, **kwargs):
        super().enter(**kwargs)

    def draw(self):
        fill_bg(self.screen)
        draw_text_centered(self.screen, "TavernRogue", 200, 'title', COLORS['text_primary'])
        draw_text_centered(self.screen, "酒馆异闻录", 260, 'large')

        self.buttons.clear()
        self.buttons.add(450, 400, 300, 50, "开始游戏",
                         lambda: self.switch_to('class_select'))
        self.buttons.add(450, 470, 300, 50, "退出游戏",
                         lambda: setattr(self.app, 'running', False))
        self.buttons.draw_all(self.screen)


class ClassSelectScene(Scene):
    """职业选择"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self._classes = self.gm.progress.get_available_classes()
        self._descriptions = {
            'warrior': '被动: 生命值+5, 技能: 战争咆哮（守卫+2HP）',
            'rogue': '被动: 敏捷+3, 技能: 暗影突袭（2点伤害）',
            'cleric': '被动: 治疗+3, 技能: 治疗祷言（拯救阵亡友军）',
            'wizard': '被动: 法力+5, 技能: 魔法飞弹（3点AOE）',
            'warlock': '被动: 生命值-3, 技能: 生命分流（HP代金）',
        }
        self._base_descriptions = {k: v.split('（')[0] for k, v in self._descriptions.items()}

    def draw(self):
        fill_bg(self.screen)
        draw_text_centered(self.screen, "选择你的英雄职业", 50, 'xlarge', COLORS['text_primary'])

        self.buttons.clear()
        for i, cls in enumerate(self._classes):
            x = 100 + (i % 3) * 350
            y = 150 + (i // 3) * 200
            w, h = 300, 160
            locked = cls.get('locked', False)

            card = pygame.Rect(x, y, w, h)
            pygame.draw.rect(self.screen, COLORS['bg_card'], card)
            pygame.draw.rect(self.screen, COLORS['accent'] if not locked else (80, 80, 80), card, 2)

            name_color = (100, 100, 100) if locked else COLORS['text_primary']
            nm = fonts.get('large').render(cls['name'], True, name_color)
            self.screen.blit(nm, nm.get_rect(center=(x + w // 2, y + 30)))

            if locked:
                lock_text = '未解锁'
                ds = fonts.get('small').render(lock_text, True, (150, 50, 50))
                self.screen.blit(ds, ds.get_rect(center=(x + w // 2, y + 70)))
                continue

            desc = self._descriptions.get(cls['id'], '')
            parts = desc.split('（', 1)
            for idx, part in enumerate(parts):
                color = COLORS['text_secondary'] if idx == 0 else COLORS['accent']
                ds = fonts.get('small').render(part, True, color)
                self.screen.blit(ds, ds.get_rect(center=(x + w // 2, y + 70 + idx * 28)))

            adv = cls.get('advancement', 0)
            adv_label = f'进阶 {adv}' if adv > 0 else '进阶 0'
            best = cls.get('best_record', {})
            best_text = f"最佳: {'通关' if best.get('victory') else f'第{best.get('floor', 0)}层'}"
            info = fonts.get('small').render(f'{adv_label} | {best_text}', True, (180, 160, 120))
            self.screen.blit(info, info.get_rect(center=(x + w // 2, y + 130)))

            self.buttons.add(x, y, w, h, '',
                             lambda cid=cls['id']: self._on_select(cid))

        self.buttons.draw_all(self.screen)

    def _on_select(self, hero_class):
        cls_info = next((c for c in self._classes if c['id'] == hero_class), None)
        if cls_info and cls_info.get('locked', False):
            return
        self.gm.new_game(hero_class)
        self.switch_to('recruit')
