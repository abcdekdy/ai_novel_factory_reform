"""
轻量信号/槽实现 —— 替代 PyQt6 的 QObject + pyqtSignal
=======================================================
本项目是**无界面的 FastAPI 服务端**，此前引入 Qt（一个 GUI 框架）只为把信号当
事件总线用，代价是打包时要拖进上百 MB 的 Qt6 运行时。这里用最小实现替代。

相比 pyqtSignal 的差异（本项目的既有用法均不涉及）：
  - 不做线程亲和：Qt 会跨线程排队投递，这里 emit 时同步调用回调。项目里所有
    emit 都来自 worker 线程，回调本身只做「转发布到 EventBroker」，无需排队。
  - 不在接收者销毁时自动断开；需要时显式 `disconnect()`。
  - 信号是**实例属性**（见 BaseAgent.__init__），不是类属性——类属性会让所有
    实例共享同一份回调列表，导致章与章之间日志串台。

原 `_headless.py`（起后台 Qt 事件循环让 pyqtSignal 可用）已随之删除。
"""

import threading
import traceback


class Signal:
    """极简信号：维护回调列表，emit 时同步调用全部回调。

    线程安全：connect/disconnect 加锁，emit 时先在锁内取快照再调用，
    因此回调内部再次 connect/emit 不会死锁，也不会边遍历边改动列表。
    """

    __slots__ = ("_callbacks", "_lock")

    def __init__(self):
        self._callbacks = []
        self._lock = threading.RLock()

    def connect(self, callback):
        """注册回调。返回回调本身，便于当作装饰器使用。"""
        with self._lock:
            self._callbacks.append(callback)
        return callback

    def disconnect(self, callback=None):
        """移除指定回调；不传参数则清空全部订阅。"""
        with self._lock:
            if callback is None:
                self._callbacks.clear()
            elif callback in self._callbacks:
                self._callbacks.remove(callback)

    def emit(self, *args, **kwargs):
        """同步调用所有回调。

        单个回调抛异常不应影响其他订阅者，也不该中断调用方（调用方通常是
        生成流程的 worker），因此就地捕获并打印堆栈。
        """
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            try:
                callback(*args, **kwargs)
            except Exception:
                traceback.print_exc()
