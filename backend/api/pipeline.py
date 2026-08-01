"""
流水线控制 API — 桥接 Qt 信号到 SSE 事件总线

将 NovelPipeline 的 pyqtSignal 连接到 event_broker.publish()，
使前端通过 SSE 实时接收 pipeline 事件。
"""
import json
import logging
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.events import event_broker
from core.config import load_config
from core._headless import ensure_qt_app

logger = logging.getLogger("novel-factory.pipeline-api")

router = APIRouter()

# 全局 pipeline 实例（懒加载）
_pipeline: Optional[object] = None
_pipeline_lock = threading.Lock()


def _get_pipeline():
    """获取或创建 pipeline 实例，并连接信号到事件总线"""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline

        # 确保 Qt 应用存在
        ensure_qt_app()

        from core.pipeline import NovelPipeline

        pipeline = NovelPipeline()
        # 注意：不再调用 _connect_signals()，因为 NovelPipeline 使用 _SimpleSignalBroker
        # 它会自动发布事件到 EventBroker，无需额外的信号连接
        _pipeline = pipeline
        return pipeline


def _connect_signals(pipeline):
    """将 pipeline 的所有信号桥接到 SSE 事件总线

    注意：PyQt6 信号在没有事件循环时会阻塞。
    我们通过替换信号的 emit 方法来直接调用 event_broker.publish。
    """
    s = pipeline.signals

    # 保存原始的 emit 方法
    _original_emits = {}

    def make_publisher(signal_name, event_name, *arg_names, **fixed_kwargs):
        """创建一个发布函数，直接调用 event_broker.publish"""
        def publisher(*args):
            kwargs = dict(zip(arg_names, args))
            kwargs.update(fixed_kwargs)
            event_broker.publish(event_name, kwargs)
        return publisher

    # 替换每个信号的 emit 方法
    signal_mappings = [
        ("log_signal", "log", "source", "message"),
        ("stage_started", "stage", "stage"),
        ("stage_completed", "stage", "stage"),
        ("stage_error", "pipeline_error", "stage", "error"),
        ("overall_progress", "progress", "overall"),
        ("world_view_ready", "world_view_ready", "data"),
        ("outline_ready", "outline_ready", "data"),
        ("chapter_ready", "chapter_ready", "data"),
        ("evaluation_ready", "evaluation_ready", "data"),
        ("revision_ready", "revision_ready", "data"),
        ("adaptation_ready", "adaptation_ready", "data"),
        ("pipeline_finished", "pipeline_finished", "data"),
        ("continuation_outline_ready", "continuation_outline_ready", "data"),
        ("continuation_progress", "continuation_progress", "text", "progress"),
        ("world_view_review_ready", "world_view_review_ready", "data"),
        ("generation_started", "generation_started"),
        ("token_update", "token_update", "agent", "tokens"),
        ("chapter_progress", "chapter_progress", "chapter_index", "progress", "status"),
    ]

    for mapping in signal_mappings:
        signal_name = mapping[0]
        event_name = mapping[1]
        arg_names = mapping[2:]

        signal = getattr(s, signal_name)

        # 创建固定参数的 kwargs
        fixed = {}
        if signal_name == "stage_started":
            fixed = {"status": "started"}
        elif signal_name == "stage_completed":
            fixed = {"status": "completed"}

        # 替换 emit 方法
        publisher = make_publisher(signal_name, event_name, *arg_names, **fixed)
        _original_emits[signal_name] = signal.emit
        signal.emit = publisher

    # Token 统计
    s.token_update.connect(lambda name, tokens: publish("token_update", {
        "agent": name,
        "tokens": tokens,
    }))


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
