"""
配置管理 - 读写config.json
管理API Key、模型选择、并发数、温度等运行参数
"""

import json
import os
from pathlib import Path

from core.paths import config_path

# 配置文件路径（可写数据目录，见 core/paths.py）
CONFIG_FILE = config_path()

# 默认配置
DEFAULT_CONFIG = {
    "api_key": "",
    # 所有服务均按 Anthropic Messages API 协议调用。用户在界面中填写
    # 服务根地址（客户端会请求 <base_url>/v1/messages）和模型名称。
    "model": "",
    "base_url": "",
    "temperature": 0.8,
    "max_tokens": 4096,
    "concurrency": 3,           # 章节并行生成并发数
    "max_revision_rounds": 3,   # 最大修订轮数
    # patch 命中率 <50% 时是否允许整章重写兜底（关闭则保留原文，少花 token）
    "enable_full_rewrite_fallback": True,
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
    # ---- 成本门禁 ----
    # 累计花费达 80% 告警、达上限自动暂停（进度无损，调高上限后可续写）。
    # 上限为 0 表示不限制。单价需用户按所用服务填写（美元 / 百万 token）。
    "budget_max_cost_usd": 0.0,           # 成本上限（美元），0 = 不限制
    "budget_price_input_per_mtok": 3.0,   # 输入单价（美元/百万 token）
    "budget_price_output_per_mtok": 15.0, # 输出单价（美元/百万 token）
    # ---- 多人格竞稿 ----
    # 每行一个人格，格式「名称|风格描述」。配置 ≥2 个人格后，每章为每个人格
    # 各写一稿，由 Judge 评分选优。留空则退回单 Writer 模式（不产生额外调用）。
    "chapter_personas": "",
}


def load_config() -> dict:
    """加载配置，如果不存在则创建默认配置"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 旧版本的厂商选择不再参与运行；下一次保存配置时会自然移除。
            saved.pop("provider", None)
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
