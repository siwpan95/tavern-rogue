"""
end_scenes.py — 游戏结束 / 胜利场景
"""
import pygame
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_text_centered, fonts, COLORS


class GameOverScene(Scene):
    """游戏结束"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self.gm.record_run(victory=False, floor=self.gm.floor)

    def draw(self):
        fill_bg(self.screen)
        draw_text_centered(self.screen, "游戏结束", 300, 'title', COLORS['health'])
        draw_text_centered(self.screen, f"你坚持到了第 {self.gm.floor} 层", 380, 'large')

        self.buttons.clear()
        self.buttons.add(450, 450, 300, 50, "返回主菜单", lambda: self.switch_to('menu'))
        self.buttons.draw_all(self.screen)


class VictoryScene(Scene):
    """通关胜利"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self.gm.record_run(victory=True, floor=self.gm.floor)

    def draw(self):
        fill_bg(self.screen)
        draw_text_centered(self.screen, "胜利！", 300, 'title', COLORS['success'])
        draw_text_centered(self.screen, "你成功通关了 TavernRogue！", 380, 'large')

        self.buttons.clear()
        self.buttons.add(450, 450, 300, 50, "返回主菜单", lambda: self.switch_to('menu'))
        self.buttons.draw_all(self.screen)
