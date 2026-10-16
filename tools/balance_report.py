#!/usr/bin/env python3
"""平衡对拍：无 UI 跑完整局，统计胜率 / 层数 / 战斗规模，支持 A/B 对照。

用法：
    python tools/balance_report.py                      # 5 职业 × 40 局，当前规则
    python tools/balance_report.py --runs 100           # 加量
    python tools/balance_report.py --ab                 # 新目标选择 vs 历史随机规则 对照
    python tools/balance_report.py --advancement 3      # 指定进阶难度
    python tools/balance_report.py --json out.json --out report.md

为什么不用 pygame：GameManager / NodeHandler 层完全无 UI 依赖，
直接驱动它们能跑得比逐帧渲染快几个数量级，且结果可复现（固定种子）。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from game.persistence import ProgressManager  # noqa: E402
from ui.game_manager import GameManager  # noqa: E402

HERO_CLASSES = ("warrior", "rogue", "cleric", "wizard", "warlock")


# ─── 单局模拟 ────────────────────────────────────────────

def _sync_to_handler(game):
    handler = game.node_handler
    handler.set_game_state(game.hero, game.hand, game.board, game.relics, game.gold)


def _sync_from_handler(game):
    handler = game.node_handler
    game.gold = handler.gold
    game.hand[:] = handler.hand
    game.board[:] = handler.board
    game.relics[:] = handler.relics


def _recruit_phase(game):
    """招募策略：买得起就买最便宜的，然后把手牌铺满场上。

    术士的血量够时用「生命分流」补足铸币差额 —— 否则测出来的术士强度是失真的
    （它的职业机制在这个口径下完全没被使用）。
    """
    game.start_recruit_turn()
    pool = getattr(game.recruit_system, "tavern_pool", [])
    for _ in range(len(pool) + 2):
        if len(game.board) >= game.MAX_BOARD:
            break
        affordable = [(index, card) for index, card in enumerate(game.recruit_system.tavern_pool)
                      if card.get("cost", 3) <= game.gold]
        if not affordable:
            # 术士：金币不够但血量够 → 生命分流买下最便宜的一张
            if _try_life_tap(game):
                continue
            if game.gold >= 1 and not game.hand:
                game.recruit_system.refresh()
                continue
            break
        index, _card = min(affordable, key=lambda item: item[1].get("cost", 3))
        if not game.recruit_system.recruit(index):
            break
        game.recruit_system.deploy_to_board(0)
    for _ in range(len(game.hand)):
        game.recruit_system.deploy_to_board(0)
    game.end_recruit_turn()


def _try_life_tap(game) -> bool:
    """术士生命分流：只在"血量安全 + 真的买得起"时使用。"""
    hero = game.hero
    if not hasattr(hero, "use_life_tap"):
        return False
    pool = getattr(game.recruit_system, "tavern_pool", [])
    if not pool:
        return False
    cheapest = min(range(len(pool)), key=lambda i: pool[i].get("cost", 3))
    cost = pool[cheapest].get("cost", 3)
    # 保留至少 6 点血做容错（保守但不过度自残：真人玩家大致也在这个区间）
    if hero.health - cost * 2 < 6:
        return False
    if not hero.can_use_life_tap(cost):
        return False
    message = game.recruit_system.use_life_tap(cheapest)
    if not message.startswith("使用生命分流"):
        return False
    game.recruit_system.deploy_to_board(0)
    return True


def _pick_node(layer):
    """节点策略：优先打怪/精英（有收益），其次营地和宝箱，最后才是商店/事件。"""
    order = {"monster": 0, "elite": 1, "camp": 2, "treasure": 3, "shop": 4, "boss": 5, "event": 6}
    pending = [node for node in layer["nodes"] if not node.get("completed")]
    if not pending:
        return None
    return sorted(pending, key=lambda n: order.get(n["type"], 9))[0]


def simulate_run(hero_class, seed, use_ai_targeting=True, advancement=0, max_steps=400):
    """跑完一局（或直到英雄阵亡）；返回统计字典。"""
    random.seed(seed)
    with tempfile.TemporaryDirectory() as tmp:
        progress = ProgressManager(save_file=os.path.join(tmp, "progress.json"))
        if advancement:
            progress.set_class_advancement(hero_class, advancement)
        game = GameManager(progress_manager=progress)
        game.new_game(hero_class)
        game.battle_engine.use_ai_targeting = use_ai_targeting

        stats = {
            "hero_class": hero_class, "seed": seed, "advancement": advancement,
            "targeting": "tree" if use_ai_targeting else "legacy",
            "victory": False, "floor": 1, "battles": 0, "battle_wins": 0,
            "nodes": 0, "hero_hp": game.hero.health, "gold": 0,
            "relics": 0, "board": 0, "steps": 0,
        }

        for step in range(max_steps):
            stats["steps"] = step
            if not game.is_hero_alive():
                break
            if game.floor > game.MAX_FLOORS:
                stats["victory"] = True
                break

            _recruit_phase(game)
            game.ensure_map()
            layer = game.get_current_layer()
            if layer is None:
                break

            # 与 UI 一致：进入条件不满足的层直接跳过（第 9 层密室需要钥匙）
            if not game.layer_accessible(layer["layer"]):
                game.map_manager.current_layer = game.map_manager._accessible_next_layer(
                    layer["layer"], game.relic_ids())
                game.floor = game.map_manager.current_layer
                continue

            node = _pick_node(layer)
            if node is None:
                game.advance_floor()
                continue

            game.map_manager.reveal_node(node["id"])
            selected = game.select_map_node(node["id"])
            if not selected:
                # 选点被拒 = 出现了上面没覆盖的情况；响亮退出而不是静默把节点标完成
                print("[balance] 警告：节点 %s 无法选择，本局提前结束" % node.get("id"))
                break
            game.current_node = selected

            _sync_to_handler(game)
            result, _logs = game.node_handler.handle_node(selected)
            _sync_from_handler(game)

            stats["nodes"] += 1
            if selected["type"] in ("monster", "elite", "boss"):
                stats["battles"] += 1
                if (result or {}).get("result") == "victory":
                    stats["battle_wins"] += 1
            game.node_handler.hero = game.hero
            if game.hero.health <= 0 and not game.is_hero_alive():
                break

            _ok, layer_done = game.complete_node(selected["id"])
            if game.is_run_won():
                stats["victory"] = True
                break
            # 注意：不能用 is_layer_completed()（MapManager 完成层时已把 current_layer 推到下一层）
            if layer_done:
                game.advance_floor()

        stats["floor"] = game.floor
        stats["hero_hp"] = game.hero.health
        stats["gold"] = game.gold
        stats["relics"] = len(game.relics)
        stats["board"] = len(game.board)
        return stats


# ─── 汇总 ────────────────────────────────────────────────

def summarize(runs):
    total = len(runs)
    if not total:
        return {}
    wins = sum(1 for run in runs if run["victory"])
    battles = sum(run["battles"] for run in runs)
    return {
        "runs": total,
        "victory_rate": wins / total,
        "avg_floor": sum(run["floor"] for run in runs) / total,
        "avg_battles": battles / total,
        "battle_win_rate": (sum(run["battle_wins"] for run in runs) / battles) if battles else 0.0,
        "avg_hero_hp": sum(run["hero_hp"] for run in runs) / total,
        "avg_relics": sum(run["relics"] for run in runs) / total,
        "avg_board": sum(run["board"] for run in runs) / total,
    }


def run_matrix(runs_per_class, advancement, use_ai_targeting, seed_base=1000):
    per_class = {}
    for class_index, hero_class in enumerate(HERO_CLASSES):
        runs = []
        for i in range(runs_per_class):
            seed = seed_base + class_index * 100000 + i
            runs.append(simulate_run(hero_class, seed,
                                     use_ai_targeting=use_ai_targeting,
                                     advancement=advancement))
        per_class[hero_class] = runs
    return per_class


def floor_histogram(runs, max_floor=9):
    """死亡层数分布 + 逐层存活率。

    用来回答"难度是坡还是墙"：如果大量局死在同一层，那一层就是墙（玩家会卡住）；
    如果分布平缓，说明曲线是连续的。
    """
    buckets = {floor: 0 for floor in range(1, max_floor + 1)}
    wins = 0
    for run in runs:
        if run["victory"]:
            wins += 1
            continue
        floor = max(1, min(int(run["floor"]), max_floor))
        buckets[floor] += 1
    total = len(runs) or 1
    reached = {floor: 0 for floor in range(1, max_floor + 2)}
    for run in runs:
        top = int(run["floor"]) if not run["victory"] else max_floor
        for floor in range(1, min(top, max_floor) + 1):
            reached[floor] += 1
    return {
        "deaths_by_floor": buckets,
        "wins": wins,
        "survival": {floor: (reached[floor] / total) for floor in range(1, max_floor + 1)},
        "reached": reached,
        "total": total,
    }


def format_floor_curve(histogram):
    """死亡层数分布的 Markdown 表。"""
    lines = ["### 难度曲线：死亡层数分布 / 逐层存活率", "",
             "| 层 | 到达率 | 存活率 | 本层阵亡 | 分布 |",
             "| --- | --- | --- | --- | --- |"]
    deaths = histogram["deaths_by_floor"]
    peak = max(deaths.values()) if deaths else 0
    for floor in sorted(deaths):
        bar = "█" * int(round(12 * deaths[floor] / peak)) if peak else ""
        lines.append("| %d | %.0f%% | %.0f%% | %d | %s |" % (
            floor, histogram["survival"][floor] * 100,
            (histogram["survival"].get(floor + 1, histogram["wins"] / histogram["total"]) * 100),
            deaths[floor], bar or "·"))
    lines.append("")
    lines.append("通关 %d / %d 局。" % (histogram["wins"], histogram["total"]))
    lines.append("")
    return "\n".join(lines)


def format_markdown(title, per_class):
    lines = ["## %s" % title, "",
             "| 职业 | 局数 | 通关率 | 平均层数 | 平均战斗数 | 战斗胜率 | 平均剩余HP | 平均宝物 | 平均场上单位 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    all_runs = []
    for hero_class in HERO_CLASSES:
        runs = per_class.get(hero_class, [])
        all_runs.extend(runs)
        stats = summarize(runs)
        if not stats:
            continue
        lines.append("| %s | %d | %.1f%% | %.2f | %.1f | %.1f%% | %.1f | %.1f | %.1f |" % (
            hero_class, stats["runs"], stats["victory_rate"] * 100, stats["avg_floor"],
            stats["avg_battles"], stats["battle_win_rate"] * 100, stats["avg_hero_hp"],
            stats["avg_relics"], stats["avg_board"]))
    overall = summarize(all_runs)
    if overall:
        lines.append("| **合计** | %d | %.1f%% | %.2f | %.1f | %.1f%% | %.1f | %.1f | %.1f |" % (
            overall["runs"], overall["victory_rate"] * 100, overall["avg_floor"],
            overall["avg_battles"], overall["battle_win_rate"] * 100, overall["avg_hero_hp"],
            overall["avg_relics"], overall["avg_board"]))
    lines.append("")
    if all_runs:
        lines.append(format_floor_curve(floor_histogram(all_runs)))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TavernRogue 平衡对拍")
    parser.add_argument("--runs", type=int, default=40, help="每个职业的局数")
    parser.add_argument("--advancement", type=int, default=0, help="进阶难度 0-5")
    parser.add_argument("--ab", action="store_true", help="额外跑一遍历史随机目标规则做对照")
    parser.add_argument("--out", help="把 Markdown 报告写到该文件")
    parser.add_argument("--json", help="把原始统计写到该文件（JSON）")
    args = parser.parse_args(argv)

    print("[balance] %d 局/职业 × %d 职业，进阶 %d" % (args.runs, len(HERO_CLASSES), args.advancement))
    tree_runs = run_matrix(args.runs, args.advancement, True)
    report = format_markdown("目标选择：决策树（当前默认）", tree_runs)

    payload = {"tree": {cls: summarize(runs) for cls, runs in tree_runs.items()}}

    if args.ab:
        legacy_runs = run_matrix(args.runs, args.advancement, False)
        report += format_markdown("目标选择：历史随机规则（对照）", legacy_runs)
        payload["legacy"] = {cls: summarize(runs) for cls, runs in legacy_runs.items()}

    print(report)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8") as handle:
            handle.write("# TavernRogue 平衡报告\n\n")
            handle.write(report)
        print("[balance] 报告已写入 %s" % args.out)
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with io.open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        print("[balance] 统计已写入 %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
