# -*- coding: utf-8 -*-
"""宠物渲染：支持 GIF 动画；没有 GIF 时绘制内置形象。

内置形象（SKINS）：哆啦A梦。表情状态：正常(睁眼眨眼) / 开心(大亮眼+笑脸+飘爱心) / 饥饿(困眼+撇嘴)
喂食特效：弹跳 + 头顶连续冒爱心粒子
"""
import math
import os
import random

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
from PySide6.QtGui import (QMovie, QPixmap, QImage, QPainter, QColor, QBrush,
                           QPen, QPolygonF, QRadialGradient, QLinearGradient,
                           QPainterPath, QFont)
from PySide6.QtWidgets import QLabel

# ---------- 形象定义 ----------
SKINS = {
    "哆啦A梦": dict(
        body=("#8fc4ff", "#4a96ff", "#2f7af0"),
        ears="none",
        eye_color="#2a2a2a",
        blush=(255, 120, 120, 90),
        whiskers=True,
        nose="#ff3b30",
        foot="#bcd9ff",
        style="doraemon",
    ),
}


def _draw_heart(painter, cx, cy, s, alpha=255):
    """在 (cx, cy) 处画一颗心，s 控制大小，alpha 控制透明度。"""
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 90, 120, alpha))
    painter.drawEllipse(QRectF(cx - s * 0.5, cy - s * 0.55, s, s))
    painter.drawEllipse(QRectF(cx - s * 0.05, cy - s * 0.55, s, s))
    painter.drawPolygon([QPoint(int(cx - s * 0.55), int(cy + s * 0.05)),
                         QPoint(int(cx + s * 0.95), int(cy + s * 0.05)),
                         QPoint(int(cx + s * 0.2), int(cy + s * 0.95))])


def _draw_eye(painter, ex, cy, r, color, big=False, look_x=0.0, look_y=0.0):
    """画一只又大又亮、睁开的圆眼（含双层高光）。

    look_x / look_y：-1~1 的眼神方向，瞳孔与高光随之偏移，实现“转头跟随光标”。
    """
    scale = 1.15 if big else 1.0
    ew, eh = r * 0.17 * scale, r * 0.23 * scale
    y0 = cy - r * 0.42
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255, 240))
    painter.drawEllipse(QRectF(ex - ew * 1.1, y0 - eh * 1.05, ew * 2.2, eh * 2.1))
    lx = look_x * ew * 0.6
    ly = look_y * eh * 0.6
    painter.setBrush(color)
    painter.drawEllipse(QRectF(ex - ew + lx, y0 - eh + ly, ew * 2, eh * 2))
    painter.setBrush(QColor(255, 255, 255))
    painter.drawEllipse(QRectF(ex - ew * 0.55 + lx, y0 - eh * 0.6 + ly, ew * 0.75, eh * 0.75))
    painter.drawEllipse(QRectF(ex + ew * 0.2 + lx, y0 + eh * 0.25 + ly, ew * 0.4, eh * 0.4))


def _draw_closed_eye(painter, ex, cy, r, color):
    """画一条向下弯的闭眼弧线（眨眼 / 困倦）。"""
    painter.setPen(QPen(color, max(2, r * 0.07), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    painter.drawArc(QRectF(ex - r * 0.18, cy - r * 0.48, r * 0.36, r * 0.3),
                    180 * 16, 180 * 16)


def _draw_ears(painter, cx, cy, r, sk):
    """按形象在头顶绘制耳朵。"""
    kind = sk["ears"]
    if kind == "none":
        return
    outer = QColor(sk["ear_outer"])
    inner = QColor(sk["ear_inner"])
    painter.setPen(Qt.NoPen)
    if kind == "cat":
        for sx in (-1, 1):
            ex = cx + sx * r * 0.45
            painter.setBrush(outer)
            painter.drawPolygon(QPolygonF([
                QPointF(ex, cy - r * 1.5),
                QPointF(ex - r * 0.28, cy - r * 1.02),
                QPointF(ex + r * 0.28, cy - r * 1.02)]))
            painter.setBrush(inner)
            painter.drawPolygon(QPolygonF([
                QPointF(ex, cy - r * 1.36),
                QPointF(ex - r * 0.13, cy - r * 1.05),
                QPointF(ex + r * 0.13, cy - r * 1.05)]))
    elif kind == "rabbit":
        for sx in (-1, 1):
            ex = cx + sx * r * 0.4
            painter.setBrush(outer)
            painter.drawEllipse(QRectF(ex - r * 0.16, cy - r * 1.6, r * 0.32, r * 0.68))
            painter.setBrush(inner)
            painter.drawEllipse(QRectF(ex - r * 0.08, cy - r * 1.52, r * 0.16, r * 0.55))
    elif kind == "bear":
        for sx in (-1, 1):
            ex = cx + sx * r * 0.45
            painter.setBrush(outer)
            painter.drawEllipse(QRectF(ex - r * 0.22, cy - r * 1.42, r * 0.44, r * 0.44))
            painter.setBrush(inner)
            painter.drawEllipse(QRectF(ex - r * 0.11, cy - r * 1.31, r * 0.22, r * 0.22))


# ---------- 内置形象绘制 ----------

def _draw_pet(pm: QPixmap, phase: float, mirrored: bool, state: str = "normal",
              fx: float = -1.0, skin: str = "哆啦A梦",
              look_x: float = 0.0, look_y: float = 0.0):
    """在 pm 上绘制宠物。

    phase: 0~1 动画相位；state: normal/hungry/happy/sleep/yawn/hang/pet；
    fx: 喂食特效进度；skin: 形象名；look_x/look_y: 眼神跟随方向(-1~1)。
    """
    sk = SKINS.get(skin, SKINS["哆啦A梦"])
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    w, h = pm.width(), pm.height()
    cx, cy = w / 2.0, h * 0.60
    if mirrored:
        painter.translate(w, 0)
        painter.scale(-1, 1)

    r = min(w, h) * 0.36
    breath_amp = 0.02 if state in ("sleep", "hang") else 0.035  # 睡觉呼吸更缓
    breath = 1 + breath_amp * math.sin(phase * 2 * math.pi)
    jump = math.sin(fx * math.pi) * r * 0.24 if fx >= 0 else 0.0

    # 地面阴影（弹跳时影子轻微缩放）
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(0, 0, 0, 40))
    sh_w = r * (1.8 - jump / (r * 0.24) * 0.15)
    painter.drawEllipse(QRectF(cx - sh_w / 2, h - r * 0.18 + jump * 0.4,
                               sh_w, r * 0.18))

    painter.save()
    painter.translate(0, -jump)          # 喂食弹跳
    painter.translate(cx, cy)
    painter.scale(breath, breath)
    painter.translate(-cx, -cy)

    # 耳朵（先画，身体盖住根部）
    _draw_ears(painter, cx, cy, r, sk)

    # 身体（上圆下尖的蛋形）
    body = QPainterPath()
    body.moveTo(cx, cy - r * 1.1)
    body.cubicTo(cx + r * 1.05, cy - r * 1.05, cx + r * 1.05, cy + r * 0.4,
                 cx + r * 0.55, cy + r * 0.75)
    body.cubicTo(cx + r * 0.35, cy + r * 0.95, cx - r * 0.35, cy + r * 0.95,
                 cx - r * 0.55, cy + r * 0.75)
    body.cubicTo(cx - r * 1.05, cy + r * 0.4, cx - r * 1.05, cy - r * 1.05,
                 cx, cy - r * 1.1)
    b0, b1, b2 = (QColor(c) for c in sk["body"])
    grad = QLinearGradient(cx - r, cy - r, cx + r, cy + r)
    grad.setColorAt(0.0, b0)
    grad.setColorAt(0.55, b1)
    grad.setColorAt(1.0, b2)
    painter.setBrush(QBrush(grad))
    painter.drawPath(body)

    # 小肚子高光 / 哆啦A梦：白色大脸+白肚皮+红项圈+金铃铛
    if sk.get("style") == "doraemon":
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(QRectF(cx - r * 0.8, cy - r * 1.08, r * 1.6, r * 1.55))  # 大脸
        painter.drawEllipse(QRectF(cx - r * 0.55, cy + r * 0.2, r * 1.1, r * 0.9))   # 白肚皮
        painter.setBrush(QColor(255, 255, 255))
        painter.drawChord(QRectF(cx - r * 0.32, cy + r * 0.28, r * 0.64, r * 0.5),
                          0, 180 * 16)                                              # 口袋
        painter.setBrush(QColor(228, 62, 62))
        painter.drawEllipse(QRectF(cx - r * 0.42, cy + r * 0.76, r * 0.84, r * 0.16))  # 红项圈
        painter.setBrush(QColor(255, 202, 40))
        painter.drawEllipse(QRectF(cx - r * 0.1, cy + r * 0.78, r * 0.2, r * 0.2))     # 金铃铛
    else:
        painter.setBrush(QColor(255, 255, 255, 90))
        painter.drawEllipse(QRectF(cx - r * 0.4, cy - r * 0.5, r * 0.8, r * 0.75))

    # 脸颊红晕（开心时更深）
    blush = (sk["blush"][0], sk["blush"][1], sk["blush"][2],
             150 if state == "happy" else sk["blush"][3])
    painter.setBrush(QColor(*blush))
    painter.drawEllipse(QRectF(cx - r * 0.95, cy + r * 0.05, r * 0.35, r * 0.22))
    painter.drawEllipse(QRectF(cx + r * 0.6, cy + r * 0.05, r * 0.35, r * 0.22))

    eye_c = QColor(sk["eye_color"])
    if state in ("hungry", "sleep"):
        # 困倦 / 睡觉：闭眼
        for ex in (cx - r * 0.42, cx + r * 0.42):
            _draw_closed_eye(painter, ex, cy, r, eye_c)
        if state == "sleep":
            # 睡觉小嘴
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(150, 110, 80))
            painter.drawEllipse(QRectF(cx - r * 0.07, cy + r * 0.16, r * 0.14, r * 0.1))
        else:
            painter.drawArc(QRectF(cx - r * 0.12, cy + r * 0.14, r * 0.24, r * 0.18),
                            180 * 16, 180 * 16)
    elif state in ("happy", "pet"):
        # 开心 / 抚摸：大亮眼 + 笑脸 + 飘爱心
        for ex in (cx - r * 0.42, cx + r * 0.42):
            _draw_eye(painter, ex, cy, r, eye_c, big=True,
                      look_x=look_x, look_y=look_y)
        painter.drawArc(QRectF(cx - r * 0.22, cy + r * 0.02, r * 0.44, r * 0.26),
                        0, 180 * 16)
        for i in range(3):
            hy = cy - r * 1.2 - (0.22 if i == 1 else 0.08) * r \
                + math.sin(phase * 2 * math.pi + i) * r * 0.05
            hx = cx + (i - 1) * r * 0.42
            _draw_heart(painter, hx, hy, r * (0.2 if i == 1 else 0.15))
    elif state == "yawn":
        # 打哈欠：眯眼 + 张大嘴
        for ex in (cx - r * 0.42, cx + r * 0.42):
            _draw_closed_eye(painter, ex, cy, r, eye_c)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(60, 35, 20))
        painter.drawEllipse(QRectF(cx - r * 0.2, cy + r * 0.02, r * 0.4, r * 0.26))
        painter.setBrush(QColor(255, 150, 140))
        painter.drawEllipse(QRectF(cx - r * 0.2, cy + r * 0.12, r * 0.4, r * 0.13))
    elif state == "hang":
        # 挂边待机：小手抓住上边缘
        for ex in (cx - r * 0.42, cx + r * 0.42):
            _draw_eye(painter, ex, cy, r, eye_c,
                      look_x=look_x, look_y=look_y)
        painter.drawArc(QRectF(cx - r * 0.22, cy + r * 0.06, r * 0.44, r * 0.26),
                        0, 180 * 16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.drawEllipse(QRectF(cx - r * 0.98, cy - r * 1.34, r * 0.3, r * 0.3))
        painter.drawEllipse(QRectF(cx + r * 0.68, cy - r * 1.34, r * 0.3, r * 0.3))
    else:
        blink = 0.72 <= phase % 1.0 < 0.78
        for ex in (cx - r * 0.42, cx + r * 0.42):
            if blink:
                _draw_closed_eye(painter, ex, cy, r, eye_c)
            else:
                _draw_eye(painter, ex, cy, r, eye_c,
                          look_x=look_x, look_y=look_y)
        if sk.get("style") == "doraemon":
            # 哆啦A梦标志性大嘴
            painter.drawArc(QRectF(cx - r * 0.24, cy + r * 0.06, r * 0.48, r * 0.3),
                            0, 180 * 16)
        else:
            painter.drawArc(QRectF(cx - r * 0.14, cy + r * 0.1, r * 0.28, r * 0.2),
                            0, 180 * 16)

    # 鼻子与胡须（部分形象）
    if sk["nose"]:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(sk["nose"]))
        if sk.get("style") == "doraemon":
            painter.drawEllipse(QRectF(cx - r * 0.09, cy - r * 0.02, r * 0.18, r * 0.16))
        else:
            painter.drawEllipse(QRectF(cx - r * 0.07, cy + r * 0.05, r * 0.14, r * 0.12))
    if sk["whiskers"]:
        painter.setPen(QPen(QColor(120, 80, 40, 160), max(1, r * 0.03),
                            Qt.SolidLine, Qt.RoundCap))
        for sx in (-1, 1):
            wx = cx + sx * r * 0.75
            wy = cy + r * 0.18
            painter.drawLine(QPointF(wx, wy), QPointF(wx + sx * r * 0.28, wy - r * 0.06))
            painter.drawLine(QPointF(wx, wy + r * 0.08), QPointF(wx + sx * r * 0.3, wy + r * 0.1))
            painter.drawLine(QPointF(wx, wy + r * 0.16), QPointF(wx + sx * r * 0.26, wy + r * 0.26))

    painter.restore()

    # 喂食特效：爱心连续从头顶升起（不受呼吸缩放影响）
    if fx >= 0:
        for i in range(3):
            t = (fx * 1.6 + i * 0.34) % 1.0
            alpha = int(255 * (1 - t))
            hy = cy - r * 1.35 - t * r * 1.5
            hx = cx + (i - 1) * r * 0.5 \
                + math.sin(phase * 2 * math.pi + i * 2) * r * 0.06
            _draw_heart(painter, hx, hy, r * (0.15 + 0.05 * i), alpha)

    # 左右小脚（走路摆动）
    foot_swing = math.sin(phase * 2 * math.pi) * r * 0.06
    painter.setBrush(QColor(sk["foot"]))
    painter.drawEllipse(QRectF(cx - r * 0.7 + foot_swing, h - r * 0.3, r * 0.34, r * 0.18))
    painter.drawEllipse(QRectF(cx + r * 0.36 - foot_swing, h - r * 0.3, r * 0.34, r * 0.18))

    painter.end()


def pet_pixmap(size: int, mirrored: bool = False, skin: str = "哆啦A梦") -> QPixmap:
    """生成一帧宠物，供窗口与托盘图标复用。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    _draw_pet(pm, 0.0, mirrored, skin=skin)
    return pm


def _mask_erode(mask: bytearray, w: int, h: int, seal: int) -> bytearray:
    """方形腐蚀：仅当 (2*seal+1) 窗口内全为 1 时保留该像素（越界视为 0）。

    用于切断"气泡尾巴/描边缺口"这类 2*seal 像素宽的白色细缝，
    防止背景洪水填充顺着细缝渗进宠物内部的白色（脸/肚皮）。
    """
    if seal <= 0:
        return mask
    try:
        import numpy as _np
    except Exception:
        return _mask_erode_py(mask, w, h, seal)
    a = _np.frombuffer(mask, dtype=_np.uint8).reshape(h, w)
    p = _np.zeros((h + 2 * seal, w + 2 * seal), dtype=_np.uint8)
    p[seal:seal + h, seal:seal + w] = a
    out = _np.ones((h, w), dtype=_np.uint8)
    for dy in range(-seal, seal + 1):
        for dx in range(-seal, seal + 1):
            out &= p[seal + dy:seal + dy + h, seal + dx:seal + dx + w]
    return out.tobytes()


def _mask_dilate(mask: bytearray, w: int, h: int, seal: int) -> bytearray:
    """方形膨胀：窗口内任一个为 1 即为 1（越界视为 0）。"""
    if seal <= 0:
        return mask
    try:
        import numpy as _np
    except Exception:
        return _mask_dilate_py(mask, w, h, seal)
    a = _np.frombuffer(mask, dtype=_np.uint8).reshape(h, w)
    p = _np.zeros((h + 2 * seal, w + 2 * seal), dtype=_np.uint8)
    p[seal:seal + h, seal:seal + w] = a
    out = _np.zeros((h, w), dtype=_np.uint8)
    for dy in range(-seal, seal + 1):
        for dx in range(-seal, seal + 1):
            out |= p[seal + dy:seal + dy + h, seal + dx:seal + dx + w]
    return out.tobytes()


def _mask_erode_py(mask: bytearray, w: int, h: int, seal: int) -> bytearray:
    out = bytearray(w * h)
    for y in range(seal, h - seal):
        base = y * w
        for x in range(seal, w - seal):
            if not mask[base + x]:
                continue
            ok = True
            for dy in range(-seal, seal + 1):
                row = (y + dy) * w
                for dx in range(-seal, seal + 1):
                    if not mask[row + x + dx]:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                out[base + x] = 1
    return out


def _mask_dilate_py(mask: bytearray, w: int, h: int, seal: int) -> bytearray:
    if seal <= 0:
        return mask
    out = bytearray(w * h)
    for y in range(h):
        base = y * w
        y0, y1 = max(0, y - seal), min(h, y + seal + 1)
        for x in range(w):
            if not mask[base + x]:
                continue
            x0, x1 = max(0, x - seal), min(w, x + seal + 1)
            for yy in range(y0, y1):
                out[yy * w + x0:x1] = b'\x01' * (x1 - x0)
    return out


def _mask_flood_border(mask: bytearray, w: int, h: int, seal: int = 0) -> bytearray:
    """从图片四边（含距边缘 ≤ seal 的像素）洪泛填充 mask 中与边框相连的 1。

    腐蚀后背景会向内缩 seal 像素、不再贴边，因此种子需放宽到距边缘
    ≤ seal 的腐蚀像素，才能把"核心背景"完整捞出来。
    """
    from collections import deque
    seen = bytearray(w * h)
    q = deque()

    def enq(x, y):
        if 0 <= x < w and 0 <= y < h and mask[y * w + x] and not seen[y * w + x]:
            seen[y * w + x] = 1
            q.append((x, y))

    # 种子：贴边 + 距边缘 ≤ seal 的一圈
    for x in range(w):
        for y in range(0, min(seal + 1, h)):
            enq(x, y)
            enq(x, h - 1 - y)
    for y in range(h):
        for x in range(0, min(seal + 1, w)):
            enq(x, y)
            enq(w - 1 - x, y)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            enq(x + dx, y + dy)
    return seen


def strip_white_bg(pm: QPixmap, threshold: int = 230, max_dim: int = 512,
                   seal: int = 1) -> QPixmap:
    """把图片边缘的白色背景变为透明（AI 绘制图常为不透明白底）。

    做法：先对白色蒙版做腐蚀（seal 像素），切断"气泡尾巴/描边缺口"这类
    细缝，再从图片边缘洪泛出"核心背景"，膨胀回原范围后只把核心背景置为
    透明。这样既去掉了外围白底，又不会顺着细缝误删宠物内部的白色
    （脸/肚皮），避免深色桌面下"白色变黑"。

    随后还会移除右下角孤立的“豆包”等水印小碎块（见 _remove_corner_watermark）。

    超清大图先缩放到 max_dim 内做连通分析，再把处理结果平滑放大回原
    尺寸，避免逐像素处理整张 2048 大图导致的卡顿。
    """
    if pm.isNull():
        return pm
    # 缩小工作图（保持宽高比，不产生填充边）
    work = pm
    if max(pm.width(), pm.height()) > max_dim:
        work = pm.scaled(max_dim, max_dim, Qt.KeepAspectRatio,
                         Qt.SmoothTransformation)
    img = work.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    bpr = img.bytesPerLine()
    try:
        rows = [bytearray(img.scanLine(y)[:bpr]) for y in range(h)]
    except Exception:
        return pm

    def is_white(x, y):
        o = x * 4
        # 内存序：B,G,R,A（小端 ARGB32）
        return rows[y][o + 3] > 240 and rows[y][o + 2] > threshold \
            and rows[y][o + 1] > threshold and rows[y][o] > threshold

    # 四个角点都不是近白 → 无白底，无需处理
    if not any(is_white(x, y) for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))):
        # 无白底但仍可能有水印，同样做一次水印清理
        _remove_corner_watermark(rows, w, h)
        return pm

    # 白色蒙版
    white = bytearray(w * h)
    for y in range(h):
        base = y * w
        for x in range(w):
            if is_white(x, y):
                white[base + x] = 1

    # 腐蚀切断细缝 → 洪泛核心背景 → 膨胀回原范围（只把背景白置为透明）
    eroded = _mask_erode(white, w, h, seal)
    core = _mask_flood_border(eroded, w, h, seal)
    remove = _mask_dilate(core, w, h, seal)

    for y in range(h):
        row = rows[y]
        base = y * w
        for x in range(w):
            if remove[base + x] and white[base + x]:
                row[x * 4 + 3] = 0     # 置 alpha=0

    # 去白底后，清理右下角孤立的“豆包”水印碎块
    _remove_corner_watermark(rows, w, h)

    try:
        out = QImage(b"".join(bytes(r) for r in rows), w, h, bpr,
                     QImage.Format_ARGB32).copy()
    except Exception:
        return pm
    out_pm = QPixmap.fromImage(out)
    if work is not pm:
        out_pm = out_pm.scaled(pm.size(), Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
    return out_pm


def _solidify_dark_edges(pm: QPixmap, dark: int = 90, alpha_min: int = 30) -> QPixmap:
    """把深色半透明像素补成不透明（alpha→255）。

    AI 绘制图在画黑色文字/线条时常用半透明抗锯齿，白底上看不出，
    但宠物窗口背景透明、桌面为暗色主题时，这些半透明黑像素会透出
    暗色背景，看起来"黑色是透明的"。这里把深色半透明像素补实。
    """
    if pm.isNull():
        return pm
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    bpr = img.bytesPerLine()
    try:
        rows = [bytearray(img.scanLine(y)[:bpr]) for y in range(h)]
    except Exception:
        return pm
    changed = False
    for y in range(h):
        row = rows[y]
        for x in range(w):
            o = x * 4
            if row[o] < dark and row[o + 1] < dark and row[o + 2] < dark \
                    and alpha_min <= row[o + 3] < 255:
                row[o + 3] = 255
                changed = True
    if not changed:
        return pm
    try:
        out = QImage(b"".join(bytes(r) for r in rows), w, h, bpr,
                     QImage.Format_ARGB32).copy()
    except Exception:
        return pm
    return QPixmap.fromImage(out)


def _remove_corner_watermark(rows, w: int, h: int,
                             zone: float = 0.90, alpha_min: int = 12,
                             main_ratio: float = 0.05):
    """原地清理右下角孤立的水印碎块（如“豆包”右下角小字）。

    水印通常是悬浮在透明背景上、位于图片右下角的一簇小碎块；而宠物
    主体是巨大的连通块，其几何中心不会落在右下角。因此：
    - 用连通区域分析找出所有不透明块；
    - 把“中心落在右下角 zone 区域”且“面积不超过主体 5%”的块置为透明。
    """
    if w <= 0 or h <= 0:
        return
    from collections import deque
    opaque = bytearray(w * h)
    for y in range(h):
        row = rows[y]
        base = y * w
        for x in range(w):
            if row[x * 4 + 3] >= alpha_min:
                opaque[base + x] = 1
    seen = bytearray(w * h)
    largest = 0
    comps = []          # (像素列表, 质心归一化x, 质心归一化y, 面积)
    for y in range(h):
        for x in range(w):
            if seen[y * w + x] or not opaque[y * w + x]:
                continue
            q = deque([(x, y)])
            seen[y * w + x] = 1
            sx = sy = n = 0
            pixels = []
            while q:
                cx, cy = q.popleft()
                pixels.append((cx, cy))
                sx += cx; sy += cy; n += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] \
                            and opaque[ny * w + nx]:
                        seen[ny * w + nx] = 1
                        q.append((nx, ny))
            comps.append((pixels, sx / n / w, sy / n / h, n))
            if n > largest:
                largest = n
    if largest <= 0:
        return
    limit = max(64, largest * main_ratio)
    changed = False
    for pixels, cx, cy, n in comps:
        # 宠物主体（最大块）绝不清理；只清理右下角区域的孤立小块
        if n == largest:
            continue
        if cx > zone and cy > zone and n < limit:
            for px_, py_ in pixels:
                rows[py_][px_ * 4 + 3] = 0
            changed = True
    return changed


def crop_sheet_cell(sheet_path: str, row: int, col: int, target: int):
    """从 3x3 素材表按 [行,列] 裁剪单个道具/形象，去白底+裁边+缩放；失败返回 None。"""
    if not sheet_path or not os.path.isfile(sheet_path):
        return None
    sheet = QPixmap(sheet_path)
    if sheet.isNull():
        return None
    w, h = sheet.width(), sheet.height()
    cw, ch = w / 3.0, h / 3.0
    cell = sheet.copy(int(col * cw), int(row * ch), int(cw) + 1, int(ch) + 1)
    cell = strip_white_bg(cell)
    img = cell.toImage().convertToFormat(QImage.Format_ARGB32)
    iw, ih = img.width(), img.height()
    bpr = img.bytesPerLine()
    try:
        rows = [bytes(img.scanLine(y)[:bpr]) for y in range(ih)]
    except Exception:
        return None
    minx, miny, maxx, maxy = iw, ih, -1, -1
    for y in range(ih):
        rr = rows[y]
        for x in range(iw):
            if rr[x * 4 + 3] >= 12:
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
    if maxx < 0:
        return None
    pad = 6
    minx = max(0, minx - pad); miny = max(0, miny - pad)
    maxx = min(iw - 1, maxx + pad); maxy = min(ih - 1, maxy + pad)
    cropped = cell.copy(minx, miny, maxx - minx + 1, maxy - miny + 1)
    return cropped.scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)


# ---------- 宠物渲染控件 ----------

class PetRenderer(QLabel):
    """显示宠物的一帧；支持 GIF（QMovie）、内置形象动画与 AI 动作图片切换。"""

    def __init__(self, gif_path: str = "", size: int = 120, skin: str = "哆啦A梦",
                 parent=None, action_dir: str = "", action_images: dict | None = None,
                 props: dict | None = None, idle_dir: str = "",
                 idle_images: dict | None = None, emotion_keys: list | None = None):
        super().__init__(parent)
        self._pixmap = QPixmap(size, size)
        self._pixmap.fill(Qt.transparent)
        self._mirrored = False
        self._gif_path = gif_path if os.path.isfile(gif_path) else ""
        self.setFixedSize(size, size)
        self._phase = 0.0
        self._state = "normal"
        self._skin = skin if skin in SKINS else "哆啦A梦"
        self._fx = -1.0
        self._fx_timer = QTimer(self)
        self._fx_timer.timeout.connect(self._fx_step)
        self._static_pixmap = None
        self._look = (0.0, 0.0)          # 眼神跟随方向（程序绘制）
        self._zzz_phase = 0.0            # 睡觉 Zzz 动画相位
        self._zzz_timer = QTimer(self)
        self._zzz_timer.timeout.connect(self._zzz_step)
        self._emotion_keys = list(emotion_keys or [])  # 悬停情绪池（脸红/打滚/生气…）
        # ---- AI 动作图片素材 ----
        self._action_dir = action_dir or ""
        self._action_map = dict(action_images or {})
        self._action_cache = {}          # 动作 key -> 已去白底缩放的 QPixmap
        self._action_override = None     # 临时动作图（QTimer 到期后恢复）
        self._persistent_key = None      # 常驻动作 key（如睡觉）
        self._persistent_pixmap = None   # 常驻动作图
        self._work_pixmap = None         # 敲键盘工作联动图（优先级低于脸红/拖动）
        self._festival_key = ""          # 节日待机 key
        self._festival_pixmap = None     # 节日待机图（替换 idle 底图，优先级低于工作联动）
        self._reading_on = False         # 看书待机（长时间不理时安静看书）
        self._reading_pixmap = None      # 看书待机图（优先级低于节日待机）
        self._action_timer = QTimer(self)
        self._action_timer.setSingleShot(True)
        self._action_timer.timeout.connect(self.end_action)
        # ---- 小道具叠加层（爱心/闪光/感叹号/问号/零食/番茄钟） ----
        self._props = dict(props or {})   # 道具 key -> [文件名, 行, 列]
        self._prop_cache = {}            # 道具 key -> 已裁剪缩放的 QPixmap
        self._prop_override = None       # 当前显示的道具图
        self._prop_timer = QTimer(self)
        self._prop_timer.setSingleShot(True)
        self._prop_timer.timeout.connect(self.clear_prop)
        # ---- 交互形象层：脸红（悬停）/ 拖动 / 晕倒（快速拖动） ----
        self._blush_on = False           # 鼠标悬停 → 脸红
        self._blush_pixmap = None
        self._drag_on = False            # 按住拖动 → 独立形象
        self._drag_pixmap = None
        self._faint_on = False           # 快速/大范围拖动 → 晕倒
        self._faint_pixmap = None
        self._running_on = False         # 游走 → 跑步形象
        self._running_pixmap = None
        self._running_dir = None
        self._running_frames = []        # 跑步双帧：[跑步左, 跑步右]
        self._running_frame = 0          # 当前帧下标
        self._running_anim = QTimer(self)  # 双帧交替定时器
        self._running_anim.timeout.connect(self._toggle_running_frame)
        # ---- idle 眼神跟随（idle_center/left/right/up/down） ----
        self._idle_dir = idle_dir or ""
        self._idle_images = dict(idle_images or {})
        self._idle_cache = {}            # 方向 -> QPixmap
        self._idle_cur = None            # 当前显示的 idle 图
        self._idle_dir_cur = None        # 当前方向
        self._idle_target = None         # 防抖中的目标方向
        self._idle_debounce = QTimer(self)
        self._idle_debounce.setSingleShot(True)
        self._idle_debounce.timeout.connect(self._apply_idle_switch)
        self._idle_active = True          # 是否处于 idle 待命（仅此状态触发眼神跟随）
        # 启动时默认加载 center 作为基础形象
        if self._idle_dir and self._idle_images:
            pm = self._load_idle("center")
            if pm is not None:
                self._idle_cur = pm
                self._idle_dir_cur = "center"

        if self._gif_path and self._gif_path.lower().endswith(".gif"):
            self._movie = QMovie(gif_path)
            self._movie.setScaledSize(self.size())
            self._movie.frameChanged.connect(self._on_frame)
            self._movie.start()
        elif self._gif_path:
            # 静态图片：直接缩放显示，不参与程序绘制
            self._movie = None
            self._pixmap = self._load_static()
            self._static_pixmap = self._pixmap
        else:
            self._movie = None
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(60)

    def _tick(self):
        self._phase = (self._phase + 0.03) % 1.0
        self._render()

    def _load_static(self):
        """加载静态图片：先去掉白底，再缩放到控件尺寸；失败时返回空白透明图。"""
        pm = QPixmap(self._gif_path)
        if pm.isNull():
            pm = QPixmap(self.width(), self.height())
            pm.fill(Qt.transparent)
            return pm
        pm = strip_white_bg(pm)
        return pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _on_frame(self, _idx):
        if self._movie:
            self._pixmap = self._movie.currentPixmap()
        self.update()

    def _render(self):
        pm = QPixmap(self.width(), self.height())
        pm.fill(Qt.transparent)
        _draw_pet(pm, self._phase, self._mirrored, self._state, self._fx,
                  self._skin, self._look[0], self._look[1])
        self._pixmap = pm
        self.update()

    # ---------- 形象切换 ----------
    def set_skin(self, skin: str):
        if skin in SKINS and skin != self._skin:
            self._skin = skin
            if not self._gif_path:
                self._render()

    # ---------- 喂食特效：弹跳 + 爱心粒子 ----------
    def play_feed_effect(self):
        self._fx = 0.0
        self._fx_timer.start(40)

    def _fx_step(self):
        self._fx += 0.05
        if self._fx > 1.0:
            self._fx = -1.0
            self._fx_timer.stop()
            if self._movie:
                self._on_frame(0)
            elif self._static_pixmap is not None:
                self.update()
            else:
                self._render()
        elif self._gif_path:
            self.update()
        else:
            self._render()

    def set_state(self, state: str):
        """切换宠物状态：happy / normal / hungry / sleep / yawn / hang / pet。"""
        if state == self._state:
            return
        self._state = state
        # idle 眼神跟随：仅待命类状态启用（normal/hungry/happy），
        # 睡觉/挂边/打哈欠/抚摸等动作与睡眠状态禁用并回中
        want_idle = state not in ("sleep", "hang", "yawn", "pet")
        if want_idle != self._idle_active:
            self._idle_active = want_idle
            self._reset_idle_to_center()
        # 睡觉状态：开启 Zzz 气泡动画；其它状态关闭
        if state == "sleep":
            self._zzz_timer.start(140)
        else:
            self._zzz_timer.stop()
        # 图片/GIF 形象：睡觉/打哈欠状态切换为对应素材；
        # hang 状态不清除常驻图（挂边图靠 _persistent_pixmap 保持），否则 overlay 清除后挂边图会被误清
        if self.using_image:
            if state == "sleep":
                self.set_persistent_action("sleep")
            elif state == "yawn":
                self.set_persistent_action("yawn")
            elif state != "hang" and self._persistent_pixmap is not None:
                self.clear_persistent_action()
        if self._static_pixmap is not None:
            self.update()
            return  # 静态图片无状态切换（Zzz 由 paintEvent 叠加）
        if self._gif_path and self._movie:
            self._movie.setSpeed(25 if state == "sleep"
                                 else 40 if state == "hungry" else 100)
        else:
            self._timer.start(180 if state == "sleep"
                              else 140 if state == "hungry" else 60)
            self._render()

    # ---------- AI 动作图片素材 ----------
    def set_action_config(self, action_dir: str, action_images: dict | None,
                          props: dict | None = None, idle_dir: str = "",
                          idle_images: dict | None = None):
        """运行中更新动作素材目录与映射（如设置里改了形象）。"""
        self._action_dir = action_dir or ""
        self._action_map = dict(action_images or {})
        self._action_cache.clear()
        if props is not None:
            self._props = dict(props)
            self._prop_cache.clear()
        if idle_images is not None:
            self._idle_dir = idle_dir or ""
            self._idle_images = dict(idle_images)
            self._idle_cache.clear()
            if self._idle_dir and self._idle_images:
                pm = self._load_idle("center")
                self._idle_cur = pm
                self._idle_dir_cur = "center" if pm is not None else None
            else:
                self._idle_cur = None
                self._idle_dir_cur = None
        if self._persistent_pixmap is not None:
            self.set_persistent_action(self._persistent_key)  # 重载常驻动作图
        if self._work_pixmap is not None:
            self._work_pixmap = self._load_action("work")     # 重载工作联动图
        if self._festival_key:
            self._festival_pixmap = self._load_action(self._festival_key)
        self.update()

    # ---------- idle 眼神跟随 ----------
    def _load_idle(self, d: str):
        """按方向加载 idle 图片（去白底+缩放，带缓存）。"""
        if d in self._idle_cache:
            return self._idle_cache[d]
        fn = self._idle_images.get(d)
        if not fn:
            return None
        path = os.path.join(self._idle_dir, fn)
        if not os.path.isfile(path):
            return None
        pm = QPixmap(path)
        if pm.isNull():
            return None
        pm = strip_white_bg(pm)
        pm = pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._idle_cache[d] = pm
        return pm

    @staticmethod
    def _dir_from_look(lx: float, ly: float) -> str:
        """由归一化眼神方向(-1~1)推断 idle 方向：center/left/right/up/down。"""
        if abs(lx) < 0.3 and abs(ly) < 0.3:
            return "center"
        if abs(ly) >= abs(lx):
            return "up" if ly < 0 else "down"
        return "left" if lx < 0 else "right"

    def _request_idle_dir(self, d: str):
        """请求切换 idle 方向（100ms 防抖）。

        光标轮询（50ms）期间只更新目标方向、不重启防抖计时，
        否则每次轮询都会把 100ms 归零，切换永远不触发。
        """
        if not d:
            self._idle_debounce.stop()
            self._idle_target = None
            return
        if d == self._idle_dir_cur:
            self._idle_debounce.stop()
            return
        self._idle_target = d
        if not self._idle_debounce.isActive():
            self._idle_debounce.start(100)

    def _apply_idle_switch(self):
        """防抖结束：直接切换 idle 图（不做淡入淡出，避免黑影频闪/眩晕）。"""
        self._idle_debounce.stop()
        d = self._idle_target
        if not d or d == self._idle_dir_cur:
            return
        pm = self._load_idle(d)
        if pm is None:
            return
        self._idle_cur = pm
        self._idle_dir_cur = d
        self.update()

    def _reset_idle_to_center(self):
        """退出/进入 idle 状态：取消未决切换，回到 center 图。"""
        self._idle_debounce.stop()
        self._idle_target = None
        if self._idle_dir_cur != "center":
            pm = self._load_idle("center")
            if pm is not None:
                self._idle_cur = pm
                self._idle_dir_cur = "center"
        self.update()

    def _load_action(self, key: str):
        """按动作 key 加载图片（去白底并缩放，带缓存）；不存在返回 None。"""
        if key in self._action_cache:
            return self._action_cache[key]
        fn = self._action_map.get(key)
        if not fn:
            return None
        path = os.path.join(self._action_dir, fn)
        if not os.path.isfile(path):
            return None
        pm = QPixmap(path)
        if pm.isNull():
            return None
        pm = strip_white_bg(pm)
        pm = pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm = _solidify_dark_edges(pm)  # 补实深色半透明像素，避免暗色主题下黑色发虚
        self._action_cache[key] = pm
        return pm

    def play_action(self, key: str, seconds: float):
        """临时显示动作图片，seconds 秒后自动恢复基础形象。"""
        pm = self._load_action(key)
        if pm is None:
            return
        self._action_override = pm
        if self._action_timer.isActive():
            self._action_timer.stop()
        self._action_timer.start(int(seconds * 1000))
        self.update()

    def end_action(self):
        """立即结束临时动作图片，恢复基础形象。"""
        self._action_timer.stop()
        self._action_override = None
        self.update()

    def set_persistent_action(self, key: str):
        """常驻显示动作图片（如睡觉），直到 clear_persistent_action。"""
        pm = self._load_action(key)
        self._persistent_key = key
        self._persistent_pixmap = pm
        self._action_timer.stop()
        self._action_override = None
        self.update()

    def clear_persistent_action(self):
        """结束常驻动作图片。"""
        self._persistent_key = None
        self._persistent_pixmap = None
        self.update()

    def set_work(self, on: bool):
        """敲键盘工作联动：显示“敲键盘工作”素材，仅在无脸红/拖动时生效。

        独立于常驻图（sleep/hang）与临时动作，避免覆盖互动图片。
        """
        if on:
            if self._work_pixmap is not None:
                return  # 已在工作显示
            pm = self._load_action("work")
            self._work_pixmap = pm if pm is not None else self._persistent_pixmap
        else:
            if self._work_pixmap is None:
                return
            self._work_pixmap = None
        self.update()

    def set_festival_idle(self, key: str):
        """设置节日待机形象（替换静止待机图；优先级低于临时动作/睡眠/拖动/脸红/工作）。"""
        key = key or ""
        if key == self._festival_key and self._festival_pixmap is not None:
            return
        self._festival_key = key
        self._festival_pixmap = self._load_action(key) if key else None
        self.update()

    def clear_festival_idle(self):
        """恢复默认静止待机形象。"""
        self.set_festival_idle("")

    def set_reading(self, on: bool):
        """看书待机：长时间不理时把静止待机图换成“看书”，有互动自动恢复。"""
        on = bool(on)
        if on == self._reading_on:
            return
        self._reading_on = on
        self._reading_pixmap = self._load_action("reading") if on else None
        self.update()

    # ---------- 小道具叠加层 ----------
    def _load_prop(self, key: str):
        """按配置加载单个道具：素材表裁剪 或 emoji 文本渲染，带缓存。"""
        if key in self._prop_cache:
            return self._prop_cache[key]
        spec = self._props.get(key)
        if not spec:
            return None
        if isinstance(spec, str):
            # emoji 道具（如水滴 💧）
            prop = self._emoji_pixmap(spec)
            if prop is not None:
                self._prop_cache[key] = prop
            return prop
        if len(spec) == 3:
            fn, row, col = spec
            path = os.path.join(self._action_dir, fn)
            target = max(18, int(self.width() * 0.30))
            prop = crop_sheet_cell(path, row, col, target)
            if prop is not None:
                self._prop_cache[key] = prop
            return prop
        return None

    def _emoji_pixmap(self, emoji: str):
        """把 emoji 渲染成透明底小图作为道具（无现成素材时的兜底）。"""
        size = max(18, int(self.width() * 0.30))
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setPen(QColor(30, 30, 30))
        painter.setFont(QFont("Segoe UI Emoji", int(size * 0.85)))
        painter.drawText(pm.rect(), Qt.AlignCenter, emoji)
        painter.end()
        return pm

    def show_prop(self, key: str, seconds: float):
        """在宠物旁边临时叠加一个道具（爱心/闪光/…），seconds 秒后消失。"""
        pm = self._load_prop(key)
        if pm is None:
            return
        self._prop_override = pm
        if self._prop_timer.isActive():
            self._prop_timer.stop()
        self._prop_timer.start(int(seconds * 1000))
        self.update()

    def clear_prop(self):
        """立即结束道具叠加。"""
        self._prop_timer.stop()
        self._prop_override = None
        self.update()

    # ---------- 交互形象层（脸红/拖动） ----------
    def set_blush(self, on: bool):
        """鼠标悬停在宠物身上 → 从情绪池随机取一张情绪图（脸红/打滚/生气…）；
        移开 → 恢复。每次重新悬停都会换一张，让情绪更多样。"""
        on = bool(on)
        if on == self._blush_on:
            return
        self._blush_on = on
        self._blush_pixmap = self._pick_hover_emotion() if on else None
        self.update()

    def _pick_hover_emotion(self):
        """从情绪池乱序挑第一张能加载的图；无配置或全部失效时回退到脸红。"""
        keys = list(self._emotion_keys or ["blush"])
        random.shuffle(keys)
        for k in keys:
            pm = self._load_action(k)
            if pm is not None:
                return pm
        return self._load_action("blush")

    def set_drag(self, on: bool):
        """按住拖动 → 切独立形象（默认开心欢呼），松手 → 恢复。"""
        on = bool(on)
        if on == self._drag_on:
            return
        self._drag_on = on
        self._drag_pixmap = self._load_action("happy") if on else None
        self.update()

    def set_faint(self, on: bool):
        """快速/大范围拖动 → 晕倒形象（叠加在拖动形象之上），恢复 → 取消。"""
        on = bool(on)
        if on == self._faint_on:
            return
        self._faint_on = on
        self._faint_pixmap = self._load_action("faint") if on else None
        self.update()

    def set_running(self, on: bool, direction: str = "right"):
        """游走时显示跑步双帧动画：跑步左/跑步右交替，模拟双腿摆动。

        两帧都朝左，向右跑时水平镜像翻到右侧；停止游走（on=False）恢复正常形象。
        """
        on = bool(on)
        if not on:
            if not self._running_on:
                return
            self._running_on = False
            self._running_anim.stop()
            self._running_pixmap = None
            self._running_frames = []
            self._running_frame = 0
            self._running_dir = None
            self.set_mirrored(False)
            self.update()
            return
        if self._running_on and direction == self._running_dir:
            return   # 方向未变，无需重载
        self._running_on = True
        self._running_dir = direction
        f1 = self._load_action("run_left")
        f2 = self._load_action("run_right")
        if f1 is None or f2 is None:
            self._running_pixmap = None
            return
        self._running_frames = [f1, f2]
        self._running_frame = 0
        self._running_pixmap = self._running_frames[0]
        # 两帧都朝左：向右跑时镜像，向左跑保持原图
        self.set_mirrored(direction != "left")
        self._running_anim.start(200)   # 200ms 交替一帧（约 5fps 慢跑）
        self.update()

    def _toggle_running_frame(self):
        """跑步双帧定时器：在跑步左/跑步右之间交替，形成双腿摆动效果。"""
        if not self._running_frames:
            self._running_anim.stop()
            return
        self._running_frame = (self._running_frame + 1) % len(self._running_frames)
        self._running_pixmap = self._running_frames[self._running_frame]
        self.update()

    def _zzz_step(self):
        self._zzz_phase = (self._zzz_phase + 0.06) % 1.0
        self.update()

    def set_look(self, lx: float, ly: float):
        """设置眼神跟随方向（-1~1）。

        图片形象且配置了 idle 素材表 → 按方向切换 idle 眼神图片（防抖+淡入淡出）；
        程序绘制形象 → 瞳孔偏移；GIF/无 idle 素材 → 整图轻微偏移。
        """
        lx = max(-1.0, min(1.0, lx))
        ly = max(-1.0, min(1.0, ly))
        # 仅 idle 待命 + 非 GIF 形象 + 配置了 idle 素材：按方向切换眼神图片
        if self._idle_active and self._idle_images and self._idle_dir \
                and self._movie is None:
            self._request_idle_dir(self._dir_from_look(lx, ly))
            return
        if abs(lx - self._look[0]) < 0.01 and abs(ly - self._look[1]) < 0.01:
            return
        self._look = (lx, ly)
        self.update()  # 所有来源都重绘（图片靠整体偏移体现转头）
        if self._movie or self._static_pixmap is not None:
            return
        self._render()

    @property
    def using_image(self) -> bool:
        """当前是否为图片/GIF 形象（而非程序绘制）。"""
        return bool(self._gif_path or self._static_pixmap is not None)

    def set_mirrored(self, mirrored: bool):
        if mirrored != self._mirrored:
            self._mirrored = mirrored
            if self._movie:
                self._on_frame(0)
            elif self._static_pixmap is not None:
                self.update()  # 静态图片由 paintEvent 负责镜像
            else:
                self._render()

    def set_source(self, gif_path: str):
        """运行中切换形象来源。gif_path 为空则回退内置形象；支持 GIF 动画与静态图片。"""
        self._gif_path = gif_path if os.path.isfile(gif_path) else ""
        if self._movie:
            self._movie.stop()
            self._movie = None
        self._static_pixmap = None
        if self._gif_path and self._gif_path.lower().endswith(".gif"):
            self._stop_anim_timer()   # 停掉程序绘制动画，避免覆盖 GIF
            self._movie = QMovie(self._gif_path)
            self._movie.setScaledSize(self.size())
            self._movie.setSpeed(25 if self._state == "sleep"
                                 else 40 if self._state == "hungry" else 100)
            self._movie.frameChanged.connect(self._on_frame)
            self._movie.start()
        elif self._gif_path:
            # 静态图片：停掉程序绘制动画后直接显示图片
            self._stop_anim_timer()
            self._pixmap = self._load_static()
            self._static_pixmap = self._pixmap
            self.update()
        elif not hasattr(self, "_timer"):
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(180 if self._state == "sleep"
                              else 140 if self._state == "hungry" else 60)
        else:
            self._timer.start(180 if self._state == "sleep"
                              else 140 if self._state == "hungry" else 60)

    def _stop_anim_timer(self):
        t = getattr(self, "_timer", None)
        if t is not None:
            t.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if self._mirrored:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        # 形象优先级：临时动作 > 晕倒(快速拖动) > 常驻 > 拖动开心 > 脸红 > 工作 > 节日 > 跑步(游走) > 看书 > 基础
        if self._action_override is not None:
            action_pm = self._action_override
        elif self._faint_pixmap is not None:
            action_pm = self._faint_pixmap
        elif self._persistent_pixmap is not None:
            action_pm = self._persistent_pixmap
        elif self._drag_pixmap is not None:
            action_pm = self._drag_pixmap
        elif self._blush_pixmap is not None:
            action_pm = self._blush_pixmap
        elif self._work_pixmap is not None:
            action_pm = self._work_pixmap
        elif self._festival_pixmap is not None:
            action_pm = self._festival_pixmap
        elif self._running_pixmap is not None:
            action_pm = self._running_pixmap
        elif self._reading_pixmap is not None:
            action_pm = self._reading_pixmap
        else:
            action_pm = None
        if action_pm is not None:
            painter.drawPixmap(self.rect(), action_pm, action_pm.rect())
        else:
            if self._idle_cur is not None and self._movie is None:
                # idle 眼神跟随形象：直接绘制当前方向图（无淡入淡出）
                painter.drawPixmap(self.rect(), self._idle_cur,
                                   self._idle_cur.rect())
            else:
                # 基础形象：眼神偏移（图片/GIF 整体朝光标方向轻微偏移）
                lean_x, lean_y = 0, 0
                if self._look != (0.0, 0.0):
                    lean = max(3, int(self.width() * 0.05))
                    lean_x = int(self._look[0] * lean * (-1 if self._mirrored else 1))
                    lean_y = int(self._look[1] * lean * 0.6)
                painter.drawPixmap(self.rect().translated(lean_x, lean_y),
                                   self._pixmap, self._pixmap.rect())
            # GIF 模式下叠加喂食爱心
            if self._fx >= 0 and self._gif_path:
                w, h = self.width(), self.height()
                cx, cy = w / 2.0, h * 0.46
                r = min(w, h) * 0.42
                for i in range(3):
                    t = (self._fx * 1.6 + i * 0.34) % 1.0
                    alpha = int(255 * (1 - t))
                    hy = cy - r * 1.35 - t * r * 1.5
                    hx = cx + (i - 1) * r * 0.5
                    _draw_heart(painter, hx, hy, r * (0.15 + 0.05 * i), alpha)
        # 状态标记（不受镜像影响）
        painter.resetTransform()
        if self._state == "sleep":
            self._draw_zzz(painter, self._zzz_phase)
        elif self._state == "hang" and self.using_image:
            self._draw_hang_hands(painter)
        # 道具叠加层：显示在宠物右上侧（不随镜像翻转）
        if self._prop_override is not None:
            pw, ph = self._prop_override.width(), self._prop_override.height()
            px = self.width() - pw - max(4, int(self.width() * 0.06))
            py = max(2, int(self.height() * 0.05))
            painter.drawPixmap(px, py, self._prop_override)

    def _draw_zzz(self, painter, t):
        """画睡觉时缓缓升起的 Zzz。t: 0~1 动画进度。"""
        painter.setFont(QFont("Arial", max(10, int(self.width() * 0.13)),
                              QFont.Bold))
        w, h = self.width(), self.height()
        for i in range(3):
            p = (t + i * 0.33) % 1.0
            alpha = int(220 * (1 - p))
            painter.setPen(QColor(90, 130, 210, alpha))
            x = w * 0.6 + i * w * 0.07
            y = h * (0.5 - p * 0.38)
            painter.drawText(int(x), int(y), "Z")

    def _draw_hang_hands(self, painter):
        """图片/GIF 形象挂边时：在头顶画两只抓住上边缘的小手。"""
        w, h = self.width(), self.height()
        hr = max(6, int(w * 0.1))
        for cx in (int(w * 0.18), int(w * 0.78)):
            painter.setPen(QPen(QColor(150, 120, 90, 170), 2))
            painter.setBrush(QColor(255, 255, 255, 235))
            painter.drawEllipse(cx - hr // 2, 3, hr, hr)
