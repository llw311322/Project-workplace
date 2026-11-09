from loguru import logger
import sys

# 配置日志格式
logger.remove()
logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO"
)

if __name__ == "__main__":
    logger.info("日志初始化完成")
