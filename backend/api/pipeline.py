"""
流水线控制 API

NovelPipeline 的信号在 emit 时自行发布到 EventBroker，因此这里无需再做
信号桥接，前端通过 SSE 直接接收 pipeline 事件。
"""
import json
import logging
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.events import event_broker
from core.config import load_config

logger = logging.getLogger("novel-factory.pipeline-api")

router = APIRouter()

# 全局 pipeline 实例（懒加载）
_pipeline: Optional[object] = None
_pipeline_lock = threading.Lock()


def _get_pipeline():
    """获取或创建 pipeline 实例。

    NovelPipeline 的每个信号在 emit 时自行调用 event_broker.publish()，
    不需要额外的信号桥接。
    """
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline

        from core.pipeline import NovelPipeline

        _pipeline = NovelPipeline()
        return _pipeline


@router.post("/start")
async def start_pipeline(body: dict):
    """启动新的小说生成流水线"""
    inspiration = body.get("inspiration", "").strip()
    if not inspiration:
        raise HTTPException(status_code=400, detail="灵感不能为空")

    chapter_count = body.get("chapter_count")
    chapter_length = body.get("chapter_length")
    api_key = body.get("api_key")

    try:
        pipeline = _get_pipeline()

        # 检查流水线是否已在运行
        if pipeline.is_running:
            raise HTTPException(
                status_code=409,
                detail="流水线已在运行中，请先暂停或等待完成"
            )

        if api_key:
            pipeline.initialize(api_key)
        else:
            pipeline.initialize()

        pipeline.start(inspiration, chapter_count, chapter_length)
        return {"ok": True, "message": "流水线已启动"}
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/resume")
async def resume_pipeline(body: dict):
    """恢复未完成的流水线"""
    project_dir = body.get("project_dir", "").strip()
    if not project_dir:
        raise HTTPException(status_code=400, detail="项目目录不能为空")

    try:
        pipeline = _get_pipeline()
        pipeline.initialize()
        pipeline.resume_from_project(project_dir)
        return {"ok": True, "message": "流水线已恢复"}
    except (RuntimeError, json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/continue")
async def continue_pipeline(body: dict):
    """续写项目"""
    project_dir = body.get("project_dir", "").strip()
    guidance = body.get("guidance", "").strip()
    batch_chapter_count = body.get("batch_chapter_count", 5)

    if not project_dir:
        raise HTTPException(status_code=400, detail="项目目录不能为空")
    if not guidance:
        raise HTTPException(status_code=400, detail="续写指引不能为空")

    try:
        pipeline = _get_pipeline()
        pipeline.initialize()
        pipeline.continue_from_project(project_dir, guidance, batch_chapter_count)
        return {"ok": True, "message": "续写大纲生成中"}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm-world-view")
async def confirm_world_view(body: dict):
    """确认世界观（审阅后继续）"""
    reviewed = body.get("world_view")
    if not reviewed or not isinstance(reviewed, dict):
        raise HTTPException(status_code=400, detail="缺少世界观数据")
    try:
        pipeline = _get_pipeline()
        pipeline.confirm_world_view(reviewed)
        return {"ok": True}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm-outline")
async def confirm_outline(body: dict):
    """确认大纲（审阅后开始章节生成）"""
    reviewed = body.get("outline")
    if not reviewed or not isinstance(reviewed, dict):
        raise HTTPException(status_code=400, detail="缺少大纲数据")
    try:
        pipeline = _get_pipeline()
        pipeline.confirm_outline(reviewed)
        return {"ok": True}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm-continuation")
async def confirm_continuation(body: dict):
    """确认续写大纲（审阅后开始章节生成）"""
    reviewed = body.get("outline")
    if not reviewed or not isinstance(reviewed, dict):
        raise HTTPException(status_code=400, detail="缺少大纲数据")
    try:
        pipeline = _get_pipeline()
        pipeline.confirm_continuation(reviewed)
        return {"ok": True}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pause")
async def pause_pipeline():
    """暂停流水线"""
    try:
        pipeline = _get_pipeline()
        pipeline.pause_and_save()
        return {"ok": True, "message": "流水线已暂停"}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stop")
async def stop_pipeline():
    """强制停止流水线并清理状态"""
    try:
        pipeline = _get_pipeline()
        pipeline.stop()
        return {"ok": True, "message": "流水线已停止"}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/retry-world-view")
async def retry_world_view():
    """重新生成世界观（审阅对话框调用）"""
    try:
        pipeline = _get_pipeline()
        ok = pipeline.retry_world_view()
        if not ok:
            raise HTTPException(status_code=400, detail="无法重试世界观：缺少灵感输入")
        return {"ok": True, "message": "世界观重新生成中"}
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/retry-outline")
async def retry_outline():
    """重新生成大纲（审阅对话框调用）"""
    try:
        pipeline = _get_pipeline()
        ok = pipeline.retry_outline()
        if not ok:
            raise HTTPException(status_code=400, detail="无法重试大纲：缺少世界观数据")
        return {"ok": True, "message": "大纲重新生成中"}
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/retry")
async def retry_pipeline():
    """重试当前失败的阶段"""
    try:
        pipeline = _get_pipeline()
        ok = pipeline.retry_current_stage()
        if not ok:
            raise HTTPException(status_code=400, detail="当前阶段不支持重试")
        return {"ok": True, "message": "正在重试..."}
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status")
async def pipeline_status():
    """获取当前流水线状态"""
    pipeline = _get_pipeline()
    return {
        "is_running": pipeline.is_running,
        "current_stage": pipeline.current_stage,
        "project_dir": str(pipeline.project_dir) if pipeline.project_dir else None,
        "chapter_count": pipeline._chapter_count,
        "completed_chapters": pipeline._completed_chapters,
    }
