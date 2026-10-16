"""
collection_scene.py — 图鉴（Collection）

设计依据（调研）：用"已发现 / 未发现"让玩家知道自己在追什么；
锁定项显示条件而不是空白，制造目标感（Balatro 的 Collection 做法）。
"""
import pygame

from game.collection import KIND_LABELS
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_text_centered, fonts, COLORS, WIDTH


class CollectionScene(Scene):
    """图鉴：宝物 / 敌人 / 事件 的发现进度"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self._collection = self.gm.collection()
        self._totals = self.gm.collection_totals()

    def draw(self):
        fill_bg(self.screen)
        draw_text_centered(self.screen, "冒险图鉴", 60, 'title', COLORS['text_primary'])

        medium = fonts.get('medium')
        small = fonts.get('small')
        y = 150
        for kind, found, total, pct in self._collection.summary(self._totals):
            label = KIND_LABELS.get(kind, kind)
            bar_bg = pygame.Rect(200, y + 34, 800, 14)
            pygame.draw.rect(self.screen, COLORS['bg_card'], bar_bg)
            bar = pygame.Rect(200, y + 34, int(800 * pct / 100.0), 14)
            pygame.draw.rect(self.screen, COLORS['gold'], bar)

            head = medium.render("%s：%d / %d（%.0f%%）" % (label, found, total, pct),
                                 True, COLORS['text_primary'])
            self.screen.blit(head, (200, y))
            hint = small.render(self._hint(kind), True, COLORS['text_secondary'])
            self.screen.blit(hint, (200, y + 58))
            y += 130

        note = small.render("未发现的条目会在遭遇后自动记录（存档在 saves/progress.json）",
                            True, COLORS['text_secondary'])
        self.screen.blit(note, note.get_rect(center=(WIDTH // 2, 600)))

        self.buttons.clear()
        self.buttons.add(450, 660, 300, 50, "返回主菜单", lambda: self.switch_to('menu'))
        self.buttons.draw_all(self.screen)

    def _hint(self, kind):
        missing = self._totals.get(kind, 0) - len(self._collection.discovered(kind))
        if missing <= 0:
            return "已全部发现 ✓"
        return "还有 %d 个未发现" % missing
