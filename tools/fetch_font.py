#!/usr/bin/env python3
"""下载内置中文字体到 `assets/fonts/`（字体是 50 MiB 级资产，**不入库**）。

为什么要下载而不是入库
  · 该字体 50.5 MiB，超过仓库卫生门禁的 5 MiB 阈值，也会让每次克隆都拖着它；
  · 它只是"表现层资产"，缺了游戏用系统 CJK 字体也能玩（`ui/renderer.py` 有回退链）。

用法
    python tools/fetch_font.py                      # 下载到 assets/fonts/
    python tools/fetch_font.py --check              # 只检查是否已就位（不联网）
    python tools/fetch_font.py --url <URL>          # 指定来源（也可用环境变量 TAVERN_ROGUE_FONT_URL）
    python tools/fetch_font.py --force              # 已存在也重新下载

就位后的位置：`assets/fonts/BaoCanMouHuiTingShouXieTi2.0-2.ttf`
退出码：0 已就位/下载成功 · 1 缺失或校验失败 · 2 用法或网络错误
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import sys
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_FILENAME = "BaoCanMouHuiTingShouXieTi2.0-2.ttf"
TARGET_DIR = os.path.join(REPO_ROOT, "assets", "fonts")
TARGET_PATH = os.path.join(TARGET_DIR, FONT_FILENAME)
LEGACY_PATH = os.path.join(REPO_ROOT, FONT_FILENAME)

# 与入库版本逐字节一致的指纹（2026-10-16 实测）
EXPECTED_SHA256 = "3d2f79b0a942fbc1b7f500ec0688549dcbc667da68e1f79661e3625540aee15f"
EXPECTED_SIZE = 52976164

# 默认来源：本仓 Gitee Release 附件（需要先把字体作为附件上传到该 tag 下）
DEFAULT_URL = ("https://gitee.com/siwpan/tavern-rogue/releases/download/"
               "assets-v1/" + FONT_FILENAME)


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate() -> str:
    """返回已就位的字体路径；没有则空串。"""
    for path in (TARGET_PATH, LEGACY_PATH):
        if os.path.exists(path):
            return path
    return ""


def manual_instructions(url: str) -> str:
    return (
        "请手工获取字体后放到：\n"
        "    %s\n"
        "来源可以是：\n"
        "    1) 任何可访问的 URL：python tools/fetch_font.py --url <URL>\n"
        "    2) 本仓 Gitee Release 附件：%s\n"
        "    3) 你手头已有的同名文件（直接复制过去即可）\n"
        "校验（可选）：sha256 应为 %s" % (TARGET_PATH, url, EXPECTED_SHA256)
    )


def check(verbose: bool = True) -> int:
    path = locate()
    if path and not os.path.exists(TARGET_PATH):
        # 老位置有副本：提示迁移，但不算失败
        if verbose:
            print("[OK] 已找到内置字体（老位置）：%s" % path)
            print("     建议迁移到规范位置：%s" % TARGET_PATH)
        return 0
    if not path:
        if verbose:
            print("[MISSING] 未找到内置字体 %s" % FONT_FILENAME)
            print(manual_instructions(DEFAULT_URL))
        return 1
    if verbose:
        size = os.path.getsize(path)
        digest = sha256_of(path)
        ok = (size == EXPECTED_SIZE and digest == EXPECTED_SHA256)
        print("[%s] %s（%d 字节，sha256 %s）" % ("OK" if ok else "WARN", path, size, digest[:16]))
        if not ok:
            print("     与入库版本指纹不一致（期望 %d 字节 / %s）——"
                  " 除非你有意替换，否则界面排版可能与预期不同。" % (EXPECTED_SIZE, EXPECTED_SHA256[:16]))
    return 0


def download(url: str, force: bool = False) -> int:
    os.makedirs(TARGET_DIR, exist_ok=True)
    if os.path.exists(TARGET_PATH) and not force:
        print("[SKIP] 已存在：%s（--force 可强制重新下载）" % TARGET_PATH)
        return check()

    print("[fetch] %s" % url)
    tmp_path = TARGET_PATH + ".part"
    try:
        with urllib.request.urlopen(url, timeout=60) as response, \
                io.open(tmp_path, "wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print("[FAIL] 下载失败：%s" % exc)
        print(manual_instructions(url))
        return 2

    size = os.path.getsize(tmp_path)
    digest = sha256_of(tmp_path)
    if size != EXPECTED_SIZE or digest != EXPECTED_SHA256:
        os.remove(tmp_path)
        print("[FAIL] 校验不通过（%d 字节 / sha256 %s）——文件已丢弃" % (size, digest[:16]))
        print("       期望 %d 字节 / %s" % (EXPECTED_SIZE, EXPECTED_SHA256[:16]))
        return 1

    os.replace(tmp_path, TARGET_PATH)
    print("[OK] 已就位：%s" % TARGET_PATH)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="下载内置中文字体（不入库的 50 MiB 资产）")
    parser.add_argument("--url", default=os.environ.get("TAVERN_ROGUE_FONT_URL", DEFAULT_URL))
    parser.add_argument("--check", action="store_true", help="只检查是否已就位")
    parser.add_argument("--force", action="store_true", help="已存在也重新下载")
    args = parser.parse_args(argv)

    if args.check:
        return check()
    return download(args.url, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
