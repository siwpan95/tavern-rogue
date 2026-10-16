#!/usr/bin/env python3
"""离线生成 TavernRogue 的音频素材（**构建期工具**，不是游戏运行时依赖）。

为什么离线生成：
  · bloodmusic 依赖 numpy + scipy（约 140 MB），冷启动约 5 秒；游戏运行时只需要 pygame；
  · 生成一次、运行时只播放，游戏进程零 numpy/scipy、零冷启动、零实时抖动。

用法：
    pip install -r requirements-assets.txt
    python tools/gen_audio_assets.py                 # 生成全量 SFX + 10 首 BGM（默认 20 秒）
    python tools/gen_audio_assets.py --no-bgm        # 只生成音效
    python tools/gen_audio_assets.py --bgm-seconds 8 # 短一点，便于快速验证
    python tools/gen_audio_assets.py --check         # 只检查素材是否齐备（不生成）

产物：assets/audio/sfx/*.wav（35 个）、assets/audio/bgm/*.wav（10 首循环）。
该目录在 .gitignore 里 —— 素材是**生成物**，不入库。
"""
from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from game.audio import BGM_PRESETS, SFX_DIR, BGM_DIR, SFX_NAMES, AudioManager  # noqa: E402


def check_assets(sfx_dir=None, bgm_dir=None) -> int:
    # 默认值在函数体内解析（而不是写成默认参数）—— 否则测试里 monkeypatch 模块常量不生效
    sfx_dir = sfx_dir or SFX_DIR
    bgm_dir = bgm_dir or BGM_DIR
    manager = AudioManager(enabled=False, sfx_dir=sfx_dir, bgm_dir=bgm_dir)
    missing = manager.missing_assets()
    if not missing:
        print("[OK] 音频素材齐备：%d 个音效 + %d 首 BGM" % (len(SFX_NAMES), len(BGM_PRESETS)))
        return 0
    print("[MISSING] 缺少 %d 个素材：" % len(missing))
    for item in missing[:10]:
        print("   -", item)
    if len(missing) > 10:
        print("   ...")
    return 1


def generate_sfx() -> int:
    try:
        from bloodmusic.simple_sfx import SimpleSFX
    except ImportError as exc:
        print("[FAIL] 需要 bloodmusic：%s" % exc)
        print("       先跑 pip install -r requirements-assets.txt")
        return 2

    os.makedirs(SFX_DIR, exist_ok=True)
    sfx = SimpleSFX(output_dir=SFX_DIR, format="wav")
    exported = sfx.export_game_pack(SFX_DIR)
    print("[SFX] 生成 %d 个音效 → %s" % (len(exported), SFX_DIR))

    missing = [name for name in SFX_NAMES
               if not os.path.exists(os.path.join(SFX_DIR, name + ".wav"))]
    if missing:
        print("[FAIL] 以下音效没生成出来：%s" % missing)
        return 1
    return 0


def generate_bgm(seconds: float) -> int:
    try:
        import bloodmusic as bm
    except ImportError as exc:
        print("[FAIL] 需要 bloodmusic：%s" % exc)
        return 2

    os.makedirs(BGM_DIR, exist_ok=True)
    failed = []
    for scene, preset_name in BGM_PRESETS.items():
        pattern = getattr(bm, preset_name, None)
        if pattern is None:
            failed.append("%s（预设 %s 不存在）" % (scene, preset_name))
            continue
        try:
            pcm = bm.render_pattern_to_array(pattern, seconds)
            path = os.path.join(BGM_DIR, scene + ".wav")
            bm.export_audio(pcm, path, format="wav")
            print("  [BGM] %-12s %.1fs → %s" % (scene, seconds, os.path.basename(path)))
        except Exception as exc:  # noqa: BLE001 - 单个 BGM 失败不该中断整批
            failed.append("%s（%s）" % (scene, exc))
    if failed:
        print("[FAIL] 以下 BGM 生成失败：%s" % failed)
        return 1
    print("[BGM] 生成 %d 首 BGM → %s" % (len(BGM_PRESETS), BGM_DIR))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 TavernRogue 音频素材（离线）")
    parser.add_argument("--check", action="store_true", help="只检查素材是否齐备")
    parser.add_argument("--no-bgm", action="store_true", help="只生成音效")
    parser.add_argument("--bgm-seconds", type=float, default=20.0, help="每首 BGM 的时长（秒）")
    args = parser.parse_args(argv)

    if args.check:
        return check_assets()

    code = generate_sfx()
    if code != 0:
        return code
    if not args.no_bgm:
        code = generate_bgm(args.bgm_seconds)
        if code != 0:
            return code

    print()
    return check_assets()


if __name__ == "__main__":
    sys.exit(main())
