"""LLM 成本护栏 —— 按用户日配额 + 全局日预算熔断。

两层含义：
  1. 单用户每日调用次数上限：防止某个访客反复刷 Agent（演示场景 30 次/天足够体验）
  2. 全局每日预算上限：所有用户累计估算成本超阈值后整体熔断——宁可暂时不可用，
     也不能让一把 Key 在公网上被刷出几百块

为什么用进程内内存而不是 Redis：
  · 单端口部署，进程即边界；不引入外部中间件，保持"零依赖可部署"的形态
  · 计数按天滚动，重启最坏后果是一天计数清零，演示场景可接受
  · 真正的止损线在厂商控制台的消费上限，这里是缓冲层，不是防线

口径：token 数按字符数 × 1.5 估算（中文偏保守），单价按「每千 token 多少元」配置。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from fastapi import HTTPException, status

from .config import settings

# 中文场景估算系数：1 个汉字大致 1~2 token，取 1.5 偏保守（宁可高估）
TOKENS_PER_CHAR = 1.5


@dataclass
class _DayState:
    """一天的全部计数，跨天整体换新"""

    day: date
    per_user_calls: dict[int, int] = field(default_factory=dict)
    spend_yuan: float = 0.0
    total_calls: int = 0


class DailyQuota:
    def __init__(self) -> None:
        self._state = _DayState(day=date.today())
        self._lock = threading.Lock()

    # ---------------- 内部 ----------------

    def _roll(self) -> None:
        """跨天自动归零（调用方必须已持锁）"""
        today = date.today()
        if self._state.day != today:
            self._state = _DayState(day=today)

    def _raise_budget_exhausted(self) -> None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "演示环境今日 AI 预算已用完，为保护接口费用已暂停调用。"
                "知识库检索、审批流等非 AI 功能不受影响，明天自动恢复。"
            ),
            headers={"Retry-After": "3600"},
        )

    # ---------------- 对外 ----------------

    def consume(self, user_id: int) -> None:
        """调用 LLM 前扣一次配额；超限直接 429（在路由里调用）"""
        with self._lock:
            self._roll()

            budget = settings.AGENT_DAILY_BUDGET_YUAN
            if budget > 0 and self._state.spend_yuan >= budget:
                self._raise_budget_exhausted()

            limit = settings.AGENT_DAILY_QUOTA_PER_USER
            used = self._state.per_user_calls.get(user_id, 0)
            if limit > 0 and used >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"今日 AI 体验额度已用完（每人 {limit} 次/天），明天自动恢复。"
                        "知识库检索、审批流等功能不受影响。"
                    ),
                    headers={"Retry-After": "3600"},
                )

            self._state.per_user_calls[user_id] = used + 1
            self._state.total_calls += 1

    def record_usage(self, prompt_chars: int, answer_chars: int) -> None:
        """调用结束后登记用量（用于全局预算估算）"""
        with self._lock:
            self._roll()
            tokens = int((prompt_chars + answer_chars) * TOKENS_PER_CHAR)
            self._state.spend_yuan += tokens / 1000 * settings.AGENT_PRICE_PER_1K_TOKENS

    def snapshot(self, user_id: Optional[int] = None) -> dict:
        """当前额度状态（给 /agent/quota 用，也方便演示时展示护栏在工作）"""
        with self._lock:
            self._roll()
            limit = settings.AGENT_DAILY_QUOTA_PER_USER
            budget = settings.AGENT_DAILY_BUDGET_YUAN
            used = self._state.per_user_calls.get(user_id, 0) if user_id else 0
            return {
                "day": self._state.day.isoformat(),
                "user_used": used,
                "user_remaining": max(limit - used, 0) if limit > 0 else -1,
                "user_limit": limit,
                "global_calls": self._state.total_calls,
                "spend_yuan": round(self._state.spend_yuan, 4),
                "budget_yuan": budget,
                "budget_exhausted": budget > 0 and self._state.spend_yuan >= budget,
            }

    def reset(self) -> None:
        """仅测试用：清空当日计数"""
        with self._lock:
            self._state = _DayState(day=date.today())


quota = DailyQuota()
