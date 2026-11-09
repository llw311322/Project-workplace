import asyncio

from agent.agent_builder import build_agent_executor
from agent.model_scheduler import scheduler
from agent.stream_runner import run_sync_stream, run_async_stream, run_token_stream
from utils.logger import logger

# 对话模式：1 非流式 / 2 同步步骤流 / 3 异步步骤流 / 4 异步 token 流
MODE_NAMES = {
    1: "非流式（一次性返回）",
    2: "同步流式（步骤级）",
    3: "异步流式（步骤级）",
    4: "异步 token 流（逐字输出）",
}


def show_model_menu():
    """列出所有已注册厂商，让用户选一个"""
    models = scheduler.list_models()
    default = scheduler.default_key()

    print("\n========== 可用厂商 ==========")
    for i, (key, name) in enumerate(models, 1):
        marker = " ⬅️ 默认" if key == default else ""
        print(f"  {i}. [{key}] {name}{marker}")
    print("==============================")

    choice = input(f"选择厂商编号（直接回车用默认 {default}）：").strip()
    if not choice:
        return default
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            return models[idx][0]
    except ValueError:
        pass
    print(f"⚠️  无效输入，使用默认 {default}")
    return default


def show_mode_menu() -> int:
    """选择对话模式"""
    print("\n========== 对话模式 ==========")
    for k, v in MODE_NAMES.items():
        print(f"  {k}. {v}")
    print("==============================")

    choice = input("选择模式编号（直接回车用 1）：").strip() or "1"
    if choice.isdigit() and int(choice) in MODE_NAMES:
        return int(choice)
    print("⚠️  无效输入，使用非流式")
    return 1


if __name__ == "__main__":
    # 启动时让用户选厂商 + 模式（也可以注释掉，直接用 .env 里的 AGENT_VENDOR 默认值）
    model_key = show_model_menu()
    mode = show_mode_menu()

    # 只有 token 级流式需要打开 LLM 的 streaming 开关
    agent_executor = build_agent_executor(model_key, streaming=(mode == 4))

    logger.info(f"===== ReAct Agent 已启动（{MODE_NAMES[mode]}），输入 exit 退出 =====")
    while True:
        user_input = input("\n请输入问题：")
        if user_input.lower() == "exit":
            logger.info("程序退出")
            break
        if not user_input.strip():
            continue

        try:
            if mode == 1:
                res = agent_executor.invoke({"input": user_input})
                print(f"\n🤖 最终回答：{res['output']}")
            elif mode == 2:
                final = run_sync_stream(agent_executor, user_input)
                print(f"\n🤖 最终回答：{final}")
            elif mode == 3:
                final = asyncio.run(run_async_stream(agent_executor, user_input))
                print(f"\n🤖 最终回答：{final}")
            else:
                # token 流已经逐字打印过正文，这里不再重复输出最终答案
                asyncio.run(run_token_stream(agent_executor, user_input))
        except Exception:
            logger.exception("本轮对话失败，Agent 未写入记忆")
