# -*- coding: utf-8 -*-
"""
文本清洗模块 — 确保 AI 生成内容不会出现中英混排。

策略：
1. 检测：分析文本中中文字符与英文单词的比例
2. 修复：当英文混入过多时，通过翻译 API 将整体转为纯中文
3. 降级：无翻译器时，移除多余的英文单词保留中文骨架

使用示例::

    from ollama_generator import OllamaTextGenerator, BaiduCleaner
    
    gen = OllamaTextGenerator()
    cleaner = BaiduCleaner()
    
    raw = gen.generate("描述一个奇幻世界")
    clean = cleaner.purify(raw)  # 确保纯中文输出
"""

import re
import json
import time
import hashlib
import urllib.parse
import urllib.request
from typing import Optional


# ============================================================
# 语言检测
# ============================================================

# 中文字符 Unicode 范围
_CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x2F800, 0x2FA1F), # CJK Compatibility Ideographs Supplement
]

# 英文单词模式 ——  使用 lookahead/lookbehind 替代 \b
# \b 在 Python 中把 CJK 字符视为 \w，导致中英文交界处无法正确识别边界
_EN_WORD = re.compile(r'(?<![a-zA-Z])[a-zA-Z]{2,}(?![a-zA-Z])')
# 中文字符模式
_CN_CHAR = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')
# 中文标点（不视为"英文"）
_CN_PUNCT = set('，。！？；：""''（）【】《》…—～、')


def count_chinese_chars(text: str) -> int:
    """统计中文字符数"""
    return len(_CN_CHAR.findall(text))


def count_english_words(text: str) -> int:
    """统计英文单词数"""
    return len(_EN_WORD.findall(text))


def is_mixed_cn_en(text: str, cn_ratio: float = 0.1, min_en_words: int = 1) -> bool:
    """判断文本是否为中英混排。

    当文本以中文为主体但混入了英文单词时，判定为混排。
    
    Args:
        text: 待检测文本
        cn_ratio: 中文字符占总字符的最小比例（低于此值不视为中文文本）
        min_en_words: 最少英文单词数（达到此数量才视为混入）
        
    Returns:
        True 表示存在中英混排
    """
    if not text or not text.strip():
        return False
    
    cn_count = count_chinese_chars(text)
    en_count = count_english_words(text)
    
    # 无中文 → 不是中文文本混排
    if cn_count == 0:
        return False
    # 英文词不够多 → 不视为混排
    if en_count < min_en_words:
        return False
    # 中文占比太低 → 不视为中文文本
    if cn_count / max(len(text), 1) < cn_ratio:
        return False
    
    return True


def strip_english_fragments(text: str) -> str:
    """简单降级：移除英文片段，仅保留中文和标点。
    
    用于无翻译器时的应急处理。
    """
    # 保留中文字符、中文标点、数字、空格、换行
    result = []
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            result.append(ch)
        elif ch in _CN_PUNCT:
            result.append(ch)
        elif ch.isdigit():
            result.append(ch)
        elif ch in ' \n\r\t':
            result.append(ch)
        # 英文、英文标点等直接丢弃
    cleaned = ''.join(result)
    # 压缩多余空白
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    return cleaned.strip()


# ============================================================
# 百度翻译集成
# ============================================================

class BaiduTranslator:
    """百度翻译 API 封装（纯逻辑，无 GUI 依赖）"""
    
    API_URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"
    
    def __init__(self, app_id: str = "", app_key: str = "",
                 config_path: str = "baidu_translate_config.json"):
        self.app_id = app_id
        self.app_key = app_key
        self._config_path = config_path
        if not app_id or not app_key:
            self._load_config()
    
    def _load_config(self):
        """从配置文件加载 API 凭据"""
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                self.app_id = cfg.get("app_id", "")
                self.app_key = cfg.get("app_key", "")
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    
    def save_config(self, app_id: str, app_key: str):
        """保存 API 凭据到配置文件"""
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump({"app_id": app_id, "app_key": app_key},
                      f, ensure_ascii=False, indent=2)
        self.app_id = app_id
        self.app_key = app_key
    
    @property
    def is_configured(self) -> bool:
        """是否已配置 API 凭据"""
        return bool(self.app_id and self.app_key)
    
    def translate(self, text: str, from_lang: str = "auto",
                  to_lang: str = "zh") -> Optional[str]:
        """翻译文本
        
        Args:
            text: 待翻译文本
            from_lang: 源语言（auto=自动检测）
            to_lang: 目标语言（zh=中文, en=英文）
            
        Returns:
            翻译结果，失败返回 None
        """
        if not self.is_configured or not text.strip():
            return None
        
        try:
            salt = str(int(time.time()))
            sign_str = f"{self.app_id}{text}{salt}{self.app_key}"
            sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
            
            data = {
                "q": text,
                "from": from_lang,
                "to": to_lang,
                "appid": self.app_id,
                "salt": salt,
                "sign": sign,
            }
            
            req = urllib.request.Request(
                self.API_URL,
                data=urllib.parse.urlencode(data).encode("utf-8"),
                method="POST",
            )
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                
            if "trans_result" in result:
                return "".join(item["dst"] for item in result["trans_result"])
            
            # API 错误
            err_code = result.get("error_code", "unknown")
            err_msg = result.get("error_msg", str(err_code))
            print(f"[BaiduTranslator] 翻译错误 ({err_code}): {err_msg}")
            return None
            
        except Exception as e:
            print(f"[BaiduTranslator] 请求失败: {e}")
            return None


# ============================================================
# 文本清洗器
# ============================================================

class TextCleaner:
    """文本清洗器基类 — 检测并修复中英混排。
    
    子类化示例::
    
        class MyCleaner(TextCleaner):
            def _fix(self, text: str) -> Optional[str]:
                # 自定义修复逻辑
                return my_translate(text)
    """
    
    def __init__(self, cn_ratio: float = 0.1, min_en_words: int = 1):
        """
        Args:
            cn_ratio: 中文字符最小比例阈值
            min_en_words: 最少英文单词数（>=此数量才触发修复）
        """
        self.cn_ratio = cn_ratio
        self.min_en_words = min_en_words
    
    def check(self, text: str) -> bool:
        """检测文本是否为中英混排"""
        return is_mixed_cn_en(text, self.cn_ratio, self.min_en_words)
    
    def _fix(self, text: str) -> Optional[str]:
        """子类覆写：修复混排文本。返回修复后文本，失败返回 None。"""
        raise NotImplementedError("子类需实现 _fix 方法")
    
    def purify(self, text: str) -> str:
        """清洗文本：检测混排 → 修复 → 返回纯中文。
        
        Args:
            text: AI 生成的原始文本
            
        Returns:
            清洗后的纯中文文本
        """
        if not text or not text.strip():
            return text or ""
        
        if not self.check(text):
            return text  # 已经是纯中文，无需处理
        
        # 尝试修复
        fixed = self._fix(text)
        if fixed:
            return fixed
        
        # 降级：直接删除英文片段
        return strip_english_fragments(text)


class BaiduCleaner(TextCleaner):
    """基于百度翻译的文本清洗器。
    
    使用示例::
    
        # 方式1: 自动读取配置文件
        cleaner = BaiduCleaner()
        
        # 方式2: 直接传入凭据
        cleaner = BaiduCleaner(app_id="xxx", app_key="yyy")
        
        # 方式3: 不配置翻译器，仅用降级策略
        cleaner = BaiduCleaner(translator=None)
        
        clean_text = cleaner.purify(ai_output)
    """
    
    def __init__(self, translator: Optional[BaiduTranslator] = None,
                 app_id: str = "", app_key: str = "",
                 config_path: str = "baidu_translate_config.json",
                 cn_ratio: float = 0.1, min_en_words: int = 1):
        super().__init__(cn_ratio, min_en_words)
        if translator is not None:
            self._translator = translator
        else:
            self._translator = BaiduTranslator(app_id, app_key, config_path)
    
    @property
    def translator_available(self) -> bool:
        """翻译服务是否可用"""
        return self._translator.is_configured
    
    def _fix(self, text: str) -> Optional[str]:
        """通过百度翻译 auto→zh 修复混排文本"""
        if not self._translator.is_configured:
            return None
        result = self._translator.translate(text, from_lang="auto", to_lang="zh")
        if result and not result.startswith("错误") and not result.startswith("请求失败"):
            return result
        return None


# ============================================================
# 快捷工厂
# ============================================================

def create_baidu_cleaner(app_id: str = "", app_key: str = "",
                         config_path: str = "baidu_translate_config.json") -> BaiduCleaner:
    """创建百度翻译清洗器的快捷方法
    
    Args:
        app_id: 百度翻译 API App ID（留空则从配置文件读取）
        app_key: 百度翻译 API Key（留空则从配置文件读取）
        config_path: 配置文件路径
        
    Returns:
        BaiduCleaner 实例
    """
    translator = BaiduTranslator(app_id, app_key, config_path)
    return BaiduCleaner(translator=translator)


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("文本清洗测试")
    print("=" * 50)
    
    # 测试混排检测
    test_cases = [
        ("纯中文文本，没有任何英文单词。", False),
        ("This is pure English text without Chinese.", False),
        ("这段文字里混入了some English words不太好。", True),
        ("AI生成的result显示the dungeon很dark。", True),
        ("你好世界", False),
        ("Hello World", False),
    ]
    
    print("\n--- 混排检测 ---")
    for text, expected in test_cases:
        result = is_mixed_cn_en(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} [{result}] {text[:50]}...")
    
    # 测试降级清洗
    print("\n--- 降级清洗（剥离英文） ---")
    dirty = "AI生成的result显示the dungeon很dark，你需要find the exit。"
    cleaned = strip_english_fragments(dirty)
    print(f"  原始: {dirty}")
    print(f"  清洗: {cleaned}")
    
    # 测试翻译器状态
    print("\n--- 翻译器状态 ---")
    cleaner = create_baidu_cleaner()
    if cleaner.translator_available:
        print("  ✓ 百度翻译已配置")
    else:
        print("  ✗ 百度翻译未配置（降级方案：剥离英文）")
        print("    配置方法：创建 baidu_translate_config.json")
        print('    内容：{"app_id": "你的ID", "app_key": "你的Key"}')
