# -*- coding: utf-8 -*-
"""温暖奶油风主题（与聊天窗/设置页统一）色板与通用样式（QSS）。

整体走"米白底 + 暖棕文字"的柔和路线，不再大范围使用蓝色：
- 卡片暖白底 #fffdf8 + 暖米边框 #e6d7b0
- 标题/正文用暖棕 #5a3a15，正文不突兀、不刺眼
- 按钮用浅奶油底 + 棕褐字，主按钮用暖橙棕 #c07a2d
- 仅"关闭/危险"保留一点红，克制点缀
说明：为兼容既有代码，变量名仍沿用 blue/blue_dark 等旧键名，值已全部替换为暖色。
"""

DORA = {
    "blue": "#c07a2d",          # 主强调（暖橙棕，原为蓝）
    "blue_dark": "#5a3a15",     # 深棕褐（标题/正文，原为深蓝）
    "blue_light": "#f7ecd7",    # 浅奶油（按钮底色，原为淡蓝）
    "blue_border": "#e6d7b0",   # 暖米边框（原为淡蓝）
    "red": "#d9534f",           # 危险/关闭
    "yellow": "#f2c76e",        # 点缀
    "white": "#fffdf8",         # 卡片底（暖白，原为纯白）
    "ink": "#4a3a22",           # 正文深色
    "gray": "#8a7a62",          # 次要文字
    "brown": "#5a3a15",
}


def card_ss(radius: int = 14) -> str:
    """卡片/弹窗通用样式：暖白底 + 暖米边框 + 奶油按钮。"""
    return f"""
QFrame#card {{ background: {DORA['white']};
               border: 1px solid {DORA['blue_border']}; border-radius: {radius}px; }}
QLabel#ttl {{ color: {DORA['blue_dark']}; font-size: 14px; font-weight: bold; }}
QLabel#hint {{ color: {DORA['gray']}; font-size: 11px; }}
QLabel#big {{ color: {DORA['blue_dark']}; font-size: 18px; font-weight: bold; }}
QPushButton {{ background: {DORA['blue_light']}; color: {DORA['blue_dark']};
              border: 1px solid {DORA['blue_border']}; border-radius: 8px;
              padding: 4px 10px; font-size: 12px; }}
QPushButton:hover {{ background: #f0e3c6; }}
QPushButton:pressed {{ background: #eadab6; }}
QPushButton#close {{ background: transparent; border: none; color: {DORA['gray']};
                    font-size: 13px; padding: 0; }}
QPushButton#close:hover {{ color: {DORA['red']}; }}
QPushButton#primary {{ background: {DORA['blue']}; color: white;
                      border-color: {DORA['blue']}; }}
QPushButton#primary:hover {{ background: #a7681f; }}
QPushButton#danger {{ background: {DORA['red']}; color: white;
                     border-color: {DORA['red']}; }}
QPushButton#danger:hover {{ background: #c13f3a; }}
QLineEdit {{ background: {DORA['white']}; color: {DORA['ink']};
             border: 1px solid {DORA['blue_border']}; border-radius: 8px;
             padding: 4px 8px; font-size: 12px; }}
QTextEdit {{ background: {DORA['white']}; color: {DORA['ink']};
             border: 1px solid {DORA['blue_border']}; border-radius: 8px;
             font-size: 13px; }}
QListWidget {{ background: {DORA['white']}; color: {DORA['ink']};
               border: 1px solid {DORA['blue_border']}; border-radius: 8px;
               font-size: 12px; }}
QComboBox {{ background: {DORA['white']}; color: {DORA['ink']};
             border: 1px solid {DORA['blue_border']}; border-radius: 8px;
             padding: 3px 8px; font-size: 12px; }}
QComboBox QAbstractItemView {{ background: {DORA['white']}; color: {DORA['ink']};
    selection-background-color: {DORA['blue_light']};
    selection-color: {DORA['blue_dark']}; }}
"""
