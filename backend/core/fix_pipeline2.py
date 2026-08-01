import sys

with open(r'C:\Users\31561\Desktop\小说生成助手（新版）\backend\core\pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 剩余的方法
more_methods = r'''

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
        """Step 4: 修订循环"""
        if self._finalize_pause_if_requested():
            return
        if not self._revision_queue:
            self._adapt_chapters()
            return

        self.current_stage = "revision"
        self.signals.stage_started.emit("回流修订")
        self.signals.log_signal.emit("Pipeline", "🔄 [4/5] 回流修订Agent 启动...")

        max_rounds = self.config.get("max_revision_rounds", 3)
        next_round_queue = []

        for item in self._revision_queue:
            if self._finalize_pause_if_requested():
                return
            chapter_index = item["chapter_index"]
            evaluation = item["evaluation"]
            round_num = item["round"]

            chapter = next((c for c in self.chapters if c.get("chapter_index") == chapter_index), None)
            if not chapter:
                continue

            if chapter.get("manually_edited"):
                self.signals.log_signal.emit(
                    "Pipeline",
                    f"第{chapter_index}章已标记为手动编辑，跳过修订以保留作者修改")
                continue

            self.signals.log_signal.emit(
                "Pipeline", f"修订第{chapter_index}章（第{round_num}轮）...")

            issues = evaluation.get("issues", [])
            highlights = evaluation.get("highlights", [])
            previous_patches = chapter.get("revision_log", [])

            agent = RevisionAgent(self.llm)
            agent.log_signal.connect(
                lambda name, msg: self.signals.log_signal.emit(name, msg))

            try:
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

                    if not new_eval.get("pass", False):
                        next_round_queue.append({
                            "chapter_index": chapter_index,
                            "evaluation": new_eval,
                            "round": round_num + 1
                        })
                    else:
                        self.signals.log_signal.emit(
                            "Pipeline",
                            f"第{chapter_index}章修订后通过！")
                elif round_num >= max_rounds:
                    self.signals.log_signal.emit(
                        "Pipeline",
                        f"⚠️ 第{chapter_index}章已达最大修订轮数({max_rounds})，保留当前版本")

            except Exception as e:
                self.signals.log_signal.emit("Pipeline", f"⚠️ 第{chapter_index}章修订异常: {e}")

            self.signals.chapter_progress.emit(chapter_index, 100, f"修订完成(R{round_num})")

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
        """处理错误"""
        self.is_running = False
        self.signals.stage_error.emit(self.current_stage, message)
        self.signals.log_signal.emit("Pipeline", f"❌ {message}")
        self.signals.pipeline_finished.emit({"error": message, "stage": self.current_stage})

    def stop(self):
        """停止流水线（尽力而为）"""
        self.is_running = False
        self.signals.log_signal.emit("Pipeline", "⏹ 流水线已手动停止")
'''

# 找到插入位置
lines = content.split('\n')
insert_pos = None
for i, line in enumerate(lines):
    if "self._adapt_chapters()" in line and "else:" not in line:
        insert_pos = i + 1
        break

if insert_pos:
    result = lines[:insert_pos] + more_methods.split('\n') + lines[insert_pos:]
    with open(r'C:\Users\31561\Desktop\小说生成助手（新版）\backend\core\pipeline.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(result))
    print(f'Added methods after line {insert_pos}')
else:
    print('Could not find insert position')
