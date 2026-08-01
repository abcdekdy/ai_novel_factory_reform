"""
Agent基类 - 定义统一接口和信号
所有Agent继承此类，通过信号向GUI和Web面板广播状态
"""

from PyQt6.QtCore import QObject, pyqtSignal
from core.llm_client import LLMClient


class BaseAgent(QObject):
    """
    所有Agent的基类
    提供统一的LLM调用封装、日志信号、进度信号
    """

    # 信号定义
    log_signal = pyqtSignal(str, str)        # (agent_name, message)
    progress_signal = pyqtSignal(str, int)   # (agent_name, percent, 0-100)
    status_signal = pyqtSignal(str, str)     # (agent_name, status: idle/running/success/error)
    finished_signal = pyqtSignal(str, dict)  # (agent_name, result_dict)

    def __init__(self, name: str, llm_client: LLMClient):
        super().__init__()
        self.name = name
        self.llm = llm_client

    def log(self, message: str):
        """发送日志信号"""
        self.log_signal.emit(self.name, message)

    def set_progress(self, percent: int):
        """设置进度（0-100）"""
        self.progress_signal.emit(self.name, max(0, min(100, percent)))

    def set_status(self, status: str):
        """设置状态: idle/running/success/error/waiting"""
        self.status_signal.emit(self.name, status)

    def call_llm(self, system_prompt: str, user_prompt: str,
                 temperature: float = None, max_tokens: int = None) -> str:
        """
        调用LLM的便捷方法，自动记录日志
        self.llm会在子类中初始化
        """
        if not hasattr(self, 'llm') or self.llm is None:
            raise RuntimeError(f"Agent {self.name} 未设置LLM客户端")

        self.log(f"正在调用模型...")
        try:
            result = self.llm.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature or 0.8,
                max_tokens=max_tokens or 4096
            )
            self.log(f"模型调用完成，返回 {len(result)} 字")
            return result
        except Exception as e:
            self.log(f"模型调用失败: {e}")
            raise

    def call_llm_stream(self, system_prompt: str, user_prompt: str,
                        temperature: float = None, max_tokens: int = None,
                        on_progress=None) -> str:
        """
        流式调用LLM。on_progress(partial_text: str) 在每个 token 到达时调用，
        可用于 UI 进度更新。返回完整响应文本。
        """
        if not hasattr(self, 'llm') or self.llm is None:
            raise RuntimeError(f"Agent {self.name} 未设置LLM客户端")

        self.log(f"正在调用模型(流式)...")
        try:
            result = self.llm.chat_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature or 0.8,
                max_tokens=max_tokens or 4096,
                on_chunk=(lambda chunk, full: on_progress(full)) if on_progress else None,
            )
            self.log(f"模型调用完成(流式)，返回 {len(result)} 字")
            return result
        except Exception as e:
            self.log(f"模型调用失败: {e}")
            raise

    def run(self, input_data: dict) -> dict:
        """
        子类必须重写此方法
        input_data: 输入数据字典
        返回: result字典
        """
        raise NotImplementedError(f"Agent {self.name} 必须实现run()方法")

    @staticmethod
    def parse_json_response(text: str) -> dict:
        """
        从 LLM 响应中提取 JSON（子类共用）。

        策略（由简到繁）:
          1. json.loads（strict=True，严格模式）
          2. json.loads（strict=False，允许控制字符 — LLM 常输出字面换行/制表符）
          3. 提取 ```json ... ``` 代码块后解析
          4. 在大文本中找到第一个 '{'，从末尾逐个位置尝试解析直到成功
        任一步成功即返回；全部失败时 dump 原始响应到文件便于诊断。
        """
        import json
        import re

        if not text or not isinstance(text, str):
            raise ValueError("LLM 响应为空或非字符串")

        text = text.strip()

        # 辅助：尝试解析一个候选字符串（两种严格模式都试）
        def _try_parse(s: str):
            for strict in (True, False):
                try:
                    return json.loads(s, strict=strict)
                except (json.JSONDecodeError, ValueError):
                    pass
            return None

        # 策略 1 + 2：直接解析（strict=True/False）
        result = _try_parse(text)
        if result is not None:
            return result

        # 策略 3：提取 ```json 代码块
        blocks = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        for block in blocks:
            result = _try_parse(block.strip())
            if result is not None:
                return result
            # 代码块内可能仍有前后文字，记录下稍后走策略 4
            text = block.strip()
            break  # 只取第一个代码块走后续流程

        # 部分模型会在长 JSON 中出现少量机械性笔误。只处理两种有明确
        # 结构特征的错误；修复后仍须通过 json.loads，不会放宽 JSON 标准。
        repaired_text = BaseAgent._repair_common_json_errors(text)
        if repaired_text != text:
            result = _try_parse(repaired_text)
            if result is not None:
                return result

        # 策略 4：从第一个 '{' 起，逐步尝试至文本末尾
        start = text.find('{')
        if start == -1:
            BaseAgent._dump_failed_response(text)
            raise ValueError(f"响应中未找到 JSON 对象:\n{text[:200]}...")

        # 快速路径：greedy 正则先试一次
        match = re.search(r'\{.*\}', text[start:], re.DOTALL)
        if match:
            result = _try_parse(match.group(0))
            if result is not None:
                return result

        # 慢速路径：从文本最后一个 '}' 往前逐个尝试
        end_positions = [i for i in range(len(text) - 1, start - 1, -1)
                        if text[i] == '}']
        for end in end_positions:
            candidate = text[start:end + 1]
            result = _try_parse(candidate)
            if result is not None:
                return result

        # 策略 5：截断自动修复 —— 当 JSON 在 max_tokens 处被硬截断时，
        # 剥离尾部不完整片段、补全未闭合的引号/括号，再尝试解析。
        repaired = BaseAgent._repair_truncated_json(text[start:])
        if repaired is not None:
            result = _try_parse(repaired)
            if result is not None:
                return result

        # 全部失败：保存原始响应到文件便于诊断
        BaseAgent._dump_failed_response(text)

        # 辅助：检测响应是否像是被 max_tokens 截断（末尾没有配对的引号/括号）。
        def _looks_truncated(s: str) -> bool:
            """判断 JSON 文本是否像在 token 上限处被截断。"""
            stripped = s.rstrip()
            if not stripped:
                return False
            # 被截断的 JSON 通常以非结构字符收尾，且缺少闭括号。
            if stripped[-1] not in '"}]':
                return True
            # 引号未闭合也强烈暗示截断。
            if stripped.count('"') % 2 == 1:
                return True
            return False

        hint = ""
        if _looks_truncated(text):
            hint = (
                "\n⚠️ 疑似响应在 max_tokens 处被截断（末尾缺少闭括号或引号未闭合）。"
                "可尝试：增大 config.json 中的 max_tokens / outline_max_tokens，"
                "或减少章节数重新生成。"
            )

        raise ValueError(
            f"无法从响应中解析 JSON（已尝试 {len(end_positions)} 个位置）:\n"
            f"{text[start:start+300]}...\n"
            f"{hint}"
        )

    @staticmethod
    def _repair_truncated_json(text: str) -> str | None:
        """
        尝试修复被 max_tokens 截断的 JSON。

        策略：正向扫描记录所有"结构分隔位置"（逗号 / 冒号 / 左括号
        在字符串外的出现位置），确认截断后从最末尾的分隔位置开始
        逐个向前尝试——在每个候选位置截断、补全闭合括号、json.loads
        验证；第一个通过验证的即返回。

        这比"基于深度的 safe_at 推断"更可靠，因为 json.loads 自身就是
        最终裁判——能解析就是对的，不能就继续向前找。
        """
        import json

        if not text:
            return None

        s = text.rstrip()
        if len(s) < 2:
            return None

        # 快速判断：已经能解析 → 不是截断
        try:
            json.loads(s, strict=False)
            return None
        except (json.JSONDecodeError, ValueError):
            pass

        # ── 1. 正向扫描：记录"结构分隔位置" ────────────────────────────
        #    分隔位置 = 在字符串外的 ','  ':'  '{'  '[' 的位置
        #    这些位置的左侧都是"潜在的安全截断点"
        separator_positions: list[int] = []
        depth_stack: list[str] = []
        in_string = False
        escape = False

        for i, ch in enumerate(s):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            # 字符串外
            if ch in ',:{[':
                separator_positions.append(i)
                if ch in '{[':
                    depth_stack.append(ch)
                elif ch in '}]':
                    if depth_stack:
                        depth_stack.pop()

        # 如果所有容器都闭合但仍解析失败，说明不是截断而是语法错误
        if not depth_stack and not in_string:
            return None

        if not separator_positions:
            return None

        # ── 2. 从最后一个分隔位置开始，逐个向前尝试修复 ────────────────
        def _closing_for(stripped: str) -> str:
            """计算 stripped 需要补多少个闭合括号，并返回补全后的字符串。"""
            stack: list[str] = []
            in_s = False
            esc = False
            for c in stripped:
                if esc:
                    esc = False
                    continue
                if c == '\\' and in_s:
                    esc = True
                    continue
                if c == '"':
                    in_s = not in_s
                    continue
                if in_s:
                    continue
                if c in '{[':
                    stack.append(c)
                elif c == '}':
                    if stack and stack[-1] == '{':
                        stack.pop()
                elif c == ']':
                    if stack and stack[-1] == '[':
                        stack.pop()
            # 如果还在字符串中，补一个引号
            result = stripped
            if in_s:
                result = result + '"'
            for opener in reversed(stack):
                result = result + ('}' if opener == '{' else ']')
            return result

        def _try_parse(stripped: str):
            """尝试解析，strict=True/False 都试。"""
            for strict in (True, False):
                try:
                    return json.loads(stripped, strict=strict)
                except (json.JSONDecodeError, ValueError):
                    pass
            return None

        # 从最末尾的分隔位置向前遍历
        for idx in range(len(separator_positions) - 1, -1, -1):
            pos = separator_positions[idx]

            # 在位置 pos 处截断（丢弃 pos 及之后的内容），保留 s[:pos]
            trimmed = s[:pos]

            # 边界 case：trimmed 末尾如果是孤儿标点（, : { [），可能有问题
            # 但 _closing_for 和 json.loads 会验证；不行的话继续向前找

            # 尝试直接解析（不补括号）
            if _try_parse(trimmed) is not None:
                return trimmed

            # 尝试补全闭合括号后解析
            candidate = _closing_for(trimmed)
            if candidate != trimmed and _try_parse(candidate) is not None:
                return candidate

        return None

    @staticmethod
    def _repair_common_json_errors(text: str) -> str:
        """修复模型输出中可无歧义识别的少量 JSON 笔误。"""
        import re

        # 例如：" "narrative_purpose": ...  →  "narrative_purpose": ...
        repaired = re.sub(
            r'"\s+"([A-Za-z_][A-Za-z0-9_]*)"\s*:',
            r'"\1":',
            text,
        )

        # 例如："key_events": "事件一", "事件二"]
        #   →  "key_events": ["事件一", "事件二"]
        # 仅限大纲 schema 中本应为字符串数组的字段，避免误改普通文本。
        list_without_opening_bracket = re.compile(
            r'("(?:key_events|characters_present|foreshadowing)"\s*:\s*)'
            r'("(?:[^"\\\\]|\\\\.)*"(?:\s*,\s*"(?:[^"\\\\]|\\\\.)*")+)' 
            r'(\s*\])'
        )
        return list_without_opening_bracket.sub(
            lambda match: f"{match.group(1)}[{match.group(2)}{match.group(3)}",
            repaired,
        )

    @staticmethod
    def _dump_failed_response(text: str) -> None:
        """把解析失败的原始响应落盘，便于排查 LLM 输出问题。"""
        import time
        from pathlib import Path
        try:
            dump_dir = Path("projects") / "_parse_failures"
            dump_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            dump_path = dump_dir / f"parse_failure_{ts}.txt"
            dump_path.write_text(
                f"# Raw LLM response that failed JSON parsing\n"
                f"# Length: {len(text)} chars\n\n{text}",
                encoding="utf-8"
            )
            print(f"[parse_json_response] 原始响应已保存到: {dump_path}")
        except Exception as e:
            print(f"[parse_json_response] 保存原始响应失败: {e}")
