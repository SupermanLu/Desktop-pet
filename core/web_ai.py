# -*- coding: utf-8 -*-
"""AI 网页快捷入口（半自动版）：把剪贴板内容带到指定国模 AI 网页版。

流程：桌宠按意图/选择打开对应 AI 网页，内容保留在剪贴板，用户直接粘贴（半自动）。
后续做浏览器扩展全自动（自动填入并发送）时，可在此扩展发送通道。
只收录国内可直接访问的模型/工具。
"""
import webbrowser

SITES = {
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://chat.deepseek.com/",
        "tag": "写/润色/翻译/查代码",
    },
    "kimi": {
        "name": "Kimi",
        "url": "https://kimi.com/",
        "tag": "长文/代码/搜索",
    },
    "metaso": {
        "name": "秘塔AI",
        "url": "https://metaso.cn/",
        "tag": "AI搜索",
    },
    "jimeng": {
        "name": "即梦AI",
        "url": "https://jimeng.jianying.com/",
        "tag": "画图/视频",
    },
    "kling": {
        "name": "可灵AI",
        "url": "https://klingai.kuaishou.com/",
        "tag": "画图/视频",
    },
}


def open_site(key: str) -> bool:
    """在默认浏览器打开对应 AI 网页版；成功返回 True。"""
    site = SITES.get(key)
    if not site:
        return False
    try:
        webbrowser.open(site["url"])
        return True
    except Exception:
        return False
