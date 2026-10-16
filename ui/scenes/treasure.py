"""
treasure.py — 宝藏密室场景
"""
import random
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_status_bar, draw_text_centered, COLORS


class TreasureScene(Scene):
    """宝藏密室"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self.gold_found = random.randint(15, 30)

    def draw(self):
        fill_bg(self.screen)
        draw_status_bar(self.screen, self.gm)

        draw_text_centered(self.screen, "💎 宝藏密室", 150, 'xlarge', COLORS['gold'])
        draw_text_centered(self.screen, "你发现了一个装满金币的宝箱！", 250, 'large')
        draw_text_centered(self.screen, f"获得 {self.gold_found} 金币！", 350, 'xlarge', COLORS['gold'])

        self.buttons.clear()
        self.buttons.add(450, 480, 300, 50, "收下金币", self._take)
        self.buttons.draw_all(self.screen)

    def _take(self):
        self.gm.gold += self.gold_found
        print(f"[TavernRogue] 获得了 {self.gold_found} 金币！")
        self._after_node()
