#!/usr/bin/env python3
"""兼容入口：综合验证现在由 `tests/` 里的 pytest 套件承担。

历史版本（2026-06）的这份脚本用的是**过期的 API 与数据**：
  · `BattleEngine(None, Hero("warrior", 1))` —— 参数语义错（第二位是 data_loader）
  · 职业名 `mage` / `ranger` —— 游戏里根本不存在（只有 warrior/rogue/cleric/wizard/warlock）
  · `_handle_turn_start(u, 1)` / `simulate_battle(..., avoid_death=False)` —— 签名对不上
  · 种族共鸣期望值 2/3 —— 与实现的「等级 = min(数量 // 2, 3)」不符
结果是它既抓不到真缺陷、也证明不了正确性（5 个 FAIL 里 4 个是脚本自己过期）。

替身（功能面 × 接任者）：

| 旧脚本的功能面 | 接任者 |
| --- | --- |
| 语法检查 | `run_tests.py`（只扫自研代码）+ `tests/test_entrypoints.py` |
| JSON 数据可解析 | `run_tests.py` + `tests/test_data_integrity.py` |
| 事件引用敌人 ID 校验 | `tests/test_data_integrity.py::test_event_battle_targets_exist` |
| 关键词逻辑（再生/护盾/连击…） | `tests/test_battle_engine.py`（全部按真实 API 重写） |
| 种族共鸣 | `tests/test_battle_engine.py::test_dragonborn_resonance_*` 等 |
| simulate_battle 全流程 | `tests/test_battle_engine.py::test_simulate_battle_*` + `tests/test_smoke_flow.py` |
| 圣物效果类型检查 | `tests/test_relic_effects.py`（按实现登记表校验，不是靠猜测） |

用法：`python test_final_verification.py`（等价于 `python run_tests.py`）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_tests  # noqa: E402 - 需要先补 sys.path


if __name__ == "__main__":
    print("[TavernRogue] test_final_verification.py 已改为兼容入口，实际验证跑 tests/ 套件。")
    sys.exit(run_tests.main([]))
