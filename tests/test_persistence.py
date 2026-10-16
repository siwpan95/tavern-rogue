"""局外成长存档：解锁链、进阶难度、战绩记录。"""
from __future__ import annotations

import json

from game.persistence import MAX_ADVANCEMENT, ProgressManager


def test_defaults_unlock_only_warrior(temp_progress_file):
    progress = ProgressManager(save_file=str(temp_progress_file))
    assert progress.is_class_unlocked("warrior")
    assert not progress.is_class_unlocked("rogue")
    assert progress.get_class_advancement("warrior") == 0


def test_progress_round_trips_through_disk(temp_progress_file):
    progress = ProgressManager(save_file=str(temp_progress_file))
    progress.unlock_class("rogue")
    progress.set_class_advancement("warrior", 3)
    progress.unlock_relic("boots_of_speed")
    progress.save()
    assert temp_progress_file.exists()

    reloaded = ProgressManager(save_file=str(temp_progress_file))
    assert reloaded.is_class_unlocked("rogue")
    assert reloaded.get_class_advancement("warrior") == 3
    assert "boots_of_speed" in reloaded.get_unlocked_relics()


def test_advancement_is_capped_and_raises_difficulty(temp_progress_file):
    progress = ProgressManager(save_file=str(temp_progress_file))
    progress.set_class_advancement("warrior", 99)
    assert progress.get_class_advancement("warrior") == MAX_ADVANCEMENT

    easy = ProgressManager(save_file=str(temp_progress_file))
    assert easy.get_difficulty_params("warrior")["enemy_health_mult"] > 1.0


def test_advancing_unlocks_next_class(temp_progress_file):
    progress = ProgressManager(save_file=str(temp_progress_file))
    assert progress.advance_class("warrior")
    assert progress.is_class_unlocked("rogue"), "战士进阶后应解锁游荡者"


def test_record_run_updates_stats_and_advances_on_victory(temp_progress_file):
    progress = ProgressManager(save_file=str(temp_progress_file))
    progress.record_run("warrior", True, 9, relics=["boots_of_speed"])
    assert progress.data["total_runs"] == 1
    assert progress.data["victories"] == 1
    assert progress.get_class_advancement("warrior") == 1
    assert progress.data["best_records"]["warrior"]["victory"] is True


def test_broken_save_falls_back_to_defaults(temp_progress_file):
    temp_progress_file.write_text("{not json", encoding="utf-8")
    progress = ProgressManager(save_file=str(temp_progress_file))
    assert progress.is_class_unlocked("warrior")
    assert progress.data["total_runs"] == 0


def test_save_file_is_valid_json(temp_progress_file):
    progress = ProgressManager(save_file=str(temp_progress_file))
    progress.record_run("warrior", False, 4)
    with open(temp_progress_file, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["total_runs"] == 1
    assert payload["run_history"][-1]["floor"] == 4


def test_available_classes_report_lock_state(temp_progress_file):
    progress = ProgressManager(save_file=str(temp_progress_file))
    classes = progress.get_available_classes()
    assert len(classes) == 5
    by_id = {row["id"]: row for row in classes}
    assert by_id["warrior"]["locked"] is False
    assert by_id["warlock"]["locked"] is True
