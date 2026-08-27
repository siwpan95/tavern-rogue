"""
recruit.py — 酒馆招募场景
"""
import pygame
from ui.scenes.base import Scene
from ui.renderer import (
    fill_bg, draw_status_bar, draw_text_centered, draw_adventurer_card,
    fonts, COLORS, WIDTH
)


class RecruitScene(Scene):
    """酒馆招募"""

    def enter(self, **kwargs):
        super().enter(**kwargs)
        self.gm.start_recruit_turn()
        self.rs = self.gm.recruit_system
        self.recruit_list = self.rs.tavern_pool
        self.life_tap_mode = False  # 术士生命分流模式

    def draw(self):
        fill_bg(self.screen)
        draw_status_bar(self.screen, self.gm)

        rs = self.rs
        draw_text_centered(self.screen, "酒馆招募", 50, 'large', COLORS['text_primary'])

        lv = fonts.get('medium').render(f"酒馆 Lv.{rs.tavern_level}", True, COLORS['gold'])
        self.screen.blit(lv, (550, 80))

        self.buttons.clear()

        # 招募列表
        for i, adv in enumerate(self.recruit_list):
            x = 50 + i * 220
            y = 130
            cost = adv.get('cost', rs.recruit_cost)
            can_buy = self.gm.gold >= cost and len(self.gm.hand) < self.gm.MAX_HAND

            btn_label = f"购买({cost}金)" if can_buy else (
                "金币不足" if self.gm.gold < cost else "手牌已满")
            self.buttons.add(x + 30, y + 95, 140, 28, btn_label,
                             lambda idx=i: self._buy(idx), enabled=can_buy)

            # 绘制卡片
            draw_adventurer_card(self.screen, x, y, adv)

        # 手牌展示
        self._draw_hand()
        # 战场展示
        self._draw_board()

        # 底部操作栏
        free = rs.free_refresh_available and rs._has_tribe_on_board('human')
        btn_text = "刷新 (免费!)" if free else f"刷新 ({rs.refresh_cost}金币)"
        self.buttons.add(50, 700, 160, 40, btn_text, self._refresh)
        self.buttons.add(250, 700, 150, 40, "结束招募", self._end)

        # 术士生命分流按钮
        if hasattr(self.gm.hero, 'life_tap_available') and self.gm.hero.life_tap_available:
            btn_text = "生命分流 (ON)" if getattr(self, 'life_tap_mode', False) else "生命分流 (2HP→1金)"
            self.buttons.add(450, 700, 220, 40, btn_text, self._toggle_life_tap)

        self.buttons.draw_all(self.screen)

    def _toggle_life_tap(self):
        """切换术士生命分流模式"""
        self.life_tap_mode = not getattr(self, 'life_tap_mode', False)
        print(f"[TavernRogue] 生命分流模式: {'ON' if self.life_tap_mode else 'OFF'}")

    def _draw_hand(self):
        if not self.gm.hand:
            return
        y = 550
        fs = fonts.get('small')
        fm = fonts.get('medium')

        title = fm.render(f"手牌 ({len(self.gm.hand)}/{self.gm.MAX_HAND})", True, COLORS['text_primary'])
        self.screen.blit(title, (50, y - 20))

        count = len(self.gm.hand)
        # 动态计算卡片尺寸：手牌区可用宽度 ~550px（50→600），留10px边距
        avail_w = 550
        base_cw, base_gap = 100, 20
        cw, gap, start_x = self._calc_card_layout(count, 50, avail_w, base_cw, base_gap, min_w=70)

        for i, card in enumerate(self.gm.hand):
            x = start_x + i * (cw + gap)
            card_rect = pygame.Rect(x, y, cw, 80)
            pygame.draw.rect(self.screen, COLORS['bg_card'], card_rect)
            pygame.draw.rect(self.screen, COLORS['accent'], card_rect, 1)
            self.screen.blit(fs.render(card['name'], True, COLORS['text_secondary']), (x + 3, y + 5))
            self.screen.blit(fs.render(f"{card['attack']}/{card['health']}", True, COLORS['text_secondary']),
                             (x + 3, y + 25))
            btn_w = max(32, int(cw * 0.4))
            self.buttons.add(x + 3, y + 45, btn_w, 20, "部署", lambda idx=i: self._deploy(idx))
            self.buttons.add(x + 5 + btn_w, y + 45, btn_w, 20, "出售", lambda idx=i: self._sell(idx))

    def _draw_board(self):
        if not self.gm.board:
            return
        y = 550
        fm = fonts.get('medium')
        fs = fonts.get('small')

        title = fm.render("战场", True, COLORS['text_primary'])
        self.screen.blit(title, (650, y - 20))

        count = len(self.gm.board)
        # 动态计算卡片尺寸：战场区可用宽度 ~500px（650→1150），留10px边距
        avail_w = 500
        base_cw, base_gap = 100, 20
        cw, gap, start_x = self._calc_card_layout(count, 650, avail_w, base_cw, base_gap, min_w=70)

        for i, card in enumerate(self.gm.board):
            x = start_x + i * (cw + gap)
            card_rect = pygame.Rect(x, y, cw, 80)
            pygame.draw.rect(self.screen, COLORS['bg_card'], card_rect)
            pygame.draw.rect(self.screen, COLORS['success'], card_rect, 2)
            self.screen.blit(fs.render(card['name'], True, COLORS['text_secondary']), (x + 3, y + 10))
            btn_w = max(40, int(cw * 0.7))
            self.buttons.add(x + (cw - btn_w) // 2, y + 50, btn_w, 20, "撤回", lambda idx=i: self._recall(idx))

    def _calc_card_layout(self, count, region_x, region_w, base_cw, base_gap, min_w=70):
        """根据卡片数量动态计算卡片宽度、间距和起始X坐标，确保不超框"""
        # 先尝试用默认尺寸
        total_w = count * base_cw + (count - 1) * base_gap
        if total_w <= region_w:
            # 正常布局，居中
            start_x = int(region_x + (region_w - total_w) / 2)
            return base_cw, base_gap, start_x

        # 需要压缩：先尝试缩小间距
        min_gap = 4
        gap = max(min_gap, (region_w - count * base_cw) / max(count - 1, 1))
        total_w = count * base_cw + (count - 1) * gap
        if total_w <= region_w:
            start_x = int(region_x + (region_w - total_w) / 2)
            return base_cw, int(gap), start_x

        # 再压缩卡片宽度
        cw = max(min_w, (region_w - (count - 1) * min_gap) / count)
        gap = min_gap
        total_w = count * cw + (count - 1) * gap
        start_x = int(region_x + (region_w - total_w) / 2)
        return int(cw), int(gap), start_x

    def _buy(self, index):
        self.gm.sync_to_recruit()
        rs = self.rs

        if getattr(self, 'life_tap_mode', False) and hasattr(self.gm.hero, 'use_life_tap'):
            result = rs.use_life_tap(index)
            self.life_tap_mode = False  # 使用后重置
        else:
            result = rs.recruit(index)

        print(f"[TavernRogue] {result}")
        self.gm.sync_from_recruit()
        self.recruit_list = rs.tavern_pool

        triple_id = rs.check_triple()
        if triple_id:
            msg = rs.perform_triple(triple_id)
            print(f"[TavernRogue] {msg}")
            self.gm.sync_from_recruit()
            pygame.time.delay(500)

    def _refresh(self):
        self.gm.sync_to_recruit()
        result = self.rs.refresh()
        print(f"[TavernRogue] {result}")
        self.gm.sync_from_recruit()
        self.recruit_list = self.rs.tavern_pool

    def _deploy(self, index):
        self.gm.sync_to_recruit()
        result = self.rs.deploy_to_board(index)
        print(f"[TavernRogue] {result}")
        self.gm.sync_from_recruit()

    def _recall(self, index):
        self.gm.sync_to_recruit()
        result = self.rs.recall_to_hand(index)
        print(f"[TavernRogue] {result}")
        self.gm.sync_from_recruit()

    def _sell(self, index):
        self.gm.sync_to_recruit()
        result = self.rs.sell_adventurer(index, from_hand=True)
        print(f"[TavernRogue] {result}")
        self.gm.sync_from_recruit()

    def _end(self):
        self.gm.end_recruit_turn()
        self.gm.ensure_map()
        self.switch_to('map')
