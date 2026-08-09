"""
流水线编排引擎
串联各Agent完成任务，管理并发、修订循环、状态广播

工作流程：
灵感 → 世界观构建 → 并行章节生成 → 质量评估 → 修订循环 → 多平台适配 → 完成
"""

import time
import json
import threading
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal

from core.llm_client import LLMClient
from core.config import load_config
from core.world_agent import WorldBuilderAgent
from core.outline_agent import OutlineBuilderAgent
from core.continuation_outline_agent import ContinuationOutlineAgent
from core.chapter_agent import ChapterGeneratorAgent
from core.quality_agent import QualityEvaluatorAgent
from core.revision_agent import RevisionAgent
from core.adapter_agent import PlatformAdapterAgent
from core.project_manager import (
    create_project, save_world_view, save_chapter,
    save_project_summary, load_project_summary,
    export_to_txt, export_to_markdown,
    load_world_view, load_outline,
    load_all_chapters_map, load_legacy_package,
    save_batch_outline, load_batch_outline,
    list_batch_outlines, get_next_batch_number,
    load_all_chapters, update_project_batches,
    build_timeline_snapshot, save_timeline_snapshot,
)


class PipelineSignals(QObject):
    """流水线全局信号"""
    # 阶段信号
    stage_started = pyqtSignal(str)        # 阶段名称
    stage_completed = pyqtSignal(str)      # 阶段名称
    stage_error = pyqtSignal(str, str)     # (阶段名称, 错误信息)

    # 进度信号
    overall_progress = pyqtSignal(int)     # 整体进度 0-100
    chapter_progress = pyqtSignal(int, int, str)  # (章索引, 进度, 状态)

    # 结果信号
    world_view_ready = pyqtSignal(dict)    # 世界观准备好
    outline_ready = pyqtSignal(dict)       # 详细大纲准备好
    chapter_ready = pyqtSignal(dict)       # 单个章节完成
    evaluation_ready = pyqtSignal(dict)    # 评估完成
    revision_ready = pyqtSignal(dict)      # 修订完成
    adaptation_ready = pyqtSignal(dict)    # 适配完成
    pipeline_finished = pyqtSignal(dict)  # 流水线完成（含全部结果）
    # ---- 续写专用信号 ----
    continuation_outline_ready = pyqtSignal(dict)   # 续写大纲已生成，待用户审阅
    continuation_progress = pyqtSignal(str, int)    # (阶段文本, 进度0-100)

    # ---- 世界观审查信号 ----
    world_view_review_ready = pyqtSignal(dict)      # 世界观已生成，待用户审阅

    # 日志
    log_signal = pyqtSignal(str, str)      # (source, message)

    # 创作启动（通知 UI 切换到工作台 tab）
    generation_started = pyqtSignal()

    # Token统计
    token_update = pyqtSignal(str, int)    # (agent_name, tokens_used)


class _Signal:
    """简单的信号实现 - 直接调用 event_broker.publish"""
    def __init__(self, event_name, *arg_names, **fixed_kwargs):
        self.event_name = event_name
        self.arg_names = arg_names
        self.fixed_kwargs = fixed_kwargs

    def connect(self, callback):
        self._callback = callback

    def emit(self, *args):
        from api.events import event_broker
        if len(self.arg_names) == 1 and self.arg_names[0] == "data" and not self.fixed_kwargs:
            # 单 "data" 参数事件直接发布值，避免 {"data": {...}} 嵌套
            event_broker.publish(self.event_name, args[0])
        else:
            kwargs = dict(zip(self.arg_names, args))
            kwargs.update(self.fixed_kwargs)
            event_broker.publish(self.event_name, kwargs)
        if hasattr(self, '_callback'):
            self._callback(*args)


class NovelPipeline(QObject):
    """小说生成流水线引擎"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 使用 _Signal 替代 Qt 信号，避免跨线程阻塞
        self.signals = type('Signals', (), {
            'log_signal': _Signal("log", "source", "message"),
            'stage_started': _Signal("stage", "stage", status="started"),
            'stage_completed': _Signal("stage", "stage", status="completed"),
            'stage_error': _Signal("pipeline_error", "stage", "error"),
            'overall_progress': _Signal("progress", "overall"),
            'world_view_ready': _Signal("world_view_ready", "data"),
            'outline_ready': _Signal("outline_ready", "data"),
            'chapter_ready': _Signal("chapter_ready", "data"),
            'evaluation_ready': _Signal("evaluation_ready", "data"),
            'revision_ready': _Signal("revision_ready", "data"),
            'adaptation_ready': _Signal("adaptation_ready", "data"),
            'pipeline_finished': _Signal("pipeline_finished", "data"),
            'outline_review_ready': _Signal("outline_review_ready", "data"),
            'continuation_outline_ready': _Signal("continuation_outline_ready", "data"),
            'continuation_progress': _Signal("continuation_progress", "text", "progress"),
            'world_view_review_ready': _Signal("world_view_review_ready", "data"),
            'generation_started': _Signal("generation_started"),
            'token_update': _Signal("token_update", "agent", "tokens"),
            'chapter_progress': _Signal("chapter_progress", "chapter_index", "progress", "status"),
        })()
        self.config = load_config()
        self.llm = None
        self.project_dir = None
        self.world_view = None
        self.outline = None          # 详细大纲（OutlineBuilderAgent 产出）
        self.chapters = []
        self.evaluations = {}
        self.adaptations = {}

        # 流水线状态
        self.is_running = False
        self.current_stage = ""
        self._chapter_count = 0
        self._completed_chapters = 0
        self._pause_requested = False
        self._pending_chapter_workers = 0

        # 修订循环状态
        self._revision_queue = []
        self._revision_in_progress = False

        # ---- 大纲审阅状态 ----
        self._pending_outline = None          # 待审阅的详细大纲
        self._outline_reviewing = False       # 是否在大纲审阅检查点暂停
        self._pending_resume_outline = None   # 恢复场景：确认大纲后补缺失章节用

        # ---- 续写状态 ----
        self._continuation_outline = None     # 待审阅的续写大纲
        self._continuation_guidance = ""       # 用户给的本批续写指引
        self._continuation_batch = 0          # 本批批次号
        self._continuation_legacy = None      # 遗产包缓存

        self._outline_for_chapters = None     # 当前用于章节生成的大纲（可能是续写批次的）

        # ---- 重试支持 ----
        self._last_inspiration = None         # 保存灵感文本，供世界构建重试用
        self._last_chapter_count = None       # 保存章节数
        self._failed_stage = None             # 记录失败阶段名

    def initialize(self, api_key: str = None):
        """初始化LLM客户端"""
        # 每次启动、恢复或续写前重新读取配置，使设置页保存后立即生效。
        self.config = load_config()
        if api_key is None:
            api_key = self.config.get("api_key", "")
        self.llm = LLMClient(
            api_key=api_key,
            base_url=self.config.get("base_url"),
            model=self.config.get("model"),
            timeout=self.config.get("timeout", 300),
        )
        self.signals.log_signal.emit(
            "Pipeline",
            f"LLM客户端初始化完成 | Anthropic Messages API | 模型: {self.llm.model}"
        )

    def start(self, inspiration: str, chapter_count: int = None, chapter_length: int = None):
        """
        启动完整流水线
        """
        if self.is_running:
            self.signals.log_signal.emit("Pipeline", "⚠️ 流水线已在运行中")
            return

        if not self.llm:
            self.initialize()

        # 参数准备
        if chapter_count is None:
            chapter_count = self.config.get("default_chapter_count", 5)
        if chapter_length is None:
            chapter_length = self.config.get("default_chapter_length", 3000)

        self.is_running = True
        self._pause_requested = False
        self.chapters = []
        self.evaluations = {}
        self.adaptations = {}
        self._chapter_count = chapter_count
        self._chapter_length = chapter_length  # 保存供后续阶段使用
        self._last_inspiration = inspiration    # 保存供重试用
        self._last_chapter_count = chapter_count
        self._completed_chapters = 0
        self._chapter_results = {}
        self._chapter_completed_count = 0
        self._pending_chapter_workers = 0

        # 创建项目目录
        safe_name = inspiration[:20] if inspiration else "untitled"
        self.project_dir = create_project(safe_name)

        self.signals.log_signal.emit("Pipeline", f"🚀 流水线启动 | 灵感: {inspiration[:30]}... | {chapter_count}章")
        self.signals.overall_progress.emit(0)

        # 在后台线程运行流水线（避免阻塞GUI）
        def run_pipeline():
            try:
                self._build_world_view(inspiration, chapter_count)
            except Exception as e:
                self.signals.log_signal.emit("Pipeline", f"❌ 流水线异常: {e}")

        self._pipeline_thread = threading.Thread(target=run_pipeline, daemon=True)
        self._pipeline_thread.start()


    def _build_world_view(self, inspiration: str, chapter_count: int):
        """Step 1: 构建世界观"""
        import logging
        logger = logging.getLogger("novel-factory.pipeline")
        self.current_stage = "world_building"
        logger.info("[PIPELINE DEBUG] _build_world_view called")  # DEBUG
        self.signals.stage_started.emit("世界观构建")
        logger.info("[PIPELINE DEBUG] stage_started emitted")  # DEBUG
        self.signals.log_signal.emit("Pipeline", "📖 [1/5] 世界观构建Agent 启动...")
        logger.info("[PIPELINE DEBUG] log emitted")  # DEBUG

        agent = WorldBuilderAgent(self.llm)

        # 连接信号以转发
        agent.log_signal.connect(lambda name, msg: self.signals.log_signal.emit(name, msg))
        agent.progress_signal.connect(lambda name, pct: (
            self.signals.overall_progress.emit(int(pct * 0.15)),  # 世界观占15%
            self.signals.chapter_progress.emit(0, pct, "世界观构建中")
        ))

        try:
            result = agent.run({
                "inspiration": inspiration,
                "chapter_count": chapter_count
            })

            if "error" in result:
                if self._finalize_pause_if_requested():
                    return
                self.signals.stage_error.emit("世界观构建", result["error"])
                self._handle_error(f"世界观构建失败: {result['error']}")
                return

            self.world_view = result

            # 保存世界观
            if self.project_dir:
                save_world_view(self.project_dir, result)
                save_project_summary(self.project_dir, {
                    "inspiration": inspiration,
                    "title": result.get("title", ""),
                    "chapter_count": chapter_count,
                    "chapter_length": self._chapter_length,
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "generating"
                })

            # ---- 世界观审查检查点：暂停流水线，等用户审阅 ----
            self._pending_world_view = result
            self._world_view_reviewing = True
            self.signals.world_view_ready.emit(result)
            self.signals.stage_completed.emit("世界观构建")
            self.signals.log_signal.emit(
                "Pipeline",
                f"✅ 世界观构建完成: {result.get('title', '')} — 等待用户审阅")
            self.signals.world_view_review_ready.emit(result)
            # 注意：不调用 _build_outline；等用户在 main_window 里调
            # confirm_world_view() / discard_world_view() 后再继续。

        except Exception as e:
            self.signals.stage_error.emit("世界观构建", str(e))
            self._handle_error(f"世界观构建异常: {e}")

    def _build_outline(self, world_view: dict, resume_existing: dict = None):
        """Step 1.5: 根据世界观生成详细大纲（消除章节间矛盾）"""
        self.current_stage = "outline_generation"
        self.signals.stage_started.emit("大纲生成")
        self.signals.log_signal.emit("Pipeline", "📋 [1.5] 大纲生成Agent 启动...")

        agent = OutlineBuilderAgent(
            self.llm,
            temperature=self.config.get("outline_temperature", 0.7),
            max_tokens=self.config.get("outline_max_tokens", 8192),
        )
        agent.log_signal.connect(lambda name, msg: self.signals.log_signal.emit(name, msg))
        agent.progress_signal.connect(lambda name, pct: (
            self.signals.overall_progress.emit(10 + int(pct * 0.15)),  # 大纲占 10%-25%
            self.signals.chapter_progress.emit(0, int(pct * 0.15), "生成详细大纲")
        ))

        try:
            result = agent.run({"world_view": world_view})

            if "error" in result and not result.get("chapters"):
                if self._finalize_pause_if_requested():
                    return
                self.signals.stage_error.emit("大纲生成", result["error"])
                self._handle_error(f"大纲生成失败: {result['error']}")
                return

            self.outline = result

            # 大纲质量检测：检查是否有足够章节包含实际剧情
            chapters = result.get("chapters", [])
            meaningful = [
                ch for ch in chapters
                if isinstance(ch, dict) and len(str(ch.get("plot_detail", "")).strip()) >= 20
            ]
            if chapters and len(meaningful) < max(1, len(chapters) * 0.3):
                # 少于30%章节有有效剧情 → 视为生成失败，允许重试
                self._handle_error(
                    f"大纲生成质量过低：{len(chapters)}章中仅{len(meaningful)}章包含有效剧情，"
                    f"建议重试")
                return

            # 保存大纲到项目目录
            if self.project_dir:
                import json
                from pathlib import Path
                outline_path = Path(self.project_dir) / "outline.json"
                outline_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )

            self.signals.outline_ready.emit(result)
            self.signals.stage_completed.emit("大纲生成")
            rules = len(result.get("consistency_rules", []))
            arcs = len(result.get("character_arcs", {}))
            ch_count = len(result.get("chapters", []))
            self.signals.log_signal.emit(
                "Pipeline",
                f"✅ 大纲生成完成：{ch_count} 章详细大纲，{rules} 条一致性规则，{arcs} 条角色弧线"
            )

            # ---- 大纲审阅检查点：暂停流水线，等用户审阅 ----
            self._pending_outline = result
            self._outline_reviewing = True
            self._pending_resume_outline = resume_existing
            self.signals.log_signal.emit(
                "Pipeline",
                "📋 大纲已生成，等待用户审阅确认..."
            )
            self.signals.outline_review_ready.emit(result)
            # 注意：不调用 _generate_chapters；等用户调 confirm_outline() 后再继续。

        except Exception as e:
            self.signals.stage_error.emit("大纲生成", str(e))
            self._handle_error(f"大纲生成异常: {e}")

    def _get_consistency_rules(self) -> list:
        """收集一致性规则（质量评估 / 修订时使用）。"""
        outline = self._outline_for_chapters if self._outline_for_chapters else self.outline
        if outline and isinstance(outline.get("consistency_rules"), list):
            return list(outline.get("consistency_rules", []))
        return []

    def _build_outline_context(self) -> dict:
        """构建供章节生成使用的整体大纲上下文（一致性规则/全局弧线/全章概要）。"""
        outline = self._outline_for_chapters if self._outline_for_chapters else self.outline
        if not outline:
            return {"consistency_rules": [], "global_arc": {}, "all_chapters_summary": []}
        rules = outline.get("consistency_rules", [])
        all_summary = []
        for ch in outline.get("chapters", []):
            if isinstance(ch, dict):
                all_summary.append({
                    "chapter_index": ch.get("chapter_index"),
                    "title": ch.get("title", ""),
                    "plot_detail": ch.get("plot_detail", ""),
                    "foreshadowing": ch.get("foreshadowing", [])
                })
        return {
            "consistency_rules": rules,
            "global_arc": outline.get("global_arc", {}),
            "all_chapters_summary": all_summary
        }

    def _generate_chapters(self, target_length: int):
        """Step 2: 并行生成全部章节（新任务，大纲审阅确认后调用）。"""
        self.current_stage = "chapter_generation"
        self.signals.stage_started.emit("章节生成")

        coarse_outline = self.world_view.get("chapter_outline", [])
        if not isinstance(coarse_outline, list) or not coarse_outline:
            self._handle_error("世界观中没有章节大纲，无法生成章节")
            return

        outline_chapters = self.outline.get("chapters", []) if self.outline else []
        outline_detail_map = {
            self._get_chapter_index(chapter, position): chapter
            for position, chapter in enumerate(outline_chapters, start=1)
            if isinstance(chapter, dict)
        }

        total_needed = self._chapter_count or len(coarse_outline)
        self._total_chapters = total_needed
        self._chapter_results = {}
        self._chapter_completed_count = 0
        self._pending_chapter_workers = total_needed
        self._completed_chapters = 0

        self.signals.log_signal.emit(
            "Pipeline", f"✍️ [2/5] 并行生成 {total_needed} 章...")

        import threading
        self._semaphore = threading.Semaphore(self.config.get("concurrency", 2))
        self._chapter_lock = threading.Lock()
        outline_context = self._build_outline_context()

        for position, outline_entry in enumerate(coarse_outline, start=1):
            chapter_index = self._get_chapter_index(outline_entry, position)
            # _chapter_results 键为 0 基位置（第 N 章存键 N-1），前章是键 position-2
            previous = self._chapter_results.get(position - 2, {})
            outline_chapter = outline_detail_map.get(chapter_index, {})
            input_data = {
                "world_view": self.world_view,
                "chapter_outline": outline_entry,
                "chapter_index": chapter_index,
                "target_length": target_length,
                "previous_chapter_summary": previous.get("summary", ""),
                "outline_chapter": outline_chapter,
                "outline_context": outline_context,
                "character_arcs": self.outline.get("character_arcs", {}) if self.outline else {},
            }
            threading.Thread(
                target=self._gen_chapter_worker,
                args=(position - 1, input_data),
                daemon=True,
            ).start()

    def _gen_chapter_worker(self, position: int, input_data: dict):
        """单个章节生成 worker（子线程运行）。"""
        chapter_index = input_data.get("chapter_index", position + 1)
        try:
            with self._semaphore:
                agent = ChapterGeneratorAgent(self.llm, agent_id=position)
                agent.log_signal.connect(
                    lambda name, msg: self.signals.log_signal.emit(name, msg))
                result = agent.run(input_data)
                self._on_chapter_complete(position, result)
        except Exception as e:
            self.signals.log_signal.emit(
                "Pipeline", f"❌ 第{chapter_index}章生成异常: {e}")
            self._on_chapter_complete(position, {
                "chapter_index": chapter_index,
                "title": f"第{chapter_index}章",
                "content": f"[生成失败: {e}]",
                "summary": "",
                "word_count": 0,
                "status": "error",
                "error": str(e)
            })

    def _on_chapter_complete(self, position: int, chapter: dict):
        """单个章节生成完成后的处理：保存 + 进度更新。"""
        with self._chapter_lock:
            self._chapter_results[position] = chapter
            self._chapter_completed_count = len(self._chapter_results)
            self._completed_chapters = self._chapter_completed_count
            self._pending_chapter_workers = max(self._pending_chapter_workers - 1, 0)
            # 同步维护 self.chapters（按 0 基缓存键排序），供评估/修订使用
            self.chapters = [self._chapter_results[i] for i in sorted(self._chapter_results)]

        chapter_index = chapter.get("chapter_index", position + 1)
        self.signals.chapter_ready.emit(chapter)

        if self.project_dir:
            try:
                save_chapter(self.project_dir, chapter_index, chapter)
            except Exception as e:
                self.signals.log_signal.emit(
                    "Pipeline", f"⚠️ 第{chapter_index}章保存失败: {e}")

        total = max(self._total_chapters, 1)
        pct = int((self._chapter_completed_count / total) * 100)
        self.signals.overall_progress.emit(25 + int(pct * 0.35))  # 章节阶段 25%-60%
        self.signals.chapter_progress.emit(chapter_index, 100, "完成")

        self.signals.log_signal.emit(
            "Pipeline",
            f"✅ 第{chapter_index}章完成 ({chapter.get('word_count', 0)}字)，"
            f"{self._chapter_completed_count}/{total}")

        if self._pending_chapter_workers <= 0:
            self._on_all_chapters_complete()

    def _on_all_chapters_complete(self):
        """所有章节生成完成，进入质量评估。"""
        if self._finalize_pause_if_requested():
            return
        self.signals.stage_completed.emit("章节生成")
        self.signals.log_signal.emit(
            "Pipeline", f"✅ 全部 {self._chapter_completed_count} 章生成完成，进入质量评估...")
        # 续写场景只评估新章节
        new_only = bool(getattr(self, "_continuation_new_indices", None))
        self._evaluate_chapters(new_only=new_only)

    def _evaluate_chapters(self, new_only: bool = False):
        """Step 3: 质量评估。"""
        if self._finalize_pause_if_requested():
            return
        self.current_stage = "quality_evaluation"
        self.signals.stage_started.emit("质量评估")
        self.signals.log_signal.emit("Pipeline", "🔍 [3/5] 质量评估Agent 启动...")

        agent = QualityEvaluatorAgent(self.llm)
        agent.log_signal.connect(lambda name, msg: self.signals.log_signal.emit(name, msg))

        threshold = self.config.get("quality_threshold", 7.0)
        needs_revision = []
        passed = []

        outline_detail_map = {}
        if hasattr(self, "_outline_for_chapters") and self._outline_for_chapters:
            for ch in self._outline_for_chapters.get("chapters", []):
                idx = ch.get("chapter_index")
                if idx is not None:
                    outline_detail_map[idx] = ch

        if new_only and hasattr(self, "_continuation_new_indices") and self._continuation_new_indices:
            chapters_to_eval = [c for c in self.chapters
                                if c.get("chapter_index") in self._continuation_new_indices]
        else:
            chapters_to_eval = self.chapters

        total_to_eval = len(chapters_to_eval)
        self.signals.log_signal.emit(
            "Pipeline", f"评估范围: {total_to_eval} 章" + ("（仅新章节）" if new_only else ""))

        for i, chapter in enumerate(chapters_to_eval):
            if self._finalize_pause_if_requested():
                return
            chapter_index = chapter.get("chapter_index", i + 1)
            if chapter_index in outline_detail_map:
                chapter_outline = outline_detail_map[chapter_index]
            else:
                outline = self.world_view.get("chapter_outline", [])
                coarse_idx = chapter_index - 1
                chapter_outline = outline[coarse_idx] if coarse_idx < len(outline) else {}

            self.signals.log_signal.emit("Pipeline", f"评估中: 第{chapter_index}章...")

            try:
                evaluation = agent.run({
                    "content": chapter.get("content", ""),
                    "title": chapter.get("title", ""),
                    "chapter_index": chapter_index,
                    "world_view": self.world_view,
                    "chapter_outline": chapter_outline,
                    "summary": chapter.get("summary", ""),
                    "target_length": self._chapter_length,
                    "consistency_rules": self._get_consistency_rules(),
                })

                self.evaluations[chapter_index] = evaluation
                self.signals.evaluation_ready.emit(evaluation)

                if evaluation.get("pass", False):
                    passed.append(chapter_index)
                    self.signals.chapter_progress.emit(chapter_index, 100, "评估通过")
                else:
                    # 仅字数 hard 硬伤（且 LLM 未挑出非字数问题）：patch 只能
                    # 局部修改，无法改变篇幅，进修订循环只会空转 3 轮 → 跳过
                    only_word_count = NovelPipeline._only_word_count_hard(evaluation)
                    if only_word_count:
                        self.signals.log_signal.emit(
                            "Pipeline",
                            f"第{chapter_index}章仅存在字数偏离问题"
                            f"（patch 修订无法修复篇幅），保留当前版本，跳过修订循环")
                        passed.append(chapter_index)
                        self.signals.chapter_progress.emit(
                            chapter_index, 100, "字数偏离，跳过修订")
                    else:
                        needs_revision.append({
                            "chapter_index": chapter_index,
                            "evaluation": evaluation,
                            "round": 1
                        })
                        self.signals.chapter_progress.emit(chapter_index, 100, "需修订")

            except Exception as e:
                self.signals.log_signal.emit("Pipeline", f"⚠️ 第{chapter_index}章评估异常: {e}")

            stage_progress = int(((i + 1) / total_to_eval) * 100) if total_to_eval else 100
            overall = 60 + int(stage_progress * 0.15)
            self.signals.overall_progress.emit(overall)

        if self._finalize_pause_if_requested():
            return

        self.signals.stage_completed.emit("质量评估")
        self.signals.log_signal.emit(
            "Pipeline",
            f"✅ 评估完成：通过 {len(passed)} 章，需修订 {len(needs_revision)} 章"
        )

        if needs_revision:
            self._revision_queue = needs_revision
            self._run_revisions()
        else:
            self._adapt_chapters()


    @staticmethod
    def _fuzzy_find(text: str, anchor: str) -> int:
        """在 text 里忽略空白与全半角标点差异地查找 anchor。"""
        import re

        def _normalize(s: str) -> str:
            s = re.sub(r"\s+", "", s)
            full = "，。！？；：“”‘’（）【】《》"
            half = ",.!?;:\"\"''()[]<>"
            trans = str.maketrans(full, half)
            return s.translate(trans)

        norm_text = _normalize(text)
        norm_anchor = _normalize(anchor)
        if not norm_anchor:
            return -1
        idx = norm_text.find(norm_anchor)
        if idx == -1:
            return -1
        ti = 0
        for ni in range(len(norm_text)):
            if ti >= len(text):
                break
            if norm_text[ni] == _normalize(text[ti:ti + 1]):
                if ni == idx:
                    return ti
                ti += 1
        return -1

    @staticmethod
    def _apply_patches(content: str, patches: list, chapter_index: int) -> tuple:
        """把 patch 列表应用到 content 上。"""
        applied = []
        failed = []
        log_entries = []
        new_content = content

        for patch in patches:
            anchor = (patch.get("anchor") or "").strip()
            replacement = (patch.get("replacement") or "").strip()
            reason = patch.get("reason", "")
            if not anchor:
                failed.append(patch)
                continue

            pos = new_content.find(anchor)
            if pos == -1:
                pos = NovelPipeline._fuzzy_find(new_content, anchor)
            if pos == -1:
                failed.append(patch)
                continue

            new_content = (new_content[:pos] + replacement
                           + new_content[pos + len(anchor):])
            applied.append(patch)
            log_entries.append({
                "reason": reason,
                "anchor": anchor[:40],
                "replacement_len": len(replacement),
            })

        return new_content, applied, failed, log_entries

    @staticmethod
    def _has_word_count_hard(evaluation: dict) -> bool:
        """评估结果中是否存在"字数 hard 硬伤"（patch 局部修订无法修复篇幅）。"""
        for i in evaluation.get("rule_issues", []):
            if i.get("severity") == "hard" and i.get("type") == "word_count":
                return True
        return False

    @staticmethod
    def _only_word_count_hard(evaluation: dict) -> bool:
        """是否仅存在字数 hard 硬伤、无其他需修订的问题（应直接跳过修订循环）。

        注意：字数硬伤一旦存在，QualityEvaluatorAgent 会因 hard_count>0 强制
        pass=False，而 patch 修订又无法改变篇幅——进修订循环只会空转轮次。
        因此只要"非字数类问题"为空，就跳过；仅当 LLM 挑出实质性问题时才进
        修订队列（且修订轮内会限制轮数，见 _revise_worker）。
        """
        if not NovelPipeline._has_word_count_hard(evaluation):
            return False
        # 存在非字数的 hard 硬伤（如禁用句式）→ 仍需修订
        for i in evaluation.get("rule_issues", []):
            if i.get("severity") == "hard" and i.get("type") != "word_count":
                return False
        # LLM 提出过非字数类问题 → 仍需修订
        llm_issues = [
            i for i in evaluation.get("issues", [])
            if i.get("source") != "rule_checker"
        ]
        return not llm_issues

    def _apply_revision_result(self, content: str, result: dict,
                               chapter_index: int, round_num: int) -> tuple:
        """根据 RevisionAgent 输出决定如何更新内容。"""
        if result.get("_fallback_full_rewrite"):
            fallback = result.get("_fallback_content", "")
            if not fallback or len(fallback) < 50:
                self.signals.log_signal.emit(
                    "Pipeline",
                    f"第{chapter_index}章第{round_num}轮：回退内容为空，保留原文")
                return content, [], [], []
            self.signals.log_signal.emit(
                "Pipeline",
                f"第{chapter_index}章第{round_num}轮：模型回退到全文重写")
            return fallback, [], [], []

        patches = result.get("patches", [])
        if not patches:
            if result.get("no_change"):
                self.signals.log_signal.emit(
                    "Pipeline",
                    f"第{chapter_index}章第{round_num}轮：模型判断无需修改")
            return content, [], [], []

        new_content, applied, failed, log_entries = self._apply_patches(
            content, patches, chapter_index)

        total = len(patches)
        success_rate = len(applied) / total if total else 0

        self.signals.log_signal.emit(
            "Pipeline",
            f"第{chapter_index}章第{round_num}轮："
            f"{len(applied)}/{total} patch 命中"
            + (f"，{len(failed)} 失败" if failed else ""))

        if success_rate < 0.5 and total >= 2:
            self.signals.log_signal.emit(
                "Pipeline",
                f"⚠️ 第{chapter_index}章第{round_num}轮 patch 命中率过低"
                f"（{success_rate:.0%}），回退到全文重写")
            fallback_content = self._fallback_full_rewrite(
                content, result, chapter_index, round_num)
            return fallback_content, [], [], []

        return new_content, applied, failed, log_entries

    def _fallback_full_rewrite(self, content: str, result: dict,
                                chapter_index: int, round_num: int) -> str:
        """全文重写回退：保留清理后的原文。"""
        import re
        cleaned = re.sub(r"<!--REVISION:[^>]*?-->", "", content)
        cleaned = re.sub(r"<!--NO_CHANGE-->", "", cleaned).strip()
        self.signals.log_signal.emit(
            "Pipeline",
            f"第{chapter_index}章第{round_num}轮：全文重写回退，保留清理后的原文"
            "（建议手动修改后重跑评估）")
        return cleaned

    def _run_revisions(self):
        """Step 4: 修订循环（并行：不同章节同时修订，受 concurrency 限制）"""
        if self._finalize_pause_if_requested():
            return
        if not self._revision_queue:
            self._adapt_chapters()
            return

        self.current_stage = "revision"
        self.signals.stage_started.emit("回流修订")
        self.signals.log_signal.emit(
            "Pipeline",
            f"🔄 [4/5] 回流修订Agent 启动（并行 {self.config.get('concurrency', 2)} 路）...")

        max_rounds = self.config.get("max_revision_rounds", 3)
        next_round_queue = []
        queue_lock = threading.Lock()

        # 过滤：跳过缺失章节 / 手动编辑章节
        items = []
        for item in self._revision_queue:
            chapter_index = item["chapter_index"]
            chapter = next((c for c in self.chapters
                            if c.get("chapter_index") == chapter_index), None)
            if not chapter:
                continue
            if chapter.get("manually_edited"):
                self.signals.log_signal.emit(
                    "Pipeline",
                    f"第{chapter_index}章已标记为手动编辑，跳过修订以保留作者修改")
                continue
            items.append((item, chapter))

        if not items:
            self._revision_queue = []
            self.signals.stage_completed.emit("回流修订")
            self.signals.log_signal.emit("Pipeline", "✅ 全部修订完成")
            self.signals.overall_progress.emit(90)
            self._adapt_chapters()
            return

        semaphore = threading.Semaphore(self.config.get("concurrency", 2))

        def _revise_worker(item: dict, chapter: dict):
            """单个章节的一轮修订（修订 + 按需重评），在子线程运行。"""
            chapter_index = item["chapter_index"]
            evaluation = item["evaluation"]
            round_num = item["round"]
            try:
                with semaphore:
                    self.signals.log_signal.emit(
                        "Pipeline", f"修订第{chapter_index}章（第{round_num}轮）...")

                    issues = evaluation.get("issues", [])
                    highlights = evaluation.get("highlights", [])
                    previous_patches = chapter.get("revision_log", [])

                    agent = RevisionAgent(self.llm)
                    agent.log_signal.connect(
                        lambda name, msg: self.signals.log_signal.emit(name, msg))

                    result = agent.run({
                        "content": chapter.get("content", ""),
                        "issues": issues,
                        "highlights": highlights,
                        "world_view": self.world_view,
                        "chapter_index": chapter_index,
                        "current_round": round_num,
                        "max_rounds": max_rounds,
                        "previous_patches": previous_patches,
                    })

                    revised_content, applied, failed, log_entries = \
                        self._apply_revision_result(chapter.get("content", ""),
                                                    result, chapter_index, round_num)

                    chapter["content"] = revised_content
                    chapter["word_count"] = len(revised_content)
                    chapter["revised"] = True
                    chapter["revision_rounds"] = round_num
                    chapter.setdefault("revision_log", [])
                    chapter["revision_log"].extend(log_entries)

                    result["content"] = revised_content
                    result["applied_count"] = len(applied)
                    result["failed_count"] = len(failed)
                    self.signals.revision_ready.emit(result)

                    if self.project_dir:
                        save_chapter(self.project_dir, chapter_index, chapter)

                    if round_num < max_rounds and result.get("revised", False):
                        eval_agent = QualityEvaluatorAgent(self.llm)
                        outline = self.world_view.get("chapter_outline", [])
                        ch_idx = chapter_index - 1
                        chapter_outline = outline[ch_idx] if ch_idx < len(outline) else {}

                        new_eval = eval_agent.run({
                            "content": chapter["content"],
                            "title": chapter.get("title", ""),
                            "chapter_index": chapter_index,
                            "world_view": self.world_view,
                            "chapter_outline": chapter_outline,
                            "summary": chapter.get("summary", ""),
                            "target_length": self._chapter_length,
                            "consistency_rules": self._get_consistency_rules(),
                        })

                        prev_score = evaluation.get("overall_score", 0)
                        new_score = new_eval.get("overall_score", 0)
                        if new_eval.get("pass", False):
                            self.signals.log_signal.emit(
                                "Pipeline",
                                f"第{chapter_index}章修订后通过！")
                        elif NovelPipeline._has_word_count_hard(new_eval):
                            # 字数硬伤 patch 修不了篇幅，继续只会空转轮次 → 停止
                            self.signals.log_signal.emit(
                                "Pipeline",
                                f"第{chapter_index}章修订后仍存在字数硬伤"
                                f"（patch 无法修复篇幅），停止修订")
                        elif (result.get("applied_count", 0) == 0
                              or new_score <= prev_score + 0.5):
                            # 收敛判断：本轮 patch 一个都没命中（改了等于没改），
                            # 或修订后分数无实质提升 → 修订已停滞，提前停止
                            self.signals.log_signal.emit(
                                "Pipeline",
                                f"第{chapter_index}章修订后分数无提升"
                                f"（{prev_score}→{new_score}），判定收敛，停止修订")
                        else:
                            with queue_lock:
                                next_round_queue.append({
                                    "chapter_index": chapter_index,
                                    "evaluation": new_eval,
                                    "round": round_num + 1
                                })
                    elif round_num >= max_rounds:
                        self.signals.log_signal.emit(
                            "Pipeline",
                            f"⚠️ 第{chapter_index}章已达最大修订轮数({max_rounds})，保留当前版本")

                    self.signals.chapter_progress.emit(
                        chapter_index, 100, f"修订完成(R{round_num})")
            except Exception as e:
                self.signals.log_signal.emit(
                    "Pipeline", f"⚠️ 第{chapter_index}章修订异常: {e}")

        threads = [
            threading.Thread(target=_revise_worker, args=(item, chapter), daemon=True)
            for item, chapter in items
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 修订期间用户可能请求暂停：join 后检查安全边界
        if self._finalize_pause_if_requested():
            return

        self._revision_queue = next_round_queue

        if self._revision_queue:
            self._run_revisions()
        else:
            self.signals.stage_completed.emit("回流修订")
            self.signals.log_signal.emit("Pipeline", "✅ 全部修订完成")
            self.signals.overall_progress.emit(90)
            self._adapt_chapters()

    def _adapt_chapters(self):
        """Step 5: 多平台适配"""
        if self._finalize_pause_if_requested():
            return
        self.current_stage = "adaptation"
        self.signals.stage_started.emit("多平台适配")
        self.signals.log_signal.emit("Pipeline", "📱 [5/5] 多平台适配Agent 启动...")

        agent = PlatformAdapterAgent(self.llm)
        agent.log_signal.connect(lambda name, msg: self.signals.log_signal.emit(name, msg))

        platform = "通用网文格式"
        adapted_count = 0

        for chapter in self.chapters:
            if self._finalize_pause_if_requested():
                return
            chapter_index = chapter.get("chapter_index", 0)
            self.signals.log_signal.emit("Pipeline", f"适配第{chapter_index}章...")

            try:
                result = agent.run({
                    "content": chapter.get("content", ""),
                    "title": chapter.get("title", ""),
                    "chapter_index": chapter_index,
                    "platform": platform
                })

                self.adaptations[chapter_index] = result
                self.signals.adaptation_ready.emit(result)
                adapted_count += 1

            except Exception as e:
                self.signals.log_signal.emit("Pipeline", f"⚠️ 第{chapter_index}章适配异常: {e}")

            overall = 90 + int(((adapted_count) / len(self.chapters)) * 10)
            self.signals.overall_progress.emit(overall)

        if self._finalize_pause_if_requested():
            return

        self.signals.stage_completed.emit("多平台适配")
        self.signals.log_signal.emit("Pipeline", f"✅ 适配完成（{adapted_count}章）")
        self._finish_pipeline()

    def _finish_pipeline(self):
        """流水线完成，汇总结果"""
        self.is_running = False
        self.current_stage = "completed"
        self.signals.overall_progress.emit(100)

        total_words = sum(c.get("word_count", 0) for c in self.chapters)
        total_count = len(self.chapters)

        avg_score = 0
        if self.evaluations:
            scores = [e.get("overall_score", 0) for e in self.evaluations.values()]
            avg_score = sum(scores) / len(scores) if scores else 0

        previous_summary = (
            load_project_summary(self.project_dir) if self.project_dir else {})

        is_continuation = (hasattr(self, "_continuation_new_indices")
                           and self._continuation_new_indices)
        if is_continuation:
            batch_info = {
                "batch_number": self._continuation_batch,
                "guidance": self._continuation_guidance,
                "chapter_range": (f"{self._continuation_new_indices[0]}-"
                                  f"{self._continuation_new_indices[-1]}"),
                "chapter_count": len(self._continuation_new_indices),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            update_project_batches(self.project_dir, batch_info)

        if is_continuation:
            status = "generating"
        else:
            status = "completed"

        summary = {
            **previous_summary,
            "title": self.world_view.get("title", ""),
            "chapter_count": total_count,
            "chapters_count": total_count,
            "total_words": total_words,
            "avg_quality_score": round(avg_score, 1),
            "project_dir": str(self.project_dir) if self.project_dir else "",
            "status": status,
            "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        if self.project_dir:
            save_project_summary(self.project_dir, summary)
            try:
                snap = build_timeline_snapshot(self.project_dir)
                save_timeline_snapshot(self.project_dir, snap)
            except Exception:
                pass

        self.signals.log_signal.emit("Pipeline", "🎉 流水线完成！")
        self.signals.log_signal.emit(
            "Pipeline",
            f"📊 统计: {total_count}章 | {total_words:,}字 | 均分{avg_score:.1f}")
        self.signals.pipeline_finished.emit(summary)

    def pause_and_save(self) -> bool:
        """请求在当前安全边界暂停，并把已完成内容落盘。"""
        if not self.is_running:
            return False
        if self._pause_requested:
            return True

        self._pause_requested = True
        self._save_pause_summary(final=False)
        self.signals.log_signal.emit(
            "Pipeline", "已请求暂停：当前模型调用完成后将保存并停止后续步骤")

        if self.current_stage == "chapter_generation" and self._pending_chapter_workers == 0:
            self._finalize_pause_if_requested()
        return True

    def _save_pause_summary(self, final: bool) -> None:
        """把暂停状态合并写入项目摘要，保留原始创作参数。"""
        if not self.project_dir:
            return
        summary = load_project_summary(self.project_dir)

        saved_chapters = (list(self._chapter_results.values())
                          if hasattr(self, "_chapter_results")
                          else self.chapters)
        total_needed = self._chapter_count or summary.get("chapter_count", 0)
        all_chapters_done = len(saved_chapters) >= total_needed > 0
        all_evaluated = all_chapters_done and len(self.evaluations) >= total_needed

        if all_chapters_done and all_evaluated:
            status = "completed"
        else:
            status = "paused"

        summary.update({
            "title": (self.world_view or {}).get("title", summary.get("title", "")),
            "chapter_count": self._chapter_count or summary.get("chapter_count", 0),
            "chapter_length": getattr(self, "_chapter_length", None)
                or summary.get("chapter_length", 3000),
            "status": status,
            "paused_stage": self.current_stage,
            "paused_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        if final:
            summary["chapters_count"] = len(saved_chapters)
            summary["total_words"] = sum(
                chapter.get("word_count", 0) for chapter in saved_chapters)
        save_project_summary(self.project_dir, summary)

    def _finalize_pause_if_requested(self) -> bool:
        """在安全边界结束暂停；返回是否已经停止当前流水线。"""
        if not self._pause_requested:
            return False
        if getattr(self, "_world_view_reviewing", False):
            return False
        if self.current_stage == "continuation_outline":
            return False
        if self.current_stage == "chapter_generation" and self._pending_chapter_workers > 0:
            return False

        self._save_pause_summary(final=True)
        self.is_running = False
        paused_stage = self.current_stage
        self.current_stage = "paused"
        self.signals.log_signal.emit("Pipeline", "✅ 项目已暂停并保存，可在项目库继续生成")
        saved_chapters = (list(self._chapter_results.values())
                          if hasattr(self, "_chapter_results")
                          else self.chapters)
        self.signals.pipeline_finished.emit({
            "paused": True,
            "title": (self.world_view or {}).get("title", ""),
            "chapters_count": len(saved_chapters),
            "total_words": sum(
                chapter.get("word_count", 0) for chapter in saved_chapters),
            "stage": paused_stage,
        })
        return True

    def _handle_error(self, message: str):
        """处理错误（记录失败阶段供重试用）"""
        self._failed_stage = self.current_stage
        self.is_running = False
        self.signals.stage_error.emit(self.current_stage, message)
        self.signals.log_signal.emit("Pipeline", f"❌ {message}")
        self.signals.pipeline_finished.emit({"error": message, "stage": self.current_stage})

    def stop(self):
        """停止流水线（尽力而为）"""
        self.is_running = False
        self.signals.log_signal.emit("Pipeline", "⏹ 流水线已手动停止")

    # ===== 阶段重试 =====

    def retry_world_view(self):
        """重新生成世界观（从审阅对话框或错误状态调用）"""
        if not self._last_inspiration:
            self.signals.log_signal.emit("Pipeline", "⚠️ 无法重试：缺少灵感输入")
            return False
        self._pending_world_view = None
        self._world_view_reviewing = False
        self._failed_stage = None
        self.is_running = True
        self.signals.log_signal.emit("Pipeline", "🔄 重新生成世界观...")
        import threading
        self._pipeline_thread = threading.Thread(
            target=self._build_world_view,
            args=(self._last_inspiration, self._last_chapter_count or 5),
            daemon=True,
        )
        self._pipeline_thread.start()
        return True

    def retry_outline(self):
        """重新生成大纲（从审阅对话框或错误状态调用）"""
        if not self.world_view:
            self.signals.log_signal.emit("Pipeline", "⚠️ 无法重试：缺少世界观数据")
            return False
        self._pending_outline = None
        self._outline_reviewing = False
        self._failed_stage = None
        self.is_running = True
        self.signals.log_signal.emit("Pipeline", "🔄 重新生成大纲...")
        import threading
        self._pipeline_thread = threading.Thread(
            target=self._build_outline,
            args=(self.world_view,),
            daemon=True,
        )
        self._pipeline_thread.start()
        return True

    def retry_current_stage(self):
        """重试当前失败的阶段（根据 _failed_stage 路由）"""
        stage = self._failed_stage or self.current_stage
        if stage in ("world_building",):
            return self.retry_world_view()
        elif stage in ("outline_generation",):
            return self.retry_outline()
        else:
            self.signals.log_signal.emit(
                "Pipeline", f"⚠️ 阶段 '{stage}' 不支持重试，请重新开始流水线")
            return False




    @staticmethod
    def _get_chapter_index(chapter: dict, fallback: int = None):
        """读取并标准化章节序号，兼容模型返回的数字字符串。"""
        if not isinstance(chapter, dict):
            return fallback
        value = chapter.get("chapter_index", chapter.get("chapter", fallback))
        try:
            return int(value)
        except (TypeError, ValueError):
            return value if value is not None else fallback

    def _outline_is_complete(self, outline: dict, coarse_outline: list) -> bool:
        """确认详细大纲覆盖所有章节，且每章包含可用的剧情细纲。"""
        if not isinstance(outline, dict) or not isinstance(coarse_outline, list):
            return False
        detailed_chapters = outline.get("chapters")
        if not isinstance(detailed_chapters, list):
            return False

        expected = {
            self._get_chapter_index(chapter, position)
            for position, chapter in enumerate(coarse_outline, start=1)
            if isinstance(chapter, dict)
        }
        detailed = {
            self._get_chapter_index(chapter, position)
            for position, chapter in enumerate(detailed_chapters, start=1)
            if isinstance(chapter, dict)
            and str(chapter.get("plot_detail", "")).strip()
        }
        return bool(expected) and expected.issubset(detailed)

    def _resume_chapter_generation(self, existing: dict):
        """从已保存的大纲继续，只生成尚未落盘的章节。"""
        self.signals.log_signal.emit(
            "Pipeline", f"▶️ _resume_chapter_generation 启动，"
                        f"world_view={'有' if self.world_view else '无'}, "
                        f"outline={'有' if self.outline else '无'}, "
                        f"existing={len(existing)} 章")
        coarse_outline = self.world_view.get("chapter_outline", [])
        total_needed = len(coarse_outline)
        outline_chapters = self.outline.get("chapters", []) if self.outline else []
        outline_detail_map = {
            self._get_chapter_index(chapter, position): chapter
            for position, chapter in enumerate(outline_chapters, start=1)
            if isinstance(chapter, dict)
        }

        existing = {
            self._get_chapter_index(chapter, index): chapter
            for index, chapter in existing.items()
            if isinstance(chapter, dict)
        }

        missing = [
            self._get_chapter_index(chapter, position)
            for position, chapter in enumerate(coarse_outline, start=1)
            if self._get_chapter_index(chapter, position) not in existing
        ]

        self.chapters = [existing[index] for index in sorted(existing)]
        self._chapter_count = total_needed
        self._total_chapters = total_needed
        # _gen_chapter_worker / _on_chapter_complete 使用 0 基位置作为缓存键。
        self._chapter_results = {
            index - 1: chapter for index, chapter in existing.items()
            if isinstance(index, int)
        }
        self._chapter_completed_count = len(self._chapter_results)
        self._completed_chapters = self._chapter_completed_count
        self._pending_chapter_workers = len(missing)

        if not missing:
            self.signals.log_signal.emit(
                "Pipeline", f"✅ 项目全部 {total_needed} 章均已生成，继续后续处理")
            self._on_all_chapters_complete()
            return

        self.current_stage = "chapter_generation"
        self.signals.stage_started.emit("章节生成")
        self.signals.log_signal.emit(
            "Pipeline",
            f"▶️ 从章节断点继续：已完成 {len(existing)}/{total_needed} 章，"
            f"缺失: {missing}")

        import threading
        self._semaphore = threading.Semaphore(self.config.get("concurrency", 2))
        self._chapter_lock = threading.Lock()

        for position, outline_entry in enumerate(coarse_outline, start=1):
            chapter_index = self._get_chapter_index(outline_entry, position)
            if chapter_index not in missing:
                continue

            previous = existing.get(chapter_index - 1, {})
            outline_chapter = outline_detail_map.get(chapter_index, {})
            input_data = {
                "world_view": self.world_view,
                "chapter_outline": outline_entry,
                "chapter_index": chapter_index,
                "target_length": self._chapter_length,
                "previous_chapter_summary": previous.get("summary", ""),
                "outline_chapter": outline_chapter,
                "outline_context": self._build_outline_context(),
                "character_arcs": self.outline.get("character_arcs", {}),
            }
            threading.Thread(
                target=self._gen_chapter_worker,
                args=(chapter_index - 1, input_data),
                daemon=True,
            ).start()






    def resume_from_project(self, project_dir):
        """
        从历史项目目录恢复运行：缺大纲先生成大纲，否则只补缺失章节。
        """
        from pathlib import Path as _Path
        project_dir = _Path(project_dir)

        title = project_dir.name
        self.signals.log_signal.emit(
            "Pipeline", f"🔁 恢复项目: {project_dir.name}")

        world_view = load_world_view(project_dir)
        if not world_view or not isinstance(world_view, dict):
            raise RuntimeError("项目 world_view.json 缺失或损坏")

        coarse_outline = world_view.get("chapter_outline", [])
        if not isinstance(coarse_outline, list) or not coarse_outline:
            raise RuntimeError("项目 world_view.json 中没有可用的章节大纲")

        existing = load_all_chapters_map(project_dir)
        outline = load_outline(project_dir)
        project_summary = load_project_summary(project_dir)

        if not self.llm:
            self.initialize()
        self.is_running = True
        self._pause_requested = False
        self.project_dir = project_dir
        self.world_view = world_view
        self.outline = outline
        saved_length = project_summary.get("chapter_length")
        try:
            self._chapter_length = int(saved_length)
        except (TypeError, ValueError):
            self._chapter_length = self.config.get("default_chapter_length", 3000)

        if not self._outline_is_complete(outline, coarse_outline):
            self.outline = None
            self.signals.log_signal.emit(
                "Pipeline", "▶️ 断点位于大纲生成：未找到完整 outline.json，开始恢复大纲")

            import threading
            self._pipeline_thread = threading.Thread(
                target=self._build_outline,
                args=(world_view,),
                kwargs={"resume_existing": existing},
                daemon=True,
            )
            self._pipeline_thread.start()
            return

        import threading
        def _resume_worker():
            try:
                self._resume_chapter_generation(existing)
            except Exception as e:
                self._handle_error(f"恢复章节生成异常: {e}")
        self._pipeline_thread = threading.Thread(
            target=_resume_worker,
            daemon=True,
        )
        self._pipeline_thread.start()

    def _merge_existing_chapters(self, existing: dict):
        """把已有章节预填进 self.chapters / self._chapter_results，用于续写场景。"""
        merged = {
            index - 1: chapter
            for index, chapter in existing.items()
            if isinstance(index, int)
        }
        self._chapter_results = merged
        self.chapters = [existing[index] for index in sorted(existing)
                         if isinstance(index, int)]
        self._chapter_completed_count = len(existing)
        self._completed_chapters = len(existing)

    def continue_from_project(self, project_dir, guidance: str,
                              batch_chapter_count: int = None,
                              chapter_length: int = None):
        """
        启动续写流程：仅生成"下一批"的新大纲，产出后暂停等待用户审阅。
        """
        from pathlib import Path as _Path
        import threading
        project_dir = _Path(project_dir)

        if not guidance or not guidance.strip():
            raise RuntimeError("续写指引不能为空")

        if self.is_running:
            self.signals.log_signal.emit("Pipeline", "⚠️ 流水线已在运行中")
            return
        if not self.llm:
            self.initialize()

        world_view = load_world_view(project_dir)
        if not world_view:
            raise RuntimeError("项目 world_view.json 缺失或损坏")

        project_summary = load_project_summary(project_dir)
        if batch_chapter_count is None:
            batch_chapter_count = self.config.get("default_chapter_count", 10)
        if chapter_length is None:
            saved_length = project_summary.get("chapter_length")
            try:
                chapter_length = int(saved_length)
            except (TypeError, ValueError):
                chapter_length = self.config.get("default_chapter_length", 3000)

        self.is_running = True
        self._pause_requested = False
        self.project_dir = project_dir
        self.world_view = world_view
        self._chapter_length = chapter_length
        self._continuation_guidance = guidance

        # 加载遗产包
        legacy = load_legacy_package(project_dir)
        self._continuation_legacy = legacy

        # 加载旧章节
        existing_chapters = load_all_chapters_map(project_dir)
        self._merge_existing_chapters(existing_chapters)

        # 生成批次号
        self._continuation_batch = get_next_batch_number(project_dir)

        self.signals.log_signal.emit(
            "Pipeline", f"🔁 续写项目: {project_dir.name} | 批次: {self._continuation_batch}")

        # 生成续写大纲
        self.current_stage = "continuation_outline"
        self.signals.stage_started.emit("续写大纲生成")
        self.signals.log_signal.emit("Pipeline", "📋 续写大纲生成中...")

        agent = ContinuationOutlineAgent(
            self.llm,
            temperature=self.config.get("outline_temperature", 0.7),
            max_tokens=self.config.get("outline_max_tokens", 8192),
        )
        agent.log_signal.connect(lambda name, msg: self.signals.log_signal.emit(name, msg))

        # 后台线程生成续写大纲，避免同步阻塞 HTTP 请求导致前端超时
        def _generate_outline():
            try:
                batch_outline = agent.run({
                    "legacy_package": legacy,
                    "guidance": guidance,
                    "batch_chapter_count": batch_chapter_count,
                })

                # 保存批次大纲
                save_batch_outline(project_dir, self._continuation_batch, batch_outline)
                self._continuation_outline = batch_outline
                self._outline_for_chapters = batch_outline

                # 计算本批章节范围
                batch_start = batch_outline.get("outline_meta", {}).get("chapter_start", 0)
                batch_count = batch_outline.get("outline_meta", {}).get("total_chapters", 0)
                self._continuation_new_indices = list(range(batch_start, batch_start + batch_count))
                self._continuation_old_count = batch_start - 1

                self.signals.continuation_outline_ready.emit(batch_outline)
                self.signals.stage_completed.emit("续写大纲生成")
                self.signals.log_signal.emit(
                    "Pipeline",
                    f"✅ 续写大纲生成完成：第 {batch_start}-{batch_start + batch_count - 1} 章 — 等待用户审阅")
            except Exception as e:
                self._handle_error(f"续写大纲生成异常: {e}")

        self._pipeline_thread = threading.Thread(
            target=_generate_outline, daemon=True)
        self._pipeline_thread.start()

    def _build_continuation_outline_context(self) -> dict:
        """构建供续写章节 agent 使用的大纲上下文"""
        if not self._outline_for_chapters:
            return {"consistency_rules": [], "all_chapters_summary": []}

        rules = self._outline_for_chapters.get("consistency_rules", [])
        all_summary = []
        for ch in self._outline_for_chapters.get("chapters", []):
            all_summary.append({
                "chapter_index": ch.get("chapter_index"),
                "title": ch.get("title", ""),
                "plot_detail": ch.get("plot_detail", ""),
                "foreshadowing": ch.get("foreshadowing", [])
            })

        return {
            "consistency_rules": rules,
            "global_arc": self._outline_for_chapters.get("global_arc", {}),
            "all_chapters_summary": all_summary
        }

    def confirm_world_view(self, reviewed_world_view: dict):
        """
        用户在 WorldViewReviewDialog 审阅确认后调用。
        """
        if not self.is_running and not getattr(self, "_world_view_reviewing", False):
            self.signals.log_signal.emit(
                "Pipeline", "⚠️ 流水线已停止，无法确认世界观")
            return

        self.world_view = reviewed_world_view
        self._pending_world_view = None
        self._world_view_reviewing = False

        if self.project_dir:
            save_world_view(self.project_dir, reviewed_world_view)
            try:
                summary = load_project_summary(self.project_dir)
                summary["title"] = reviewed_world_view.get("title", summary.get("title", ""))
                save_project_summary(self.project_dir, summary)
            except Exception:
                pass

        title = reviewed_world_view.get("title", "")
        self.signals.log_signal.emit(
            "Pipeline", f"▶️ 用户确认世界观《{title}》，启动大纲生成...")

        if self._finalize_pause_if_requested():
            return
        import threading
        self._pipeline_thread = threading.Thread(
            target=self._build_outline,
            args=(reviewed_world_view,),
            daemon=True,
        )
        self._pipeline_thread.start()

    def confirm_outline(self, reviewed_outline: dict):
        """
        用户在 OutlineReviewDialog 审阅确认后调用。
        用审阅过的大纲开始章节生成。
        """
        if not self.is_running and not getattr(self, "_outline_reviewing", False):
            self.signals.log_signal.emit(
                "Pipeline", "⚠️ 流水线已停止，无法确认大纲")
            return

        self.outline = reviewed_outline
        self._pending_outline = None
        self._outline_reviewing = False

        # 保存审阅后的大纲
        if self.project_dir:
            import json
            from pathlib import Path
            outline_path = Path(self.project_dir) / "outline.json"
            outline_path.write_text(
                json.dumps(reviewed_outline, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        ch_count = len(reviewed_outline.get("chapters", []))
        self.signals.log_signal.emit(
            "Pipeline", f"▶️ 用户确认大纲（{ch_count} 章），开始生成章节...")

        if self._finalize_pause_if_requested():
            return
        import threading
        if self._pending_resume_outline:
            # 恢复场景：只补缺失章节
            resume_existing = self._pending_resume_outline
            self._pending_resume_outline = None
            self._pipeline_thread = threading.Thread(
                target=self._resume_chapter_generation,
                args=(resume_existing,),
                daemon=True,
            )
        else:
            self._pipeline_thread = threading.Thread(
                target=self._generate_chapters,
                args=(self._chapter_length,),
                daemon=True,
            )
        self._pipeline_thread.start()

    def confirm_continuation(self, reviewed_outline: dict):
        """
        用户审阅确认后，用审阅过的大纲开始生成章节。
        """
        if not self.is_running:
            self.signals.log_signal.emit("Pipeline", "⚠️ 流水线已停止，无法启动章节生成")
            return

        # 兜底：审阅回传可能丢失 outline_meta（含章节范围），从已落盘的批次大纲恢复，
        # 否则后续 _generate_continuation_chapters 直接下标访问会抛 KeyError
        if not isinstance(reviewed_outline.get("outline_meta"), dict):
            saved = load_batch_outline(self.project_dir, self._continuation_batch)
            if isinstance(saved, dict) and isinstance(saved.get("outline_meta"), dict):
                reviewed_outline["outline_meta"] = saved.get("outline_meta")

        # 磁盘文件可能也被覆盖/损坏，依据已记录的本批章节范围重建
        if not isinstance(reviewed_outline.get("outline_meta"), dict):
            ch_count = len(reviewed_outline.get("chapters", []))
            batch_start = getattr(self, "_continuation_old_count", 0) + 1
            reviewed_outline["outline_meta"] = {
                "chapter_start": batch_start,
                "chapter_end": batch_start + max(ch_count - 1, 0),
                "total_chapters": ch_count,
            }

        self._continuation_outline = reviewed_outline
        self._outline_for_chapters = reviewed_outline
        save_batch_outline(
            self.project_dir, self._continuation_batch, reviewed_outline)

        start_idx = reviewed_outline.get("outline_meta", {}).get("chapter_start", 0)
        end_idx = reviewed_outline.get("outline_meta", {}).get("chapter_end", 0)
        self.signals.log_signal.emit(
            "Pipeline",
            f"▶️ 用户确认续写大纲，开始生成第 {start_idx}-{end_idx} 章...")

        import threading
        def _run_chapters():
            try:
                self._generate_continuation_chapters(reviewed_outline)
            except Exception as e:
                self._handle_error(f"续写章节生成异常: {e}")
        self._pipeline_thread = threading.Thread(
            target=_run_chapters, daemon=True)
        self._pipeline_thread.start()

    def _generate_continuation_chapters(self, outline: dict):
        """用审阅后的续写大纲并行生成章节。"""
        self.current_stage = "chapter_generation"
        self.signals.stage_started.emit("章节生成")

        meta = outline.get("outline_meta") or {}
        batch_start = meta.get("chapter_start", 1)
        chapter_count = meta.get("total_chapters", 0)
        existing_count = batch_start - 1

        self.signals.log_signal.emit(
            "Pipeline",
            f"✍️ [续写] 并行生成第 {batch_start}-{batch_start + chapter_count - 1} 章...")

        outline_context = self._build_continuation_outline_context()
        outline_detail_map = {
            ch.get("chapter_index"): ch
            for ch in outline.get("chapters", [])
        }

        existing_chapters = load_all_chapters_map(self.project_dir)
        self._merge_existing_chapters(existing_chapters)
        self._continuation_old_count = existing_count
        self._continuation_new_indices = list(range(batch_start, batch_start + chapter_count))

        import threading
        concurrency = self.config.get("concurrency", 3)
        self._semaphore = threading.Semaphore(concurrency)
        self._chapter_lock = threading.Lock()
        self._total_chapters = chapter_count
        self._pending_chapter_workers = chapter_count
        self._completed_chapters = 0

        for i, outline_entry in enumerate(outline.get("chapters", [])):
            chapter_index = outline_entry.get("chapter_index", batch_start + i)

            prev_summary = ""
            if i > 0 and (i - 1) in self._chapter_results:
                prev_summary = self._chapter_results[i - 1].get("summary", "")
            elif existing_count > 0:
                legacy_recent = self._continuation_legacy.get(
                    "recent_chapters", []) if self._continuation_legacy else []
                if legacy_recent:
                    prev_summary = legacy_recent[-1].get("summary", "")

            outline_ch = outline_detail_map.get(chapter_index, outline_entry)

            input_data = {
                "world_view": self.world_view,
                "chapter_outline": outline_entry,
                "chapter_index": chapter_index,
                "target_length": self._chapter_length,
                "previous_chapter_summary": prev_summary,
                "outline_chapter": outline_ch,
                "outline_context": outline_context,
                "character_arcs": self.outline.get("character_arcs", {}) if self.outline else {}
            }
            threading.Thread(
                target=self._gen_chapter_worker,
                args=(i, input_data),
                daemon=True,
            ).start()

    def discard_world_view(self):
        """用户取消世界观审阅时调用 — 取消本次生成，回到空闲。"""
        self.is_running = False
        self.current_stage = "idle"
        self._pending_world_view = None
        self._world_view_reviewing = False
        self.world_view = None
        self.signals.log_signal.emit(
            "Pipeline", "❌ 用户取消世界观审阅，本次生成已取消")

    def get_status(self) -> dict:
        """获取当前流水线状态（供Web面板轮询）"""
        return {
            "is_running": self.is_running,
            "current_stage": self.current_stage,
            "total_chapters": self._chapter_count,
            "completed_chapters": self._completed_chapters,
            "world_view": self.world_view,
            "outline": self.outline,
            "chapters": self.chapters,
            "evaluations": {str(k): v for k, v in self.evaluations.items()},
            "adaptations_count": len(self.adaptations),
            "project_dir": str(self.project_dir) if self.project_dir else None
        }

    def export_txt(self, output_path: str) -> bool:
        """导出txt"""
        if self.project_dir:
            return export_to_txt(self.project_dir, output_path)
        return False

    def export_markdown(self, output_path: str) -> bool:
        """导出Markdown"""
        if self.project_dir:
            return export_to_markdown(self.project_dir, output_path)
        return False
