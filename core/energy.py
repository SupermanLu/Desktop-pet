# -*- coding: utf-8 -*-
"""体力值系统：随时间缓慢衰减，喂食恢复，并驱动宠物状态（饥饿/正常/开心）。

体力持久化在 config.json 的 energy / energy_ts 字段中；
程序重启时按离线时长补齐衰减，保证"隔天回来宠物真的饿了"。
"""
import time

from PySide6.QtCore import QObject, Signal, QTimer


class EnergyManager(QObject):
    changed = Signal(int)  # 体力变化后发射当前值（0-100）

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self.max = 100
        self.decay_interval = cfg.get("energy_decay_interval", 90)
        self.decay_amount = cfg.get("energy_decay_amount", 1)
        self.hungry_th = cfg.get("hungry_threshold", 30)
        self.happy_th = cfg.get("happy_threshold", 85)

        # 从配置恢复体力，并按离线时间衰减
        self.energy = max(0, min(self.max, int(cfg.get("energy", 80))))
        last = cfg.get("energy_ts", 0.0)
        if last:
            elapsed = time.time() - last
            self.energy = max(0, self.energy
                              - int(elapsed // self.decay_interval) * self.decay_amount)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(self.decay_interval * 1000))

    def _tick(self):
        self.energy = max(0, self.energy - self.decay_amount)
        self.changed.emit(self.energy)

    def feed(self, food: dict) -> int:
        """喂食并返回实际恢复量（体力已满时返回 0）。"""
        old = self.energy
        self.energy = min(self.max, self.energy + int(food.get("gain", 10)))
        self.changed.emit(self.energy)
        return self.energy - old

    def state(self) -> str:
        """根据体力返回宠物状态：happy / normal / hungry。"""
        if self.energy >= self.happy_th:
            return "happy"
        if self.energy <= self.hungry_th:
            return "hungry"
        return "normal"

    def snapshot(self):
        """把当前体力写回配置（退出时调用）。"""
        self._cfg["energy"] = self.energy
        self._cfg["energy_ts"] = time.time()
