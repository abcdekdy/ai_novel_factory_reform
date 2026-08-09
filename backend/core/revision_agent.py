"""
回流修订 Agent（E1: patch 协议）
========================================
根据质量评估结果，对章节内容做**局部**精准修订 —— 不再全量重写。

协议
--------
模型输出 JSON（不再输出全文）：

    {
      "patches": [
        {
          "anchor": "原文中 >= 15 字的逐字片段（必须能在原文中唯一命中）",
          "replacement": "替换后的文本",
          "reason": "logic|timing|character|worldview|style —— 为什么改"
        }
      ],
      "highlights_preserved": ["评估里指出的亮点，逐字引用"],
      "no_change": false,
      "change_summary": "一句话总结本轮改了什么"
    }

Pipeline 拿到 JSON 后：
  1. 按顺序在原文里 find(anchor) → 替换为 replacement
  2. anchor 找不到 → 尝试 fuzzy match（忽略空白/标点）
  3. 还找不到 → 该 patch 标 failed，跳过
  4. 一轮里 >50% 的 patch 失败 → 回退到"整章重写"模式（安全网）

输入新增字段
-------------
- `highlights`: 评估里指出的亮点（必须保留）
- `previous_patches`: 上一轮实际生效的 patch 列表（防震荡）
- `issues`: 评估出的问题列表（替代 evaluation 整个对象，更聚焦）
"""

from core.base_agent import BaseAgent

SYSTEM_PROMPT = """你是一位专业的小说内容优化专家，擅长审稿后的精准修订。

你的任务是：根据编辑的审稿意见（问题列表），对章节内容做**局部精准修改**。

## 核心原则

1. **只改问题部分**：不要重写全文，只针对指出的问题进行最小化修改
2. **保留亮点**：评估中指出的亮点必须完整保留，一个字都不要改
3. **保持风格**：修订后的文风要与原文一致，不要让读者感到"这一段是 AI 重写的"
4. **世界观一致**：所有修改必须严格遵守世界观设定
5. **不引入新问题**：修订时不要引入新的逻辑矛盾
6. **不重复上一轮**：上一轮已经改过的地方，除非必要不要改回去

## 输出格式（严格 JSON，不要任何额外文字）

{
    "patches": [
        {
            "anchor": "原文中一段 >= 15 字的逐字片段（必须能在原文中唯一命中）",
            "replacement": "替换后的文本",
            "reason": "logic|timing|character|worldview|style"
        }
    ],
    "highlights_preserved": ["评估里指出的亮点，逐字引用"],
    "no_change": false,
    "change_summary": "一句话总结本轮修改了哪些内容"
}

## 锚点规则（必须严格遵守）

- anchor 必须从原文中**逐字复制**，不要改写、缩写、加字或删字
- anchor 长度 >= 15 个汉字（或 10 个英文单词），确保在原文中**唯一**命中
- 如果问题涉及多处分散的小改动，输出多个 patch
- 如果找不到 >= 15 字的唯一锚点，选最长的可用片段（但不要 < 8 字）
- 如果问题无法通过局部修改解决（如整体节奏问题），设 no_change=true 并在 change_summary 说明原因

## 常见错误（不要犯）

- ❌ anchor 是改写后的文字（模型"总结"了原文） → pipeline 找不到，patch 失败
- ❌ anchor 太短（< 8 字） → 可能在原文中多次出现，替换错位置
- ❌ replacement 改变了原意之外的内容 → 引入新问题
- ❌ 输出全文而不是 patch → pipeline 无法消费"""


class RevisionAgent(BaseAgent):
    """回流修订 Agent —— patch 协议版"""

    def __init__(self, llm_client):
        super().__init__("回流修订", llm_client)

    def run(self, input_data: dict) -> dict:
        """
        输入: {
            "content": str,            # 原始章节正文
            "issues": list,            # 评估出的问题列表 [{type, description, location, suggestion}]
            "highlights": list,        # 评估里指出的亮点（必须保留）
            "world_view": dict,
            "chapter_index": int,
            "current_round": int,
            "max_rounds": int,
            "previous_patches": list    # 上一轮实际生效的 patch（防震荡）
        }
        输出: {
            "chapter_index": int,
            "patches": [...],
            "highlights_preserved": [...],
            "no_change": bool,
            "change_summary": str,
            "revised": bool,
            "round": int,
            "issues_count": int,
            "word_count": int
        }
        """
        content = input_data.get("content", "")
        issues = input_data.get("issues", [])
        highlights = input_data.get("highlights", [])
        world_view = input_data.get("world_view", {})
        chapter_index = input_data.get("chapter_index", 1)
        current_round = input_data.get("current_round", 1)
        max_rounds = input_data.get("max_rounds", 3)
        previous_patches = input_data.get("previous_patches", [])

        self.set_status("running")
        self.log(f"开始修订第{chapter_index}章（第{current_round}轮）...")
        self.set_progress(10)

        if not issues:
            self.log("没有问题需要修订，跳过")
            self.set_progress(100)
            self.set_status("success")
            return {
                "chapter_index": chapter_index,
                "patches": [],
                "highlights_preserved": highlights,
                "no_change": True,
                "change_summary": "无问题，无需修订",
                "revised": False,
                "round": current_round,
                "issues_count": 0,
                "word_count": len(content),
            }

        # 构建问题列表文本
        issues_text = self._format_issues(issues)
        highlights_text = self._format_highlights(highlights)
        prev_patches_text = self._format_previous_patches(previous_patches)

        user_prompt = f"""【需要修订的章节正文】
{content}

【世界观规则（修订时必须严格遵守）】
{world_view.get('world_view', {}).get('rules', '无特殊规则')}

【评估出的问题（必须全部处理）】
{issues_text}

【评估里指出的亮点（必须完整保留，一个字都不要改）】
{highlights_text}
{prev_patches_text}
【修订要求】
1. 针对每个问题，找到原文中的具体位置，输出 anchor（逐字复制）+ replacement
2. 严格遵循世界观设定
3. 亮点必须原样保留
4. 上一轮已经改过的地方，除非必要不要改回去
5. 输出 JSON 格式的 patches"""

        self.set_progress(40)
        self.log(
            f"第{chapter_index}章第{current_round}轮修订中，共 {len(issues)} 个问题...")

        try:
            # LongCat-2.0 的思考过程与响应共享 max_tokens 预算。
            # 修订 prompt 包含完整章节正文 + 问题 + 亮点，很大。
            # LLMClient 内置自动重试：空响应时自动提高预算重试（最多 2 次）。
            # 初始预算设高，绝大多数情况一次成功。
            raw = self.call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.5,
                max_tokens=8192,  # 修订输出是 patch JSON，8k 足够，降低思考时长
            )

            self.set_progress(80)
            self.set_status("success")

            result = self._parse_patch_response(
                raw, content, chapter_index, current_round, len(issues),
                highlights)

            self.set_progress(100)
            self.log(
                f"✅ 第{chapter_index}章第{current_round}轮修订完成："
                f"{len(result.get('patches', []))} 个 patch，"
                f"no_change={result.get('no_change')}，"
                f"summary={result.get('change_summary', '')[:40]}")

            self.finished_signal.emit(self.name, result)
            return result

        except Exception as e:
            self.set_status("error")
            self.log(f"❌ 修订失败: {e}")
            result = {
                "chapter_index": chapter_index,
                "patches": [],
                "highlights_preserved": highlights,
                "no_change": True,
                "change_summary": f"修订失败: {e}",
                "revised": False,
                "round": current_round,
                "issues_count": len(issues),
                "word_count": len(content),
                "error": str(e),
            }
            self.finished_signal.emit(self.name, result)
            return result

    # ------------------------------------------------------------------
    #  响应解析
    # ------------------------------------------------------------------
    def _parse_patch_response(self, raw: str, content: str,
                              chapter_index: int, current_round: int,
                              issues_count: int, highlights: list) -> dict:
        """解析模型输出的 patch JSON；失败时回退到全文模式。"""
        parsed = None
        try:
            parsed = self.parse_json_response(raw)
        except Exception:
            parsed = None

        if parsed is None or not isinstance(parsed, dict):
            # JSON 解析失败：回退到"全文重写"模式（安全网）
            self.log("⚠️ patch JSON 解析失败，回退到全文重写模式")
            cleaned = self._strip_html_comments(raw)
            # 关键修复：若模型返回内容为空，保留原文而非清空
            if not cleaned or len(cleaned) < 50:
                self.log("⚠️ 模型返回内容为空，保留原文不做修改")
                return {
                    "chapter_index": chapter_index,
                    "patches": [],
                    "_fallback_full_rewrite": False,
                    "_fallback_content": content,   # 保留原文
                    "highlights_preserved": highlights,
                    "no_change": True,
                    "change_summary": "模型返回内容为空，保留原文",
                    "revised": False,
                    "round": current_round,
                    "issues_count": issues_count,
                    "word_count": len(content),
                }
            return {
                "chapter_index": chapter_index,
                "patches": [],
                "_fallback_full_rewrite": True,   # 标记：pipeline 直接替换全文
                "_fallback_content": cleaned,
                "highlights_preserved": highlights,
                "no_change": False,
                "change_summary": "JSON 解析失败，回退到全文重写",
                "revised": True,
                "round": current_round,
                "issues_count": issues_count,
                "word_count": len(cleaned),
            }

        patches = parsed.get("patches", [])
        if not isinstance(patches, list):
            patches = []

        # 校验每个 patch 的必要字段
        valid_patches = []
        for p in patches:
            if not isinstance(p, dict):
                continue
            anchor = (p.get("anchor") or "").strip()
            replacement = (p.get("replacement") or "").strip()
            if not anchor:
                continue
            valid_patches.append({
                "anchor": anchor,
                "replacement": replacement,
                "reason": p.get("reason", ""),
            })

        no_change = bool(parsed.get("no_change", False))
        if no_change:
            valid_patches = []

        return {
            "chapter_index": chapter_index,
            "patches": valid_patches,
            "highlights_preserved": parsed.get("highlights_preserved",
                                               highlights),
            "no_change": no_change,
            "change_summary": parsed.get("change_summary", ""),
            "revised": bool(valid_patches) and not no_change,
            "round": current_round,
            "issues_count": issues_count,
            "word_count": len(content),
        }

    # ------------------------------------------------------------------
    #  格式化辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _format_issues(issues: list) -> str:
        """格式化问题列表"""
        if not issues:
            return "  （无问题）"
        lines = []
        for i, issue in enumerate(issues, 1):
            itype = issue.get("type", "unknown")
            desc = issue.get("description", "")
            location = issue.get("location", "")
            suggestion = issue.get("suggestion", "")
            lines.append(f"{i}. [类型:{itype}] {desc}")
            if location:
                lines.append(f"   位置: {location}")
            if suggestion:
                lines.append(f"   建议: {suggestion}")
        return "\n".join(lines)

    @staticmethod
    def _format_highlights(highlights: list) -> str:
        """格式化亮点列表"""
        if not highlights:
            return "  （评估未指出亮点）"
        lines = []
        for i, hl in enumerate(highlights, 1):
            lines.append(f"  {i}. {hl}")
        return "\n".join(lines)

    @staticmethod
    def _format_previous_patches(previous_patches: list) -> str:
        """格式化上一轮已生效的 patch（防震荡）"""
        if not previous_patches:
            return ""
        lines = ["【上一轮已做的修改（除非必要，不要改回去）】"]
        for i, p in enumerate(previous_patches, 1):
            reason = p.get("reason", "")
            anchor_preview = (p.get("anchor") or "")[:30]
            lines.append(f"  {i}. [{reason}] 「{anchor_preview}…」")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    #  HTML 注释清理（兼容旧版模型输出）
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_html_comments(text: str) -> str:
        """清理模型可能残留的 HTML 注释标记。"""
        import re
        text = re.sub(r"<!--REVISION:[^>]*?-->", "", text)
        text = re.sub(r"<!--NO_CHANGE-->", "", text)
        return text.strip()
