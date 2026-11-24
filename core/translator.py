# -*- coding: utf-8 -*-
"""翻译助手：提供外文翻译功能。

使用百度翻译API，支持多语言互译。
"""
import json
import urllib.request
import urllib.error
import urllib.parse
import hashlib
import random
from typing import Optional

# 百度翻译API配置
BAIDU_APP_ID = "20260818002668116"
BAIDU_SECRET_KEY = "4VSnzE7YKFknD6cMzlh8"


def translate_text(text: str, from_lang: str = "auto", to_lang: str = "zh") -> Optional[str]:
    """翻译文本。
    
    Args:
        text: 待翻译的文本
        from_lang: 源语言代码（auto=自动检测，en=英语，ja=日语等）
        to_lang: 目标语言代码（zh=中文，en=英语等）
    
    Returns:
        翻译后的文本，失败时返回 None
    """
    if not text or not text.strip():
        return None
    
    text = text.strip()
    
    # 使用多个翻译API备用方案
    apis = [
        # 方案1: 使用有道翻译（国内可用）
        lambda: _translate_youdao(text, from_lang, to_lang),
        # 方案2: 使用百度翻译（国内可用）
        lambda: _translate_baidu(text, from_lang, to_lang),
    ]
    
    for api_func in apis:
        try:
            result = api_func()
            if result:
                return result
        except Exception as e:
            print(f"[Translator] API失败: {e}")
            continue
    
    return None


def _translate_youdao(text: str, from_lang: str, to_lang: str) -> Optional[str]:
    """使用有道翻译API（需要配置API key）"""
    # 这里需要用户配置有道翻译的API key和secret
    # 暂时返回None，提示用户需要配置
    return None


def _translate_baidu(text: str, from_lang: str, to_lang: str) -> Optional[str]:
    """使用百度翻译API"""
    if not BAIDU_APP_ID or not BAIDU_SECRET_KEY:
        return None
    
    # 百度翻译语言代码映射
    lang_map = {
        "auto": "auto",
        "zh": "zh",
        "en": "en",
        "ja": "jp",
        "ko": "kor",
        "fr": "fra",
        "de": "de",
        "es": "spa",
    }
    
    from_lang = lang_map.get(from_lang, "auto")
    to_lang = lang_map.get(to_lang, "zh")
    
    # 生成签名
    salt = str(random.randint(32768, 65536))
    sign_str = BAIDU_APP_ID + text + salt + BAIDU_SECRET_KEY
    sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
    
    # 构造请求
    url = "http://api.fanyi.baidu.com/api/trans/vip/translate"
    params = {
        "q": text,
        "from": from_lang,
        "to": to_lang,
        "appid": BAIDU_APP_ID,
        "salt": salt,
        "sign": sign,
    }
    
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "TraeDeskPet/1.0"})
    
    with urllib.request.urlopen(req, timeout=5) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    
    if "trans_result" in result:
        return "\n".join(item["dst"] for item in result["trans_result"])
    return None


def detect_language(text: str) -> str:
    """简单检测文本语言（基于字符特征）。
    
    Args:
        text: 待检测的文本
    
    Returns:
        语言代码：'en'(英语), 'ja'(日语), 'ko'(韩语), 'zh'(中文), 'unknown'
    """
    if not text:
        return "unknown"
    
    # 统计字符类型
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in text)
    has_hiragana = any('\u3040' <= c <= '\u309f' for c in text)
    has_katakana = any('\u30a0' <= c <= '\u30ff' for c in text)
    has_hangul = any('\uac00' <= c <= '\ud7af' for c in text)
    has_latin = any('a' <= c.lower() <= 'z' for c in text)
    
    if has_hiragana or has_katakana:
        return "ja"
    if has_hangul:
        return "ko"
    if has_cjk:
        return "zh"
    if has_latin:
        return "en"
    
    return "unknown"


def translate_to_chinese(text: str) -> Optional[str]:
    """将外文翻译成中文（自动检测源语言）。
    
    Args:
        text: 待翻译的外文文本
    
    Returns:
        翻译后的中文文本，失败时返回 None
    """
    return translate_text(text, from_lang="auto", to_lang="zh")
