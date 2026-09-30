"""
免安装绿色版组装脚本
========================================
把 Electron 运行时、前端构建产物、冻结后的后端组装成一个可直接分发的目录，
并打成 zip。解压后双击 `ai-novel-factory.exe` 即可运行，无需安装 Python。

为什么不用 electron-forge / electron-packager：
    它们依赖 extract-zip 解压 Electron 压缩包，而该环节在本机环境下会在写出
    第一个文件后静默终止（已确认压缩包本身完好：73 个条目全部通过校验，
    Python 可完整解压）。改为直接复用 node_modules/electron/dist —— 那是
    npm 安装 Electron 时就已经解压好的完整运行时，确定性且快得多。

产物结构：
    out/AI小说工厂-win32-x64/
        ai-novel-factory.exe        <- 由 electron.exe 改名而来
        resources/
            app/                    <- 应用代码（main.js / preload.js / frontend）
            novel-backend/          <- 冻结的 Python 后端
        data/                       <- 首次运行时由后端自动创建

用法：python package_portable.py
前置：先跑 frontend 的 vite build 和 backend/build_backend.py
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "AI小说工厂-win32-x64"
EXE_NAME = "ai-novel-factory.exe"

ELECTRON_DIST = ROOT / "node_modules" / "electron" / "dist"
FRONTEND_DIST = ROOT / "frontend" / "dist"
BACKEND_FROZEN = ROOT / "backend" / "dist" / "novel-backend"
OUT_DIR = ROOT / "out" / APP_NAME

# 应用代码里保留哪些内容（相对项目根）。main.js 只依赖 Node 内置模块，
# 因此不需要带 node_modules。
APP_FILES = ["electron", "assets"]
APP_DIRS = ["frontend/dist"]


def fail(message: str) -> None:
    print(f"构建失败：{message}")
    sys.exit(1)


def robust_rmtree(target: Path) -> bool:
    """删除目录，返回是否已彻底删除。

    两个 Windows 坑叠加，光靠 shutil.rmtree 删不干净：
      1. 个别文件带只读属性 → 出错时清掉只读位再重试
      2. **长路径**（Electron 目录嵌套深 + 项目路径本身很长，轻易超过
         MAX_PATH）→ shutil.rmtree 直接失败，改用系统命令兜底
    """

    def _on_error(func, path, _exc_info):  # noqa: ANN001
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    for _ in range(3):
        if not target.exists():
            return True
        shutil.rmtree(target, onerror=_on_error)
        if not target.exists():
            return True
        time.sleep(0.3)

    if not target.exists():
        return True

    # 兜底：交给系统命令（走不同的路径处理，能应付超长路径）
    try:
        if sys.platform == "win32":
            subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(target)],
                           check=False)
        else:
            subprocess.run(["rm", "-rf", str(target)], check=False)
    except Exception:
        pass
    return not target.exists()


def check_prerequisites() -> None:
    if not (ELECTRON_DIST / "electron.exe").exists():
        fail(f"未找到 Electron 运行时：{ELECTRON_DIST}\n请先执行 npm install")
    if not (FRONTEND_DIST / "index.html").exists():
        fail(f"未找到前端构建产物：{FRONTEND_DIST}\n请先执行 npm run build:frontend")
    if not (BACKEND_FROZEN / "novel-backend.exe").exists():
        fail(
            f"未找到冻结后的后端：{BACKEND_FROZEN}\n请先执行 python backend/build_backend.py"
        )


def build_app_dir(app_root: Path) -> None:
    """组装 resources/app —— Electron 会优先加载它而非 default_app.asar。"""
    app_root.mkdir(parents=True, exist_ok=True)

    # 精简的 package.json：只保留 Electron 启动所需字段
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    (app_root / "package.json").write_text(
        json.dumps(
            {
                "name": pkg.get("name", "ai-novel-factory"),
                # 版本以根 package.json 为唯一来源，避免这里留下会过期的字面量
                "version": pkg.get("version", "0.0.0"),
                "description": pkg.get("description", ""),
                "main": pkg.get("main", "electron/main.js"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    for rel in APP_FILES:
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, app_root / rel, dirs_exist_ok=True)

    for rel in APP_DIRS:
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, app_root / rel, dirs_exist_ok=True)


def main() -> int:
    check_prerequisites()

    print(f"清理旧产物：{OUT_DIR}")
    if not robust_rmtree(OUT_DIR):
        fail(
            f"无法清理旧产物：{OUT_DIR}\n"
            f"通常是上一次构建的程序还在运行（ai-novel-factory.exe / novel-backend.exe）。\n"
            f"请先关闭它们再重试。"
        )
    OUT_DIR.mkdir(parents=True)

    print("复制 Electron 运行时...")
    shutil.copytree(ELECTRON_DIST, OUT_DIR, dirs_exist_ok=True)

    # 重命名入口 exe；Electron 依据 exe 所在位置定位 resources/app，改名是安全的
    (OUT_DIR / "electron.exe").rename(OUT_DIR / EXE_NAME)

    # 把图标写进 exe 的 PE 资源。BrowserWindow({icon}) 只管窗口/任务栏图标，
    # **资源管理器里显示的 exe 文件图标来自 PE 资源**，必须在这一步改写，
    # 否则解压后在文件夹里看到的是 Electron 默认图标。
    icon = ROOT / "assets" / "icon.ico"
    icon_script = ROOT / "set_exe_icon.mjs"
    if icon.exists() and icon_script.exists():
        print("写入 exe 图标...")
        try:
            subprocess.run(
                ["node", str(icon_script), str(OUT_DIR / EXE_NAME), str(icon)],
                cwd=str(ROOT), check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"  写入图标失败（不影响运行）: {exc}")
    else:
        print("跳过 exe 图标（缺少 assets/icon.ico 或 set_exe_icon.mjs）")

    resources = OUT_DIR / "resources"

    # 移走 Electron 自带的示例应用。它是**文件**不是目录，必须 unlink ——
    # 留着会有个隐蔽的坏结果：一旦我们的 app/ 加载失败，Electron 会静默回退
    # 到它，界面上表现为"打开了另一个空白应用"，很难排查。
    default_app = resources / "default_app.asar"
    if default_app.is_file():
        default_app.unlink()
    elif default_app.is_dir():
        shutil.rmtree(default_app, ignore_errors=True)

    print("组装应用代码 -> resources/app")
    build_app_dir(resources / "app")

    print("复制冻结后端 -> resources/novel-backend")
    shutil.copytree(BACKEND_FROZEN, resources / "novel-backend", dirs_exist_ok=True)

    print("压缩为 zip...")
    archive = shutil.make_archive(
        str(ROOT / "out" / APP_NAME), "zip", root_dir=str(OUT_DIR.parent), base_dir=APP_NAME
    )

    size_mb = Path(archive).stat().st_size / 1024 / 1024
    print()
    print("构建完成！")
    print(f"  目录：{OUT_DIR}")
    print(f"  压缩包：{archive}（{size_mb:.1f} MB）")
    print(f"  使用：解压后双击 {EXE_NAME}，无需安装 Python")
    return 0


if __name__ == "__main__":
    sys.exit(main())
