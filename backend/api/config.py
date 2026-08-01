"""
配置管理 API
"""
import logging

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
    """更新配置"""
    config = load_config()
    # 只允许更新已知字段
    for key in body:
        if key in DEFAULT_CONFIG and key != "api_key":
            config[key] = body[key]
    # API Key 单独处理（不覆盖为空）
    if body.get("api_key"):
        config["api_key"] = body["api_key"]
    try:
        save_config(config)
        return {"ok": True}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {e}")


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
            provider=config.get("provider", "longcat"),
            base_url=config.get("base_url"),
            model=config.get("model", "LongCat-2.0"),
            timeout=30,
        )
        result = client.test_connection()
        return result
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"服务端缺少 LLM SDK: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"连接测试失败: {e}")
