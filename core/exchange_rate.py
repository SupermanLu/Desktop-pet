# -*- coding: utf-8 -*-
"""汇率转换：识别剪贴板中的金额，自动查询汇率并转换。

支持常见货币符号和代码，使用免费汇率API。
"""
import json
import re
import urllib.request
import urllib.error
from typing import Optional, Tuple

# 货币符号映射
CURRENCY_SYMBOLS = {
    "$": "USD", "¥": "CNY", "€": "EUR", "£": "GBP",
    "₩": "KRW", "₹": "INR", "₽": "RUB", "฿": "THB",
}

# 货币代码正则：匹配 "100USD"、"$100"、"100美元"、"100 CNY" 等
_AMOUNT_RE = re.compile(
    r"([€$£₩₹₽฿]?\s*)?(\d+(?:\.\d{1,2})?)\s*"
    r"(CNY|RMB|USD|EUR|GBP|JPY|KRW|HKD|TWD|SGD|AUD|CAD|CHF|THB|INR|RUB|"
    r"元|美元|欧元|英镑|日元|韩元|港币|台币|新加坡元|澳元|加元|瑞郎|泰铢|卢比|卢布)?",
    re.I)

# 中文货币名 → 代码
_CN_TO_CODE = {
    "元": "CNY", "人民币": "CNY", "rmb": "CNY",
    "美元": "USD", "美金": "USD",
    "欧元": "EUR",
    "英镑": "GBP",
    "日元": "JPY",
    "韩元": "KRW", "韩币": "KRW",
    "港币": "HKD",
    "台币": "TWD",
    "新加坡元": "SGD",
    "澳元": "AUD", "澳大利亚元": "AUD",
    "加元": "CAD", "加拿大元": "CAD",
    "瑞郎": "CHF", "瑞士法郎": "CHF",
    "泰铢": "THB",
    "卢比": "INR",
    "卢布": "RUB",
}

# 常用汇率缓存（避免频繁请求）
_rate_cache = {"ts": 0.0, "rates": {}}
_CACHE_TTL = 3600  # 缓存1小时


def _fetch_rates(base: str = "CNY") -> dict:
    """获取汇率数据，带缓存。"""
    import time
    now = time.time()
    if _rate_cache["rates"] and now - _rate_cache["ts"] < _CACHE_TTL:
        return _rate_cache["rates"]

    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TraeDeskPet/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("result") == "success":
            _rate_cache["rates"] = data["rates"]
            _rate_cache["ts"] = now
            return data["rates"]
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, KeyError):
        pass
    return {}


def parse_amount(text: str) -> Optional[Tuple[float, str]]:
    """从文本中解析金额和货币。

    Returns:
        (金额, 货币代码) 或 None
    """
    text = text.strip()
    if not text or len(text) > 100:
        return None

    m = _AMOUNT_RE.fullmatch(text)
    if not m:
        return None

    symbol_prefix = m.group(1) or ""
    amount_str = m.group(2)
    currency_raw = (m.group(3) or "").strip()

    try:
        amount = float(amount_str)
    except ValueError:
        return None

    # 确定货币
    if currency_raw:
        code = _CN_TO_CODE.get(currency_raw.lower(), currency_raw.upper())
    elif symbol_prefix:
        symbol = symbol_prefix.strip()
        code = CURRENCY_SYMBOLS.get(symbol, "")
    else:
        return None

    if not code or code not in ("CNY", "USD", "EUR", "GBP", "JPY", "KRW",
                                 "HKD", "TWD", "SGD", "AUD", "CAD", "CHF",
                                 "THB", "INR", "RUB"):
        return None

    return (amount, code)


def convert(amount: float, from_code: str, to_code: str = "CNY") -> Optional[str]:
    """转换金额并返回格式化结果。

    Returns:
        格式化后的转换结果字符串，失败返回 None
    """
    if from_code == to_code:
        return None

    rates = _fetch_rates(from_code)
    if not rates or to_code not in rates:
        return None

    converted = amount * rates[to_code]

    # 格式化：日元/韩元/泰铢/卢比/卢布不保留小数
    if to_code in ("JPY", "KRW", "THB", "INR", "RUB"):
        return f"{amount:.2f} {from_code} = {converted:,.0f} {to_code}"
    return f"{amount:.2f} {from_code} = {converted:,.2f} {to_code}"


def auto_convert(text: str) -> Optional[str]:
    """自动识别金额并转换（外币→人民币，人民币→美元）。

    Returns:
        转换结果文本，无法识别时返回 None
    """
    parsed = parse_amount(text)
    if not parsed:
        return None

    amount, code = parsed
    # 外币转人民币，人民币转美元
    target = "CNY" if code != "CNY" else "USD"
    return convert(amount, code, target)
