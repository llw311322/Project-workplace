"""
LLM 调度层 —— 只管配置选择 + 密钥轮询，
真正的 LLM 调用仍由 LangChain ChatOpenAI 负责。

当前部署只接入一家厂商（通义千问 / 百炼），对话与向量化共用同一把 Key：
选一家的理由是「一把 Key + 一个预算开关」能把演示环境的成本上限锁死，
比维护多家 Key 更可控。厂商表仍是数据驱动结构，将来要加回多厂商，
只需往 VENDOR_DEFS 里补一行 + 在 FALLBACK_CHAIN 里排好顺序。

对外暴露两个核心能力：
  1. list_models() → 返回所有可用 model_key 列表（前端选择用）
  2. get_llm_config(model_key) → 返回 (api_key, base_url, model_name)

用法示例：
  from agent.model_scheduler import scheduler
  api_key, base_url, model_name = scheduler.get_llm_config("qwen")
  llm = ChatOpenAI(api_key=api_key, base_url=base_url, model=model_name, temperature=0)
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from utils.logger import logger

load_dotenv()


@dataclass
class ModelConfig:
    """单个厂商的完整配置（含多密钥）"""
    key: str                        # 调度器里的别名，如 "qwen"
    display_name: str               # 给用户看的名字，如 "通义千问 Qwen-Plus"
    api_keys: List[str]             # 支持逗号分隔多 key 轮询
    base_url: str
    model_name: str                 # 官方模型名
    fallback_to: Optional[str] = None  # 故障时降级到哪个 key（可选）
    bad_keys: set = field(default_factory=set)  # 临时失效黑名单


class ModelScheduler:
    """从 .env 自动发现多厂商配置，提供统一调度接口"""

    # 厂商定义表：key → (env 前缀, 默认模型名, 显示名)
    # 只要 .env 里有对应的 *_API_KEY 和 *_BASE_URL 就能自动注册
    # 当前只接一家：qwen（百炼）。对话 qwen-plus + 向量 text-embedding-v3 共用一把 Key
    VENDOR_DEFS = [
        ("qwen", "QWEN", "qwen-plus", "通义千问 Qwen-Plus"),
    ]

    # 故障降级顺序。单厂商时为空，多厂商时按顺序往后降
    FALLBACK_CHAIN: List[str] = []

    def __init__(self):
        self._configs: Dict[str, ModelConfig] = {}
        self._discover_from_env()
        self._setup_default_fallback()

    # ----------------------------- 内部：从 .env 自动发现 -----------------------------

    def _discover_from_env(self):
        for key, prefix, default_model, display_name in self.VENDOR_DEFS:
            api_key_raw = os.getenv(f"{prefix}_API_KEY", "").strip()
            base_url    = os.getenv(f"{prefix}_BASE_URL", "").strip()
            model_name  = os.getenv(f"{prefix}_MODEL", default_model).strip()

            if not api_key_raw or not base_url:
                continue  # .env 里没配完整，跳过这个厂商

            # 支持逗号分隔多密钥
            api_keys = [k.strip() for k in api_key_raw.split(",") if k.strip()]

            self._configs[key] = ModelConfig(
                key=key,
                display_name=display_name,
                api_keys=api_keys,
                base_url=base_url,
                model_name=model_name,
            )
            logger.debug(f"✅ 发现厂商 {key}: model={model_name}, base_url={base_url}, keys={len(api_keys)}")

        # 用户默认选哪个厂商
        default_key = os.getenv("AGENT_VENDOR", "qwen").strip()
        self._default_key = default_key if default_key in self._configs else (
            next(iter(self._configs.keys()), None)
        )
        logger.info(f"🔍 已注册厂商: {list(self._configs.keys())}, 默认={self._default_key}")

    def _setup_default_fallback(self):
        """按 FALLBACK_CHAIN 注册降级链；单厂商部署时链为空，不注册任何降级"""
        chain = self.FALLBACK_CHAIN
        for i in range(len(chain) - 1):
            if chain[i] in self._configs and chain[i + 1] in self._configs:
                self._configs[chain[i]].fallback_to = chain[i + 1]

    # ----------------------------- 对外 API -----------------------------

    def list_models(self) -> List[Tuple[str, str]]:
        """返回 (key, display_name) 列表，供前端/菜单展示"""
        return [(c.key, c.display_name) for c in self._configs.values()]

    def default_key(self) -> Optional[str]:
        return self._default_key

    def get_llm_config(self, model_key: Optional[str] = None) -> Tuple[str, str, str]:
        """
        获取 LangChain ChatOpenAI 需要的三元组。
        自动处理：密钥轮询 + 黑名单跳过 + 降级路由（如果主模型所有 key 都挂了）。

        返回: (api_key, base_url, model_name)
        """
        target = model_key or self._default_key
        if target not in self._configs:
            raise KeyError(f"未注册厂商 '{target}'，可选: {list(self._configs.keys())}")

        return self._pick_key_with_fallback(target)

    def mark_key_fail(self, model_key: str, api_key: str):
        """调用方在 LLM 抛异常时可以回调此方法，临时拉黑一个 key"""
        cfg = self._configs.get(model_key)
        if cfg and api_key in cfg.api_keys:
            cfg.bad_keys.add(api_key)
            logger.warning(f"🔴 标记一个密钥临时失效 [{model_key}]（不记录密钥内容）")

    # ----------------------------- 内部：密钥选择 + 降级 -----------------------------

    def _pick_key_with_fallback(self, key: str) -> Tuple[str, str, str]:
        """选择密钥；如果主厂商所有 key 都坏了，自动降级到 fallback 厂商"""
        tried = set()
        current = key
        while current and current not in tried:
            tried.add(current)
            cfg = self._configs[current]
            usable = [k for k in cfg.api_keys if k not in cfg.bad_keys]
            if usable:
                chosen = random.choice(usable)
                if len(cfg.api_keys) > 1:
                    # 只记录序号，绝不落盘任何密钥片段（日志可能被收集/转发）
                    logger.debug(f"🎯 [{current}] 从 {len(cfg.api_keys)} 个密钥中选用第 {cfg.api_keys.index(chosen) + 1} 个")
                return chosen, cfg.base_url, cfg.model_name
            # 当前厂商所有 key 都坏了
            logger.warning(f"⚠️ [{current}] 所有密钥均失效，尝试降级到 {cfg.fallback_to}")
            current = cfg.fallback_to
        raise RuntimeError(f"所有可用厂商都失效了（尝试过: {list(tried)}）")


# 单例，整个进程共享
scheduler = ModelScheduler()
