"""
collection_scene.py — 图鉴（Collection）

设计依据（调研）：用"已发现 / 未发现"让玩家知道自己在追什么；
锁定项显示**剪影 + 类别线索**而不是空白，制造目标感（Balatro 的 Collection 做法）。
表现层（第二批）：从"进度条 + 计数"升级为可翻页的条目网格。
"""
import pygame

from game.collection import KIND_LABELS
from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_text_centered, fonts, COLORS, WIDTH

COLS = 4
ROWS = 7
PER_PAGE = COLS * ROWS
TABS = ("relics", "enemies", "events")

# 未发现时的类别线索（不是空白，而是"这里会是什么"）
LOCK_HINTS = {
    "relics": "未发现的宝物",
    "enemies": "未遭遇的敌人",
    "events": "未经历的事件",
}


class CollectionScene(Scene):
    """图鉴：宝物 / 敌人 / 事件，已发现显示名字，未发现显示剪影"""

    def enter(self, tab: str = "relics", page: int = 0, **kwargs):
        super().enter(**kwargs)
        self._collection = self.gm.collection()
        self._totals = self.gm.collection_totals()
        self._tab = tab if tab in TABS else "relics"
        self._entries = self._load_entries(self._tab)
        # 页码要在拿到条目之后再夹一次（否则 page=99 会画出空页）
        self._page = max(0, min(int(page or 0), self._page_count - 1))

    # ─── 数据 ─────────────────────────────────────────

    def _load_entries(self, tab: str):
        """取该类的全部条目（名字 + 稀有度等信息），按名字排序保证顺序稳定。"""
        rows = self.gm.load_data("%s.json" % tab) or []
        entries = []
        for row in rows:
            entries.append({
                "id": row.get("id"),
                "name": row.get("name") or row.get("id"),
                "extra": self._extra_of(tab, row),
            })
        entries.sort(key=lambda entry: entry["name"])
        return entries

    @staticmethod
    def _extra_of(tab: str, row: dict) -> str:
        if tab == "relics":
            return {"common": "常见", "rare": "稀有", "epic": "史诗"}.get(
                row.get("rarity"), row.get("rarity") or "")
        if tab == "enemies":
            if row.get("is_boss"):
                return "Boss"
            if row.get("is_elite"):
                return "精英"
            return "%d 星" % row.get("tier", 1)
        options = row.get("options")
        return "%d 个选项" % len(options) if options else ""

    @property
    def _page_count(self) -> int:
        return max(1, (len(self._entries) + PER_PAGE - 1) // PER_PAGE)

    def _page_entries(self):
        start = self._page * PER_PAGE
        return self._entries[start:start + PER_PAGE]

    # ─── 绘制 ─────────────────────────────────────────

    def draw(self):
        fill_bg(self.screen)
        draw_text_centered(self.screen, "冒险图鉴", 40, 'large', COLORS['text_primary'])

        self.buttons.clear()
        # 分类标签（当前分类用高亮下划线标出 —— Button 本身不带颜色参数）
        for index, tab in enumerate(TABS):
            found, total, pct = self._collection.progress_of(tab, self._totals.get(tab, 0))
            label = "%s %d/%d" % (KIND_LABELS.get(tab, tab), found, total)
            active = tab == self._tab
            x = 90 + index * 240
            self.buttons.add(x, 84, 220, 40, label,
                             lambda t=tab: self.switch_to('collection', tab=t, page=0))
            if active:
                pygame.draw.rect(self.screen, COLORS['gold'],
                                 pygame.Rect(x, 122, 220, 3))
            bar = pygame.Rect(x + 10, 132, 200, 8)
            pygame.draw.rect(self.screen, COLORS['bg_card'], bar)
            pygame.draw.rect(self.screen, COLORS['gold'],
                             pygame.Rect(x + 10, 132, int(200 * pct / 100.0), 8))

        discovered = self._collection.discovered(self._tab)
        small = fonts.get('small')
        medium = fonts.get('medium')
        for index, entry in enumerate(self._page_entries()):
            col, row = index % COLS, index // COLS
            x = 90 + col * 290
            y = 165 + row * 62
            known = entry["id"] in discovered

            box = pygame.Rect(x, y, 270, 52)
            pygame.draw.rect(self.screen, COLORS['bg_card'], box)
            pygame.draw.rect(self.screen, COLORS['accent'] if known else COLORS['bg_secondary'],
                             box, 2)

            if known:
                name = medium.render(entry["name"], True, COLORS['text_primary'])
                self.screen.blit(name, (x + 12, y + 6))
                extra = small.render(entry["extra"], True, COLORS['text_secondary'])
                self.screen.blit(extra, (x + 12, y + 30))
            else:
                # 剪影：用方块代替文字，保留"这里有个东西"的形状感
                silhouette = pygame.Rect(x + 12, y + 16, 96, 20)
                pygame.draw.rect(self.screen, COLORS['bg_secondary'], silhouette)
                hint = small.render(LOCK_HINTS.get(self._tab, "未发现"), True,
                                    COLORS['text_secondary'])
                self.screen.blit(hint, (x + 118, y + 18))

        # 翻页
        if self._page_count > 1:
            self.buttons.add(300, 600, 180, 40, "← 上一页",
                             lambda: self.switch_to('collection', tab=self._tab,
                                                    page=self._page - 1))
            self.buttons.add(520, 600, 180, 40, "下一页 →",
                             lambda: self.switch_to('collection', tab=self._tab,
                                                    page=self._page + 1))
            counter = small.render("%d / %d 页" % (self._page + 1, self._page_count),
                                   True, COLORS['text_secondary'])
            self.screen.blit(counter, counter.get_rect(center=(WIDTH // 2, 585)))

        self.buttons.add(450, 655, 300, 46, "返回主菜单", lambda: self.switch_to('menu'))
        self.buttons.draw_all(self.screen)
