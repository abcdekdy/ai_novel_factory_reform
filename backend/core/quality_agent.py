"""
质量评估Agent
对生成的章节内容进行质量审核：评分、问题检测、改进建议。

评估分两层：
  1) 程序化硬校验（core.rule_checker）—— 字数、禁用句式、章尾钩子、
     关键事件覆盖、出场人物。零 LLM 调用，结果确定。
  2) LLM 主观打分 —— 文笔、节奏、吸引力、人物、世界观遵循、情节连贯。
     对硬校验已发现的问题，LLM 会收到提示以避免重复报告，并把精力放在
     主观维度上。

两层结果合并后写入 evaluation["issues"]，RevisionAgent 在修订时能看到
全部问题（含程序发现 + LLM 发现）。硬校验严重失败会强制 pass=false。
"""

from core.base_agent import BaseAgent
from core.rule_checker import check_chapter

SYSTEM_PROMPT = """你是一位资深的网文小说编辑和审稿专家，负责对小说章节进行专业质量评估。

评估维度（每项满分10分）：
1. **情节连贯性**：情节推进是否合理，与前文/大纲是否一致
2. **人物一致性**：人物行为、性格是否与设定一致
3. **文笔质量**：语言流畅度、描写生动性、对话自然度
4. **节奏把控**：叙事节奏是否得当，是否有拖沓或仓促
5. **世界观遵循**：是否遵守已设定的世界观规则
6. **吸引力**：是否引人入胜，悬念设置是否有效

注意：程序化硬校验已经发现若干问题（见用户提示中的【程序化硬校验结果】），
那些问题你不需要重复列出，但请在对应维度评分中体现其影响。
你重点关注硬校验覆盖不到的**主观维度**（文笔、节奏、吸引力、人物弧光、情绪流）。

输出格式（严格JSON，不要任何额外文字）：

{
    "overall_score": 8.5,
    "dimensions": {
        "plot_coherence": {"score": 8, "comment": "评价说明"},
        "character_consistency": {"score": 9, "comment": "评价说明"},
        "writing_quality": {"score": 8, "comment": "评价说明"},
        "pacing": {"score": 7, "comment": "评价说明"},
        "worldview_adherence": {"score": 9, "comment": "评价说明"},
        "engagement": {"score": 8, "comment": "评价说明"}
    },
    "issues": [
        {
            "type": "logic/timing/character/worldview/style",
            "description": "具体问题描述",
            "location": "出现位置（如'第3段对话'、'结尾处'）",
            "suggestion": "修改建议"
        }
    ],
    "highlights": ["亮点1", "亮点2"],
    "summary": "总体评价（100字以内）",
    "pass": true/false,
    "needs_revision": true/false
}

评判标准：
- 总分 ≥ 7.0 且无明显逻辑硬伤：pass=true
- 总分 < 7.0 或有严重逻辑矛盾：pass=false, needs_revision=true
- issues为空数组则无需修订"""


class QualityEvaluatorAgent(BaseAgent):
    """质量评估Agent —— 程序化硬校验 + LLM 主观打分双层评估"""

    def __init__(self, llm_client):
        super().__init__("质量评估", llm_client)

    def run(self, input_data: dict) -> dict:
        """
        输入: {
            "content": str,                       # 章节正文
            "title": str,
            "chapter_index": int,
            "world_view": dict,
            "chapter_outline": dict,              # 含 key_events / characters_present / cliffhanger / foreshadowing
            "summary": str,
            "target_length": int,                 # 目标字数（可选，默认 3000）
            "consistency_rules": list[str],       # 全局一致性规则（可选）
        }
        输出: 评估结果字典（含 rule_issues / rule_stats / rule_pass）
        """
        content = input_data.get("content", "")
        title = input_data.get("title", "")
        chapter_index = input_data.get("chapter_index", 1)
        world_view = input_data.get("world_view", {})
        chapter_outline = input_data.get("chapter_outline", {})

        self.set_status("running")
        self.log(f"开始评估第{chapter_index}章质量: {title}")
        self.set_progress(10)

        # ── 第一层：程序化硬校验 ──────────────────────────────
        rule_result = self._run_rule_checks(content, input_data, world_view,
                                            chapter_outline)
        rule_issues = rule_result["all_issues"]
        rule_pass = rule_result["rule_pass"]
        hard_count = len(rule_result["hard_issues"])
        soft_count = len(rule_result["soft_issues"])

        if hard_count:
            self.log(
                f"⚡ 第{chapter_index}章硬校验发现 {hard_count} 个严重问题"
                + (f"，{soft_count} 个提醒" if soft_count else "")
            )
        elif soft_count:
            self.log(f"⚡ 第{chapter_index}章硬校验发现 {soft_count} 个提醒项")
        else:
            self.log(f"✓ 第{chapter_index}章硬校验全部通过")

        self.set_progress(30)

        # ── 第二层：LLM 主观打分 ──────────────────────────────
        user_prompt = self._build_user_prompt(
            content, title, chapter_index, world_view,
            chapter_outline, rule_issues,
        )

        self.set_progress(50)

        try:
            result = self.call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,  # 评估任务用较低温度保证一致性
                max_tokens=6144,  # 评估输出 JSON（6 维评分+issues+highlights），6k 足够
            )

            self.set_progress(80)
            self.log("正在解析评估结果...")

            evaluation = self.parse_json_response(result)

            # 添加章节索引信息
            evaluation["chapter_index"] = chapter_index
            evaluation["chapter_title"] = title

            # ── 合并两层 issues ──────────────────────────────
            llm_issues = evaluation.get("issues", [])
            # 给 LLM issues 也打上 source 标记（便于 UI 区分）
            for issue in llm_issues:
                issue.setdefault("source", "llm_evaluator")
            merged_issues = rule_issues + llm_issues
            evaluation["issues"] = merged_issues
            evaluation["rule_issues"] = rule_issues
            evaluation["rule_stats"] = rule_result["stats"]
            evaluation["rule_pass"] = rule_pass
            evaluation["rule_hard_count"] = hard_count
            evaluation["rule_soft_count"] = soft_count

            # ── 硬校验严重失败时强制不通过 ──────────────────
            overall = evaluation.get("overall_score", 0)
            llm_pass = evaluation.get("pass", False)

            if hard_count > 0:
                # 硬校验发现严重问题：无论 LLM 给多高的分，都强制修订
                evaluation["pass"] = False
                evaluation["needs_revision"] = True
                if llm_pass:
                    self.log(
                        f"⚠️ 第{chapter_index}章 LLM 评分为 {overall} 且标记通过，"
                        f"但硬校验发现 {hard_count} 个严重问题，已强制改为需修订"
                    )
            else:
                evaluation["pass"] = llm_pass
                evaluation["needs_revision"] = evaluation.get("needs_revision", False)

            issues_count = len(merged_issues)
            passed = evaluation["pass"]

            self.set_progress(100)
            self.set_status("success")
            self.log(
                f"✅ 第{chapter_index}章评估完成：{overall}/10分，"
                f"共 {issues_count} 个问题（硬校验 {hard_count}+{soft_count}，"
                f"LLM {len(llm_issues)}），{'通过' if passed else '需修订'}"
            )

            self.finished_signal.emit(self.name, evaluation)
            return evaluation

        except Exception as e:
            self.set_status("error")
            self.log(f"❌ 评估失败: {e}")
            error_result = {
                "chapter_index": chapter_index,
                "overall_score": 0,
                "pass": False,
                "needs_revision": True,
                "issues": rule_issues + [
                    {"type": "system", "source": "rule_checker",
                     "severity": "hard",
                     "description": f"评估失败: {e}",
                     "suggestion": "重新评估"}
                ],
                "rule_issues": rule_issues,
                "rule_stats": rule_result["stats"],
                "rule_pass": rule_pass,
                "rule_hard_count": hard_count,
                "rule_soft_count": soft_count,
                "error": str(e),
            }
            self.finished_signal.emit(self.name, error_result)
            return error_result

    # ------------------------------------------------------------------
    #  内部：程序化硬校验
    # ------------------------------------------------------------------
    def _run_rule_checks(self, content: str, input_data: dict,
                         world_view: dict, chapter_outline: dict) -> dict:
        """构造 rule_checker 所需的 context 并执行校验。"""
        # 全部角色名（用于关键事件的人名锚定）
        all_characters = [
            c.get("name", "") for c in world_view.get("characters", [])
            if c.get("name")
        ]
        # 去重
        all_characters = list(dict.fromkeys(all_characters))

        context = {
            "chapter_index": input_data.get("chapter_index", 1),
            "target_length": input_data.get("target_length", 3000),
            "key_events": chapter_outline.get("key_events", []),
            "foreshadowing": chapter_outline.get("foreshadowing", []),
            "cliffhanger": chapter_outline.get("cliffhanger", ""),
            "characters_present": chapter_outline.get("characters_present", []),
            "characters_all": all_characters,
            "consistency_rules": input_data.get("consistency_rules", []),
            "world_rules": (world_view.get("world_view") or {}).get("rules", ""),
        }
        return check_chapter(content, context)

    # ------------------------------------------------------------------
    #  内部：构建 LLM 用户提示
    # ------------------------------------------------------------------
    def _build_user_prompt(self, content, title, chapter_index,
                           world_view, chapter_outline,
                           rule_issues) -> str:
        """构建评估用用户提示，含硬校验结果摘要。"""
        outline_summary = chapter_outline.get("summary", "")
        world_summary = world_view.get("summary", "")
        world_rules = (world_view.get("world_view") or {}).get("rules", "")
        story_conflict = (world_view.get("story_framework") or {}).get("conflict", "")

        # 硬校验结果摘要（让 LLM 知道哪些问题已经被程序确认）
        if rule_issues:
            rule_lines = []
            for i, issue in enumerate(rule_issues, 1):
                sev = "严重" if issue.get("severity") == "hard" else "提醒"
                rule_lines.append(
                    f"  {i}. [{sev}][{issue.get('type', '?')}] "
                    f"{issue.get('description', '')}"
                )
            rule_block = (
                "【程序化硬校验结果 —— 以下问题已确认存在，请不要再重复列出，"
                "但在对应维度评分中体现其影响】\n"
                + "\n".join(rule_lines)
            )
        else:
            rule_block = "【程序化硬校验结果】全部通过，无程序级问题。"

        return (
            f"【章节标题】第{chapter_index}章：{title}\n\n"
            f"【章节概要】{outline_summary}\n\n"
            f"【小说世界观简介】{world_summary}\n\n"
            f"【世界规则】{world_rules}\n\n"
            f"【核心冲突】{story_conflict}\n\n"
            f"{rule_block}\n\n"
            f"【需评估的章节正文】\n{content}\n\n"
            "请对以上章节内容进行全面的质量评估，输出JSON格式。"
        )
