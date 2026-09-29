"""
候选稿评审 Agent（竞稿选优）
========================================
多人格竞稿模式下，每个人格为同一章各写一稿，由本 Agent 评分并选出中选稿。

设计要点
--------
1. **逐稿独立打分**：明确要求不受稿序影响，避免"先读到的分数高"。
2. **必须引用原文举证**：每稿要给出一段逐字引用作为评分依据，抑制空泛打分
   （参考 ainovel-cli 的 Editor 评审要求）。
3. **输出可降级**：任何解析失败 / 编号越界都回退到第 1 稿，绝不让评审环节
   把整条流水线拖垮——竞稿是锦上添花，不是关键路径。
4. **编号约定**：模型输出 `best_index` 按 **1 起** 编号（与提示一致），本模块
   统一换算为 **0 起** 后再返回，调用方拿到的一定是可直接下标的值。
"""

from core.base_agent import BaseAgent

SYSTEM_PROMPT = """你是一位资深网文主编，负责在多位作者的候选稿中选出最好的一稿。

## 评审维度（每项 1-10 分）

1. **情节完整度**：大纲要求的关键事件是否全部覆盖，有无遗漏
2. **一致性**：人物行为、世界观设定是否与给定设定冲突
3. **文笔**：语言质感、描写生动度、对话区分度
4. **节奏**：叙事张弛、有无拖沓或仓促
5. **章尾钩子**：结尾是否具备让人继续读下去的悬念力度

## 评审要求

- **逐稿独立打分**，不要受候选稿出现顺序的影响
- 每稿的 `evidence` 必须**逐字引用**该稿正文中 >= 8 字的片段作为评分依据
- `total_score` 为五个维度的综合判断（不必是算术平均）
- 选出综合质量最高的一稿；若两稿接近，选更贴合大纲要求的那一稿

## 输出格式（严格 JSON，不要任何额外文字）

{
  "candidates": [
    {
      "index": 1,
      "persona": "候选稿的人格名",
      "total_score": 8.5,
      "dimensions": {"plot": 8, "consistency": 9, "prose": 8, "pacing": 9, "hook": 8},
      "evidence": "从该稿中逐字引用的片段",
      "comment": "一句话点评"
    }
  ],
  "best_index": 2,
  "reason": "为什么选它（50 字以内）",
  "revision_hint": "给中选稿的后续修改建议，没有则留空"
}

注意：`best_index` 使用**从 1 开始**的候选编号，与 `candidates[].index` 对应。"""


class JudgeAgent(BaseAgent):
    """竞稿评审 Agent —— 为多个候选稿打分并选出最优稿"""

    def __init__(self, llm_client):
        super().__init__("竞稿评审", llm_client)

    def run(self, input_data: dict) -> dict:
        """
        输入: {
            "candidates": [{"persona": str, "content": str}, ...],  # >= 2 稿
            "world_view": dict,
            "chapter_outline": dict,
            "chapter_index": int,
            "target_length": int,
        }
        输出: {
            "chapter_index": int,
            "best_index": int,      # 0 起，保证落在候选范围内
            "scores": [...],        # 模型给出的逐稿评分（可能为空）
            "reason": str,
            "revision_hint": str,
            "persona": str,         # 中选稿的人格名
            "error": str,           # 仅评审失败时存在
        }
        """
        candidates = input_data.get("candidates", []) or []
        chapter_index = input_data.get("chapter_index", 1)

        self.set_status("running")
        self.set_progress(10)

        if not candidates:
            return self._fallback(chapter_index, candidates, "无候选稿")
        if len(candidates) == 1:
            return {
                "chapter_index": chapter_index,
                "best_index": 0,
                "scores": [],
                "reason": "仅一稿，无需评选",
                "revision_hint": "",
                "persona": candidates[0].get("persona", ""),
            }

        self.log(f"开始评审第{chapter_index}章 {len(candidates)} 份候选稿...")

        chapter_outline = input_data.get("chapter_outline", {}) or {}
        world_view = input_data.get("world_view", {}) or {}
        target_length = input_data.get("target_length", 3000)

        try:
            user_prompt = self._build_user_prompt(
                candidates, chapter_outline, world_view, chapter_index,
                target_length)

            self.set_progress(40)
            raw = self.call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.2,   # 评审要稳定，低温度
                max_tokens=4096,
            )
            self.set_progress(80)

            parsed = self.parse_json_response(raw)
            if not isinstance(parsed, dict):
                return self._fallback(chapter_index, candidates, "评审结果不是 JSON 对象")

            best = self._normalize_best_index(parsed.get("best_index"), len(candidates))
            scores = parsed.get("candidates", [])
            if not isinstance(scores, list):
                scores = []

            reason = str(parsed.get("reason", "") or "")
            self.set_progress(100)
            self.set_status("success")
            self.log(
                f"✅ 第{chapter_index}章评审完成：中选第 {best + 1} 稿"
                f"「{candidates[best].get('persona', '')}」— {reason[:50]}")

            return {
                "chapter_index": chapter_index,
                "best_index": best,
                "scores": scores,
                "reason": reason,
                "revision_hint": str(parsed.get("revision_hint", "") or ""),
                "persona": candidates[best].get("persona", ""),
            }

        except Exception as e:
            self.set_status("error")
            self.log(f"❌ 评审失败: {e}")
            return self._fallback(chapter_index, candidates, str(e))

    # ------------------------------------------------------------------
    #  内部
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_best_index(raw, count: int) -> int:
        """把模型给的编号换算成 0 起下标；越界一律回退到 0。"""
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return 0
        # 提示里要求 1 起编号；模型偶尔会给 0 基，视作 0 基处理
        index = value if value == 0 else value - 1
        return index if 0 <= index < count else 0

    def _fallback(self, chapter_index: int, candidates: list, reason: str) -> dict:
        """评审不可用时保底选用第 1 稿，保证章节生成不被评审环节拖垮。"""
        self.log(f"⚠️ 评审未产出可用结论（{reason}），保底选用第 1 稿")
        return {
            "chapter_index": chapter_index,
            "best_index": 0,
            "scores": [],
            "reason": f"评审降级：{reason}",
            "revision_hint": "",
            "persona": candidates[0].get("persona", "") if candidates else "",
            "error": reason,
        }

    @staticmethod
    def _build_user_prompt(candidates: list, chapter_outline: dict,
                           world_view: dict, chapter_index: int,
                           target_length: int) -> str:
        outline_detail = (
            chapter_outline.get("plot_detail")
            or chapter_outline.get("summary", "")
        )
        key_events = chapter_outline.get("key_events", []) or []
        key_events_text = (
            "\n".join(f"  - {e}" for e in key_events) if key_events else "  （无）"
        )

        blocks = []
        for i, cand in enumerate(candidates, 1):
            blocks.append(
                f"──────── 候选稿 {i}（人格：{cand.get('persona', '')}）────────\n"
                f"{cand.get('content', '')}"
            )

        return (
            f"【小说标题】{world_view.get('title', '未命名')}\n\n"
            f"【本章大纲】第{chapter_index}章\n{outline_detail}\n\n"
            f"【必须覆盖的关键事件】\n{key_events_text}\n\n"
            f"【目标字数】{target_length} 字\n\n"
            f"【候选稿共 {len(candidates)} 份】\n\n"
            + "\n\n".join(blocks)
            + "\n\n请按系统提示的 JSON 格式评审并选出最优稿。"
        )
