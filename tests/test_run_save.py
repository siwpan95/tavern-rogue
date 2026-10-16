"""局内存档：SaveLoadManager 往返 + 降级路径 + 与局外进度分目录。"""
from __future__ import annotations

import os

import pytest

from game import run_save
from game.persistence import ProgressManager
from ui.game_manager import GameManager


@pytest.fixture
def game(tmp_path):
    progress = ProgressManager(save_file=str(tmp_path / "progress.json"))
    manager = GameManager(progress_manager=progress)
    manager.new_game("warrior")
    return manager


@pytest.fixture
def isolated_save_dir(tmp_path, monkeypatch):
    save_dir = tmp_path / "runs"
    monkeypatch.setattr(run_save, "SAVE_DIR", str(save_dir))
    monkeypatch.setattr(run_save, "FALLBACK_FILE", str(save_dir / "run_slot0.json"))
    return save_dir


def test_snapshot_contains_run_state(game):
    game.start_recruit_turn()
    data = run_save.snapshot_from(game)
    assert data["hero_class"] == "warrior"
    assert data["gold"] == game.gold
    assert data["floor"] == game.floor
    assert isinstance(data["hand"], list)


def test_save_and_load_round_trip(game, isolated_save_dir):
    game.start_recruit_turn()
    for index in range(len(game.recruit_system.tavern_pool)):
        if game.recruit_system.recruit(index):
            game.recruit_system.deploy_to_board(0)
            break
    game.ensure_map()
    game.floor = 4
    game.gold = 7
    board_before = [(u["name"], u["health"]) for u in game.board]

    assert run_save.save_run(game) is True
    assert run_save.has_saved_run() is True

    # 打乱现场，再读档
    game.new_game("rogue")
    assert game.hero.hero_class == "rogue"
    assert run_save.load_run(game) is True
    assert game.hero.hero_class == "warrior"
    assert game.floor == 4
    assert game.gold == 7
    assert [(u["name"], u["health"]) for u in game.board] == board_before


def test_clear_run_removes_save(game, isolated_save_dir):
    run_save.save_run(game)
    assert run_save.has_saved_run() is True
    run_save.clear_run()
    assert run_save.has_saved_run() is False


def test_load_without_save_returns_false(game, isolated_save_dir):
    assert run_save.load_run(game) is False


def test_save_dir_is_separate_from_progress_file(game, isolated_save_dir):
    """局内存档与局外进度必须分目录，互不覆盖。"""
    run_save.save_run(game)
    assert "runs" in os.path.normpath(isolated_save_dir)
    assert not os.path.exists(os.path.join(str(isolated_save_dir), "progress.json"))


def test_fallback_when_engine_unavailable(game, isolated_save_dir, monkeypatch):
    """引擎不可用时应降级为 JSON 直写，功能不失效。"""
    monkeypatch.setattr(run_save, "ENGINE_AVAILABLE", False)
    monkeypatch.setattr(run_save, "SaveLoadManager", None)
    assert run_save.save_run(game) is True
    assert os.path.exists(str(isolated_save_dir / "run_slot0.json"))
    assert run_save.has_saved_run() is True
    assert run_save.load_run(game) is True


def test_game_manager_wrappers(game, isolated_save_dir):
    assert game.has_saved_run() is False
    assert game.save_run() is True
    assert game.has_saved_run() is True
    assert game.load_run() is True
    assert game.clear_saved_run() is True
