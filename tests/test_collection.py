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
