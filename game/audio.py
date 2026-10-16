"""音频播放：运行时只依赖 pygame，素材由 bloodmusic 离线生成。

分工（关键设计）：
  · **生成**素材是构建期的事 → `tools/gen_audio_assets.py`（需要 bloodmusic + numpy/scipy，
    全量 38 个音效约 0.2 秒，30 秒 BGM 约 0.2 秒）；
  · **播放**是运行时的事 → 本模块，只用 pygame.mixer，不引入 numpy/scipy，
    也没有 bloodmusic 的 5 秒级冷启动。

素材缺失 / mixer 起不来时**降级但出声一次**：游戏照常可玩，只是没声音。
"""
from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(REPO_ROOT, "assets", "audio")
SFX_DIR = os.path.join(AUDIO_DIR, "sfx")
BGM_DIR = os.path.join(AUDIO_DIR, "bgm")

# 场景 → BGM 文件名（由 tools/gen_audio_assets.py 按这些名字产出）
SCENE_BGM = {
    "menu": "menu.wav",
    "class_select": "menu.wav",
    "recruit": "tavern.wav",
    "map": "dungeon.wav",
    "battle": "battle_low.wav",
    "shop": "merchant.wav",
    "camp": "campfire.wav",
    "event": "event.wav",
    "treasure": "dungeon.wav",
    "reward": "menu.wav",
    "game_over": "game_over.wav",
    "victory": "credits.wav",
}

# 战斗动画事件 → 音效名（对应 bloodmusic SimpleSFX 的命名）
EVENT_SFX = {
    "attack": "attack",
    "dodge": "dodge",
    "heal": "heal",
    "death": "death",
    "shield": "shield",
    "poison": "poison",
    "frenzy": "crit",
    "buff": "level_up",
    "resurrect": "win",
    "summon": "magic",
    "boss": "boss",
    "elite": "elite",
    "gold": "gold",
}

# 需要生成的全套音效（与 bloodmusic SimpleSFX 的 38 个名字对齐）
SFX_NAMES = (
    "click", "hover", "confirm", "cancel", "error", "notification", "scroll",
    "card_play", "card_draw", "card_hover", "shuffle", "card_upgrade",
    "attack", "magic", "hit", "block", "damage", "heal", "dodge", "crit",
    "death", "player_hurt", "shield", "poison", "weak_hit",
    "level_up", "achievement", "gold", "item", "potion", "transition",
    "lose", "win", "elite", "boss",
)

# 需要生成的 BGM（scene → bloodmusic 预设名）
BGM_PRESETS = {
    "menu": "MENU_MUSIC",
    "tavern": "TAVERN_MUSIC",
    "dungeon": "DUNGEON_MUSIC",
    "battle_low": "BATTLE_LOW_MUSIC",
    "boss_fight": "BOSS_FIGHT_MUSIC",
    "merchant": "MERCHANT_MUSIC",
    "campfire": "CAMPFIRE_MUSIC",
    "event": "EVENT_MUSIC",
    "game_over": "GAME_OVER_MUSIC",
    "credits": "CREDITS_MUSIC",
}


class AudioManager:
    """极简音频管理器：加载预制素材、播放 SFX / BGM。"""

    def __init__(self, enabled: bool = True, sfx_dir: str = SFX_DIR, bgm_dir: str = BGM_DIR,
                 volume: float = 0.6):
        self.enabled = bool(enabled)
        self.sfx_dir = sfx_dir
        self.bgm_dir = bgm_dir
        self.volume = volume
        self.mixer_ready = False
        self.unavailable_reason = ""
        self._sfx_cache: dict = {}
        self._bgm_cache: dict = {}
        self._current_bgm: str | None = None
        self._warned = False

        if self.enabled:
            self._init_mixer()

    # ─── 初始化 ───────────────────────────────────

    def _init_mixer(self) -> None:
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(44100, -16, 2, 512)
                pygame.mixer.init()
            self.mixer_ready = True
        except Exception as exc:  # noqa: BLE001 - 没声卡/dummy 驱动都要能玩
            self.mixer_ready = False
            self.unavailable_reason = str(exc)
            self._warn_once("音频设备不可用（%s），游戏将静音运行" % exc)

    def _warn_once(self, message: str) -> None:
        if not self._warned:
            print("[TavernRogue] %s" % message, file=sys.stderr)
            self._warned = True

    # ─── 素材状态 ─────────────────────────────────

    def missing_assets(self) -> list:
        missing = []
        for name in SFX_NAMES:
            if not os.path.exists(os.path.join(self.sfx_dir, name + ".wav")):
                missing.append("sfx/%s.wav" % name)
        # BGM_PRESETS 的**键**就是落盘文件名（值只是 bloodmusic 的预设名）
        for stem in BGM_PRESETS:
            if not os.path.exists(os.path.join(self.bgm_dir, stem + ".wav")):
                missing.append("bgm/%s.wav" % stem)
        return missing

    # ─── 播放 ─────────────────────────────────────

    def _load_sfx(self, name: str):
        if name in self._sfx_cache:
            return self._sfx_cache[name]
        path = os.path.join(self.sfx_dir, name + ".wav")
        sound = None
        if os.path.exists(path):
            try:
                import pygame
                sound = pygame.mixer.Sound(path)
                sound.set_volume(self.volume)
            except Exception as exc:  # noqa: BLE001
                self._warn_once("音效加载失败（%s）：%s" % (name, exc))
        self._sfx_cache[name] = sound
        return sound

    def play(self, name: str) -> bool:
        """播放一个音效；素材缺失或设备不可用时返回 False（不抛错）。"""
        if not self.mixer_ready or not name:
            return False
        sound = self._load_sfx(name)
        if sound is None:
            self._warn_once("缺少音效素材 %s.wav（跑 tools/gen_audio_assets.py 生成）" % name)
            return False
        try:
            sound.play()
            return True
        except Exception:  # noqa: BLE001
            return False

    def play_event(self, event_type: str) -> bool:
        """按战斗动画事件类型播放（attack/dodge/heal/…）。"""
        return self.play(EVENT_SFX.get(event_type, ""))

    def play_bgm(self, scene_name: str, fade_ms: int = 400) -> bool:
        """按场景切换 BGM；同一首不重复起播。"""
        filename = SCENE_BGM.get(scene_name)
        if not filename:
            return False
        if not self.mixer_ready:
            return False
        if self._current_bgm == filename:
            return True

        path = os.path.join(self.bgm_dir, filename)
        if not os.path.exists(path):
            self._warn_once("缺少 BGM 素材 %s（跑 tools/gen_audio_assets.py 生成）" % filename)
            return False
        try:
            import pygame
            if filename not in self._bgm_cache:
                self._bgm_cache[filename] = pygame.mixer.Sound(path)
                self._bgm_cache[filename].set_volume(self.volume * 0.5)
            if self._current_bgm and self._current_bgm in self._bgm_cache:
                self._bgm_cache[self._current_bgm].fadeout(fade_ms)
            channel = self._bgm_cache[filename].play(loops=-1, fade_ms=fade_ms)
            self._current_bgm = filename
            return channel is not None
        except Exception as exc:  # noqa: BLE001
            self._warn_once("BGM 播放失败（%s）：%s" % (filename, exc))
            return False

    def stop(self) -> None:
        if not self.mixer_ready:
            return
        try:
            import pygame
            pygame.mixer.stop()
            self._current_bgm = None
        except Exception:  # noqa: BLE001
            pass

    def status(self) -> dict:
        """自检信息（测试与 --audio-check 用）。"""
        return {
            "enabled": self.enabled,
            "mixer_ready": self.mixer_ready,
            "reason": self.unavailable_reason,
            "missing": self.missing_assets(),
            "current_bgm": self._current_bgm,
        }
