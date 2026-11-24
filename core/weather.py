# -*- coding: utf-8 -*-
"""天气联动提醒：获取实时天气数据，根据天气状况触发桌宠提醒。

使用 uapis.cn 免费 API，支持自定义城市输入。
"""
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any


# 天气状况映射为友好的中文描述和提醒建议
WEATHER_CONDITIONS = {
    "晴": {"desc": "阳光明媚", "tip": "适合外出活动，记得防晒哦～", "mood": "happy"},
    "多云": {"desc": "云层较多", "tip": "天气不错，可以出去走走～", "mood": "neutral"},
    "阴": {"desc": "阴天", "tip": "天色较暗，注意保暖～", "mood": "neutral"},
    "小雨": {"desc": "小雨淅沥", "tip": "记得带伞哦～", "mood": "sad"},
    "中雨": {"desc": "雨势中等", "tip": "雨比较大，尽量带伞出门～", "mood": "sad"},
    "大雨": {"desc": "大雨倾盆", "tip": "雨很大，非必要不出门哦～", "mood": "sad"},
    "暴雨": {"desc": "暴雨预警", "tip": "暴雨天气，尽量待在室内～", "mood": "sad"},
    "雷阵雨": {"desc": "雷雨交加", "tip": "打雷了，注意安全～", "mood": "sad"},
    "雪": {"desc": "雪花飘飘", "tip": "下雪了，注意保暖防滑～", "mood": "happy"},
    "雾": {"desc": "雾气蒙蒙", "tip": "能见度低，出行注意安全～", "mood": "neutral"},
    "霾": {"desc": "雾霾天气", "tip": "空气质量差，记得戴口罩～", "mood": "sad"},
}

# 温度提醒阈值
TEMP_THRESHOLDS = {
    "high": 35,  # 高温提醒
    "low": 5,    # 低温提醒
}


def fetch_weather(city: str) -> Optional[Dict[str, Any]]:
    """获取指定城市的实时天气数据。
    
    Args:
        city: 城市名称，如"北京"、"上海"
    
    Returns:
        包含天气信息的字典，失败时返回 None
        格式：{
            "city": "北京",
            "weather": "晴",
            "temp": "25",
            "humidity": "60",
            "wind": "东北风3级",
            "aqi": "50",
            "update_time": "2026-09-13 10:00"
        }
    """
    if not city or not city.strip():
        return None
    
    city = city.strip()
    url = f"https://uapis.cn/api/weather?city={urllib.request.quote(city)}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TraeDeskPet/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            
        if not data or "data" not in data:
            return None
        
        weather_data = data["data"]
        return {
            "city": city,
            "weather": weather_data.get("wea", ""),
            "temp": weather_data.get("tem", ""),
            "temp_high": weather_data.get("tem1", ""),
            "temp_low": weather_data.get("tem2", ""),
            "humidity": weather_data.get("humidity", ""),
            "wind": weather_data.get("wind", ""),
            "wind_speed": weather_data.get("win_speed", ""),
            "aqi": weather_data.get("aqi", ""),
            "update_time": weather_data.get("update_time", ""),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, 
            json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[Weather] 获取天气失败: {e}")
        return None


def get_weather_reminder(weather_data: Dict[str, Any]) -> Optional[str]:
    """根据天气数据生成友好的提醒文本。
    
    Args:
        weather_data: fetch_weather 返回的天气数据
    
    Returns:
        提醒文本，不需要提醒时返回 None
    """
    if not weather_data:
        return None
    
    reminders = []
    city = weather_data.get("city", "")
    weather = weather_data.get("weather", "")
    temp_str = weather_data.get("temp", "")
    
    # 天气状况提醒
    for condition, info in WEATHER_CONDITIONS.items():
        if condition in weather:
            reminders.append(f"{city}{info['desc']}，{info['tip']}")
            break
    
    # 温度提醒
    try:
        temp = int(temp_str)
        if temp >= TEMP_THRESHOLDS["high"]:
            reminders.append(f"当前温度{temp}°C，天气炎热，注意防暑降温～")
        elif temp <= TEMP_THRESHOLDS["low"]:
            reminders.append(f"当前温度{temp}°C，天气寒冷，注意保暖哦～")
    except (ValueError, TypeError):
        pass
    
    return "\n".join(reminders) if reminders else None


def get_weather_mood(weather_data: Dict[str, Any]) -> str:
    """根据天气数据返回适合的情绪状态。
    
    Args:
        weather_data: fetch_weather 返回的天气数据
    
    Returns:
        情绪状态：'happy', 'neutral', 'sad'
    """
    if not weather_data:
        return "neutral"
    
    weather = weather_data.get("weather", "")
    for condition, info in WEATHER_CONDITIONS.items():
        if condition in weather:
            return info.get("mood", "neutral")
    
    return "neutral"
