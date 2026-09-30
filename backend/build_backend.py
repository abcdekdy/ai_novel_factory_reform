"""
把后端冻结为独立可执行文件（供免安装绿色版分发）
==================================================
产物 `backend/dist/novel-backend/` 由 Electron 打包时作为 extraResource 一并
分发，最终用户无需安装 Python 及任何依赖。

用法：python build_backend.py
依赖：pip install pyinstaller

为什么用脚本而不是直接敲命令：参数较多（隐藏导入 / 排除模块 / 各路径），
放在这里比 bat 里的长续行更可靠，也便于版本追踪。
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST_DIR = HERE / "dist"
WORK_DIR = HERE / "build"
APP_NAME = "novel-backend"

# uvicorn 的循环/协议/生命周期实现是按字符串动态导入的，静态分析看不到，
# 不显式声明会在运行时报 "No module named uvicorn.protocols.http.auto" 之类。
HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "anyio._backends._asyncio",
]

# 无界面服务端用不到的重型依赖。排除它们把产物体积压到 ~30MB；
# 尤其 PyQt6 —— 它只是历史遗留的信号总线，已改用 core/signals.py，
# 若被误打进包会平白多出上百 MB。
EXCLUDES = [
    "tkinter", "PyQt6", "PyQt5", "PySide6",
    "matplotlib", "numpy", "pandas", "scipy",
    "PIL", "pytest",
]


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 PyInstaller，请先执行：pip install pyinstaller")
        return 1

    # 清理旧产物，避免混入上一次构建的残留文件
    for path in (DIST_DIR, WORK_DIR):
        shutil.rmtree(path, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", APP_NAME,
        "--onedir",          # 目录形态：启动比 onefile 快，且便于随包分发
        "--noconsole",       # 不弹黑色控制台窗；日志仍经管道交给 Electron
        "--distpath", str(DIST_DIR),
        "--workpath", str(WORK_DIR),
        "--specpath", str(WORK_DIR),
    ]
    for module in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", module]
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    cmd.append("run_server.py")

    print("正在冻结后端，首次构建可能需要一两分钟...")
    result = subprocess.run(cmd, cwd=str(HERE))
    if result.returncode != 0:
        print("后端冻结失败")
        return result.returncode

    exe = DIST_DIR / APP_NAME / (f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME)
    if not exe.exists():
        print(f"未找到预期产物：{exe}")
        return 1

    size_mb = sum(f.stat().st_size for f in (DIST_DIR / APP_NAME).rglob("*") if f.is_file())
    print(f"后端冻结完成：{exe.parent}（约 {size_mb / 1024 / 1024:.1f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
