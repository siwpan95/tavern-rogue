"""
Scene 基类与 SceneManager — 替代阻塞式 while 循环的场景管理架构

每个 Scene 实现标准生命周期：
  enter() → [handle_event / update / draw] × N → leave()
"""
from pygame.locals import QUIT, MOUSEMOTION, MOUSEBUTTONDOWN


class Scene:
    """场景基类 — 所有游戏界面的抽象父类"""

    def __init__(self, app, game_manager):
        self.app = app          # TavernRogueApp 实例
        self.gm = game_manager   # GameManager 实例
        self.screen = app.screen
        self.buttons = app.buttons  # ButtonManager
        self.name = self.__class__.__name__

    # ─── 生命周期 ────────────────────────────────

    def enter(self, **kwargs):
        """进入场景时调用一次，kwargs 可传递参数"""
        self.buttons.clear()

    def leave(self):
        """离开场景时调用一次"""
        self.buttons.clear()

    def handle_event(self, event):
        """处理单个 pygame 事件"""
        if event.type == QUIT:
            self.app.running = False

    def update(self, dt: float):
        """每帧更新逻辑"""
        pass

    def draw(self):
        """每帧渲染"""
        pass

    # ─── 场景切换辅助 ────────────────────────────

    def switch_to(self, scene_name: str, **kwargs):
        """切换到另一个场景"""
        self.app.scenes.switch_to(scene_name, **kwargs)

    def _after_node(self):
        """节点完成后的标准流程：检查层完成 → 招募/地图"""
        current = self.gm.current_node
        if not current:
            # 响亮失败：没有 current_node 说明调用方没走「选节点」这条路，
            # 拿 None 去索引只会抛 TypeError（旧版就是这样崩的）。
            print("[TavernRogue] 警告：没有进行中的节点，无法结算，已返回地图")
            self.switch_to('map')
            return
        ok, layer_done = self.gm.complete_node(current['id'])
        self.gm.save_run()  # 每个节点结算后自动存档（局内存档，与局外进度分目录）

        if self.gm.is_run_won():
            self.switch_to('victory')
            return
        if layer_done:
            self.gm.advance_floor()
            if self.gm.floor > self.gm.MAX_FLOORS:
                self.switch_to('victory')
            else:
                self.switch_to('recruit')
        else:
            self.switch_to('map')


class SceneManager:
    """场景管理器 — 管理场景注册、切换与生命周期"""

    def __init__(self, app, game_manager):
        self.app = app
        self.gm = game_manager
        self._scenes: dict[str, Scene] = {}
        self._current: Scene = None

    def register(self, name: str, scene_cls):
        """注册场景类（延迟实例化）"""
        self._scenes[name] = scene_cls

    def switch_to(self, name: str, **kwargs):
        """切换到指定场景"""
        if name not in self._scenes:
            raise ValueError(f"未注册的场景: {name}")

        if self._current:
            self._current.leave()

        # 每次切换创建新实例（保证状态干净）
        self._current = self._scenes[name](self.app, self.gm)
        self._current.enter(**kwargs)

        # 场景 BGM（单点接入：所有切换都走这里）
        audio = getattr(self.app, 'audio', None)
        if audio is not None:
            audio.play_bgm(name)

    @property
    def current(self) -> Scene:
        return self._current

    def handle_event(self, event):
        """分发事件到当前场景"""
        if self._current:
            # 全局鼠标处理
            if event.type == MOUSEMOTION:
                self.app.buttons.handle_motion(event.pos)
            elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                self.app.buttons.handle_click(event.pos)
            self._current.handle_event(event)

    def update(self, dt: float):
        if self._current:
            self._current.update(dt)

    def draw(self):
        if self._current:
            self._current.draw()
