# -*- coding: utf-8 -*-
"""
AI 文本生成 — 核心模块
支持 Ollama 本地模型 与 Deepseek API，可自动降级到本地模型。
"""

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover - requests 是惰性导入的可选依赖
    import requests

# ollama 为可选依赖，仅在调用本地模型时才需要
_ollama = None


def _get_ollama():
    """惰性导入 ollama 库"""
    global _ollama
    if _ollama is None:
        import ollama as _o
        _ollama = _o
    return _ollama


# requests 为可选依赖，仅在调用 Deepseek API 时才需要
_requests = None


def _get_requests():
    """惰性导入 requests"""
    global _requests
    if _requests is None:
        import requests as _r
        _requests = _r
    return _requests


# 全局 Session，复用 TCP 连接
_global_session = None


def _get_session() -> "requests.Session":
    """获取可复用的 requests Session（连接池）"""
    global _global_session
    if _global_session is None:
        _requests_mod = _get_requests()
        _global_session = _requests_mod.Session()
        adapter = _requests_mod.adapters.HTTPAdapter(
            pool_connections=4,
            pool_maxsize=8,
            max_retries=1,  # 由我们自己的重试逻辑处理
        )
        _global_session.mount("https://", adapter)
        _global_session.mount("http://", adapter)
    return _global_session


# ============================================================
# 配置
# ============================================================

@dataclass
class GenerationConfig:
    """生成配置
    
    后端选择：
      - backend="ollama"：使用本地 Ollama 服务
      - backend="deepseek"：使用 Deepseek API（推荐 deepseek-v4-pro / deepseek-v4-flash）
    """
    model: str = "llama3.2"       # 模型名：ollama 模型名 或 deepseek-v4-pro / deepseek-v4-flash
    backend: str = "ollama"       # "ollama" 或 "deepseek"
    temperature: float = 0.8       # 创造性（0.0-2.0）
    max_tokens: int = 150          # 最大生成 token 数
    timeout: int = 30              # 请求超时（秒）
    host: str = ""                 # Ollama 服务地址，留空用默认值
    headers: Dict[str, str] = field(default_factory=dict)  # 自定义请求头
    api_key: str = ""              # Deepseek API key（也可通过环境变量/配置文件提供）
    deepseek_base_url: str = "https://api.deepseek.com/v1"  # Deepseek API 基础地址
    fallback_to_ollama: bool = True  # Deepseek 失败时是否降级到 Ollama
    fallback_model: str = "llama3.2"  # 降级时使用的 Ollama 模型

    def __post_init__(self):
        if self.backend == "deepseek" and not self.api_key:
            self.api_key = _load_deepseek_api_key()


def _load_deepseek_api_key() -> str:
    """加载 Deepseek API key：直接配置 > 环境变量 > 配置文件"""
    # 1. 环境变量
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key

    # 2. 配置文件
    config_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "deepseek_config.json"),
        os.path.join(os.getcwd(), "deepseek_config.json"),
    ]
    for path in config_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("api_key"):
                    return data["api_key"]
        except Exception:
            continue
    return ""


# ============================================================
# 系统提示词（可自定义）
# ============================================================

SYSTEM_PROMPTS: Dict[str, str] = {
    "room": (
        "你是一个地下城冒险游戏的叙事者。"
        "擅长用生动的语言描述场景，包含视觉、听觉、嗅觉等感官细节。"
        "保持紧张刺激的氛围，使用第二人称视角。"
    ),
    "monster": (
        "你是一个地下城冒险游戏的叙事者。"
        "擅长描述怪物遭遇，创造紧张刺激的战斗氛围。"
        "用生动的语言描绘怪物的外观和行为。"
    ),
    "combat": (
        "你是一个地下城战斗系统的叙事引擎。"
        "生成简洁有力的战斗描述，包含命中效果或失手描写。"
        "保持节奏紧凑，富有画面感。"
    ),
    "story": (
        "你是一个地下城冒险游戏的故事叙述者。"
        "生成引人入胜的剧情事件，包含冒险、选择和结果。"
        "保持角色扮演的沉浸感。"
    ),
}


# ============================================================
# 核心生成器
# ============================================================

class AITextGenerator:
    """统一 AI 文本生成器 — 支持 Ollama 本地模型 和 Deepseek API
    
    使用示例::
    
        from ollama_generator import AITextGenerator, GenerationConfig
        
        # Deepseek API（推荐）
        config = GenerationConfig(
            backend="deepseek",
            model="deepseek-v4-pro",
            temperature=0.7,
        )
        gen = AITextGenerator(config)
        result = gen.generate("描述一个黑暗森林")
        
        # Ollama 本地模型
        config = GenerationConfig(backend="ollama", model="qwen2.5")
        gen = AITextGenerator(config)
        result = gen.generate("描述一个黑暗森林")
    """
    
    def __init__(self, config: Optional[GenerationConfig] = None):
        self.config = config or GenerationConfig()
        self._available: Optional[bool] = None  # 缓存可用性
    
    # ---- 可用性检查 ----
    
    @property
    def is_available(self) -> bool:
        """检查 AI 服务是否可连接（结果会缓存）"""
        if self._available is not None:
            return self._available
        
        if self.config.backend == "deepseek":
            self._available = bool(self.config.api_key)
        else:
            try:
                _get_ollama().list()
                self._available = True
            except Exception:
                self._available = False
        return self._available
    
    def refresh_availability(self) -> bool:
        """强制刷新可用性状态"""
        self._available = None
        return self.is_available
    
    # ---- 底层 API ----
    
    def _build_ollama_kwargs(self) -> Dict[str, Any]:
        """构建 ollama.chat() 的关键字参数"""
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        if self.config.host:
            kwargs["host"] = self.config.host
        if self.config.headers:
            kwargs["headers"] = self.config.headers
        return kwargs
    
    def _call_deepseek(self, messages: List[Dict[str, str]], retries: int = 3) -> Optional[str]:
        """调用 Deepseek API（带重试和连接池复用）
        
        Args:
            messages: 消息列表
            retries: 最大重试次数（仅对网络错误/5xx 重试）
        """
        if not self.config.api_key:
            print("[Deepseek] 缺少 API key，请设置 DEEPSEEK_API_KEY 环境变量或 deepseek_config.json")
            return None

        url = f"{self.config.deepseek_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.config.headers)
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        last_error = None
        for attempt in range(1, retries + 1):
            try:
                session = _get_session()
                response = session.post(
                    url, headers=headers, json=payload,
                    timeout=self.config.timeout,
                )

                # HTTP 错误但可重试（5xx / 429）
                if response.status_code >= 500 or response.status_code == 429:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    if attempt < retries:
                        wait = 2 ** attempt
                        print(f"[Deepseek] {last_error}，{wait}s 后重试 ({attempt}/{retries})...")
                        time.sleep(wait)
                        continue
                    else:
                        print(f"[Deepseek] 重试 {retries} 次后仍失败: {last_error}")
                        return None

                # 客户端错误（4xx，除 429）不重试
                if response.status_code == 401:
                    print("[Deepseek] 认证失败 (401) — API Key 可能已过期")
                    body = response.text[:300]
                    print(f"[Deepseek] 响应: {body}")
                    return None
                if response.status_code == 404:
                    print(f"[Deepseek] 模型未找到 (404): {self.config.model}")
                    print("[Deepseek] 提示: 可尝试 deepseek-chat 或 deepseek-reasoner")
                    return None
                if 400 <= response.status_code < 500:
                    last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                    print(f"[Deepseek] 请求错误: {last_error}")
                    return None

                # 2xx 成功
                response.raise_for_status()
                data = response.json()
                msg = data["choices"][0]["message"]
                # deepseek-v4-pro 等推理模型将输出放在 reasoning_content 字段
                content = (msg.get("content") or "").strip()
                if not content:
                    content = (msg.get("reasoning_content") or "").strip()
                return content if content else None

            except (_get_requests().exceptions.Timeout,
                    _get_requests().exceptions.ConnectionError) as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt < retries:
                    wait = 2 ** attempt
                    print(f"[Deepseek] {last_error}，{wait}s 后重试 ({attempt}/{retries})...")
                    time.sleep(wait)
                else:
                    print(f"[Deepseek] 重试 {retries} 次后仍失败: {last_error}")
                    print("[Deepseek] 提示: 检查网络 / 代理 / VPN 设置")

            except Exception as e:
                print(f"[Deepseek] 请求异常: {type(e).__name__}: {e}")
                return None

        return None
    
    def _call_ollama(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """调用 Ollama 本地模型"""
        if not self.is_available:
            return None
        try:
            kwargs = self._build_ollama_kwargs()
            response = _get_ollama().chat(messages=messages, **kwargs)
            content = response["message"]["content"]
            return content.strip() if content else None
        except Exception as e:
            print(f"[Ollama] 请求失败: {e}")
            return None
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """生成文本（底层方法）
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            
        Returns:
            生成的文本，失败返回 None
        """
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        return self.chat(messages)
    
    def chat(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """多轮对话生成
        
        Args:
            messages: 消息列表，每项含 role 和 content
                      [{"role": "user/assistant/system", "content": "..."}]
            
        Returns:
            助手回复文本，失败返回 None
        """
        if self.config.backend == "deepseek":
            result = self._call_deepseek(messages)
            if result:
                return result
            if self.config.fallback_to_ollama:
                print("[AI] Deepseek 不可用，降级到 Ollama 本地模型...")
                self.config.backend = "ollama"
                self.config.model = self.config.fallback_model
                self._available = None
                return self._call_ollama(messages)
            return None
        else:
            return self._call_ollama(messages)
    
    # ---- 地下城游戏方法（向后兼容） ----
    
    def generate_room_description(self, theme: str, room_type: str = "普通房间") -> str:
        """生成房间场景描述"""
        prompt = (
            f"为地下城游戏生成一个{theme}主题的{room_type}的生动描述。\n\n"
            "要求：\n"
            "- 长度适中（50-100字）\n"
            "- 包含视觉、听觉、嗅觉等感官细节\n"
            "- 氛围紧张刺激\n"
            '- 使用第二人称“你”\n\n'
            "直接输出描述，不要其他内容。"
        )
        result = self.generate(prompt, SYSTEM_PROMPTS["room"])
        return result if result else self._fallback_room(theme)
    
    def generate_monster_encounter(self, monster_name: str, theme: str, context: str = "") -> str:
        """生成怪物遭遇描述"""
        prompt = (
            f"在{theme}主题的地下城中，你遇到了{monster_name}。\n\n"
            f"{context}\n\n"
            "生成一段紧张刺激的怪物遭遇描述，包含：\n"
            "- 怪物的外观细节\n"
            "- 你的反应和感受\n"
            "- 战斗即将开始的氛围\n\n"
            "长度50-80字，第二人称。"
        )
        result = self.generate(prompt, SYSTEM_PROMPTS["monster"])
        return result if result else self._fallback_monster(monster_name, theme)
    
    def generate_combat_narration(self, action: str, attacker: str, target: str,
                                   damage: int, hit: bool, theme: str) -> str:
        """生成战斗叙事"""
        if hit:
            prompt = (
                f"{attacker}对{target}发动了{action}！\n\n"
                "生成一段精彩的战斗命中描述：\n"
                "- 命中效果（血液飞溅/击中要害等）\n"
                f"- 造成{damage}点伤害\n"
                "- 场景氛围\n"
                "- 视觉冲击\n\n"
                "40-60字，简洁有力。"
            )
        else:
            prompt = (
                f"{attacker}对{target}发动了{action}！\n\n"
                "生成一段战斗失手描述：\n"
                "- 攻击落空或被躲避\n"
                "- 紧张的氛围\n"
                "- 下一回合的悬念\n\n"
                "30-50字。"
            )
        result = self.generate(prompt, SYSTEM_PROMPTS["combat"])
        return result if result else self._fallback_combat(action, hit, damage)
    
    def generate_story_event(self, event_type: str, theme: str,
                             player_stats: Dict[str, Any]) -> str:
        """生成剧情事件描述"""
        prompt = (
            f"在{theme}地下城中发生了{event_type}事件。\n\n"
            f"玩家状态：{player_stats}\n\n"
            "生成一段引人入胜的事件描述：\n"
            "- 事件的具体发生\n"
            "- 玩家的选择或反应\n"
            "- 结果或影响\n\n"
            "60-100字，第二人称。"
        )
        result = self.generate(prompt, SYSTEM_PROMPTS["story"])
        return result if result else f"突然，{event_type}发生了！"
    
    # ---- 回退方案 ----
    
    def _fallback_room(self, theme: str) -> str:
        fallbacks = [
            f"幽暗的{theme}房间中，烛火摇曳。墙壁上爬满了不知名的藤蔓，空气中弥漫着潮湿和腐朽的气息。",
            f"你进入了一个{theme}风格的大厅。破碎的雕像散落四处，地上有奇怪的符文在微微发光。",
            f"这个{theme}房间充满了神秘感。角落里堆放着古老的遗物，似乎在诉说着过去的秘密。",
        ]
        return random.choice(fallbacks)
    
    def _fallback_monster(self, monster: str, theme: str) -> str:
        fallbacks = [
            f"一只{monster}从阴影中现身，挡住了你的去路！",
            f"{monster}发出低沉的咆哮，准备发起攻击！",
            f"在{theme}的深处，你发现了{monster}的身影。",
        ]
        return random.choice(fallbacks)
    
    def _fallback_combat(self, action: str, hit: bool, damage: int) -> str:
        if hit:
            fallbacks = [
                f"你的{action}命中了目标！造成了 {damage} 点伤害！",
                f"攻击成功！{action}造成了 {damage} 点伤害！",
                f"完美命中！{damage} 点伤害！",
            ]
        else:
            fallbacks = [
                f"你的{action}被躲开了！",
                "攻击落空！",
                "未能命中目标！",
            ]
        return random.choice(fallbacks)


# 向后兼容别名
OllamaTextGenerator = AITextGenerator


# ============================================================
# 全局单例
# ============================================================

_generator: Optional[AITextGenerator] = None


def get_generator(config: Optional[GenerationConfig] = None) -> AITextGenerator:
    """获取生成器单例（线程不安全，适用于单线程 GUI 应用）
    
    Args:
        config: 首次调用时使用的配置，后续调用忽略此参数
    """
    global _generator
    if _generator is None:
        _generator = AITextGenerator(config)
    return _generator


def is_ai_available() -> bool:
    """检查 AI 是否可用（快捷方式）"""
    return get_generator().is_available


def reset_generator() -> None:
    """重置全局单例（用于切换配置时）"""
    global _generator
    _generator = None


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    gen = get_generator()
    
    print("=" * 50)
    print("AI 文本生成测试")
    print("=" * 50)
    print(f"后端: {gen.config.backend}")
    print(f"模型: {gen.config.model}")
    
    if gen.is_available:
        print("✓ AI 服务可用")
        
        print("\n--- 通用生成 ---")
        result = gen.generate("用一句话介绍人工智能", system_prompt="你是技术科普作家。")
        print(result or "(生成失败)")
        
        print("\n--- 房间描述 ---")
        print(gen.generate_room_description("黑暗沼泽", "房间"))
        
        print("\n--- 怪物遭遇 ---")
        print(gen.generate_monster_encounter("骷髅战士", "墓穴"))
        
        print("\n--- 战斗叙事 ---")
        print(gen.generate_combat_narration("重击", "你", "哥布林", 15, True, "地牢"))
        
        print("\n--- 剧情事件 ---")
        print(gen.generate_story_event("宝藏发现", "古堡", {"level": 3}))
    else:
        print("✗ AI 服务不可用")
        if gen.config.backend == "deepseek":
            print("\n请确保已设置 Deepseek API key:")
            print("  1. 环境变量: DEEPSEEK_API_KEY")
            print("  2. 配置文件: deepseek_config.json")
        else:
            print("\n请确保已安装并启动 Ollama:")
            print("  1. 安装: https://ollama.ai/")
            print("  2. 启动服务: ollama serve")
            print("  3. 下载模型: ollama pull llama3.2")
