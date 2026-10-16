"""音频契约：场景 BGM、动画事件 SFX、素材落盘三者必须对得上。

写这些用例的原因（2026-10-16 实测）：`battle.py` 里调了 `play_bgm('boss_fight')`，
但 `SCENE_BGM` 没有登记这个键 —— 代码"以为"切了 Boss 战 BGM，实际什么都没发生，
而且没有任何地方会报错。这类"静默无操作"必须由契约测试看住。
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from game.audio import BGM_PRESETS, EVENT_SFX, SCENE_BGM, SFX_NAMES

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_every_scene_bgm_has_a_generated_preset():
    """SCENE_BGM 引用的文件名必须都有对应的 bloodmusic 预设（否则永远静音）。"""
    orphans = {scene: name for scene, name in SCENE_BGM.items()
               if name.replace(".wav", "") not in BGM_PRESETS}
    assert not orphans, "这些场景引用了不存在的 BGM 预设：%s" % orphans


def test_every_event_sfx_exists():
    bad = {event: name for event, name in EVENT_SFX.items() if name and name not in SFX_NAMES}
    assert not bad, "这些动画事件映射到了不存在的音效：%s" % bad


def test_play_bgm_calls_in_ui_are_registered():
    """UI 里 `play_bgm('x')` 的每个字面量都必须在 SCENE_BGM 里登记。"""
    missing = {}
    for path in (PROJECT_ROOT / "ui").rglob("*.py"):
        text = io.open(path, encoding="utf-8").read()
        for scene in set(re.findall(r"play_bgm\(\s*['\"]([\w-]+)['\"]", text)):
            if scene not in SCENE_BGM:
                missing.setdefault(str(path.relative_to(PROJECT_ROOT)), []).append(scene)
    assert not missing, "UI 调用了未登记的 BGM 场景：%s" % missing


def test_play_sfx_calls_in_ui_exist():
    """UI 里 `audio.play('x')` / `play_event('x')` 的调用必须能落到真实素材上。"""
    problems = {}
    for path in (PROJECT_ROOT / "ui").rglob("*.py"):
        text = io.open(path, encoding="utf-8").read()
        for name in set(re.findall(r"\.play\(\s*['\"]([\w-]+)['\"]", text)):
            if name not in SFX_NAMES:
                problems.setdefault(str(path.relative_to(PROJECT_ROOT)), []).append(name)
    assert not problems, "UI 播放了不存在的音效：%s" % problems


def test_battle_animation_events_have_sfx():
    """战斗动画的每种事件类型都要有音效（新增动画事件时这里会红）。"""
    source = io.open(PROJECT_ROOT / "ui" / "scenes" / "battle.py", encoding="utf-8").read()
    types = set(re.findall(r"etype == '(\w+)'", source))
    assert types, "没有解析到动画事件类型（正则或实现变了）"
    missing = sorted(t for t in types if t not in EVENT_SFX)
    assert not missing, "这些动画事件没有音效：%s" % missing


def test_scene_bgm_covers_every_registered_scene():
    """app 里注册的场景都应该有 BGM（没有就静音，属于遗漏）。"""
    source = io.open(PROJECT_ROOT / "ui" / "app.py", encoding="utf-8").read()
    scenes = set(re.findall(r"scenes\.register\(\s*['\"]([\w-]+)['\"]", source))
    assert scenes
    missing = sorted(scene for scene in scenes if scene not in SCENE_BGM)
    assert not missing, "这些场景没有配 BGM：%s" % missing


@pytest.mark.parametrize("scene", sorted(SCENE_BGM))
def test_scene_bgm_filename_shape(scene):
    assert SCENE_BGM[scene].endswith(".wav")
