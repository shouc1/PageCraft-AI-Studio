"""统一日志配置。

控制台输出 INFO 级别，文件记录 DEBUG 级别（按天轮转，保留 7 天）。
所有模块用 `from app.logger import logger` 即可。
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# 日志目录
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _setup() -> logging.Logger:
    logger = logging.getLogger("photo-ai")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # 避免重复输出

    if logger.handlers:  # 防止重复添加
        return logger

    # 控制台：INFO 级别
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(_FORMAT, _DATE_FORMAT))
    logger.addHandler(console)

    # 文件：DEBUG 级别，按天轮转，保留 7 天
    file_handler = TimedRotatingFileHandler(
        LOG_DIR / "app.log",
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FORMAT, _DATE_FORMAT))
    logger.addHandler(file_handler)

    return logger


logger = _setup()
