import sys
import time
from loguru import logger
from conf.system import SYS_CONFIG
from conf.path import LOGS_ROOT
from pathlib import Path

from src.context import username_context


def setup_logger() -> None:
    """
    Sets up the loguru logger with configured settings.
    Logs will be output to both console and a file.
    """
    log_dir = Path(LOGS_ROOT)
    log_dir.mkdir(exist_ok=True)

    log_file_template = SYS_CONFIG.log_file
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    log_file_path = log_dir / log_file_template.format(time=timestamp)

    logger.remove()

    logger.configure(patcher=lambda record: record.update(context=username_context.get()))

    logger.add(
        sys.stderr,
        level=SYS_CONFIG.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<blue>username: {context: <10}</blue> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    logger.add(
        log_file_path,
        level=SYS_CONFIG.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | username: {context: <10} | {name}:{function}:{line} - {message}",
        rotation=SYS_CONFIG.rotation,
        retention=SYS_CONFIG.retention,
        compression="zip",
        encoding="utf-8",
        serialize=False,
        backtrace=True,
        diagnose=True,
    )

    logger.info("Logger initialized.")
    logger.debug(f"Log level: {SYS_CONFIG.log_level}")
    logger.debug(f"Log file path: {log_file_path}; template: {log_file_template}")


setup_logger()

__all__ = ["logger"]
