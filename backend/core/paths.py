"""
可写数据目录解析
========================================
`config.json` 与 `projects/` 属于**用户数据**，必须落在可写且不会被清理的位置。

此前它们统一由 `Path(__file__).parent.parent` 推导（即 backend/ 目录），这在
源码运行下没问题，但打包后会指向 PyInstaller 包内部——那里要么只读，要么在
onefile 模式下是退出即删的临时目录，等于用户数据凭空消失。

解析优先级：
  1. 环境变量 `NOVEL_DATA_DIR` —— 由 Electron 在打包态显式注入，指向应用根目录
     下的 data/，使绿色版"整个文件夹挪走，数据跟着走"
  2. 冻结环境（PyInstaller）下的兜底：可执行文件同级的 data/
  3. 开发环境：backend/ —— 保持既有行为，老项目与 config.json 不受影响
"""

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否运行在 PyInstaller 冻结产物中。"""
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    """返回可写数据根目录（不存在则创建）。"""
    override = os.environ.get("NOVEL_DATA_DIR", "").strip()
    if override:
        path = Path(override)
    elif is_frozen():
        path = Path(sys.executable).resolve().parent / "data"
    else:
        # core/paths.py -> core -> backend
        path = Path(__file__).resolve().parent.parent

    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    """config.json 的完整路径。"""
    return data_dir() / "config.json"


def projects_dir() -> Path:
    """项目库根目录（不存在则创建）。"""
    path = data_dir() / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path
