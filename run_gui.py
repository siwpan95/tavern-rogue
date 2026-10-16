"""
TavernRogue 图形界面启动脚本（重构版）

用法：
    python run_gui.py                 # 随机种子
    python run_gui.py --seed 12345    # 固定种子（可复现 / 可分享，结算屏会显示种子）
"""
import argparse
import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 导入并运行图形界面（新架构）
from ui.app import main


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="TavernRogue - 酒馆异闻录")
    parser.add_argument("--seed", type=int, default=None,
                        help="固定随机种子（相同种子 = 相同地图与随机序列）")
    parser.add_argument("--mutator", action="append", default=None, metavar="ID",
                        help="启用自定义规则（可重复；如 one_hp / midas / ironman）")
    parser.add_argument("--list-mutators", action="store_true", help="列出全部自定义规则")
    return parser.parse_args(argv)


if __name__ == '__main__':
    args = parse_args()
    if args.list_mutators:
        from game.mutators import list_mutators
        for entry in list_mutators():
            print("%-12s [%s] %s" % (entry["id"], entry["type"], entry["description"]))
        sys.exit(0)
    main(seed=args.seed, mutators=args.mutator)
