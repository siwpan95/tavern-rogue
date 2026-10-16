"""字体：不入库 + 下载脚本 + 渲染层回退（缺字体不能崩，降级要出声）。"""
from __future__ import annotations

import hashlib
import os

import pytest

from tools import fetch_font


# ─── 不入库与下载脚本 ─────────────────────────────────────

def test_font_is_not_tracked(repo_root):
    """50 MiB 级字体必须走下载，不能进索引（门禁 H4 的 >5 MiB 规则）。"""
    import subprocess

    result = subprocess.run(["git", "-C", str(repo_root), "ls-files"],
                            capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        pytest.skip("git 不可用")
    tracked = [line for line in result.stdout.splitlines() if line.endswith(".ttf")]
    assert tracked == [], "字体不应入库：%s" % tracked


def test_font_search_order_prefers_assets_dir():
    from ui import renderer

    assert renderer.FONT_SEARCH_PATHS[0].endswith(
        os.path.join("assets", "fonts", renderer.FONT_FILENAME))
    assert renderer.FONT_SEARCH_PATHS[1].endswith(renderer.FONT_FILENAME)


def test_fetch_font_check_fails_loudly_when_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch_font, "TARGET_PATH", str(tmp_path / "missing.ttf"))
    monkeypatch.setattr(fetch_font, "LEGACY_PATH", str(tmp_path / "missing2.ttf"))
    assert fetch_font.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert "MISSING" in out
    assert "fetch_font.py --url" in out, "失败时必须给出可执行的下一步"


def test_fetch_font_check_passes_when_present(tmp_path, monkeypatch, capsys):
    target = tmp_path / fetch_font.FONT_FILENAME
    target.write_bytes(b"x" * 32)
    monkeypatch.setattr(fetch_font, "TARGET_PATH", str(target))
    monkeypatch.setattr(fetch_font, "LEGACY_PATH", str(tmp_path / "none.ttf"))
    assert fetch_font.main(["--check"]) == 0
    out = capsys.readouterr().out
    # 文件在就算"就位"（退出 0），但指纹不符时必须出声警告 —— 不许静默当成功
    assert "[OK]" in out or "[WARN]" in out
    assert "[WARN]" in out and "指纹不一致" in out


def test_fetch_font_check_ok_on_matching_fingerprint(tmp_path, monkeypatch, capsys):
    payload = b"font" * 64
    target = tmp_path / fetch_font.FONT_FILENAME
    target.write_bytes(payload)
    monkeypatch.setattr(fetch_font, "TARGET_PATH", str(target))
    monkeypatch.setattr(fetch_font, "LEGACY_PATH", str(tmp_path / "none.ttf"))
    monkeypatch.setattr(fetch_font, "EXPECTED_SIZE", len(payload))
    monkeypatch.setattr(fetch_font, "EXPECTED_SHA256", hashlib.sha256(payload).hexdigest())
    assert fetch_font.main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "[OK]" in out and "[WARN]" not in out


def test_fetch_font_download_verifies_and_places(tmp_path, monkeypatch, capsys):
    payload = b"fake-font-bytes" * 100
    source = tmp_path / "source.ttf"
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    target_dir = tmp_path / "fonts"
    monkeypatch.setattr(fetch_font, "TARGET_DIR", str(target_dir))
    monkeypatch.setattr(fetch_font, "TARGET_PATH", str(target_dir / fetch_font.FONT_FILENAME))
    monkeypatch.setattr(fetch_font, "EXPECTED_SIZE", len(payload))
    monkeypatch.setattr(fetch_font, "EXPECTED_SHA256", digest)

    assert fetch_font.main(["--url", source.as_uri()]) == 0
    assert (target_dir / fetch_font.FONT_FILENAME).read_bytes() == payload


def test_fetch_font_discards_corrupted_download(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.ttf"
    source.write_bytes(b"corrupted")
    target_dir = tmp_path / "fonts"
    monkeypatch.setattr(fetch_font, "TARGET_DIR", str(target_dir))
    monkeypatch.setattr(fetch_font, "TARGET_PATH", str(target_dir / fetch_font.FONT_FILENAME))
    monkeypatch.setattr(fetch_font, "EXPECTED_SIZE", 999999)
    monkeypatch.setattr(fetch_font, "EXPECTED_SHA256", "0" * 64)

    assert fetch_font.main(["--url", source.as_uri()]) == 1
    assert not (target_dir / fetch_font.FONT_FILENAME).exists(), "校验失败的文件必须丢弃"
    assert "[FAIL]" in capsys.readouterr().out


# ─── 渲染层回退 ───────────────────────────────────────────

def test_renderer_falls_back_and_warns(tmp_path, monkeypatch, capsys):
    import pygame
    from ui import renderer

    pygame.init()
    monkeypatch.setattr(renderer, "FONT_SEARCH_PATHS", (str(tmp_path / "nope.ttf"),))
    monkeypatch.setattr(renderer.FontManager, "_instance", None)

    manager = renderer.FontManager()
    manager.ensure_init()
    assert manager.fonts, "无论有没有内置字体都必须拿到可渲染的字体对象"
    assert manager.font_source.startswith("sysfont:") or manager.font_source == "pygame-default"
    assert "字体" in capsys.readouterr().err, "降级必须出声（不许静默）"
    assert manager.get("medium") is not None
