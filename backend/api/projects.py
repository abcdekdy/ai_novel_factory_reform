"""
项目管理 API
"""
import logging
import time
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.project_manager import (
    list_projects,
    load_project_summary,
    load_world_view,
    load_outline,
    load_all_chapters_map,
    export_to_txt,
    export_to_markdown,
    list_batch_outlines,
)

logger = logging.getLogger("novel-factory.projects-api")

router = APIRouter()


@router.get("")
async def get_projects():
    """列出所有项目"""
    projects = list_projects()
    return {"projects": projects}


@router.get("/{project_name:path}/summary")
async def get_project_summary(project_name: str):
    """获取项目摘要"""
    # 从 project_name 重建完整路径
    projects = list_projects()
    target = None
    for p in projects:
        if p.get("name") == project_name or p.get("path", "").endswith(project_name):
            target = p.get("path")
            break
    if not target:
        raise HTTPException(status_code=404, detail="项目不存在")

    summary = load_project_summary(target)
    return summary


@router.get("/{project_name:path}/world-view")
async def get_world_view(project_name: str):
    """获取世界观"""
    project_dir = _resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="项目不存在")
    return load_world_view(project_dir)


@router.get("/{project_name:path}/outline")
async def get_outline(project_name: str):
    """获取详细大纲"""
    project_dir = _resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="项目不存在")
    return load_outline(project_dir)


@router.get("/{project_name:path}/chapters")
async def get_chapters(project_name: str):
    """获取所有章节"""
    project_dir = _resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="项目不存在")
    return load_all_chapters_map(project_dir)


@router.get("/{project_name:path}/batches")
async def get_batches(project_name: str):
    """获取续写批次列表"""
    project_dir = _resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"batches": load_batch_outlines(project_dir)}


@router.delete("/{project_name:path}")
async def delete_project(project_name: str):
    """删除项目（整个目录）"""
    logger.info(f"[DELETE] project_name={project_name!r}")
    project_dir = _resolve_project_dir(project_name)
    if not project_dir:
        # 调试：列出所有项目帮助排查
        all_projects = list_projects()
        logger.warning(
            f"[DELETE] not found. name={project_name!r}, "
            f"available={[p['name'] for p in all_projects]}"
        )
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_name}")
    target = Path(project_dir)
    if not target.exists():
        raise HTTPException(status_code=404, detail="项目目录不存在")
    # 安全检查：确保路径在 projects 目录下
    projects_root = (Path(__file__).parent.parent / "projects").resolve()
    try:
        target.resolve().relative_to(projects_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法路径")
    # 删除目录，带重试（Windows 文件锁/权限问题）
    last_err = None
    for attempt in range(3):
        try:
            shutil.rmtree(target)
            return {"ok": True, "message": "项目已删除"}
        except PermissionError as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.3 * (attempt + 1))
        except OSError as e:
            last_err = e
            break
    raise HTTPException(
        status_code=500,
        detail=f"删除失败: {last_err}"
    )


@router.post("/{project_name:path}/export/txt")
async def export_txt(project_name: str):
    """导出为 TXT"""
    project_dir = _resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        output = Path(project_dir) / "exports"
        output.mkdir(exist_ok=True)
        output_path = output / f"{project_name}.txt"
        export_to_txt(project_dir, str(output_path))
        return {"ok": True, "path": str(output_path)}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")


@router.post("/{project_name:path}/export/markdown")
async def export_markdown(project_name: str):
    """导出为 Markdown"""
    project_dir = _resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        output = Path(project_dir) / "exports"
        output.mkdir(exist_ok=True)
        output_path = output / f"{project_name}.md"
        export_to_markdown(project_dir, str(output_path))
        return {"ok": True, "path": str(output_path)}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")


def _resolve_project_dir(project_name: str) -> str | None:
    """根据项目名称解析完整路径（支持精确匹配和路径后缀匹配）"""
    projects = list_projects()
    # 1. 精确匹配 name
    for p in projects:
        if p.get("name") == project_name:
            return p.get("path")
    # 2. 路径后缀匹配（兼容带分隔符的 URL）
    for p in projects:
        if p.get("path", "").endswith(project_name):
            return p.get("path")
    # 3. 宽松匹配：URL 解码后再比较
    from urllib.parse import unquote
    decoded = unquote(project_name)
    for p in projects:
        if p.get("name") == decoded:
            return p.get("path")
    return None
