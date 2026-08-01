import sys

with open(r'C:\Users\31561\Desktop\小说生成助手（新版）\backend\core\pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 所有剩余的方法
all_methods = r'''

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
'''

# 找到插入位置
lines = content.split('\n')
insert_pos = None
for i, line in enumerate(lines):
    if "self._handle_error(f\"大纲生成异常: {e}\")" in line:
        insert_pos = i + 1
        break

if insert_pos:
    result = lines[:insert_pos] + all_methods.split('\n') + lines[insert_pos:]
    with open(r'C:\Users\31561\Desktop\小说生成助手（新版）\backend\core\pipeline.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(result))
    print(f'Added methods after line {insert_pos}')
else:
    print('Could not find insert position')
