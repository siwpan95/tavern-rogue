# -*- coding: utf-8 -*-
"""
Ollama Generator — 通用 AI 文本生成 + 中英混排清洗

安装依赖::

    pip install ollama

使用方式::

    # 1. 仅生成
    from ollama_generator import OllamaTextGenerator, get_generator, is_ai_available

    gen = get_generator()
    if is_ai_available():
        result = gen.generate("描述一个奇幻世界")

    # 2. 生成 + 自动清洗中英混排
    from ollama_generator import (
        OllamaTextGenerator, BaiduCleaner, create_baidu_cleaner
    )

    gen = OllamaTextGenerator(GenerationConfig(temperature=0.5))
    cleaner = create_baidu_cleaner()  # 自动读取 baidu_translate_config.json

    raw = gen.generate("用中文描述一座魔法城堡", system_prompt="你是中文奇幻作家。")
    clean = cleaner.purify(raw)  # 确保输出不包含英文单词
    print(clean)

    # 3. 搭配地下城游戏方法（向后兼容）
    from ollama_generator import get_generator
    gen = get_generator()
    desc = gen.generate_room_description("黑暗沼泽")
"""

from .core import (
    GenerationConfig,
    AITextGenerator,
    OllamaTextGenerator,
    SYSTEM_PROMPTS,
    get_generator,
    is_ai_available,
    reset_generator,
)

from .cleaner import (
    TextCleaner,
    BaiduCleaner,
    BaiduTranslator,
    create_baidu_cleaner,
    is_mixed_cn_en,
    strip_english_fragments,
    count_chinese_chars,
    count_english_words,
)

# 版本
__version__ = "1.0.0"
__all__ = [
    # 核心
    "GenerationConfig",
    "AITextGenerator",
    "OllamaTextGenerator",
    "SYSTEM_PROMPTS",
    "get_generator",
    "is_ai_available",
    "reset_generator",
    # 清洗
    "TextCleaner",
    "BaiduCleaner",
    "BaiduTranslator",
    "create_baidu_cleaner",
    "is_mixed_cn_en",
    "strip_english_fragments",
    "count_chinese_chars",
    "count_english_words",
]
