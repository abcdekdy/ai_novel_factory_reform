"""
世界观构建Agent
根据用户灵感，生成完整的小说世界观、人物设定、故事框架 + 章节大纲。

实现策略：拆成两次 LLM 调用以避免单次输出过长被 max_tokens 截断。
  - 第 1 次：世界观本体（title, genre, summary, world_view, characters, story_framework）
  - 第 2 次：章节大纲（chapter_outline[]），把第 1 次输出作为上下文以保证连贯性
"""

import json

from core.base_agent import BaseAgent

# ── 第 1 次调用：世界观本体（不含章节大纲） ──────────────────────────────

SYSTEM_PROMPT_WORLD = """你是一位专业的世界观架构师和小说策划专家，擅长从零开始构建完整的幻想世界。

你的任务是根据用户的创意灵感，构建一个逻辑自洽、细节丰富的小说世界观。

输出格式要求（严格遵循JSON格式，不要有任何额外文字，不要生成章节大纲）：

{
    "title": "小说名称",
    "genre": "小说类型（如：科幻、玄幻、都市、悬疑等）",
    "summary": "200-300字的世界观核心简介",
    "world_view": {
        "era": "时代背景",
        "location": "主要地理设定",
        "rules": "世界核心规则/物理法则（如魔法体系、科技水平等）",
        "factions": ["主要势力/组织1", "势力2"],
        "history": "世界历史背景概述"
    },
    "characters": [
        {
            "name": "角色名",
            "role": "主角/配角/反派",
            "desc": "角色描述和背景（100字以内）",
            "ability": "核心能力/特长"
        }
    ],
    "story_framework": {
        "premise": "故事开端（如何引入）",
        "conflict": "核心矛盾/冲突",
        "climax": "高潮设计",
        "ending_type": "结局方向（开放式/圆满/悲剧等）"
    }
}

要求：
1. 世界观必须逻辑自洽，规则清晰
2. 人物设计要有记忆点和成长空间
3. 故事框架要有张力，冲突明确
4. 本次只输出世界观本体，不要生成章节大纲（大纲会单独请求）"""

# ── 第 2 次调用：章节大纲 ────────────────────────────────────────────────

SYSTEM_PROMPT_OUTLINE = """你是一位专业的网文小说大纲策划，擅长根据已定稿的世界观设定，生成连贯、有节奏感的章节大纲。

你的任务是根据给定的世界观，为整本小说列出每一章的标题与剧情概要。

## 严格约束

1. 章节内容必须严格遵循给定的世界观、人物设定、核心冲突，不能偏离
2. 章节之间要有起承转合，开端→发展→高潮→结局，节奏张弛有度
3. 每章剧情要与前后章衔接，不能出现设定矛盾
4. 章节标题要有吸引力，剧情概要要具体可写（100字左右）

## 输出格式（严格JSON数组，不要有任何额外文字）：

[
    {
        "chapter": 1,
        "title": "章节标题",
        "summary": "章节剧情概要（100字左右）"
    },
    {
        "chapter": 2,
        "title": "章节标题",
        "summary": "章节剧情概要（100字左右）"
    }
]

现在开始输出章节大纲。"""


class WorldBuilderAgent(BaseAgent):
    """世界观构建Agent — 两次 LLM 调用，避免单次输出过长被截断"""

    def __init__(self, llm_client):
        super().__init__("世界观构建", llm_client)

    def run(self, input_data: dict) -> dict:
        """
        输入: {"inspiration": str, "chapter_count": int}
        输出: 完整世界观设定字典（含chapter_outline）
        """
        inspiration = input_data.get("inspiration", "")
        chapter_count = input_data.get("chapter_count", 5)

        self.set_status("running")
        self.log(f"开始构建世界观，灵感: {inspiration[:50]}...")
        self.set_progress(5)

        # ── 第 1 次调用：世界观本体 ──────────────────────────────────────
        self.log("第 1 步：生成世界观本体（设定/人物/框架）...")
        self.set_progress(10)

        user_prompt_1 = f"""用户灵感：{inspiration}

请根据以上灵感，构建完整的小说世界观。

要求：
- 人物设定 3-5 个核心角色
- 世界观细节丰富但不冗余
- 本次只输出世界观本体（不要生成章节大纲）
- 以JSON格式输出"""

        try:
            result_1 = self.call_llm(
                system_prompt=SYSTEM_PROMPT_WORLD,
                user_prompt=user_prompt_1,
                temperature=0.9,
                max_tokens=8192
            )
            self.set_progress(40)
            self.log("解析世界观本体...")

            world_body = self.parse_json_response(result_1)

            title = world_body.get("title", "未命名")
            self.log(f"世界观本体完成：{title}")
            self.set_progress(50)

        except Exception as e:
            self.set_status("error")
            self.log(f"世界观本体构建失败: {e}")
            self.finished_signal.emit(self.name, {"error": str(e)})
            return {"error": str(e)}

        # ── 第 2 次调用：章节大纲 ────────────────────────────────────────
        self.log(f"第 2 步：生成 {chapter_count} 章章节大纲...")
        self.set_progress(55)

        user_prompt_2 = self._build_outline_prompt(world_body, chapter_count, inspiration)

        try:
            result_2 = self.call_llm(
                system_prompt=SYSTEM_PROMPT_OUTLINE,
                user_prompt=user_prompt_2,
                temperature=0.8,
                max_tokens=8192
            )
            self.set_progress(85)
            self.log("解析章节大纲...")

            chapter_outline = self.parse_json_response(result_2)

            # 兼容：LLM 可能返回 { "chapter_outline": [...] } 而不是纯数组
            if isinstance(chapter_outline, dict):
                chapter_outline = (
                    chapter_outline.get("chapter_outline")
                    or chapter_outline.get("chapters")
                    or chapter_outline.get("outline")
                    or []
                )

            if not isinstance(chapter_outline, list):
                raise ValueError(f"章节大纲格式异常（期望数组，得到 {type(chapter_outline).__name__}）")

        except Exception as e:
            # 兜底：大纲失败不影响本体，记录错误但返回本体
            self.log(f"章节大纲生成失败（将返回空大纲）: {e}")
            chapter_outline = []
            outline_error = str(e)
        else:
            outline_error = None

        # ── 合并结果 ─────────────────────────────────────────────────────
        world_body["chapter_outline"] = chapter_outline

        # 标准化：确保每个大纲元素都有 chapter_index
        for i, item in enumerate(chapter_outline):
            if isinstance(item, dict) and "chapter_index" not in item:
                item["chapter_index"] = item.get("chapter", i + 1)

        actual_count = len(chapter_outline)
        self.set_progress(100)
        self.set_status("success")

        if outline_error:
            self.log(f"世界观构建部分完成（本体 OK，大纲失败需重试）：{title}，大纲 {actual_count} 章")
        else:
            self.log(f"世界观构建完成！小说：{title}，共 {actual_count} 章")

        result = world_body
        if outline_error:
            result["_outline_error"] = outline_error  # 软错误标记，pipeline 可选择性处理

        self.finished_signal.emit(self.name, result)
        return result

    # ------------------------------------------------------------------
    #  辅助：构建第 2 次调用（章节大纲）的 user prompt
    # ------------------------------------------------------------------
    def _build_outline_prompt(self, world_body: dict, chapter_count: int,
                              inspiration: str) -> str:
        """把第 1 次输出的世界观本体格式化后，作为第 2 次调用的上下文。"""

        world_view = world_body.get("world_view", {})
        characters = world_body.get("characters", [])
        story = world_body.get("story_framework", {})

        # 角色列表文本
        char_lines = []
        for c in characters:
            if isinstance(c, dict):
                char_lines.append(
                    f"- {c.get('name', '未知')}（{c.get('role', '')}）："
                    f"{c.get('desc', '')} | 能力：{c.get('ability', '')}"
                )
        chars_text = "\n".join(char_lines) if char_lines else "（无角色设定）"

        prompt = f"""请根据以下已定稿的世界观，为整本小说生成 {chapter_count} 章的连贯大纲。

【小说标题】{world_body.get('title', '未命名')}
【类型】{world_body.get('genre', '未知')}
【原始灵感】{inspiration}

【世界观核心简介】
{world_body.get('summary', '')}

【世界规则】{world_view.get('rules', '')}
【时代背景】{world_view.get('era', '')}
【地理设定】{world_view.get('location', '')}
【主要势力】{', '.join(world_view.get('factions', [])) if isinstance(world_view.get('factions'), list) else world_view.get('factions', '')}
【历史背景】{world_view.get('history', '')}

【主要角色】
{chars_text}

【核心冲突】{story.get('conflict', '')}
【故事开端】{story.get('premise', '')}
【高潮设计】{story.get('climax', '')}
【结局方向】{story.get('ending_type', '')}

【要求】
- 共 {chapter_count} 章，每章包括：chapter（章序号）、title（章节标题）、summary（100字左右的剧情概要）
- 章节之间要有起承转合（开端→发展→高潮→结局），节奏张弛有度
- 严格遵循上述世界观与人物设定，不能偏离
- 每章剧情要与前后章衔接，人物行为符合其设定
- 输出纯 JSON 数组，不要有任何额外文字"""

        return prompt
