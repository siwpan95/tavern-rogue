"""
TavernRogue 图形界面启动脚本（重构版）
"""
import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 导入并运行图形界面（新架构）
from ui.app import main

if __name__ == '__main__':
    main()
