"""
SSE 事件总线 — 将 pipeline 的实时事件流式推送到前端

事件类型:
- log: Agent 日志消息
- progress: 整体进度更新 (0-100)
- agent_status: Agent 状态变更
- stage: 流水线阶段变更
- chapter_ready: 章节生成完成
- world_view_ready: 世界观构建完成（等待审阅）
- outline_ready: 大纲生成完成
- continuation_outline_ready: 续写大纲就绪（等待审阅）
- pipeline_finished: 流水线完成
- pipeline_error: 流水线错误
- stream_token: LLM 流式 token
"""
import asyncio
import json
import logging
import threading
from typing import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("novel-factory.events")


class EventBroker:
    """异步事件代理 — pipeline 推送事件，SSE 端点消费事件

    线程安全：publish() 可从任意线程调用（pipeline 后台线程），
    内部通过 call_soon_threadsafe 切回 asyncio 事件循环执行 put。
    _queues 受 _lock 保护，subscribe/unpublish/publish 均先获取锁。
    """

    def __init__(self):
        self._queues: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """绑定 SSE 消费者所在的事件循环（在 subscribe 时自动设置）"""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._queues.append(q)
        # 首次订阅时记录事件循环
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        return q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            if q in self._queues:
                self._queues.remove(q)

    def publish(self, event: str, data: dict):
        """发布事件到所有订阅者（线程安全，可从后台线程调用）"""
        payload = {"event": event, "data": data}
        loop = self._loop
        if loop is None:
            return
        # 快照队列列表，避免迭代时列表被修改
        with self._lock:
            queues = list(self._queues)
        logger.info(f"[EventBroker] publish: {event}, queues={len(queues)}")  # DEBUG
        for q in queues:
            # 线程安全：把 put 调度回 asyncio 事件循环
            def _put(queue=q, p=payload):
                try:
                    queue.put_nowait(p)
                except asyncio.QueueFull:
                    logger.warning("SSE QueueFull, dropping event %s", event)
            try:
                loop.call_soon_threadsafe(_put)
            except RuntimeError:
                # 事件循环已关闭，回退到直接调用
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass


# 全局单例
event_broker = EventBroker()

router = APIRouter()


@router.get("/stream")
async def event_stream():
    """SSE 事件流端点"""
    event_broker.set_loop(asyncio.get_running_loop())
    q = event_broker.subscribe()

    async def generator() -> AsyncGenerator:
        try:
            # 发送连接成功事件
            yield {"event": "connected", "data": json.dumps({"ok": True})}
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30)
                    logger.info(f"[SSE] sending: {payload['event']}")  # DEBUG
                    yield {
                        "event": payload["event"],
                        "data": json.dumps(payload["data"], ensure_ascii=False),
                    }
                except asyncio.TimeoutError:
                    # 心跳保活
                    yield {"event": "ping", "data": "{}"}
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            event_broker.unsubscribe(q)

    return EventSourceResponse(generator())
