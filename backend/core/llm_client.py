"""Anthropic Messages API client used by every writing agent.

The application deliberately does not identify a model vendor.  Any service
that implements the Anthropic Messages API can be used after supplying its API
key, service base URL and model name in the Electron settings page.
"""

import threading
import time
from typing import Callable
from urllib.parse import urlparse

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class LLMClient:
    """A vendor-neutral client for the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
        timeout: float = 120.0,
    ):
        if not HAS_ANTHROPIC:
            raise ImportError("请先安装 anthropic SDK：pip install anthropic")

        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").strip().rstrip("/")
        self.model = (model or "").strip()
        self.max_retries = max(1, max_retries)
        self.timeout = timeout

        # 用量累计（每次调用后从响应的 usage 字段累加），供成本门禁使用。
        self._usage_lock = threading.Lock()
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.budget = {
            "max_cost_usd": 0.0,          # 0 = 不限制
            "price_input_per_mtok": 3.0,
            "price_output_per_mtok": 15.0,
        }

        if not self.api_key:
            raise ValueError("请先在设置中填写 API Key")
        if not self.base_url:
            raise ValueError("请先在设置中填写 Anthropic API Base URL")
        if not self.model:
            raise ValueError("请先在设置中填写模型名称")

        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Anthropic API Base URL 必须是有效的 HTTP(S) 地址")

        # api_key is the official Anthropic authentication method.  Sending a
        # Bearer header as well preserves compatibility with common
        # Anthropic-compatible gateways that use that authentication style.
        self.client = anthropic.Anthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
            max_retries=0,
            default_headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Send one non-streaming Messages API request with bounded retries.

        Retries on exceptions AND on empty/short responses (raising the token
        budget each retry, since a truncated response is often caused by the
        max_tokens ceiling).
        """
        token_limit = max_tokens or 4096
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                result = self._create_message(
                    system_prompt, user_prompt, temperature, token_limit
                )
                if result and len(result.strip()) >= 50:
                    return result
                # 空/极短响应：提高预算重试（常因 max_tokens 触顶截断所致）
                if attempt < self.max_retries - 1:
                    token_limit = int(token_limit * 1.5) + 2000
                    print(
                        f"[LLMClient] 响应为空或过短，提高预算重试 "
                        f"(重试 {attempt + 2}/{self.max_retries}, max_tokens={token_limit})"
                    )
                    continue
                return result
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)

        assert last_error is not None
        raise last_error

    def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        on_chunk: Callable[[str, str], None] | None = None,
        on_complete: Callable[[str], None] | None = None,
    ) -> str:
        """Stream text from a Messages API response and return the full text."""
        token_limit = max_tokens or 4096
        full_text = ""
        # 首 token 停滞检测：服务端可能长时间不吐第一个 token（长 prompt 推理）。
        # 阻塞式迭代在收到 token 前不会执行循环体，故在此刻比较起始时间最准确。
        start_time = time.time()
        stall_warned = False

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=token_limit,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    if on_chunk:
                        on_chunk(text, full_text)
                    if not stall_warned and time.time() - start_time > 60:
                        stall_warned = True
                        print(
                            f"[LLMClient] 警告: 流式响应首 token 等待超过 60 秒，"
                            f"服务端可能仍在推理，继续等待"
                        )
                # 流式结束后取最终消息累计用量。部分 Anthropic 兼容网关不实现
                # get_final_message，取不到就跳过，不影响正文。
                try:
                    final = stream.get_final_message()
                    self._record_usage(getattr(final, "usage", None))
                except Exception:
                    pass
        except Exception:
            # Do not silently turn a provider failure into a partial chapter.
            raise

        if on_complete:
            on_complete(full_text)
        return full_text

    def _create_message(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        self._record_usage(getattr(response, "usage", None))
        text_blocks = [
            block.text
            for block in response.content
            if hasattr(block, "text") and block.text
        ]
        return "".join(text_blocks)

    # ------------------------------------------------------------------
    #  用量统计与成本门禁
    # ------------------------------------------------------------------
    def _record_usage(self, usage) -> None:
        """累计一次调用的 token 用量。

        Anthropic 兼容网关未必都返回 usage，字段也可能缺失——缺失时静默跳过，
        绝不能让统计问题影响正常生成。
        """
        if usage is None:
            return
        try:
            inp = int(getattr(usage, "input_tokens", 0) or 0)
            out = int(getattr(usage, "output_tokens", 0) or 0)
        except (TypeError, ValueError):
            return
        with self._usage_lock:
            self.usage["calls"] += 1
            self.usage["input_tokens"] += inp
            self.usage["output_tokens"] += out

    def configure_budget(self, max_cost_usd: float = 0.0,
                         price_input_per_mtok: float = 3.0,
                         price_output_per_mtok: float = 15.0) -> None:
        """配置成本上限与单价（美元 / 百万 token）。上限 0 表示不限制。"""

        def _num(value, default):
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                return default

        self.budget = {
            "max_cost_usd": _num(max_cost_usd, 0.0),
            "price_input_per_mtok": _num(price_input_per_mtok, 3.0),
            "price_output_per_mtok": _num(price_output_per_mtok, 15.0),
        }

    def cost_usd(self) -> float:
        """按配置单价估算累计花费（美元）。"""
        with self._usage_lock:
            inp = self.usage["input_tokens"]
            out = self.usage["output_tokens"]
        return (inp / 1_000_000.0) * self.budget["price_input_per_mtok"] \
            + (out / 1_000_000.0) * self.budget["price_output_per_mtok"]

    def budget_status(self) -> dict:
        """返回成本门禁状态；调用方据此决定告警或暂停。"""
        limit = self.budget["max_cost_usd"]
        spent = self.cost_usd()
        with self._usage_lock:
            usage = dict(self.usage)
        return {
            "spent_usd": round(spent, 4),
            "limit_usd": limit,
            "ratio": round(spent / limit, 4) if limit > 0 else 0.0,
            "exceeded": limit > 0 and spent >= limit,
            **usage,
        }

    def test_connection(self) -> dict:
        """Test the configured service with the same Messages API used by agents."""
        try:
            response = self.chat(
                system_prompt="You are a helpful assistant.",
                user_prompt="回复“连接成功”三个字，不要多答。",
                max_tokens=50,
            )
            return {"ok": True, "message": f"连接正常：{response.strip()}"}
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            if "401" in message or "unauthorized" in lowered or "authentication" in lowered:
                user_message = "API Key 无效或认证失败，请检查设置"
            elif "403" in message or "forbidden" in lowered:
                user_message = "当前 API Key 没有访问该模型的权限"
            elif "404" in message or "not found" in lowered:
                user_message = "找不到接口或模型，请检查 Base URL 和模型名称"
            elif "timeout" in lowered or "connection" in lowered:
                user_message = "网络连接超时，请检查 Base URL 和网络"
            else:
                user_message = f"连接异常：{message[:120]}"
            return {"ok": False, "message": user_message}

    def set_connection(self, base_url: str | None = None, model: str | None = None):
        """Update connection metadata for callers that keep an existing client."""
        if base_url:
            self.base_url = base_url.strip().rstrip("/")
        if model:
            self.model = model.strip()


def test_connection(api_key: str, base_url: str, model: str) -> tuple[bool, str]:
    """Compatibility helper for code that tests a connection outside the API."""
    result = LLMClient(api_key=api_key, base_url=base_url, model=model).test_connection()
    return result["ok"], result["message"]
