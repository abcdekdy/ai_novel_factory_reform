"""
章节生成 Agent
========================================
根据世界观 + 详细大纲（含前后章节上下文 + 一致性规则 + 角色弧线），
生成具体章节正文。支持流式输出，可并行调用。
"""

from core.base_agent import BaseAgent


SYSTEM_PROMPT = """你是一位才华横溢的网文小说创作者，擅长根据详细大纲创作引人入胜的章节内容。

你的任务是根据给定的世界观、人物设定、**详细大纲上下文**，写出精彩的章节正文。

## 创作要求

1. 文风流畅生动，对话自然，描写细致
2. **严格遵循一致性规则**，绝对不能违反已设定的规则（违反则章节作废）
3. 人物性格和行为与设定保持一致，符合当前角色弧线状态
4. 按照当前章节的详细剧情描述（plot_detail）来写，不要偏离
5. 关键事件必须全部覆盖，不能遗漏
6. 章节结尾必须呼应cliffhanger（悬念）设计
7. 为后续章节的伏笔自然埋入（参考foreshadowing字段）
8. 开头要自然承接上一章的情绪/事件
9. 每章有完整的起承转合，情节推进合理
10. 节奏张弛有度，紧张与舒缓交替

## 绝对禁止

- 违反一致性规则中的任何一条
- 让角色做出不符合其当前弧线状态的行为
- 提前揭示后续章节的伏笔（伏笔只能暗示，不能明示）
- 使用"第一章""第二节"等 markdown 标记
- 输出"本章说"之类的元说明
- 混入英文段落

## 技术规范

- 用中文创作
- 对话用中文引号""
- 每段不宜过长，注意留白和节奏
- 直接写正文内容，不要添加任何说明文字
- 按要求控制字数"""


class ChapterGeneratorAgent(BaseAgent):
    """章节生成Agent - 可并行调用的章节生成器（携带详细大纲上下文）"""

    def __init__(self, llm_client, agent_id: int = 0):
        super().__init__(f"章节生成-{agent_id}", llm_client)
        self.agent_id = agent_id

    def run(self, input_data: dict) -> dict:
        """
        输入: {
            "world_view": dict,
            "chapter_outline": dict,       # 单个章节的粗大纲
            "chapter_index": int,
            "target_length": int,
            "previous_chapter_summary": str,
            --- 新增：大纲上下文 ---
            "outline_chapter": dict,       # 本章节的详细大纲条目
            "outline_context": dict,        # {consistency_rules, global_arc, all_chapters_summary}
            "character_arcs": dict          # 角色弧线
        }
        输出: dict (章节数据)
        """
        world_view = input_data.get("world_view", {})
        chapter_outline = input_data.get("chapter_outline", {})
        chapter_index = input_data.get("chapter_index", 1)
        target_length = input_data.get("target_length", 3000)
        on_chunk = input_data.get("callback", None)

        # ---- 详细大纲字段（新增） ----
        outline_ch = input_data.get("outline_chapter", {})
        outline_ctx = input_data.get("outline_context", {})
        character_arcs = input_data.get("character_arcs", {})

        self.set_status("running")
        self.log(f"开始生成第{chapter_index}章: {chapter_outline.get('title', '')}")
        self.set_progress(5)

        # 构建上下文
        world_summary = world_view.get("summary", "")
        world_rules = world_view.get("world_view", {}).get("rules", "")
        characters_info = self._format_characters(world_view.get("characters", []))
        story_conflict = world_view.get("story_framework", {}).get("conflict", "")

        # 前情提要（如果有前一章）
        prev_summary = input_data.get("previous_chapter_summary", "")
        prev_hint = f"\n\n前情提要：{prev_summary}" if prev_summary else ""

        # ---- 一致性规则 ----
        consistency_rules = outline_ctx.get("consistency_rules", [])
        rules_text = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(consistency_rules)) if consistency_rules else "  （无特殊规则）"

        # ---- 角色弧线（仅本章节出场角色） ----
        chars_present = outline_ch.get("characters_present", [])
        arcs_text = self._format_arcs_for_chapter(character_arcs, chars_present, chapter_index)

        # ---- 整体走向（前后章节） ----
        all_summaries = outline_ctx.get("all_chapters_summary", [])
        past_future_text = self._format_surrounding_chapters(all_summaries, chapter_index)

        # ---- 伏笔 ----
        foreshadowing = outline_ch.get("foreshadowing", [])
        foreshadowing_text = "\n".join(f"  - {f}" for f in foreshadowing) if foreshadowing else "  （本章无伏笔设计）"

        user_prompt = f"""【小说设定】
标题：{world_view.get('title', '未命名')}
类型：{world_view.get('genre', '未知')}
世界观简介：{world_summary}
世界规则：{world_rules}
核心冲突：{story_conflict}

【主要人物】
{characters_info}

━━━━━━━━━━━━━━━━━━━━━━━━
【全局一致性规则 — 绝对禁止违反】
{rules_text}

【故事整体走向】
{past_future_text}

【角色弧线参考（仅本章节出场角色）】
{arcs_text}
━━━━━━━━━━━━━━━━━━━━━━━━

【当前章节详细大纲】
第{chapter_index}章：{outline_ch.get('title', chapter_outline.get('title', ''))}
━━━━━━━━━━━━━━━━━━━━━━
📖 详细剧情：
{outline_ch.get('plot_detail', chapter_outline.get('summary', ''))}

🎯 关键事件（必须全部覆盖）：
{self._format_list(outline_ch.get('key_events', []))}

🎭 人物变化：
{self._format_dev(outline_ch.get('character_developments', {}))}

🔮 伏笔（自然埋入，不要明示）：
{foreshadowing_text}

🎬 章尾悬念：{outline_ch.get('cliffhanger', '自然收束')}
━━━━━━━━━━━━━━━━━━━━━━
📝 本章在整体中的功能：{outline_ch.get('narrative_purpose', '')}
{prev_hint}

【写作要求】
- 章节标题已在大纲中，正文从第一段开始写即可
- 目标字数：{target_length}字左右
- 详细剧情中的关键事件**必须全部覆盖**，不要遗漏
- 大胆遵循伏笔提示，为后续剧情做铺垫
- 章尾必须呼应悬念设计，吸引读者继续阅读
- 严格遵循世界观、一致性规则、角色弧线
- 直接输出正文，不要添加任何说明文字"""

        self.set_progress(20)
        self.log(f"第{chapter_index}章 - 调用模型生成中...")

        try:
            if on_chunk:
                content = self.llm.chat_stream(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.8,
                    max_tokens=6000,
                    on_chunk=on_chunk,
                    on_complete=lambda full: self.log(f"第{chapter_index}章生成完成，共 {len(full)} 字")
                )
            else:
                content = self.call_llm(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.8,
                    max_tokens=6000
                )

            self.set_progress(100)
            self.set_status("success")
            self.log(f"✅ 第{chapter_index}章生成完成：{chapter_outline.get('title')} ({len(content)}字)")

            result = {
                "chapter_index": chapter_index,
                "title": outline_ch.get("title", chapter_outline.get("title", f"第{chapter_index}章")),
                "content": content,
                "summary": outline_ch.get("plot_detail", chapter_outline.get("summary", "")),
                "word_count": len(content),
                "status": "draft"
            }

            self.finished_signal.emit(self.name, result)
            return result

        except Exception as e:
            self.set_status("error")
            self.log(f"❌ 第{chapter_index}章生成失败: {e}")

            result = {
                "chapter_index": chapter_index,
                "title": outline_ch.get("title", chapter_outline.get("title", f"第{chapter_index}章")),
                "content": f"[生成失败: {e}]",
                "summary": outline_ch.get("plot_detail", chapter_outline.get("summary", "")),
                "word_count": 0,
                "status": "error",
                "error": str(e)
            }
            self.finished_signal.emit(self.name, result)
            return result

    # ------------------------------------------------------------------
    #  格式化辅助
    # ------------------------------------------------------------------
    def _format_characters(self, characters: list) -> str:
        lines = []
        for char in characters:
            name = char.get("name", "")
            role = char.get("role", "")
            desc = char.get("desc", "")
            ability = char.get("ability", "")
            lines.append(f"- {name}（{role}）：{desc} | 能力：{ability}")
        return "\n".join(lines) if lines else "-（无角色设定）"

    def _format_arcs_for_chapter(self, arcs: dict, chars_present: list, chapter_index: int) -> str:
        """只输出本章节出场角色的弧线在‘当前章节’的状态"""
        if not arcs or not chars_present:
            return "  （本章无需追踪弧线）"
        lines = []
        for name in chars_present:
            if name in arcs:
                arc = arcs[name]
                arc_type = arc.get("arc_type", "")
                traj = arc.get("trajectory", [])
                # 找到当前或最近的前置状态
                state = ""
                for t in traj:
                    if t.get("chapter", 0) <= chapter_index:
                        state = t.get("state", "")
                if not state and traj:
                    state = traj[0].get("state", "")
                lines.append(f"  - {name}（{arc_type}）：{state}")
        return "\n".join(lines) if lines else "  （本章无需追踪弧线）"

    def _format_surrounding_chapters(self, all_summaries: list, chapter_index: int) -> str:
        """生成前后章节走向（加总全局弧线 + 邻近章节的标题/概要）"""
        if not all_summaries:
            return "  （暂无整体走向信息）"
        lines = []
        lines.append("全局弧线结构：")

        # 找 global_arc（可能在 context 外层，这里只打印邻近章节）
        for ch in all_summaries:
            idx = ch.get("chapter_index")
            if idx is None:
                continue
            marker = " ⬅️ 当前" if idx == chapter_index else ""
            if abs(idx - chapter_index) <= 3 or idx == chapter_index:
                plot = ch.get("plot_detail", "")
                if len(plot) > 60:
                    plot = plot[:60] + "..."
                lines.append(f"  第{idx}章「{ch.get('title', '')}」{marker}")
                lines.append(f"    {plot}")

        # 远邻只给标题
        far = [ch for ch in all_summaries
               if ch.get("chapter_index") is not None
               and abs(ch.get("chapter_index") - chapter_index) > 3]
        if far:
            far_titles = " → ".join(f"第{ch.get('chapter_index')}「{ch.get('title', '')}’"
                                     for ch in far)
            lines.append(f"  后续远章：{far_titles}")

        return "\n".join(lines)

    @staticmethod
    def _format_list(items: list) -> str:
        if not items:
            return "  （无关键事件）"
        return "\n".join(f"  - {item}" for item in items)

    @staticmethod
    def _format_dev(devs: dict) -> str:
        if not devs:
            return "  （本章无明显人物变化）"
        return "\n".join(f"  - {k}：{v}" for k, v in devs.items())
