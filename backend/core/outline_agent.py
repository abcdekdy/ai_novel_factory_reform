"""
大纲生成 Agent
========================================
在世界观构建之后、章节生成之前运行，把粗大纲扩展为结构化详细大纲。

职责:
  - 接收世界观 agent 的完整产出（含粗 chapter_outline）
  - 为每章生成: 详细剧情(300-500字)、关键事件、出场人物、人物变化、伏笔、章尾悬念
  - 提炼全局一致性规则（不能违反的设定清单）
  - 构建角色弧线轨迹（每章角色状态）
  - 输出标准 JSON，供章节 agent 并行时携带

输出结构（OutlineBuilderAgent.run 返回）:
  see SYSTEM_PROMPT 中的 schema
"""

from core.base_agent import BaseAgent


SYSTEM_PROMPT = """你是一位专业的网文小说总策划和首席编剧，擅长把粗纲扩展为逻辑严密、前后呼应的详细章节大纲。

你的任务是：根据给定的世界观设定和粗章节大纲，生成一份**高度连贯、无矛盾**的详细大纲。

## 严格约束

1. **绝对一致性**: 所有章节的设定、人物能力、世界规则必须与 `world_view` 完全一致，章节之间不能互相矛盾
2. **前后呼应**: 前文埋下的伏笔必须在后文有对应的揭晓；前面说过的事后面不能推翻
3. **角色弧线**: 每个角色的变化轨迹必须连贯合理，不能突然性格大变（除非剧情明确铺垫）
4. **节奏把控**: 开端→发展→发展→高潮→结局，张弛有度，不能每章都平淡或都高潮
5. **伏笔管理**: 每章最多埋 1-2 个伏笔，且必须在后续章节中明确回收
6. **衔接锚点**: 每章开头要能自然承接上一章结尾的悬念或情绪

## 输出格式（严格 JSON，不要任何额外文字）

{
    "outline_meta": {
        "version": 1,
        "total_chapters": 5,
        "generated_from": "世界观构建Agent"
    },
    "global_arc": {
        "three_act_structure": {
            "setup":        {"chapters": [1, 2], "purpose": "建立世界观、引入核心冲突"},
            "confrontation": {"chapters": [3, 4], "purpose": "冲突升级、角色成长"},
            "resolution":   {"chapters": [5],  "purpose": "高潮与结局"}
        },
        "core_thread": "一句话概括核心故事线索"
    },
    "consistency_rules": [
        "不能违反的规则1（如：灵气不能在真空中存在，主角的火系灵根在水下威力减半）",
        "不能违反的规则2（如：师傅在第三章前不能暴露真实身份）"
    ],
    "chapters": [
        {
            "chapter_index": 1,
            "title": "章节标题",
            "plot_detail": "300-500字的详细剧情描述，包含完整的起承转合，明确写出本章讲了什么",
            "key_events": ["关键事件1", "关键事件2"],
            "characters_present": ["角色A", "角色B"],
            "character_developments": {
                "角色A": "本章节该角色的状态/性格/能力变化描述"
            },
            "foreshadowing": ["为后续章节埋下的伏笔（本章不揭晓）"],
            "cliffhanger": "章尾悬念或转折，吸引读者继续阅读",
            "narrative_purpose": "本章在整体结构中的功能定位"
        }
    ],
    "character_arcs": {
        "角色A": {
            "arc_type": "成长型/堕落型/觉醒型/悲剧型",
            "trajectory": [
                {"chapter": 1, "state": "初始状态描述"},
                {"chapter": 3, "state": "遭遇重大转变"},
                {"chapter": 5, "state": "最终状态"}
            ]
        }
    }
}

## 特别注意

- `consistency_rules` 是整个大纲中最重要的部分，列出所有"绝对不能违反"的设定
- 规则要具体（涉及能力限制、人物关系、时间线、关键事件），不要空泛
- 如果世界观 agent 的粗大纲本身有矛盾或逻辑漏洞，你要**主动修正**并记录到 consistency_rules 中
- `plot_detail` 要写得足够详细（300-500字），让写手一看就知道要写什么
- `character_arcs` 中的 `trajectory` 要覆盖该角色状态发生质变的关键章节

现在开始生成详细大纲。"""


class OutlineBuilderAgent(BaseAgent):
    """大纲生成 Agent — 把粗纲扩展为结构化详细大纲"""

    def __init__(self, llm_client, temperature: float = 0.7,
                 max_tokens: int = 8192):
        super().__init__("大纲生成", llm_client)
        self.temperature = temperature
        self.max_tokens = max_tokens

    def run(self, input_data: dict) -> dict:
        """
        输入: {"world_view": dict}   (世界观 agent 的完整输出)
        输出: 详细大纲 JSON（见 SYSTEM_PROMPT schema）
        """
        world_view = input_data.get("world_view", {})

        self.set_status("running")
        self.log("开始生成详细大纲...")
        self.set_progress(10)

        # 构建上下文
        outline_coarse = world_view.get("chapter_outline", [])
        characters_info = self._format_characters(world_view.get("characters", []))
        world_view_info = world_view.get("world_view", {})
        story_framework = world_view.get("story_framework", {})

        # 粗大纲文本（用于 prompt）
        coarse_text = self._format_coarse_outline(outline_coarse)

        user_prompt = f"""【小说标题】{world_view.get('title', '未命名')}
【类型】{world_view.get('genre', '未知')}
【世界观简介】{world_view.get('summary', '')}

【世界规则】{world_view_info.get('rules', '')}
【时代背景】{world_view_info.get('era', '')}
【地理设定】{world_view_info.get('location', '')}
【主要势力】{', '.join(world_view_info.get('factions', []))}
【历史背景】{world_view_info.get('history', '')}

【核心冲突】{story_framework.get('conflict', '')}
【故事开端】{story_framework.get('premise', '')}
【高潮设计】{story_framework.get('climax', '')}
【结局方向】{story_framework.get('ending_type', '')}

【主要角色】
{characters_info}

【粗章节大纲（需要扩展为详细大纲）】
{coarse_text}

请根据以上信息，生成一份高度连贯、无矛盾的详细章节大纲，严格输出 JSON 格式。"""

        self.set_progress(30)
        self.log(f"调用模型生成大纲，共 {len(outline_coarse)} 章需要细化...")

        try:
            result = self.call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            self.set_progress(70)
            self.log("正在解析大纲数据...")

            outline = self.parse_json_response(result)

            # 校验 & 修复
            outline = self._validate_outline(outline, outline_coarse)

            total = len(outline.get("chapters", []))
            rules_count = len(outline.get("consistency_rules", []))
            arcs_count = len(outline.get("character_arcs", {}))

            self.set_progress(100)
            self.set_status("success")
            self.log(
                f"✅ 大纲生成完成：{total} 章详细大纲，"
                f"{rules_count} 条一致性规则，"
                f"{arcs_count} 条角色弧线"
            )

            self.finished_signal.emit(self.name, outline)
            return outline

        except Exception as e:
            self.set_status("error")
            self.log(f"❌ 大纲生成失败: {e}")
            error_result = {
                "error": str(e),
                "chapters": [],
                "consistency_rules": [],
                "character_arcs": {}
            }
            self.finished_signal.emit(self.name, error_result)
            return error_result

    # ------------------------------------------------------------------
    #  校验：确保每章都有详细条目，缺失的从粗大纲补
    # ------------------------------------------------------------------
    def _validate_outline(self, outline: dict, coarse: list) -> dict:
        """校验详细大纲，确保覆盖所有章节；缺失则从粗大纲兜底"""
        if not isinstance(outline, dict):
            raise ValueError("大纲响应的顶层结构必须是 JSON 对象")
        if not isinstance(coarse, list):
            raise ValueError("世界观中的 chapter_outline 必须是列表")

        # 确保顶层字段存在
        if not isinstance(outline.get("outline_meta"), dict):
            outline["outline_meta"] = {}
        outline["outline_meta"].setdefault("version", 1)
        outline["outline_meta"].setdefault("total_chapters", len(coarse))
        if not isinstance(outline.get("global_arc"), dict):
            outline["global_arc"] = {}
        if not isinstance(outline.get("consistency_rules"), list):
            outline["consistency_rules"] = []
        if not isinstance(outline.get("chapters"), list):
            outline["chapters"] = []
        if not isinstance(outline.get("character_arcs"), dict):
            outline["character_arcs"] = {}

        def normalise_index(value, fallback=None):
            """兼容模型返回的数字字符串，避免有效大纲被错误当成缺失。"""
            if value is None:
                return fallback
            try:
                return int(value)
            except (TypeError, ValueError):
                return value

        # 建立已有详细条目的索引
        detailed_map = {}
        for position, ch in enumerate(outline["chapters"], start=1):
            if not isinstance(ch, dict):
                self.log(f"⚠️ 跳过第 {position} 个非对象大纲条目")
                continue
            idx = normalise_index(ch.get("chapter_index"), position)
            if idx is not None:
                ch["chapter_index"] = idx
                detailed_map[idx] = ch

        # 填充缺失的章节
        new_chapters = []
        for position, item in enumerate(coarse, start=1):
            if not isinstance(item, dict):
                self.log(f"⚠️ 跳过第 {position} 个非对象粗大纲条目")
                continue
            idx = normalise_index(item.get("chapter_index", item.get("chapter")), position)
            if idx in detailed_map:
                new_chapters.append(detailed_map[idx])
            else:
                self.log(f"⚠️ 第{idx}章无详细大纲，使用粗大纲兜底")
                new_chapters.append({
                    "chapter_index": idx,
                    "title": item.get("title", f"第{idx}章"),
                    "plot_detail": item.get("summary", ""),
                    "key_events": [],
                    "characters_present": [],
                    "character_developments": {},
                    "foreshadowing": [],
                    "cliffhanger": "",
                    "narrative_purpose": ""
                })
        outline["chapters"] = new_chapters
        outline["outline_meta"]["total_chapters"] = len(new_chapters)
        return outline

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

    def _format_coarse_outline(self, outline: list) -> str:
        lines = []
        for item in outline:
            idx = item.get("chapter_index", item.get("chapter"))
            title = item.get("title", "")
            summary = item.get("summary", "")
            lines.append(f"第{idx}章：{title}\n概要：{summary}")
        return "\n\n".join(lines)
