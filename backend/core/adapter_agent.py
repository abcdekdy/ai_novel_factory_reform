"""
多平台适配Agent
将小说内容自动适配为不同发布平台的格式
"""

from core.base_agent import BaseAgent

SYSTEM_PROMPT = """你是一位专业的内容运营专家，擅长将小说内容适配到不同的发布平台。

目标平台规则：

1. **起点中文网/番茄小说等网文平台**：
   - 章节标题格式：「第X章 标题」
   - 段落短、节奏快
   - 对话占比高，描写精炼
   - 末尾可加"本章说"式的互动引导

2. **微信公众号**：
   - 排版精美，段落间空行
   - 标题加粗效果（用【】标记）
   - 适合手机阅读

3. **知乎/短篇平台**：
   - 紧凑叙事，信息密度高
   - 开头即高潮
   - 适合一次性阅读

4. **有声/广播剧脚本**：
   - 标注旁白和角色
   - 对话为主，描写转化为旁白

5. **Markdown电子书**：
   - 标准Markdown格式
   - 章节用##标记
   - 适合Gitbook/电子书阅读

输出格式（严格JSON）：
{
    "platform_name": "平台名",
    "formatted_content": "适配后的内容",
    "formatting_notes": ["适配说明1", "适配说明2"]
}"""


class PlatformAdapterAgent(BaseAgent):
    """多平台适配Agent"""

    def __init__(self, llm_client):
        super().__init__("多平台适配", llm_client)

    def run(self, input_data: dict) -> dict:
        """
        输入: {
            "content": str,
            "title": str,
            "chapter_index": int,
            "platform": str  # 目标平台
        }
        输出: 适配结果字典
        """
        content = input_data.get("content", "")
        title = input_data.get("title", "")
        chapter_index = input_data.get("chapter_index", 1)
        platform = input_data.get("platform", "通用网文格式")

        self.set_status("running")
        self.log(f"适配第{chapter_index}章 → {platform}")
        self.set_progress(30)

        user_prompt = f"""【章节标题】第{chapter_index}章：{title}

【章节正文】
{content}

【目标平台】{platform}

请将以上章节内容适配为{platform}的发布格式。"""

        try:
            result = self.call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=6000
            )

            self.set_progress(80)

            # 与其它 Agent 共用同一套 5 层 JSON 解析（此前这里有一份简化版，
            # 遇到代码块/前后缀文字就退回"原文当内容"，等于静默降级）。
            adapted = self.parse_json_response(result)
            if not isinstance(adapted, dict):
                raise ValueError("适配结果不是 JSON 对象")
            adapted["chapter_index"] = chapter_index
            adapted["platform"] = platform
            adapted["original_title"] = title

            self.set_progress(100)
            self.set_status("success")
            self.log(f"✅ 第{chapter_index}章适配完成 → {platform}")

            self.finished_signal.emit(self.name, adapted)
            return adapted

        except Exception as e:
            self.set_status("error")
            self.log(f"❌ 适配失败: {e}")
            # 失败时返回原文
            result = {
                "chapter_index": chapter_index,
                "platform": platform,
                "formatted_content": content,
                "original_title": title,
                "formatting_notes": [f"适配失败返回原文: {e}"],
                "error": str(e)
            }
            self.finished_signal.emit(self.name, result)
            return result
