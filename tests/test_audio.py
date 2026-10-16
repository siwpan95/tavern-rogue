"""音频：素材缺失/无设备时静音降级；事件映射与生成器检查入口可用。"""
from __future__ import annotations

import os

import pytest

from game.audio import AudioManager, BGM_PRESETS, EVENT_SFX, SCENE_BGM, SFX_NAMES


@pytest.fixture
def empty_audio(tmp_path):
    return AudioManager(enabled=True, sfx_dir=str(tmp_path / "sfx"), bgm_dir=str(tmp_path / "bgm"))


def test_event_sfx_mapping_covers_battle_animation_events():
    for etype in ("attack", "dodge", "heal", "death", "shield", "poison", "frenzy"):
        assert etype in EVENT_SFX


def test_scene_bgm_covers_all_registered_scenes():
    scenes = {"menu", "class_select", "recruit", "map", "battle", "shop", "camp",
              "event", "treasure", "reward", "game_over", "victory"}
    assert scenes <= set(SCENE_BGM)


def test_bgm_files_exist_in_preset_list():
    generated = {scene + ".wav" for scene in BGM_PRESETS}
    for filename in set(SCENE_BGM.values()):
        assert filename in generated, "%s 没有对应的生成预设" % filename


def test_play_without_assets_degrades_quietly(empty_audio):
    assert empty_audio.play("attack") is False
    assert empty_audio.play_event("attack") is False
    assert empty_audio.play_bgm("menu") is False


def test_status_reports_missing_assets(empty_audio):
    status = empty_audio.status()
    assert status["enabled"] is True
    assert len(status["missing"]) == len(SFX_NAMES) + len(BGM_PRESETS)


def test_disabled_manager_is_inert(tmp_path):
    manager = AudioManager(enabled=False, sfx_dir=str(tmp_path), bgm_dir=str(tmp_path))
    assert manager.mixer_ready is False
    assert manager.play("attack") is False


def test_generator_check_exit_code(tmp_path, monkeypatch, capsys):
    """素材不齐时 `--check` 必须响亮失败（退出码 1，SKIP 不是通过）。"""
    from tools import gen_audio_assets

    monkeypatch.setattr(gen_audio_assets, "SFX_DIR", str(tmp_path / "sfx"))
    monkeypatch.setattr(gen_audio_assets, "BGM_DIR", str(tmp_path / "bgm"))
    assert gen_audio_assets.main(["--check"]) == 1
    assert "MISSING" in capsys.readouterr().out


def test_generator_check_passes_when_assets_present(tmp_path, monkeypatch, capsys):
    from tools import gen_audio_assets

    sfx_dir = tmp_path / "sfx"
    bgm_dir = tmp_path / "bgm"
    os.makedirs(sfx_dir, exist_ok=True)
    os.makedirs(bgm_dir, exist_ok=True)
    for name in SFX_NAMES:
        (sfx_dir / (name + ".wav")).write_bytes(b"RIFF")
    for scene in BGM_PRESETS:
        (bgm_dir / (scene + ".wav")).write_bytes(b"RIFF")

    monkeypatch.setattr(gen_audio_assets, "SFX_DIR", str(sfx_dir))
    monkeypatch.setattr(gen_audio_assets, "BGM_DIR", str(bgm_dir))
    assert gen_audio_assets.main(["--check"]) == 0
    assert "[OK]" in capsys.readouterr().out


def test_tools_directory_is_scanned_by_run_tests():
    import run_tests

    scanned = [str(path).replace("\\", "/") for path in run_tests.iter_python_files(run_tests.PROJECT_ROOT)]
    assert any(path.endswith("tools/gen_audio_assets.py") for path in scanned)
