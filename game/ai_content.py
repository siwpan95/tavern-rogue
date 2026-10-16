"""
AI 内容生成 — 为 TavernRogue 提供简单 AI 接入

使用：
    from game.ai_content import AIContentGenerator

    gen = AIContentGenerator()
    if gen.is_available():
        event = gen.enhance_event(original_event)
"""
import sys
import json
import random

# 自研 AI 后端（game/ai_backend/，随仓分发）。
# 这里曾经是无条件 import 且目标目录被 .gitignore 忽略 —— 干净克隆直接
# ModuleNotFoundError，游戏连启动都做不到（2026-10-16 实测）。
# 现在：后端缺失时**出声**降级，事件文案回退到 data/events.json 原文。
AI_BACKEND_AVAILABLE = False
AI_BACKEND_ERROR = ""

try:
    from game.ai_backend import (
        AITextGenerator, GenerationConfig, is_ai_available, get_generator
    )
    AI_BACKEND_AVAILABLE = True
except ImportError as exc:  # 干净克隆或未装依赖
    AITextGenerator = None
    GenerationConfig = None

    def is_ai_available(*_args, **_kwargs):
        return False

    def get_generator(*_args, **_kwargs):
        return None

    AI_BACKEND_ERROR = str(exc)
    print(
        "[TavernRogue] AI 文案增强不可用（缺少 game.ai_backend）：%s；"
        "事件将使用 data/events.json 的原始文案。" % exc,
        file=sys.stderr,
    )


class AIContentGenerator:
    """TavernRogue 专用 AI 内容生成器"""

    def __init__(self, backend='deepseek', model='deepseek-v4-pro', temperature=0.7):
        """
        backend: 'deepseek' 或 'ollama'；默认 deepseek
        model: 模型名称；默认 deepseek-v4-pro
        """
        self._available = None
        self._gen = None
        self._backend = backend
        self._model = model
        self._temperature = temperature

    def _ensure_generator(self):
        if self._gen is not None:
            return self._gen
        try:
            cfg = GenerationConfig(
                backend=self._backend,
                model=self._model,
                temperature=self._temperature,
            )
            self._gen = AITextGenerator(cfg)
        except Exception as e:
            print(f"[AI] 初始化失败: {e}")
            self._gen = None
        return self._gen

    def is_available(self):
        """AI 是否可用（配置正确且能连上）"""
        if self._available is not None:
            return self._available
        if not AI_BACKEND_AVAILABLE:
            self._available = False
            return False
        gen = self._ensure_generator()
        if gen is None:
            self._available = False
        else:
            self._available = gen.is_available
        return self._available

    def _call_ai(self, prompt, system=None, fallback=None):
        """调用 AI，失败时返回 fallback"""
        gen = self._ensure_generator()
        if not gen or not gen.is_available:
            return fallback
        try:
            return gen.generate(prompt, system_prompt=system)
        except Exception as e:
            print(f"[AI] 生成失败: {e}")
            return fallback

    def enhance_event(self, event):
        """
        增强一个已有事件：用 AI 重写描述和选项文本，保留原有效果。
        如果 AI 不可用，原样返回。
        """
        if not self.is_available():
            return event

        prompt = self._build_event_prompt(event)
        system = (
            "你是《TavernRogue》这款中文奇幻 Roguelike 游戏的文案设计师。"
            "请用中文输出一段不超过 150 字的描述，以及 2-3 个选项，每个选项一行，"
            "格式严格为：选项名|结果文本。不要输出任何额外说明。"
        )
        raw = self._call_ai(prompt, system=system)
        if not raw:
            return event

        enhanced = self._parse_event_text(raw, event)
        return enhanced

    def generate_event(self, seed=None):
        """
        完全生成一个随机事件（包含效果）。
        目前为简单版本，返回基于模板构建的事件，AI 只负责文案。
        """
        templates = [
            {
                "effects_pool": [
                    {"heal": 5},
                    {"damage_hero": 3},
                    {"gain_gold": 5},
                    {"gain_adventurer": {"tier": 2, "random": True}},
                    {"gain_relic": {"random": True}},
                    {"coin_flip": True},
                ]
            },
            {
                "effects_pool": [
                    {"upgrade_board": {"stat": "attack", "value": 1}},
                    {"upgrade_board": {"stat": "health", "value": 2}},
                    {"purify_board": True},
                    {"enchant_board": {"keyword": "SHIELD", "all": True}},
                ]
            },
        ]
        template = random.choice(templates)
        effects = random.sample(template["effects_pool"], k=min(3, len(template["effects_pool"])))

        base = {
            "id": f"ai_event_{random.randint(10000, 99999)}",
            "name": "未知遭遇",
            "description": "你遇到了某种神秘的存在。",
            "options": []
        }
        for i, eff in enumerate(effects):
            base["options"].append({
                "text": f"选项 {i + 1}",
                "effects": eff,
                "outcome": "结果待定。"
            })

        if self.is_available():
            return self.enhance_event(base)
        return base

    def _build_event_prompt(self, event):
        """根据事件构建提示词"""
        lines = [
            "请为以下 Roguelike 游戏事件重写中文描述和选项文本。",
            "",
            f"事件名称：{event.get('name', '未知事件')}",
            f"原描述：{event.get('description', '')}",
            "",
            "选项："
        ]
        for opt in event.get('options', []):
            lines.append(f"- {opt.get('text', '')} -> {opt.get('outcome', '')}")
        lines.append("")
        lines.append("要求：")
        lines.append("1. 描述一行，不超过 150 字；")
        lines.append("2. 每个选项输出为：选项名|结果文本；")
        lines.append("3. 不要改变事件效果，只改文案；")
        lines.append("4. 不要输出任何额外说明。")
        return "\n".join(lines)

    def _parse_event_text(self, raw, original):
        """解析 AI 输出，合并到原始事件"""
        result = dict(original)
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        if not lines:
            return result

        # 第一行作为描述（如果看起来像描述而不是选项）
        first = lines[0]
        if '|' not in first and not first.startswith('选项'):
            result['description'] = first[:300]
            option_lines = lines[1:]
        else:
            option_lines = lines

        # 解析选项
        options = []
        for opt in original.get('options', []):
            options.append(dict(opt))

        for i, line in enumerate(option_lines):
            if '|' in line:
                text, outcome = line.split('|', 1)
                text = text.strip()
                outcome = outcome.strip()
                if i < len(options):
                    options[i]['text'] = text[:50] or options[i].get('text', '')
                    options[i]['outcome'] = outcome[:200] or options[i].get('outcome', '')

        result['options'] = options
        return result


# 模块级便捷函数
def create_ai_generator(backend=None, model=None, temperature=0.7):
    return AIContentGenerator(backend=backend, model=model, temperature=temperature)


def enhance_event(event, backend=None, model=None):
    gen = create_ai_generator(backend=backend, model=model)
    return gen.enhance_event(event)


if __name__ == '__main__':
    # 简单自检
    gen = AIContentGenerator()
    print(f"AI 可用: {gen.is_available()}")
    sample = {
        "id": "test",
        "name": "魔法喷泉",
        "description": "你发现了一个发光的水池。",
        "options": [
            {"text": "饮用泉水", "effects": {"heal": 5}, "outcome": "恢复了 5 点生命值。"},
            {"text": "收集泉水", "effects": {"gain_adventurer": {"tier": 2, "random": True}}, "outcome": "获得 2 星冒险者。"},
        ]
    }
    out = gen.enhance_event(sample)
    print(json.dumps(out, ensure_ascii=False, indent=2))
