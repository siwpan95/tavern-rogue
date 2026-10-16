"""help_scene.py — 游戏内帮助（规格 §11：编写游戏内帮助文本）

分页而不是一屏糊满：每页一个主题，玩家按需翻。
文本与实现同源的地方（关键词、共鸣、进阶、规则）直接从代码里读，
避免帮助文本变成"第二个事实源"。
"""
import pygame

from ui.scenes.base import Scene
from ui.renderer import fill_bg, draw_text_centered, fonts, COLORS, WIDTH


# 关键词帮助文本：**键必须是引擎/数据里的关键词 id**
# （tests/test_spec_gaps.py 会拿数据里的关键词集合与这里比对，缺一个就红）
KEYWORD_HELP = {
    "GUARD": "守卫：敌人必须先攻击它",
    "SHIELD": "力场护盾：免疫下一次伤害",
    "ARMOR": "护甲：每次受到的伤害 -1（最低 1）",
    "POISON": "剧毒：伤害直接消灭目标",
    "FRENZY": "连击：每回合可以攻击两次",
    "DODGE": "闪避：有几率完全躲开攻击",
    "FLYING": "飞行：无视守卫，直接打后排",
    "REGENERATION": "再生：每回合恢复生命",
    "FIRE_BREATH": "火焰吐息：战斗开始时造成伤害",
    "BLOOD_FURY": "血怒：友军阵亡后攻击力提升",
    "CLEAVE": "横扫：攻击时顺劈两侧敌人",
    "OVERKILL": "过杀：超额伤害触发额外效果",
    "AEGIS": "神盾：开战获得吸收值，先吃吸收再掉血",
    "THORNS": "荆棘：反弹所承受伤害的 50%",
    "INTIMIDATE": "威吓：被打中未死的敌人攻击力下降（最多 3 层）",
    "AURA": "光环：相邻同伴 +1 攻击 +1 生命",
    "WARRIOR_SPIRIT": "战魂：每 2 次击杀 +1 攻击（每场最多 +4）",
    "MARTYR": "殉道：阵亡时给 2 名存活友军护盾",
}


def _keyword_pages():
    """关键词页（顺序固定，便于玩家形成肌肉记忆）。"""
    return [KEYWORD_HELP[key] for key in KEYWORD_HELP]


def build_pages():
    """帮助页内容（每次调用都重新生成，保证与实现同步）。"""
    from game.hero import get_all_hero_classes
    from game.mutators import list_mutators
    from game.persistence import ADVANCEMENT_DIFFICULTY, MAX_ADVANCEMENT
    from game.data_labels import TRIBE_NAMES

    class_lines = []
    for entry in get_all_hero_classes():
        hero = None
        try:
            from game.hero import create_hero
            hero = create_hero(entry["id"])
        except Exception:  # noqa: BLE001
            pass
        extra = []
        if hero is not None:
            if getattr(hero, "PASSIVE_HEALTH_BONUS", 0):
                extra.append("生命 +%d" % hero.PASSIVE_HEALTH_BONUS)
            if getattr(hero, "PASSIVE_INITIATIVE_BONUS", 0):
                extra.append("全队先攻 +%d" % hero.PASSIVE_INITIATIVE_BONUS)
            if getattr(hero, "PASSIVE_TEAM_HEALTH_BONUS", 0):
                extra.append("全队生命 +%d" % hero.PASSIVE_TEAM_HEALTH_BONUS)
            if getattr(hero, "MISSILE_DAMAGE", 0):
                extra.append("飞弹 %d 点" % hero.MISSILE_DAMAGE)
            if getattr(hero, "PASSIVE_ATTACK_BONUS", 0):
                extra.append("全队攻击 +%d" % hero.PASSIVE_ATTACK_BONUS)
            if getattr(hero, "PASSIVE_MAX_HEALTH_PENALTY", 0):
                extra.append("生命 -%d" % hero.PASSIVE_MAX_HEALTH_PENALTY)
        class_lines.append("%s：技能「%s」%s" % (
            entry["name"], entry["skill"], ("｜被动：" + "、".join(extra)) if extra else ""))

    mutator_lines = ["%s（%s）：%s" % (m["name"], m["id"], m["description"])
                     for m in list_mutators()]

    advancement = ["进阶 %d：%s" % (level, _advancement_note(level))
                   for level in range(1, MAX_ADVANCEMENT + 1)]
    # ADVANCEMENT_DIFFICULTY 直接读出来，保证说明与数值同源
    assert ADVANCEMENT_DIFFICULTY[MAX_ADVANCEMENT], "进阶表不能是空的"

    return [
        ("核心循环", [
            "旅店招募 → 选地图节点 → 结算节点 → 下一层，直到击败第 8 层的最终 Boss。",
            "每回合先发铸币，再在酒馆买冒险者、调站位，然后出战（自动结算）。",
            "英雄生命归零 = 本局结束；战斗失败会按敌方剩余人数扣英雄生命。",
            "第 9 层是**可选**的宝藏密室：带「密室钥匙」才能进，没钥匙会被跳过。",
        ]),
        ("铸币与招募", [
            "回合收入 = 3 + 当前层数 + 人类共鸣加成（上限 10）。",
            "买冒险者 3 铸币起（星级越高越贵）；刷新酒馆 1 铸币。",
            "同一冒险者凑满 3 个自动三连合成精英版（属性提升 + 发现一张新卡）。",
            "卖掉不需要的冒险者可以回血回币；术士可以用生命分流顶铸币。",
        ]),
        ("种族共鸣", [
            "场上同族数量达到 2 / 4 / 6 触发对应档位，档位越高效果越强。",
            "六大种族：" + "、".join(TRIBE_NAMES.values()) + "。",
            "人类：每回合额外铸币 + 首次刷新免费；精灵：闪避与先攻。",
            "矮人：护甲 + 首回合减伤；龙裔：开战火焰伤害。",
            "半兽人：暴击几率与倍率随档位提升；提夫林：友军阵亡时反伤。",
            "「职介棱镜」这类宝物会改写共鸣计数，凑不满 6 个也能吃满最高档。",
        ]),
        ("关键词（1/2）", _keyword_pages()[:9]),
        ("关键词（2/2）", _keyword_pages()[9:]),
        ("英雄职业", class_lines),
        ("地图与节点", [
            "9 层地图：第 1 层营地 → 第 2-7 层随机（战斗/精英/商店/奇遇/营地）",
            "→ 第 8 层龙穴（Boss 池，随机一种）→ 第 9 层密室（可选，需钥匙）。",
            "每层 2-4 个节点，节点内容进入后才揭晓；精英与 Boss 会带**词缀**（第 5 层起）。",
            "节点的具体内容：怪物巢穴（战斗+铸币）、精英（必掉宝物）、商人（买卡/宝物+卖卡）、",
            "古老祭坛（文本事件）、安全营地（回血或训练 +1/+1）、首领（升酒馆等级+稀有宝物）。",
        ]),
        ("宝物与事件", [
            "最多带 6 件宝物；稀有度权重 常见 60% / 稀有 30% / 史诗 10%。",
            "史诗宝物会改变玩法：职介棱镜（共鸣 +1）、毁灭契约（全队连击换生命）、",
            "耐心沙漏（每回合全队攻击递增）。",
            "事件同局不重复；选项的后果在文本里写明，选完立即结算。",
        ]),
        ("进阶与自定义规则", advancement + [
            "—",
            "自定义规则（命令行 `--mutator`，可叠加）：",
        ] + mutator_lines),
        ("图鉴与存档", [
            "主菜单「冒险图鉴」记录见过的宝物/敌人/事件，以及完成度。",
            "游戏会在一局中途自动存档，主菜单可以「继续冒险」。",
            "局外成长（职业解锁、进阶、战绩）存在 saves/progress.json。",
            "想复现某一局：`python run_gui.py --seed <种子>`（种子显示在结算屏）。",
        ]),
        ("操作", [
            "鼠标左键：点击按钮/卡片选择；ESC：返回上一级（菜单里为退出）。",
            "战斗中自动结算，无需操作；招募/商店/事件需要你点选。",
            "命令行参数：`--seed N` 固定随机种子，`--mutator ID` 自定义规则，",
            "`--list-mutators` 列出全部规则；`python run_tests.py` 跑自检。",
        ]),
    ]


def _advancement_note(level: int) -> str:
    from game.persistence import ADVANCEMENT_DIFFICULTY

    params = ADVANCEMENT_DIFFICULTY[level]
    parts = []
    if params.get("elite_node_weight", 1.0) > 1.0:
        parts.append("精英节点 ×%.1f" % params["elite_node_weight"])
    if params.get("enemy_health_mult", 1.0) > 1.0:
        parts.append("敌人生命 ×%.2f" % params["enemy_health_mult"])
    if params.get("enemy_attack_mult", 1.0) > 1.0:
        parts.append("敌人攻击 ×%.2f" % params["enemy_attack_mult"])
    if params.get("shop_price_mult", 1.0) > 1.0:
        parts.append("商店价格 ×%.2f" % params["shop_price_mult"])
    if params.get("boss_gold_mult", 1.0) < 1.0:
        parts.append("Boss 掉落 ×%.2f" % params["boss_gold_mult"])
    if params.get("camp_heal_mult", 1.0) < 1.0:
        parts.append("营地治疗 ×%.1f" % params["camp_heal_mult"])
    if params.get("affix_bonus", 0):
        parts.append("Boss 额外词缀 +%d" % params["affix_bonus"])
    if params.get("start_gold_penalty", 0):
        parts.append("起始铸币 -%d" % params["start_gold_penalty"])
    return "、".join(parts) or "与普通难度相同"


class HelpScene(Scene):
    """分页帮助"""

    def enter(self, page=0, **kwargs):
        super().enter(**kwargs)
        self._pages = build_pages()
        self._page = max(0, min(int(page or 0), len(self._pages) - 1))

    def draw(self):
        fill_bg(self.screen)
        title, lines = self._pages[self._page]
        draw_text_centered(self.screen, "帮助 · %s" % title, 44, 'large', COLORS['text_primary'])

        font = fonts.get('medium')
        y = 100
        for line in lines:
            # 很长的行按屏幕宽度硬切（避免出屏）
            while line:
                chunk, line = line[:46], line[46:]
                surf = font.render(chunk, True, COLORS['text_secondary'])
                self.screen.blit(surf, (90, y))
                y += 28
            if y > 620:
                break

        self.buttons.clear()
        self.buttons.add(80, 660, 200, 46, "← 上一页",
                         lambda: self.switch_to('help', page=self._page - 1))
        self.buttons.add(300, 660, 200, 46, "下一页 →",
                         lambda: self.switch_to('help', page=self._page + 1))
        self.buttons.add(520, 660, 200, 46, "返回主菜单", lambda: self.switch_to('menu'))
        counter = fonts.get('small').render(
            "%d / %d" % (self._page + 1, len(self._pages)), True, COLORS['text_secondary'])
        self.screen.blit(counter, counter.get_rect(center=(WIDTH // 2, 640)))
        self.buttons.draw_all(self.screen)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.switch_to('menu')
            return
        super().handle_event(event)
