"""图鉴：发现记录、完成度、以及"记录了但不崩"的健壮性。"""
from __future__ import annotations

import pytest

from game.collection import Collection, KINDS, KIND_LABELS
from game.persistence import ProgressManager
from ui.game_manager import GameManager


@pytest.fixture
def progress(tmp_path):
    return ProgressManager(save_file=str(tmp_path / "progress.json"))


def test_mark_returns_true_only_on_first_discovery(progress):
    collection = Collection(progress)
    assert collection.mark("relics", "boots_of_speed") is True
    assert collection.mark("relics", "boots_of_speed") is False
    assert collection.is_discovered("relics", "boots_of_speed")


def test_collection_persists_across_sessions(tmp_path):
    path = str(tmp_path / "progress.json")
    first = Collection(ProgressManager(save_file=path))
    first.mark("enemies", "goblin_scout")
    second = Collection(ProgressManager(save_file=path))
    assert second.is_discovered("enemies", "goblin_scout")


def test_mark_rejects_unknown_kind(progress):
    collection = Collection(progress)
    assert collection.mark("dragons", "x") is False
    assert collection.mark("relics", None) is False


def test_progress_of_reports_percentage(progress):
    collection = Collection(progress)
    collection.mark_many("events", ["a", "b"])
    found, total, pct = collection.progress_of("events", 8)
    assert (found, total) == (2, 8)
    assert pct == pytest.approx(25.0)


def test_summary_covers_all_kinds(progress):
    collection = Collection(progress)
    rows = collection.summary({"relics": 36, "enemies": 56, "events": 36})
    assert [row[0] for row in rows] == list(KINDS)
    assert all(row[1] == 0 for row in rows)
    assert set(KIND_LABELS) == set(KINDS)


def test_game_manager_marks_relics_on_pickup(tmp_path):
    progress = ProgressManager(save_file=str(tmp_path / "p.json"))
    game = GameManager(progress_manager=progress)
    game.new_game("warrior")
    relic = game.load_data("relics.json")[0]
    assert game.add_relic(dict(relic)) is True
    assert game.collection().is_discovered("relics", relic["id"])


def test_game_manager_totals_match_data(tmp_path):
    progress = ProgressManager(save_file=str(tmp_path / "p.json"))
    game = GameManager(progress_manager=progress)
    game.new_game("warrior")
    totals = game.collection_totals()
    assert totals["relics"] == len(game.load_data("relics.json"))
    assert totals["enemies"] == len(game.load_data("enemies.json"))
    assert totals["events"] == len(game.load_data("events.json"))


# ─── 图鉴场景（表现层：条目网格 + 剪影 + 翻页）─────────────

def make_scene(tmp_path, tab="relics", page=0, discovered=()):
    from ui.app import TavernRogueApp

    app = TavernRogueApp()
    app.game.new_game("warrior")
    if discovered:
        app.game.mark_collection(tab, list(discovered))
    app.scenes.switch_to("collection", tab=tab, page=page)
    return app


def test_codex_lists_entries_for_every_tab(tmp_path):
    app = make_scene(tmp_path, tab="relics")
    scene = app.scenes.current
    assert len(scene._entries) == len(app.game.load_data("relics.json"))
    assert scene._page_count >= 1
    assert all(entry["id"] and entry["name"] for entry in scene._entries)

    app.scenes.switch_to("collection", tab="enemies")
    assert len(app.scenes.current._entries) == len(app.game.load_data("enemies.json"))
    app.scenes.switch_to("collection", tab="events")
    assert len(app.scenes.current._entries) == len(app.game.load_data("events.json"))


def test_codex_page_is_clamped(tmp_path):
    app = make_scene(tmp_path, tab="relics", page=99)
    scene = app.scenes.current
    assert scene._page == scene._page_count - 1
    assert scene._page_entries(), "夹住后的页面必须有条目（不能画空页）"


def test_codex_unknown_tab_falls_back(tmp_path):
    app = make_scene(tmp_path, tab="dragons")
    assert app.scenes.current._tab == "relics"


def test_codex_entries_carry_category_hints(tmp_path):
    app = make_scene(tmp_path, tab="enemies")
    extras = {entry["extra"] for entry in app.scenes.current._entries}
    assert extras & {"Boss", "精英"}, "敌人条目要标出 Boss/精英：%s" % extras
    app.scenes.switch_to("collection", tab="relics")
    rarities = {entry["extra"] for entry in app.scenes.current._entries}
    assert rarities <= {"常见", "稀有", "史诗"}, rarities


def test_codex_locked_entries_have_a_hint(tmp_path):
    from ui.scenes.collection_scene import LOCK_HINTS, TABS

    for tab in TABS:
        assert LOCK_HINTS.get(tab), "%s 缺少未发现时的线索文案" % tab


def test_codex_draws_with_and_without_discoveries(tmp_path):
    app = make_scene(tmp_path, tab="relics", discovered=["boots_of_speed"])
    app.scenes.update(0.016)
    app.scenes.draw()
    assert app.scenes.current._collection.is_discovered("relics", "boots_of_speed")
    # 注意：**不要**在这里 pygame.quit() —— 会关掉其它用例共享的 display
