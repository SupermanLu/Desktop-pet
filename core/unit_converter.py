# -*- coding: utf-8 -*-
"""单位换算：识别剪贴板中的数值+单位，自动换算。

支持长度、重量、温度、面积、体积、速度等常见单位。
"""
import re
from typing import Optional, Tuple

# 单位分组：{类别: {单位名: 相对于基准单位的换算系数}}
# 基准单位：长度=米, 重量=克, 面积=平方米, 体积=升, 速度=米/秒
UNITS = {
    "length": {
        "mm": 0.001, "毫米": 0.001,
        "cm": 0.01, "厘米": 0.01,
        "dm": 0.1, "分米": 0.1,
        "m": 1.0, "米": 1.0,
        "km": 1000.0, "千米": 1000.0, "公里": 1000.0,
        "inch": 0.0254, "in": 0.0254, "英寸": 0.0254,
        "ft": 0.3048, "feet": 0.3048, "英尺": 0.3048,
        "yd": 0.9144, "yard": 0.9144, "码": 0.9144,
        "mi": 1609.344, "mile": 1609.344, "英里": 1609.344,
        "海里": 1852.0, "nmi": 1852.0,
        "里": 500.0, "丈": 10.0 / 3,
    },
    "weight": {
        "mg": 0.001, "毫克": 0.001,
        "g": 1.0, "克": 1.0,
        "kg": 1000.0, "千克": 1000.0, "公斤": 1000.0,
        "t": 1_000_000.0, "吨": 1_000_000.0,
        "oz": 28.3495, "ounce": 28.3495, "盎司": 28.3495,
        "lb": 453.592, "pound": 453.592, "磅": 453.592,
        "斤": 500.0, "两": 50.0,
    },
    "area": {
        "mm2": 1e-6, "平方毫米": 1e-6,
        "cm2": 1e-4, "平方厘米": 1e-4,
        "m2": 1.0, "平方米": 1.0, "平米": 1.0,
        "km2": 1e6, "平方千米": 1e6, "平方公里": 1e6,
        "ha": 1e4, "公顷": 1e4,
        "亩": 666.667,
        "acre": 4046.86, "英亩": 4046.86,
        "ft2": 0.092903, "平方英尺": 0.092903,
    },
    "volume": {
        "ml": 0.001, "毫升": 0.001,
        "cl": 0.01, "厘升": 0.01,
        "l": 1.0, "L": 1.0, "升": 1.0,
        "gal": 3.78541, "gallon": 3.78541, "加仑": 3.78541,
        "qt": 0.946353, "quart": 0.946353, "夸脱": 0.946353,
        "pt": 0.473176, "pint": 0.473176, "品脱": 0.473176,
        "cup": 0.236588, "杯": 0.236588,
        "floz": 0.0295735, "液盎司": 0.0295735,
        "tbsp": 0.0147868, "汤匙": 0.0147868,
        "tsp": 0.00492892, "茶匙": 0.00492892,
    },
    "speed": {
        "m/s": 1.0, "米/秒": 1.0,
        "km/h": 1.0 / 3.6, "千米/时": 1.0 / 3.6, "公里/时": 1.0 / 3.6,
        "mph": 0.44704, "英里/时": 0.44704,
        "knot": 0.514444, "节": 0.514444,
        "ft/s": 0.3048, "英尺/秒": 0.3048,
    },
    "data": {
        "b": 1, "B": 1, "字节": 1,
        "kb": 1024, "KB": 1024,
        "mb": 1024**2, "MB": 1024**2,
        "gb": 1024**3, "GB": 1024**3,
        "tb": 1024**4, "TB": 1024**4,
    },
}

# 温度单独处理（不是线性换算）
_TEMP_UNITS = {"°C": "C", "℃": "C", "C": "C", "摄氏度": "C",
               "°F": "F", "℉": "F", "F": "F", "华氏度": "F",
               "K": "K", "开尔文": "K"}

# 构建正则：匹配 "数值+单位" 或 "数值 单位"
_ALL_UNIT_NAMES = []
for cat_units in UNITS.values():
    _ALL_UNIT_NAMES.extend(cat_units.keys())
_ALL_UNIT_NAMES.extend(_TEMP_UNITS.keys())

# 按长度排序，长单位优先匹配
_ALL_UNIT_NAMES.sort(key=len, reverse=True)
_UNIT_PATTERN = "|".join(re.escape(u) for u in _ALL_UNIT_NAMES)
_VALUE_RE = re.compile(
    rf"^(\d+(?:\.\d+)?)\s*({_UNIT_PATTERN})$", re.I)


def _find_unit_category(unit_str: str) -> Tuple[Optional[str], str]:
    """查找单位所属类别和标准化单位名。"""
    unit_lower = unit_str.lower()
    # 温度
    for k, v in _TEMP_UNITS.items():
        if unit_str == k or unit_lower == k.lower():
            return ("temp", k)
    # 其他单位
    for cat, units in UNITS.items():
        for k in units:
            if unit_lower == k.lower():
                return (cat, k)
    return (None, unit_str)


def _convert_temp(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """温度转换。"""
    from_type = _TEMP_UNITS.get(from_unit, "")
    to_type = _TEMP_UNITS.get(to_unit, "")
    if not from_type or not to_type or from_type == to_type:
        return None

    # 先转摄氏度
    if from_type == "C":
        celsius = value
    elif from_type == "F":
        celsius = (value - 32) * 5 / 9
    elif from_type == "K":
        celsius = value - 273.15
    else:
        return None

    # 再从摄氏度转目标
    if to_type == "C":
        return celsius
    elif to_type == "F":
        return celsius * 9 / 5 + 32
    elif to_type == "K":
        return celsius + 273.15
    return None


def _pick_target_unit(from_unit: str, category: str) -> str:
    """智能选择目标单位：选择更常用的等价单位。"""
    if category == "temp":
        from_type = _TEMP_UNITS.get(from_unit, "")
        # 摄氏度→华氏度，华氏度→摄氏度，开尔文→摄氏度
        if from_type == "C":
            return "°F"
        elif from_type == "F":
            return "°C"
        else:
            return "°C"

    units = UNITS.get(category, {})
    from_lower = from_unit.lower()
    # 中文单位 → 转英文等价；英文单位 → 转中文等价
    is_chinese = any('\u4e00' <= c <= '\u9fff' for c in from_unit)
    factor = units.get(from_unit, 0) or units.get(from_lower, 0)

    if is_chinese:
        # 找英文等价单位（同系数）
        for k, v in units.items():
            if abs(v - factor) < 1e-10 and not any('\u4e00' <= c <= '\u9fff' for c in k):
                return k
    else:
        # 找中文等价单位
        for k, v in units.items():
            if abs(v - factor) < 1e-10 and any('\u4e00' <= c <= '\u9fff' for c in k):
                return k

    # 找不到等价单位，选一个更合适的
    if factor < 1:
        for k, v in units.items():
            if v >= 1 and v <= factor * 1000:
                return k
    else:
        for k, v in units.items():
            if v < 1 and v >= factor / 1000:
                return k

    return ""


def parse_unit_value(text: str) -> Optional[Tuple[float, str, str]]:
    """从文本中解析数值和单位。

    Returns:
        (数值, 单位, 类别) 或 None
    """
    text = text.strip()
    if not text or len(text) > 50:
        return None

    m = _VALUE_RE.match(text)
    if not m:
        return None

    try:
        value = float(m.group(1))
    except ValueError:
        return None

    unit_str = m.group(2)
    category, norm_unit = _find_unit_category(unit_str)
    if category is None:
        return None

    return (value, norm_unit, category)


def auto_convert(text: str) -> Optional[str]:
    """自动识别数值+单位并换算。

    Returns:
        换算结果文本，无法识别时返回 None
    """
    parsed = parse_unit_value(text)
    if not parsed:
        return None

    value, from_unit, category = parsed
    target_unit = _pick_target_unit(from_unit, category)
    if not target_unit:
        return None

    if category == "temp":
        result = _convert_temp(value, from_unit, target_unit)
        if result is None:
            return None
        return f"{value}{from_unit} = {result:.1f}{target_unit}"

    units = UNITS.get(category, {})
    from_factor = units.get(from_unit, 0) or units.get(from_unit.lower(), 0)
    to_factor = units.get(target_unit, 0) or units.get(target_unit.lower(), 0)

    if not from_factor or not to_factor:
        return None

    converted = value * from_factor / to_factor

    # 格式化
    if converted >= 1000:
        return f"{value}{from_unit} = {converted:,.0f}{target_unit}"
    elif converted >= 1:
        return f"{value}{from_unit} = {converted:.2f}{target_unit}"
    else:
        return f"{value}{from_unit} = {converted:.4f}{target_unit}"
