"""
配置管理 - 读写config.json
管理API Key、模型选择、并发数、温度等运行参数
"""

import json
import os
from pathlib import Path

# 配置文件路径
CONFIG_FILE = Path(__file__).parent.parent / "config.json"

# 默认配置
DEFAULT_CONFIG = {
    "api_key": "",
    "provider": "longcat",               # longcat | deepseek
    "model": "LongCat-2.0",              # 默认模型名
    "base_url": "https://api.longcat.chat/anthropic",  # LongCat接入点
    "temperature": 0.8,
    "max_tokens": 4096,
    "concurrency": 3,           # 章节并行生成并发数
    "max_revision_rounds": 3,   # 最大修订轮数
    "quality_threshold": 7.0,   # 质量评估通过阈值(满分10)
    "default_chapter_count": 5, # 默认章节数
    "default_chapter_length": 3000,  # 默认每章字数
    "web_monitor_port": 5000,   # Web监控面板端口
    # ---- 大纲生成 Agent 配置 ----
    "enable_outline_agent": True,     # 是否启用大纲生成（可在设置页关闭）
    "outline_max_tokens": 8192,       # 大纲生成最大 token
    "outline_temperature": 0.7,       # 大纲生成温度
    # ---- 网络超时 ----
    "timeout": 300,                   # LLM 单次调用超时秒数（续写大纲等长任务建议 ≥ 300）
}


def load_config() -> dict:
    """加载配置，如果不存在则创建默认配置"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 合并默认配置（兼容新增字段）
            config = {**DEFAULT_CONFIG, **saved}
            return config
        except (json.JSONDecodeError, IOError):
            pass

    # 创建默认配置文件
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """保存配置到文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_config(key: str, default=None):
    """获取单个配置项"""
    config = load_config()
    return config.get(key, default)


def set_config(key: str, value):
    """设置单个配置项并保存"""
    config = load_config()
    config[key] = value
    save_config(config)


def is_api_key_set() -> bool:
    """检查API Key是否已配置"""
    return bool(get_config("api_key"))
