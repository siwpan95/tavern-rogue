"""
共享渲染器 — 提取所有绘制原语，避免各 Scene 重复实现
"""
import os
import sys

import pygame


# ─── 颜色调色板 ───────────────────────────────────

COLORS = {
    'bg_primary':    (26, 26, 46),
    'bg_secondary':  (22, 33, 62),
    'bg_card':       (15, 52, 96),
    'text_primary':  (233, 69, 96),
    'text_secondary':(255, 255, 255),
    'accent':        (83, 52, 131),
    'gold':          (255, 215, 0),
    'health':        (255, 68, 68),
    'mana':          (68, 68, 255),
    'success':       (68, 255, 68),
    'warning':       (255, 170, 0),
    'enemy_bg':      (80, 20, 20),
    'ally_bg':       (20, 50, 80),
    'selected_bg':   (60, 60, 30),
}

WIDTH, HEIGHT = 1200, 800


# ─── 字体管理 ─────────────────────────────────────

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_FILENAME = "BaoCanMouHuiTingShouXieTi2.0-2.ttf"
# 字体是 50 MiB 级资产，**不入库**（`tools/fetch_font.py` 下载）。查找顺序：
#   1) assets/fonts/（下载后的规范位置） 2) 仓根（老位置的本地副本）
#   3) 系统 CJK 字体  4) pygame 默认字体（无中文字形，会显示方块 → 出声警告）
FONT_SEARCH_PATHS = (
    os.path.join(REPO_ROOT, "assets", "fonts", FONT_FILENAME),
    os.path.join(REPO_ROOT, FONT_FILENAME),
)
SYSTEM_FONT_CANDIDATES = ("microsoftyahei", "simhei", "notosanscjksc", "notosanscjk", "simsun")


class FontManager:
    """统一字体加载与管理（延迟初始化，需在 pygame.init() 后调用 ensure_init()）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def ensure_init(self):
        """在 pygame.init() 之后调用以完成字体加载"""
        if self._initialized:
            return
        self._init()
        self._initialized = True

    def _init(self):
        sizes = {'small': 16, 'medium': 20, 'large': 28, 'xlarge': 36, 'title': 52}
        self.fonts = {}
        self.font_source = ""

        for path in FONT_SEARCH_PATHS:
            if not os.path.exists(path):
                continue
            try:
                for name, size in sizes.items():
                    self.fonts[name] = pygame.font.Font(path, size)
                self.font_source = path
                return
            except Exception as exc:  # noqa: BLE001 - 字体坏了也要能进游戏
                print("[TavernRogue] 内置字体加载失败（%s）：%s" % (path, exc), file=sys.stderr)

        # 回退 1：系统 CJK 字体
        available = set(pygame.font.get_fonts())
        for candidate in SYSTEM_FONT_CANDIDATES:
            if candidate in available:
                for name, size in sizes.items():
                    self.fonts[name] = pygame.font.SysFont(candidate, size)
                self.font_source = "sysfont:%s" % candidate
                print("[TavernRogue] 未找到内置手写体，回退系统字体 %s"
                      "（跑 `python tools/fetch_font.py` 可下载内置字体）" % candidate,
                      file=sys.stderr)
                return

        # 回退 2：pygame 默认字体（没有中文字形，必须出声）
        for name, size in sizes.items():
            self.fonts[name] = pygame.font.Font(None, size)
        self.font_source = "pygame-default"
        print("[TavernRogue] 警告：没有可用的中文字体，界面中文可能显示为方块 —— "
              "跑 `python tools/fetch_font.py` 下载，或手工把 %s 放到 assets/fonts/"
              % FONT_FILENAME, file=sys.stderr)

    def _load_sysfonts(self, sizes):
        for name, size in sizes.items():
            self.fonts[name] = pygame.font.SysFont("microsoftyahei", size)

    def get(self, name='medium'):
        """获取字体: small/medium/large/xlarge/title"""
        self.ensure_init()
        return self.fonts.get(name, self.fonts['medium'])


fonts = FontManager()


# ─── 按钮系统 ─────────────────────────────────────

class Button:
    """GUI 按钮"""
    __slots__ = ('rect', 'text', 'callback', 'hover', 'enabled')

    def __init__(self, x, y, w, h, text, callback, enabled=True):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback if enabled else None
        self.hover = False
        self.enabled = enabled

    def draw(self, screen):
        if not self.text:
            return
        color = COLORS['accent'] if self.hover else COLORS['bg_card']
        if not self.enabled:
            color = (50, 50, 70)
        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, COLORS['accent'], self.rect, 2)
        surf = fonts.get('medium').render(self.text, True, COLORS['text_secondary'])
        screen.blit(surf, surf.get_rect(center=self.rect.center))

    def check_hover(self, pos):
        self.hover = self.rect.collidepoint(pos)

    def check_click(self, pos):
        if self.rect.collidepoint(pos) and self.callback and self.enabled:
            self.callback()


class ButtonManager:
    """按钮批量管理"""
    def __init__(self):
        self.buttons: list[Button] = []

    def clear(self):
        self.buttons.clear()

    def add(self, x, y, w, h, text, callback, enabled=True):
        btn = Button(x, y, w, h, text, callback, enabled)
        self.buttons.append(btn)
        return btn

    def handle_motion(self, pos):
        for btn in self.buttons:
            btn.check_hover(pos)

    def handle_click(self, pos):
        for btn in self.buttons:
            btn.check_click(pos)

    def draw_all(self, screen):
        for btn in self.buttons:
            btn.draw(screen)


# ─── 卡片渲染 ────────────────────────────────────

def draw_adventurer_card(screen, x, y, adventurer, width=200, height=130,
                         game_manager=None, show_buy=False, buy_index=None):
    """绘制标准冒险者卡片"""
    tier = adventurer.get('tier', 1)
    color = game_manager.get_tier_color(tier) if game_manager else (128, 128, 128)
    card = pygame.Rect(x, y, width, height)
    pygame.draw.rect(screen, color, card)
    pygame.draw.rect(screen, COLORS['accent'], card, 2)

    fm = fonts.get('medium')
    fs = fonts.get('small')

    # 名称
    screen.blit(fm.render(adventurer['name'], True, COLORS['text_secondary']), (x + 10, y + 8))

    # 属性
    atk_hp = f"ATK:{adventurer['attack']} HP:{adventurer['health']}"
    screen.blit(fs.render(atk_hp, True, COLORS['text_secondary']), (x + 10, y + 32))

    # 费用
    cost = adventurer.get('cost', 3)
    screen.blit(fs.render(f"费用:{cost}金", True, COLORS['gold']), (x + 10, y + 52))

    # 关键词
    if adventurer.get('keywords'):
        kw = ','.join(adventurer['keywords'])
        screen.blit(fs.render(kw, True, COLORS['accent']), (x + 10, y + 72))

    # 购买按钮
    if show_buy and game_manager and buy_index is not None:
        can = game_manager.gold >= cost and len(game_manager.hand) < game_manager.MAX_HAND
        label = f"购买({cost}金)" if can else ("金币不足" if game_manager.gold < cost else "手牌已满")
        return Button(x + 30, y + 95, 140, 28, label, None, enabled=can)


def draw_unit_card(screen, x, y, unit, w=180, h=120, is_enemy=False, selected=False):
    """绘制战斗单位卡片"""
    border_color = COLORS['health'] if is_enemy else COLORS['success']
    if selected:
        border_color = COLORS['gold']
        pygame.draw.rect(screen, COLORS['selected_bg'], (x - 3, y - 3, w + 6, h + 6))

    bg = COLORS['enemy_bg'] if is_enemy else COLORS['ally_bg']
    pygame.draw.rect(screen, bg, (x, y, w, h))
    pygame.draw.rect(screen, border_color, (x, y, w, h), 3)

    fm = fonts.get('medium')
    fs = fonts.get('small')

    screen.blit(fm.render(unit['name'], True, COLORS['text_secondary']), (x + 8, y + 8))
    screen.blit(fs.render(f"ATK:{unit['attack']}", True, COLORS['text_secondary']), (x + 8, y + 38))

    # HP 条
    max_hp = max(unit.get('max_health', unit['health']), 1)
    ratio = min(unit['health'] / max_hp, 1.0)
    bar_w = w - 20
    pygame.draw.rect(screen, (60, 0, 0), (x + 8, y + 60, bar_w, 14))
    hp_c = (0, 200, 0) if ratio > 0.5 else (200, 200, 0) if ratio > 0.25 else (200, 0, 0)
    pygame.draw.rect(screen, hp_c, (x + 8, y + 60, int(bar_w * ratio), 14))
    screen.blit(fs.render(f"HP:{unit['health']}", True, COLORS['text_secondary']), (x + 8, y + 78))


def draw_status_bar(screen, game_manager):
    """绘制顶部状态栏 (0,0 → 1200,40)"""
    pygame.draw.rect(screen, COLORS['bg_secondary'], (0, 0, WIDTH, 40))
    fs = fonts.get('small')

    items = [
        (f"英雄: {game_manager.hero.hero_class}", 100, COLORS['text_primary']),
        (f"生命: {game_manager.health}/{game_manager.max_health}", 280, COLORS['health']),
        (f"金币: {game_manager.gold}", 460, COLORS['gold']),
        (f"层数: {game_manager.floor}", 600, COLORS['text_secondary']),
        (f"手牌: {len(game_manager.hand)}/{game_manager.MAX_HAND}", 740, COLORS['mana']),
        (f"宝物: {len(game_manager.relics)}/{game_manager.MAX_RELICS}", 920, COLORS['accent']),
    ]
    for text, cx, color in items:
        surf = fs.render(text, True, color)
        screen.blit(surf, surf.get_rect(center=(cx, 20)))


def draw_text_centered(screen, text, y, font_name='large', color=None):
    """屏幕居中绘制文字"""
    if color is None:
        color = COLORS['text_secondary']
    surf = fonts.get(font_name).render(text, True, color)
    screen.blit(surf, surf.get_rect(center=(WIDTH // 2, y)))


def fill_bg(screen):
    """填充背景色"""
    screen.fill(COLORS['bg_primary'])
