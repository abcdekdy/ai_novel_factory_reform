"""
无头模式支持 — 让 PyQt6 pipeline 在没有 GUI 的环境中运行

提供 QCoreApplication 实例，使 pyqtSignal 在纯后端环境中正常工作。
Qt 事件循环在后台线程中运行，确保跨线程信号不会阻塞。
"""
import sys
import threading
from PyQt6.QtCore import QCoreApplication, QTimer

_qt_app = None
_qt_thread = None


def ensure_qt_app() -> QCoreApplication:
    """确保存在一个 QCoreApplication 实例（线程安全）"""
    global _qt_app, _qt_thread
    if _qt_app is not None:
        return _qt_app

    if QCoreApplication.instance() is not None:
        _qt_app = QCoreApplication.instance()
        return _qt_app

    _qt_app = QCoreApplication(sys.argv)

    # 在后台线程中运行 Qt 事件循环，确保跨线程信号不会阻塞
    def run_loop():
        _qt_app.exec()

    _qt_thread = threading.Thread(target=run_loop, daemon=True)
    _qt_thread.start()

    return _qt_app


def process_events():
    """处理挂起的 Qt 事件（在需要时调用）"""
    app = QCoreApplication.instance()
    if app is not None:
        app.processEvents()
