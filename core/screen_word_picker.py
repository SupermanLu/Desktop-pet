# -*- coding: utf-8 -*-
"""屏幕取词/划词翻译：选中外文后按快捷键，自动翻译并显示气泡。

实现方案：
1. 监听全局快捷键（Ctrl+Alt+T）
2. 按下快捷键时，模拟 Ctrl+C 复制选中文本
3. 调用翻译 API 翻译
4. 显示翻译结果气泡

这个方案不需要 OCR 依赖，更轻量实用。
"""
import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, QPoint, Signal, Qt
from PySide6.QtGui import QGuiApplication, QCursor, QKeyEvent
from PySide6.QtWidgets import QApplication


class ScreenWordPicker(QObject):
    """屏幕取词/划词翻译管理器"""
    
    word_picked = Signal(str, str, QPoint)  # (原文, 翻译, 位置)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = True
        self._shortcut = (Qt.ControlModifier | Qt.AltModifier, Qt.Key_D)  # Ctrl+Alt+D
        self._clipboard = QGuiApplication.clipboard()
        self._original_clipboard = ""  # 保存原始剪贴板内容
    
    def set_enabled(self, enabled: bool):
        """启用/禁用屏幕取词"""
        self._enabled = enabled
    
    def on_key_press(self, event: QKeyEvent):
        """键盘按下事件"""
        if not self._enabled:
            return
        
        modifiers = event.modifiers()
        key = event.key()
        
        # 检查是否按下快捷键
        if (modifiers & self._shortcut[0]) == self._shortcut[0] and key == self._shortcut[1]:
            self._pick_selected_word()
    
    def _pick_selected_word(self):
        """获取选中的文本并翻译"""
        try:
            # 保存当前剪贴板内容
            self._original_clipboard = self._clipboard.text()
            
            # 模拟 Ctrl+C 复制选中文本
            # 注意：这里需要确保焦点在正确的窗口
            from PySide6.QtGui import QKeySequence
            from PySide6.QtWidgets import QShortcut
            
            # 使用系统级快捷键模拟
            import ctypes
            from ctypes import wintypes
            
            user32 = ctypes.windll.user32
            
            # 发送 Ctrl+C 按键
            user32.keybd_event(0x11, 0, 0, 0)  # Ctrl down
            user32.keybd_event(0x43, 0, 0, 0)  # C down
            time.sleep(0.05)  # 短暂延迟
            user32.keybd_event(0x43, 0, 2, 0)  # C up
            user32.keybd_event(0x11, 0, 2, 0)  # Ctrl up
            
            # 等待剪贴板更新
            QTimer.singleShot(100, self._process_clipboard)
            
        except Exception as e:
            print(f"[ScreenWordPicker] 取词失败: {e}")
    
    def _process_clipboard(self):
        """处理剪贴板内容"""
        try:
            new_text = self._clipboard.text().strip()
            
            # 检查剪贴板是否更新
            if not new_text or new_text == self._original_clipboard:
                return
            
            # 检查是否是有效的文本（不是太长，包含字母）
            if len(new_text) > 500:
                return
            if not any(c.isalpha() for c in new_text):
                return
            
            # 检查是否包含外文（非纯中文）
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in new_text)
            has_foreign = any(c.isalpha() and ord(c) < 128 for c in new_text)
            
            if has_chinese and not has_foreign:
                # 纯中文，不翻译
                return
            
            # 翻译
            from core.translator import translate_to_chinese
            translated = translate_to_chinese(new_text)
            
            if translated:
                pos = QCursor.pos()
                self.word_picked.emit(new_text, translated, pos)
                
        except Exception as e:
            print(f"[ScreenWordPicker] 处理剪贴板失败: {e}")
