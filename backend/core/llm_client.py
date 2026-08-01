"""
LLM客户端 - 支持 LongCat (Anthropic兼容) 和 DeepSeek (OpenAI兼容)
默认使用 LongCat API: https://api.longcat.chat/anthropic
"""

import time

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class LLMClient:
    """
    统一LLM客户端，根据配置自动选择后端
    provider: "longcat" | "deepseek"

    LongCat配置:
        base_url: https://api.longcat.chat/anthropic
        model: (需要根据LongCat实际模型名填写)
        使用 anthropic SDK

    DeepSeek配置:
        base_url: https://api.deepseek.com/v1
        model: deepseek-chat
        使用 openai SDK
    """

    def __init__(self, api_key: str, provider: str = "longcat",
                 base_url: str = None, model: str = None, max_retries: int = 3,
                 timeout: float = 120.0):
        """
        timeout: 单次调用超时秒数（connect + read 合计）。
                 续写大纲等长 prompt 场景建议 ≥ 120s。
        """
        self.api_key = api_key
        self.provider = provider.lower()
        self.max_retries = max_retries
        self.timeout = timeout
        self._streaming_callback = None

        if self.provider == "longcat":
            # Anthropic兼容模式 (LongCat使用Bearer <REDAUTH>)
            if not HAS_ANTHROPIC:
                raise ImportError("请先安装 anthropic SDK: pip install anthropic")
            self.base_url = base_url or "https://api.longcat.chat/anthropic"
            self.model = model or "LongCat-2.0"
            self.client = anthropic.Anthropic(
                auth_token=api_key,   # Bearer <REDAUTH> 方式
                base_url=self.base_url,
                timeout=timeout,
            )
        elif self.provider == "deepseek":
            # OpenAI兼容模式
            if not HAS_OPENAI:
                raise ImportError("请先安装 openai SDK: pip install openai")
            self.base_url = base_url or "https://api.deepseek.com/v1"
            self.model = model or "deepseek-chat"
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url=self.base_url,
                max_retries=0,
                timeout=timeout,
            )
        else:
            raise ValueError(f"不支持的provider: {provider}，可选: longcat, deepseek")

    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.7, max_tokens: int = None) -> str:
        """普通聊天调用。内部用线程 + 心跳日志，避免长时间无反馈。
        自动重试：空响应时提高预算重试，心跳显示总耗时。"""
        if max_tokens is None:
            max_tokens = 8192 if self.provider == "longcat" else 4096

        import threading
        actual_max = max_tokens
        total_elapsed = 0
        heartbeat_interval = min(15, max(1, int(self.timeout)))

        for retry in range(3):  # 原始 + 2 次重试
            result_holder = {"value": None, "error": None, "done": False}

            def _worker():
                try:
                    if self.provider == "longcat":
                        result_holder["value"] = self._chat_anthropic(
                            system_prompt, user_prompt, temperature, actual_max)
                    else:
                        result_holder["value"] = self._chat_openai(
                            system_prompt, user_prompt, temperature, actual_max)
                except Exception as e:
                    result_holder["error"] = e
                finally:
                    result_holder["done"] = True

            t = threading.Thread(target=_worker, daemon=True)
            t.start()

            # 心跳：显示总耗时（跨重试累计）
            elapsed_this_retry = 0
            while not result_holder["done"]:
                t.join(timeout=heartbeat_interval)
                elapsed_this_retry += heartbeat_interval
                total_elapsed += heartbeat_interval
                if not result_holder["done"]:
                    retry_tag = f"[重试 {retry + 1}/3]" if retry > 0 else ""
                    print(f"[LLMClient] 仍在等待模型响应{retry_tag}... "
                          f"(本次 {elapsed_this_retry} 秒, "
                          f"累计 {total_elapsed} 秒, "
                          f"超时上限 {self.timeout} 秒)")

            if result_holder["error"] is not None:
                raise result_holder["error"]

            result = result_holder["value"]
            # 空响应且还有重试次数 → 提高预算重试
            if not result or (isinstance(result, str) and len(result.strip()) < 50):
                if retry < 2:
                    actual_max = int(actual_max * 1.5) + 2000
                    print(f"[LLMClient] 响应为空，自动重试 "
                          f"(重试 {retry + 2}/3, max_tokens={actual_max})")
                    continue
            return result

        return ""

    def chat_stream(self, system_prompt: str, user_prompt: str,
                    temperature: float = 0.7, max_tokens: int = None,
                    on_chunk=None, on_complete=None):
        """
        流式聊天调用。内置停滞检测：若 60 秒无新 token，打印警告。
        """
        import time as _time
        if max_tokens is None:
            max_tokens = 8192 if self.provider == "longcat" else 4096
        full_text = ""
        last_token_time = _time.time()
        stall_warned = False

        def _on_chunk(text, full):
            nonlocal last_token_time, stall_warned
            last_token_time = _time.time()
            stall_warned = False
            if on_chunk:
                on_chunk(text, full)

        if self.provider == "longcat":
            try:
                kwargs = {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "stream": True,
                }
                # 如果base_url不是默认的，需要传入
                if self.base_url != "https://api.longcat.chat/anthropic":
                    kwargs["base_url"] = self.base_url

                with self.client.messages.stream(**kwargs) as stream:
                    for text in stream.text_stream:
                        full_text += text
                        _on_chunk(text, full_text)
                        # 停滞检测
                        if not stall_warned and _time.time() - last_token_time > 60:
                            stall_warned = True
                            print(f"[LLMClient] 警告: 流式响应停滞超过 60 秒无新 token，"
                                  f"已收到 {len(full_text)} 字")
            except Exception as e:
                print(f"[LLMClient] 流式输出中断: {e}，已收到 {len(full_text)} 字")
                if on_chunk:
                    on_chunk(f"\n[流式输出中断: {e}]", full_text)
        else:
            # DeepSeek
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            try:
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        delta = chunk.choices[0].delta.content
                        full_text += delta
                        if on_chunk:
                            on_chunk(delta, full_text)
            except Exception as e:
                if on_chunk:
                    on_chunk(f"\n[流式输出中断: {e}]", full_text)

        if on_complete:
            on_complete(full_text)
        return full_text

    def _chat_anthropic(self, system_prompt, user_prompt, temperature, max_tokens):
        """Anthropic兼容调用（LongCat）。单次调用，无内置重试。
        重试逻辑已移至 chat() 方法层面，便于心跳显示累计耗时。"""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        response = self.client.messages.create(**kwargs)
        if response.content:
            text_blocks = [b for b in response.content
                           if hasattr(b, 'text') and b.text]
            if text_blocks:
                return text_blocks[0].text
        return ""

    def _chat_openai(self, system_prompt, user_prompt, temperature, max_tokens):
        """OpenAI兼容调用（DeepSeek）"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content
            except openai.RateLimitError:
                time.sleep(2 ** attempt)
            except openai.APIError:
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                else:
                    raise
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(2)
                else:
                    raise
        return ""

    def test_connection(self) -> dict:
        """测试当前配置的连通性，返回 {ok, message}"""
        try:
            response = self.chat(
                system_prompt="You are a helpful assistant.",
                user_prompt="回复'连接成功'三个字，不要多答。",
                max_tokens=50
            )
            return {"ok": True, "message": f"连接正常：{response.strip()}"}
        except Exception as e:
            err_msg = str(e)
            if "401" in err_msg or "Unauthorized" in err_msg or "authentication" in err_msg.lower():
                return {"ok": False, "message": "API Key 无效或认证失败，请检查设置"}
            elif "403" in err_msg or "Forbidden" in err_msg:
                return {"ok": False, "message": "权限不足，请检查 Key 的访问权限"}
            elif "404" in err_msg:
                return {"ok": False, "message": "接入点不存在，请检查 Base URL"}
            elif "timeout" in err_msg.lower() or "connection" in err_msg.lower():
                return {"ok": False, "message": "网络连接超时，请检查网络"}
            else:
                return {"ok": False, "message": f"连接异常：{err_msg[:100]}"}

    def set_model(self, model: str):
        self.model = model

    def set_provider(self, provider: str = None, base_url: str = None, model: str = None):
        """切换provider（会重新创建client）"""
        if provider:
            self.provider = provider.lower()
        if base_url:
            self.base_url = base_url
        if model:
            self.model = model

        # 重建client（保留 timeout 设定）
        if self.provider == "longcat":
            if HAS_ANTHROPIC:
                self.client = anthropic.Anthropic(
                    auth_token=self.api_key, base_url=self.base_url,
                    timeout=self.timeout)
        elif self.provider == "deepseek":
            if HAS_OPENAI:
                self.client = openai.OpenAI(
                    api_key=self.api_key, base_url=self.base_url,
                    max_retries=0, timeout=self.timeout)


# ===== 兼容层：保留DeepSeekClient作为别名 =====

class DeepSeekClient(LLMClient):
    """向后兼容的DeepSeek客户端（内部使用LLMClient实现）"""
    def __init__(self, api_key, base_url="https://api.deepseek.com/v1",
                 model="deepseek-chat", max_retries=3):
        super().__init__(api_key=api_key, provider="deepseek",
                        base_url=base_url, model=model, max_retries=max_retries)


# ===== 测试连通性 =====

def test_connection(api_key: str, provider: str = "longcat", base_url: str = None) -> tuple:
    """测试API连通性"""
    try:
        client = LLMClient(api_key=api_key, provider=provider, base_url=base_url)
        response = client.chat(
            system_prompt="You are a helpful assistant.",
            user_prompt="回复'连接成功'三个字，不要多答。",
            max_tokens=50
        )
        return True, f"连接正常：{response.strip()}"
    except Exception as e:
        err_msg = str(e)
        if "401" in err_msg or "Unauthorized" in err_msg or "authentication" in err_msg.lower():
            return False, "API Key无效或认证失败，请检查"
        elif "403" in err_msg or "Forbidden" in err_msg:
            return False, "权限不足，请检查Key的访问权限"
        elif "404" in err_msg:
            return False, "接入点不存在，请检查base_url"
        elif "timeout" in err_msg.lower() or "connection" in err_msg.lower():
            return False, "网络连接超时，请检查网络"
        else:
            return False, f"连接异常：{err_msg[:100]}"
