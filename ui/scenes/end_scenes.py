"""
end_scenes.py — 游戏结束 / 胜利场景

设计依据（2026-10-16 调研）：失败屏必须让玩家①能归因（为什么输）②没白打（局外进度动了）
③知道下一步做什么。旧版只有一行"你坚持到了第 N 层"。

表现层（第二批）：结算改成**逐行揭示**（staged reveal）——一次性糊满屏幕的信息没人读；
一行一行出现会自然形成"回顾这一局"的节奏，也顺带把音效卡在节拍上。
"""
import pygame

from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_text_centered, fonts, COLORS, WIDTH


class _SummaryScene(Scene):
    """结束场景公共部分：标题 + 本局统计 + 个人最佳 + 下一目标（逐行揭示）。"""

    title = ""
    title_color = None
    subtitle = ""
    line_interval = 0.35          # 每行出现的间隔（秒）
    reveal_delay = 0.6            # 标题出现后多久开始出统计

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self.gm.record_run(victory=self.is_victory_run(), floor=self.gm.floor)
        self._lines = self.gm.run_summary_lines()
        self._elapsed = 0.0
        self._revealed = 0
        self._play_end_audio()

    def is_victory_run(self) -> bool:
        return False

    # ─── 音频（通关/失败各有收束音）────────────────

    def _play_end_audio(self) -> None:
        audio = getattr(self.app, "audio", None)
        if audio is None:
            return
        from game.audio import SFX_NAMES
        name = "win" if self.is_victory_run() else "lose"
        if name in SFX_NAMES:
            audio.play(name)

    # ─── 逐行揭示 ──────────────────────────────────

    def update(self, dt: float):
        super().update(dt)
        self._elapsed += dt
        wanted = int(max(0.0, self._elapsed - self.reveal_delay) / self.line_interval) + 1
        wanted = min(wanted, len(self._lines))
        if wanted > self._revealed:
            self._revealed = wanted
            self._play_tick_audio()

    def _play_tick_audio(self) -> None:
        audio = getattr(self.app, "audio", None)
        if audio is None:
            return
        from game.audio import SFX_NAMES
        if "card_hover" in SFX_NAMES:
            audio.play("card_hover")

    def skip_reveal(self) -> None:
        self._revealed = len(self._lines)

    def handle_event(self, event):
        # 点一下/按键就立刻全部展开（不让动画挡路）
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            if self._revealed < len(self._lines):
                self.skip_reveal()
                return
        super().handle_event(event)

    def draw(self):
        fill_bg(self.screen)
        draw_text_centered(self.screen, self.title, 190, 'title', self.title_color)
        if self.subtitle:
            draw_text_centered(self.screen, self.subtitle, 260, 'large')

        small = fonts.get('medium')
        for index, line in enumerate(self._lines[:self._revealed]):
            color = COLORS['gold'] if line.startswith("下一目标") else COLORS['text_secondary']
            # 最新一行稍亮：眼睛自然落在"正在发生的"那一行
            if index == self._revealed - 1 and self._revealed < len(self._lines):
                color = COLORS['text_primary']
            text = small.render(line, True, color)
            self.screen.blit(text, text.get_rect(center=(WIDTH // 2, 340 + index * 38)))

        if self._revealed < len(self._lines):
            hint = fonts.get('small').render("（点击/按键可立即展开）", True, COLORS['text_secondary'])
            self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 560)))

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

    def draw(self):
        super().draw()
        # 归因：明确写出"你倒在哪一层"，而不是让玩家自己数
        cause = fonts.get('small').render(
            "本局止步：第 %d 层 · %s" % (self.gm.floor, self._cause_text()),
            True, COLORS['text_secondary'])
        self.screen.blit(cause, cause.get_rect(center=(WIDTH // 2, 585)))

    def _cause_text(self) -> str:
        stats = getattr(self.gm, "run_stats", {}) or {}
        battles = stats.get("battles", 0)
        wins = stats.get("battle_wins", 0)
        if battles and wins / max(1, battles) < 0.6:
            return "战斗失利偏多（胜率 %.0f%%）" % (100.0 * wins / battles)
        return "血线被消耗殆尽"


class VictoryScene(_SummaryScene):
    """通关胜利（含 Boss 名与套装回顾）"""

    title = "胜利！"
    title_color = COLORS['success']
    subtitle = "你击败了远古龙穴的主人"
    line_interval = 0.4

    def is_victory_run(self) -> bool:
        return True

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self.subtitle = "你击败了%s" % self._boss_name()
        self._relic_line = self._relic_recap()

    def _boss_name(self) -> str:
        return getattr(self.gm, "defeated_boss_name", "") or "远古龙穴的主人"

    def _relic_recap(self) -> str:
        names = [r.get("name", "?") for r in self.gm.relics][:4]
        return "携行宝物：%s" % ("、".join(names) if names else "无")

    def draw(self):
        super().draw()
        line = fonts.get('small').render(self._relic_line, True, COLORS['text_secondary'])
        self.screen.blit(line, line.get_rect(center=(WIDTH // 2, 585)))
