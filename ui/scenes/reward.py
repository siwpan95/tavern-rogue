"""
reward.py — 战斗奖励场景
"""
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_status_bar, fonts, COLORS


class RewardScene(Scene):
    """战斗奖励选择"""

    def enter(self, messages=None, **kwargs):
        super().enter(**kwargs)
        self._card_reward = self.gm.reward_system._random_adventurer() \
            if self.gm.reward_system else None
        self._relic_reward = self.gm.reward_system._random_relic() \
            if self.gm.reward_system and self.gm.can_add_relic() else None

    def draw(self):
        fill_bg(self.screen)
        draw_status_bar(self.screen, self.gm)

        t = fonts.get('large').render("战斗胜利！选择奖励", True, COLORS['success'])
        self.screen.blit(t, (600, 50))

        self.buttons.clear()

        self.buttons.add(200, 150, 200, 50, "金币 +10", lambda: self._pick('gold', 10))

        if self._card_reward:
            self.buttons.add(200, 220, 200, 50, f"获得 {self._card_reward['name']}",
                             lambda c=self._card_reward: self._pick('card', c))

        if self._relic_reward:
            self.buttons.add(200, 290, 200, 50, f"获得 {self._relic_reward['name']}",
                             lambda r=self._relic_reward: self._pick('relic', r))

        self.buttons.add(200, 360, 200, 50, "恢复 10 生命值",
                         lambda: self._pick('heal', 10))

        self.buttons.draw_all(self.screen)

    def _pick(self, rtype, value):
        if rtype == 'gold':
            self.gm.gold += value
            print(f"[TavernRogue] 获得 {value} 金币！")
        elif rtype == 'card':
            if self.gm.can_add_to_hand():
                self.gm.add_to_hand(value)
                print(f"[TavernRogue] 获得冒险者 {value['name']}！")
        elif rtype == 'relic':
            if self.gm.can_add_relic():
                self.gm.add_relic(value)
                print(f"[TavernRogue] 获得宝物 {value['name']}！")
        elif rtype == 'heal':
            a = self.gm.heal_hero(value)
            print(f"[TavernRogue] 恢复 {a} 生命值！")

        self._after_node()
