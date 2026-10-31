"""
配置管理 API
"""
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from core.config import load_config, save_config, is_api_key_set, DEFAULT_CONFIG

logger = logging.getLogger("novel-factory.config-api")

router = APIRouter()


@router.get("")
async def get_config():
    """获取当前配置（隐藏 API Key）"""
    config = load_config()
    # 不返回完整 API Key
    safe = {k: v for k, v in config.items() if k != "api_key"}
    safe["api_key_set"] = is_api_key_set()
    if config.get("api_key"):
        key = config["api_key"]
        safe["api_key_masked"] = key[:4] + "*" * (len(key) - 8) + key[-4:] if len(key) > 8 else "****"
    return safe


@router.put("")
async def update_config(body: dict):
    """更新配置（带类型与范围校验）"""
    config = load_config()
    base_url = body.get("base_url")
    if base_url is not None:
        if not isinstance(base_url, str):
            raise HTTPException(status_code=422, detail="Base URL 必须是字符串")
        normalized_url = base_url.strip().rstrip("/")
        if normalized_url:
            parsed = urlparse(normalized_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise HTTPException(status_code=422, detail="Base URL 必须是有效的 HTTP(S) 地址")
        body["base_url"] = normalized_url

    model = body.get("model")
    if model is not None:
        if not isinstance(model, str):
            raise HTTPException(status_code=422, detail="模型名称必须是字符串")
        body["model"] = model.strip()

    # 只允许更新已知字段，且必须通过类型/范围校验。
    # 此前只做白名单过滤：把 concurrency 写成 "abc" 也能存进去，随后流水线里
    # threading.Semaphore("abc") 在工作线程抛错——没有兜底，表现为无声卡住。
    for key in list(body):
        if key not in DEFAULT_CONFIG or key in ("api_key", "base_url", "model"):
            continue
        value = body[key]

        if key in _NUMERIC_RULES:
            kind, low, high = _NUMERIC_RULES[key]
            if isinstance(value, bool) or value is None:
                raise HTTPException(status_code=422, detail=f"{key} 必须是数字")
            try:
                number = kind(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"{key} 必须是数字")
            if not (low <= number <= high):
                raise HTTPException(
                    status_code=422,
                    detail=f"{key} 超出允许范围（{low}–{high}）")
            config[key] = number
        elif key in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise HTTPException(status_code=422, detail=f"{key} 必须是布尔值")
            config[key] = value
        elif key in _TEXT_KEYS:
            if not isinstance(value, str):
                raise HTTPException(status_code=422, detail=f"{key} 必须是字符串")
            config[key] = value
        else:
            config[key] = value

    # API Key 单独处理（不覆盖为空）
    if body.get("api_key"):
        config["api_key"] = body["api_key"]
    try:
        save_config(config)
        return {"ok": True}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {e}")


# 数值配置的允许范围：类型, 最小值, 最大值
_NUMERIC_RULES: dict[str, tuple] = {
    "concurrency": (int, 1, 20),
    "max_revision_rounds": (int, 0, 10),
    "quality_threshold": (float, 0.0, 10.0),
    "default_chapter_count": (int, 1, 100),
    "default_chapter_length": (int, 500, 20000),
    "outline_max_tokens": (int, 512, 65536),
    "outline_temperature": (float, 0.0, 2.0),
    "timeout": (int, 10, 3600),
    "budget_max_cost_usd": (float, 0.0, 1_000_000.0),
    "budget_price_input_per_mtok": (float, 0.0, 1_000_000.0),
    "budget_price_output_per_mtok": (float, 0.0, 1_000_000.0),
}
_BOOL_KEYS = {"enable_full_rewrite_fallback", "enable_platform_adaptation"}
_TEXT_KEYS = {"chapter_personas"}


@router.post("/test-connection")
async def test_connection():
    """测试 LLM 连接"""
    from core.llm_client import LLMClient
    config = load_config()
    if not config.get("api_key"):
        raise HTTPException(status_code=400, detail="请先设置 API Key")

    try:
        client = LLMClient(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
            model=config.get("model"),
            timeout=30,
        )
        result = client.test_connection()
        return result
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"服务端缺少 LLM SDK: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"连接测试失败: {e}")
