"""本局统计、种子复现与结算屏文案（失败屏要能归因、有进度、有下一步）。"""
from __future__ import annotations

import random

import pytest

from game.persistence import ProgressManager
from ui.game_manager import GameManager


@pytest.fixture
def game(tmp_path):
    progress = ProgressManager(save_file=str(tmp_path / "progress.json"))
    manager = GameManager(progress_manager=progress)
    manager.new_game("warrior")
    return manager


def test_new_game_records_a_seed(game):
    assert isinstance(game.seed, int)
    assert game.run_stats["battles"] == 0


def test_explicit_seed_makes_map_reproducible(tmp_path):
    def build():
        progress = ProgressManager(save_file=str(tmp_path / "p.json"))
        manager = GameManager(progress_manager=progress)
        manager.new_game("warrior", seed=20261016)
        manager.ensure_map()
        return [[(n["id"], n["type"]) for n in layer["nodes"]]
                for layer in manager.map_manager.map_data["layers"]]

    assert build() == build()


def test_random_seed_does_not_seed_global_rng(tmp_path, monkeypatch):
    """不传种子时不能给全局 RNG 播种（否则调用方的随机序列被悄悄改掉）。"""
    calls = []
    real_seed = random.seed

    def spy_seed(*args, **kwargs):
        calls.append(args)
        return real_seed(*args, **kwargs)

    monkeypatch.setattr(random, "seed", spy_seed)
    progress = ProgressManager(save_file=str(tmp_path / "p.json"))
    GameManager(progress_manager=progress).new_game("warrior")
    assert calls == [], "new_game 未显式传种子时不应调用 random.seed"

    GameManager(progress_manager=progress).new_game("warrior", seed=1234)
    assert calls and calls[0] == (1234,), "显式传种子时必须播种"


def test_record_battle_counts_results(game):
    game.record_battle("ally", "monster")
    game.record_battle("enemy", "elite")
    game.record_battle("ally", "boss")
    assert game.run_stats["battles"] == 3
    assert game.run_stats["battle_wins"] == 2
    assert game.run_stats["elites"] == 1
    assert game.run_stats["bosses"] == 1


def test_record_run_persists_stats_and_seed(game):
    game.record_battle("ally", "monster")
    game.record_run(victory=False, floor=5)
    record = game.progress.data["run_history"][-1]
    assert record["floor"] == 5
    assert record["stats"]["battles"] == 1
    assert record["seed"] == game.seed
    assert game.progress.data["totals"]["battles"] == 1
    assert game.progress.data["total_runs"] == 1


def test_run_summary_lines_include_goal_and_seed(game):
    game.record_battle("ally", "boss")
    game.record_run(victory=True, floor=8)
    lines = game.run_summary_lines()
    joined = "\n".join(lines)
    assert "种子" in joined
    assert "下一目标" in joined
    assert "总局数" in joined
    assert any("Boss" in line for line in lines)


def test_next_goal_hint_varies_by_progress(game):
    assert "突破第" in game.next_goal_hint()
    game.floor = game.MAX_FLOORS - 1
    assert "最终 Boss" in game.next_goal_hint()
    game.record_run(victory=True, floor=8)
    assert "进阶" in game.next_goal_hint()


def test_event_pool_does_not_repeat_within_a_run(tmp_path):
    import json
    import io

    from game.events import EventSystem

    def loader(filename):
        with io.open("data/%s" % filename, encoding="utf-8") as handle:
            return json.load(handle)

    system = EventSystem(loader)
    system.load_events()
    picked = [system.select_random_event()["id"] for _ in range(len(system.events_data))]
    assert len(set(picked)) == len(picked), "同一局内事件不应重复"
