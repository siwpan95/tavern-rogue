"""
end_scenes.py — 游戏结束 / 胜利场景

设计依据（2026-10-16 调研）：失败屏必须让玩家①能归因（为什么输）②没白打（局外进度动了）
③知道下一步做什么。旧版只有一行"你坚持到了第 N 层"。
"""
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_text_centered, fonts, COLORS, WIDTH


class _SummaryScene(Scene):
    """结束场景公共部分：标题 + 本局统计 + 个人最佳 + 下一目标。"""

    title = ""
    title_color = None
    subtitle = ""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self.gm.record_run(victory=self.is_victory_run(), floor=self.gm.floor)
        self._lines = self.gm.run_summary_lines()

    def is_victory_run(self) -> bool:
        return False

    def draw(self):
        fill_bg(self.screen)
        draw_text_centered(self.screen, self.title, 190, 'title', self.title_color)
        if self.subtitle:
            draw_text_centered(self.screen, self.subtitle, 260, 'large')

        small = fonts.get('medium')
        for index, line in enumerate(self._lines):
            color = COLORS['gold'] if line.startswith("下一目标") else COLORS['text_secondary']
            text = small.render(line, True, color)
            self.screen.blit(text, text.get_rect(center=(WIDTH // 2, 340 + index * 38)))

        self.buttons.clear()
        self.buttons.add(300, 620, 260, 50, "再来一局", lambda: self.switch_to('class_select'))
        self.buttons.add(640, 620, 260, 50, "返回主菜单", lambda: self.switch_to('menu'))
        self.buttons.draw_all(self.screen)


class GameOverScene(_SummaryScene):
    """游戏结束"""

    title = "游戏结束"
    title_color = COLORS['health']
    subtitle = "英雄倒下了，但冒险日志记下了这一局"

    def is_victory_run(self) -> bool:
        return False


class VictoryScene(_SummaryScene):
    """通关胜利"""

    title = "胜利！"
    title_color = COLORS['success']
    subtitle = "你击败了远古龙穴的主人"

    def is_victory_run(self) -> bool:
        return True
