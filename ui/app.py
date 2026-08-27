"""
app.py — TavernRogue 图形界面主应用（重构版）

架构：
  Model  → GameManager   (ui/game_manager.py) 中央状态
  View   → Renderer      (ui/renderer.py)     共享渲染
  Control→ SceneManager  (ui/scenes/base.py)  场景调度

每个游戏界面是一个 Scene，拥有 enter / draw / handle_event / leave 标准生命周期。
不再使用阻塞式 while 循环，全部通过 SceneManager 驱动。
"""
import os
import sys
import pygame
from pygame.locals import QUIT

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.renderer import WIDTH, HEIGHT, ButtonManager, fonts
from ui.game_manager import GameManager
from ui.scenes.base import SceneManager
from game.persistence import ProgressManager


class TavernRogueApp:
    """精简的应用外壳 — 仅负责 pygame 初始化 + 主循环"""

    def __init__(self):
        pygame.init()
        fonts.ensure_init()  # 必须在 pygame.init() 之后
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("TavernRogue - 酒馆异闻录")

        self.clock = pygame.time.Clock()
        self.running = True
        self.buttons = ButtonManager()

        # 初始化 Model 层
        self.progress = ProgressManager()
        self.game = GameManager(progress_manager=self.progress)

        # 初始化 Scene 管理器
        self.scenes = SceneManager(self, self.game)
        self._register_scenes()

        # 启动主菜单
        self.scenes.switch_to('menu')

    def _register_scenes(self):
        """注册所有场景"""
        from ui.scenes.menu import MenuScene, ClassSelectScene
        from ui.scenes.recruit import RecruitScene
        from ui.scenes.map_scene import MapScene
        from ui.scenes.battle import BattleScene
        from ui.scenes.shop import ShopScene
        from ui.scenes.camp import CampScene
        from ui.scenes.event_scene import EventScene
        from ui.scenes.treasure import TreasureScene
        from ui.scenes.reward import RewardScene
        from ui.scenes.end_scenes import GameOverScene, VictoryScene

        self.scenes.register('menu', MenuScene)
        self.scenes.register('class_select', ClassSelectScene)
        self.scenes.register('recruit', RecruitScene)
        self.scenes.register('map', MapScene)
        self.scenes.register('battle', BattleScene)
        self.scenes.register('shop', ShopScene)
        self.scenes.register('camp', CampScene)
        self.scenes.register('event', EventScene)
        self.scenes.register('treasure', TreasureScene)
        self.scenes.register('reward', RewardScene)
        self.scenes.register('game_over', GameOverScene)
        self.scenes.register('victory', VictoryScene)

    def run(self):
        """主游戏循环"""
        while self.running:
            dt = self.clock.tick(60) / 1000.0

            # 处理事件（分发到当前场景）
            for event in pygame.event.get():
                self.scenes.handle_event(event)

            # 更新 + 渲染
            self.scenes.update(dt)
            self.scenes.draw()

            pygame.display.flip()

        pygame.quit()


def main():
    app = TavernRogueApp()
    app.run()
    sys.exit()


if __name__ == '__main__':
    main()
