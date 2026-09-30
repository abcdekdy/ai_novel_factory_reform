"""
打包专用入口 —— 以编程方式启动 uvicorn
========================================
开发时仍用 `uvicorn main:app --reload --port 8765`（见 dev.bat / npm run dev:backend）；
本文件只服务于 PyInstaller 冻结产物，让打包后的后端成为**独立可执行文件**，
最终用户无需安装 Python 及任何依赖。

与命令行启动的差异：直接传入 app 对象而非导入字符串，因此不支持 `--reload`
（冻结产物本就不需要热重载）。
"""

import multiprocessing
import os
import sys

# 确保冻结后仍能从同目录导入项目模块
if getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(sys.executable))

import uvicorn

from main import app


def main() -> None:
    # 冻结后若运行期派生进程，Windows 需要此调用，否则会反复重启自身
    multiprocessing.freeze_support()

    host = os.environ.get("NOVEL_BACKEND_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("NOVEL_BACKEND_PORT", "8765"))
    except ValueError:
        port = 8765

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        # 冻结后不启用访问日志，减少 Electron 控制台噪音
        access_log=False,
    )


if __name__ == "__main__":
    main()
