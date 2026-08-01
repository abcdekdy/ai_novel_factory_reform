"""
续写大纲生成 Agent
========================================
在已有小说基础上，根据"遗产包 + 用户续写指引"生成下一批次的详细章节大纲。

和普通 outline_agent 的关键区别：
  - 输入不是空世界观，而是已有 N 章小说的全部上下文（遗产包）
  - 输出只覆盖"本批新章节"，不重写旧章节
  - 必须把旧规则、旧角色弧线当作硬约束，但可以在轨迹上追加新节点
  - 有机会回收旧伏笔（在 output 里标记回收了哪些）
"""

from core.base_agent import BaseAgent


SYSTEM_PROMPT = """你是一位资深网文小说总策划，擅长在已连载作品的基础上，规划下一批章节的详细大纲。

你的任务是：根据**已有的小说世界观、人物设定、前 N 章剧情**，以及**作者给出的续写方向指引**，为下一批新章节制定**高度连贯、无矛盾**的详细大纲。

## 严格约束

1. **绝对一致性**: 新章节必须与已有世界观、人物设定、世界规则**完全一致**，不能推翻任何已有设定
2. **遵守已有规则**: 下方的"已有一致性规则"是整部小说的铁律，新章节必须全部遵守，不能违反任何一条
3. **角色弧线延续**: 每个角色的状态必须从"当前状态"自然延续，不能突然性格大变（除非剧情明确铺垫）
4. **前情衔接**: 新大纲的第一章必须自然承接上一批**最后一章的章尾悬念**，形成连贯过渡
5. **伏笔管理**:
   - 优先回收下方列出的"未回收伏笔"（在输出里标记你回收了哪些）
   - 同时埋下新伏笔供后续批次回收
   - 每个回收/新增的伏笔都要标注清楚
6. **节奏把控**: 每章都要有完整的起承转合；批次内整体保持张弛有度
7. **章末留钩**: 每章结尾必须有悬念或转折，吸引读者追更

## 输出格式（严格 JSON，不要任何额外文字）

{
    "outline_meta": {
        "version": 1,
        "batch": 2,
        "total_chapters": 10,
        "chapter_start": 11,
        "chapter_end": 20,
        "generated_from": "ContinuationOutlineAgent"
    },
    "batch_guidance": "作者在指引中给出的方向（原样保留，便于追溯）",
    "resolved_foreshadowing": [
        {"from_chapter": 3, "foreshadowing": "...", "resolved_in_chapter": 12}
    ],
    "new_foreshadowing": [
        {"set_in_chapter": 15, "foreshadowing": "...", "planned_resolve_chapter": "后续批次"}
    ],
    "consistency_rules": [
        "旧规则1（保留）",
        "旧规则2（保留）",
        "本批新增规则..."
    ],
    "chapters": [
        {
            "chapter_index": 11,
            "title": "章节标题",
            "plot_detail": "300-500字的详细剧情描述",
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
                {"chapter": 20, "state": "本批次结束时的新状态（只追加，不要重写旧轨迹）"}
            ]
        }
    }
}

## 特别注意

- `consistency_rules` 里**必须包含全部旧规则**（原样保留），再追加本批新规则（如有）
- `character_arcs` 只追加本批角色的**最新轨迹点**（chapter 号要对应本批章节），不要重写旧轨迹
- `resolved_foreshadowing` 和 `new_foreshadowing` 是续写大纲独有的字段，普通大纲没有
- `plot_detail` 要写得足够详细（300-500字），让写手一看就知道要写什么
- 章节序号从 `chapter_start` 起连续编号，不要从 1 开始

现在开始生成续写大纲。"""


class ContinuationOutlineAgent(BaseAgent):
    """续写大纲 Agent — 基于遗产包 + 用户指引规划下一批章节"""

    def __init__(self, llm_client, temperature: float = 0.7,
                 max_tokens: int = 8192):
        super().__init__("续写大纲生成", llm_client)
        self.temperature = temperature
        self.max_tokens = max_tokens

    def run(self, input_data: dict) -> dict:
        """
        输入: {
            "legacy_package": dict,      # load_legacy_package() 的返回
            "guidance": str,             # 用户续写指引
            "batch_chapter_count": int,  # 本批章数
            "chapter_length": int,       # 每章字数（传给章节 agent 用，这里保留记录）
        }
        输出: 详细大纲 JSON（仅含本批新章节）
        """
        legacy = input_data.get("legacy_package", {})
        guidance = input_data.get("guidance", "")
        batch_count = input_data.get("batch_chapter_count", 10)
        chapter_length = input_data.get("chapter_length", 3000)

        world_view = legacy.get("world_view", {})

        self.set_status("running")
        self.log(f"续写大纲生成启动 | 已有 {legacy.get('existing_chapters_count', 0)} 章 | 本批 {batch_count} 章")
        self.set_progress(10)

        # 格式化 prompt 各段
        legacy_text = self._format_legacy(legacy)
        world_text = self._format_world_view(world_view)

        start_index = legacy.get("existing_chapters_count", 0) + 1
        end_index = legacy.get("existing_chapters_count", 0) + batch_count

        # 上一批最后一章的章尾悬念（用于硬约束提示）
        recent_chapters = legacy.get("recent_chapters", [])
        if recent_chapters:
            last_cliffhanger = recent_chapters[-1].get("cliffhanger", "（无）")
        else:
            last_cliffhanger = "（无）"

        user_prompt = f"""【续写方向指引（作者给定）】
{guidance}

━━━━━━━━━━━━━━━━━━━━━━━━

【小说标题】{world_view.get('title', '未命名')}
【类型】{world_view.get('genre', '未知')}
【世界观简介】{world_view.get('summary', '')}

{world_text}

{legacy_text}

━━━━━━━━━━━━━━━━━━━━━━━━

【任务】
为以上小说规划第 {start_index} 到 {end_index} 章（共 {batch_count} 章）的详细续写大纲。

【硬约束】
1. 第 {start_index} 章开头必须自然承接上一批最后一章的悬念：
   "{last_cliffhanger}"
2. 所有"已有一致性规则"必须原样保留，绝不违反
3. 角色状态必须从"当前状态"延续
4. 优先回收列出的未回收伏笔

严格输出 JSON 格式，不要有任何额外文字。"""

        self.set_progress(30)
        self.log(f"调用模型生成第 {start_index}-{end_index} 章续写大纲...")

        try:
            # 使用流式调用，让用户能看到进度（续写 prompt 很大，思考时间长）
            result = self.call_llm_stream(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                on_progress=lambda full: self.log(
                    f"续写大纲生成中... 已收到 {len(full)} 字"),
            )

            self.set_progress(70)
            self.log("正在解析续写大纲数据...")

            outline = self.parse_json_response(result)

            # 注入是本批的 meta
            outline = self._validate_and_fix(
                outline, legacy, batch_count, start_index, guidance
            )

            total = len(outline.get("chapters", []))
            rules_count = len(outline.get("consistency_rules", []))
            resolved = len(outline.get("resolved_foreshadowing", []))
            new_fs = len(outline.get("new_foreshadowing", []))

            self.set_progress(100)
            self.set_status("success")
            self.log(
                f"✅ 续写大纲生成完成：{total} 章（第 {start_index}-{end_index} 章），"
                f"{rules_count} 条规则（含旧规则），"
                f"回收伏笔 {resolved} 个，新增伏笔 {new_fs} 个"
            )

            self.finished_signal.emit(self.name, outline)
            return outline

        except Exception as e:
            self.set_status("error")
            self.log(f"❌ 续写大纲生成失败: {e}")
            error_result = {
                "error": str(e),
                "outline_meta": {"batch": 0, "total_chapters": 0},
                "consistency_rules": [],
                "chapters": [],
                "character_arcs": {},
                "resolved_foreshadowing": [],
                "new_foreshadowing": [],
            }
            self.finished_signal.emit(self.name, error_result)
            return error_result

    # ------------------------------------------------------------------
    #  校验 & 修复
    # ------------------------------------------------------------------
    def _validate_and_fix(self, outline: dict, legacy: dict,
                          batch_count: int, start_index: int,
                          guidance: str) -> dict:
        """校验续写大纲，补齐缺失字段，兜底修复。"""
        if not isinstance(outline, dict):
            raise ValueError("续写大纲响应的顶层结构必须是 JSON 对象")

        existing_rules = legacy.get("existing_rules", [])

        # 确保顶层字段
        if not isinstance(outline.get("outline_meta"), dict):
            outline["outline_meta"] = {}
        outline["outline_meta"]["version"] = 1
        outline["outline_meta"]["generated_from"] = "ContinuationOutlineAgent"
        outline["outline_meta"]["total_chapters"] = len(outline.get("chapters", []))
        outline["outline_meta"]["chapter_start"] = start_index
        outline["outline_meta"]["chapter_end"] = start_index + batch_count - 1

        # 保留作者指引原文
        outline["batch_guidance"] = guidance

        # 一致性规则：旧规则 + 新规则合并
        new_rules = outline.get("consistency_rules", [])
        if not isinstance(new_rules, list):
            new_rules = []
        # 旧规则前置（去重）
        merged_rules = list(existing_rules)
        for r in new_rules:
            if r not in merged_rules:
                merged_rules.append(r)
        outline["consistency_rules"] = merged_rules

        # 伏笔字段
        if not isinstance(outline.get("resolved_foreshadowing"), list):
            outline["resolved_foreshadowing"] = []
        if not isinstance(outline.get("new_foreshadowing"), list):
            outline["new_foreshadowing"] = []

        # 章节字段
        if not isinstance(outline.get("chapters"), list):
            outline["chapters"] = []
        if not isinstance(outline.get("character_arcs"), dict):
            outline["character_arcs"] = {}

        # 修复每章的 chapter_index（确保连续）
        for i, ch in enumerate(outline["chapters"], start=start_index):
            if not isinstance(ch, dict):
                continue
            ch["chapter_index"] = i
            ch.setdefault("title", f"第{i}章")
            ch.setdefault("plot_detail", "")
            ch.setdefault("key_events", [])
            ch.setdefault("characters_present", [])
            ch.setdefault("character_developments", {})
            ch.setdefault("foreshadowing", [])
            ch.setdefault("cliffhanger", "")
            ch.setdefault("narrative_purpose", "")

        return outline

    # ------------------------------------------------------------------
    #  格式化辅助
    # ------------------------------------------------------------------
    def _format_world_view(self, world_view: dict) -> str:
        """格式化世界观本体。兼容 characters 字段为 dict / list / tuple 多种旧格式。"""
        wv = world_view.get("world_view", {})
        if not isinstance(wv, dict):
            wv = {}
        characters = world_view.get("characters", [])
        if not isinstance(characters, list):
            characters = list(characters) if hasattr(characters, '__iter__') else []
        story = world_view.get("story_framework", {})
        if not isinstance(story, dict):
            story = {}

        lines = []
        world_rules = wv.get("rules", '') if isinstance(wv, dict) else ''
        if world_rules:
            lines.append(f"【世界规则】{world_rules}")
        era = wv.get("era", '') if isinstance(wv, dict) else ''
        if era:
            lines.append(f"【时代背景】{era}")
        loc = wv.get("location", '') if isinstance(wv, dict) else ''
        if loc:
            lines.append(f"【地理设定】{loc}")
        factions = wv.get("factions", []) if isinstance(wv, dict) else []
        if factions:
            lines.append(f"【主要势力】{', '.join(factions) if isinstance(factions, (list, tuple)) else factions}")
        history = wv.get("history", '') if isinstance(wv, dict) else ''
        if history:
            lines.append(f"【历史背景】{history}")

        if characters:
            lines.append("\n【主要角色】")
            for c in characters:
                # 兼容 dict / list / tuple 多种格式
                if isinstance(c, dict):
                    name = c.get("name", "")
                    role = c.get("role", "")
                    desc = c.get("desc", "")
                    ability = c.get("ability", "")
                elif isinstance(c, (list, tuple)) and len(c) >= 3:
                    name = c[0] if c[0] else ""
                    role = c[1] if len(c) > 1 else ""
                    desc = c[2] if len(c) > 2 else ""
                    ability = c[3] if len(c) > 3 else ""
                else:
                    continue
                lines.append(f"  - {name}（{role}）：{desc} | 能力：{ability}")

        if story:
            lines.append("\n【故事框架】")
            lines.append(f"  开端: {story.get('premise', '')}")
            lines.append(f"  冲突: {story.get('conflict', '')}")
            lines.append(f"  高潮: {story.get('climax', '')}")
            lines.append(f"  结局: {story.get('ending_type', '')}")

        return "\n".join(lines)

    def _format_legacy(self, legacy: dict) -> str:
        """格式化遗产包为 prompt 文本。"""
        lines = []

        # 最近章节
        recent = legacy.get("recent_chapters", [])
        if recent:
            lines.append("【前 N 章剧情摘要（续写起点）】")
            for ch in recent:
                idx = ch.get("chapter_index", "?")
                title = ch.get("title", "")
                summary = ch.get("summary", "")
                cliff = ch.get("cliffhanger", "")
                lines.append(f"  第{idx}章「{title}」")
                lines.append(f"    剧情：{summary}")
                if cliff:
                    lines.append(f"    章尾悬念：{cliff}")
            lines.append("")

        # 角色当前状态
        states = legacy.get("character_current_states", {})
        if states:
            lines.append("【角色当前状态（从这里延续，不能突变）】")
            for name, state in states.items():
                lines.append(f"  - {name}：{state}")
            lines.append("")

        # 已有规则
        rules = legacy.get("existing_rules", [])
        if rules:
            lines.append("【已有一致性规则（铁律，违反则章节作废）】")
            for i, r in enumerate(rules, 1):
                lines.append(f"  {i}. {r}")
            lines.append("")

        # 未回收伏笔
        unresolved = legacy.get("unresolved_foreshadowing", [])
        if unresolved:
            lines.append("【未回收伏笔（优先在本批回收）】")
            for fs in unresolved[:20]:  # 上限 20 条，避免 prompt 过长
                lines.append(f"  第{fs.get('from_chapter', '?')}章：{fs.get('foreshadowing', '')}")
            if len(unresolved) > 20:
                lines.append(f"  ...还有 {len(unresolved) - 20} 条伏笔省略")
            lines.append("")

        # 历史批次
        prev_batches = legacy.get("previous_batches", [])
        if prev_batches:
            lines.append("【历史续写批次（追溯用）】")
            for b in prev_batches:
                lines.append(f"  批次 {b.get('batch_number', '?')}（{b.get('chapter_range', '')}）")
                lines.append(f"    指引：{b.get('guidance', '')[:80]}")
            lines.append("")

        return "\n".join(lines) if lines else "（暂无前情上下文）"
