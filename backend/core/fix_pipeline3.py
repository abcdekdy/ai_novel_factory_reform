import sys

with open(r'C:\Users\31561\Desktop\小说生成助手（新版）\backend\core\pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 剩余的方法
final_methods = r'''

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

    def confirm_continuation(self, reviewed_outline: dict):
        """
        用户审阅确认后，用审阅过的大纲开始生成章节。
        """
        if not self.is_running:
            self.signals.log_signal.emit("Pipeline", "⚠️ 流水线已停止，无法启动章节生成")
            return

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

        batch_start = outline.get("outline_meta", {}).get("chapter_start", 1)
        chapter_count = outline["outline_meta"].get("total_chapters", 0)
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
'''

# 找到插入位置
lines = content.split('\n')
insert_pos = len(lines)
for i in range(len(lines) - 1, -1, -1):
    if 'self._pipeline_thread.start()' in lines[i] and 'resume' in lines[i+1]:
        insert_pos = i + 1
        break

if insert_pos:
    result = lines[:insert_pos] + final_methods.split('\n') + lines[insert_pos:]
    with open(r'C:\Users\31561\Desktop\小说生成助手（新版）\backend\core\pipeline.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(result))
    print(f'Added methods after line {insert_pos}')
else:
    print('Could not find insert position')
