"""
utils/logger.py
--------------
JIRA CLI 로그 유틸리티.
파일 + 콘솔 동시 로깅, 날짜별 로테이션 지원.
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


# ANSI 컬러 코드
class _Colors:
    RESET   = "\033[0m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    BOLD    = "\033[1m"


class ColoredFormatter(logging.Formatter):
    """콘솔 출력용 컬러 포매터."""

    LEVEL_COLORS = {
        logging.DEBUG:    _Colors.CYAN,
        logging.INFO:     _Colors.GREEN,
        logging.WARNING:  _Colors.YELLOW,
        logging.ERROR:    _Colors.RED,
        logging.CRITICAL: _Colors.MAGENTA + _Colors.BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, _Colors.WHITE)
        record.levelname = f"{color}{record.levelname:<8}{_Colors.RESET}"
        return super().format(record)


def setup_logger(
    name: str = "jira_cli",
    log_cfg: dict | None = None,
) -> logging.Logger:
    """
    로거를 초기화하고 반환합니다.

    Parameters
    ----------
    name    : 로거 이름 (모듈별로 다르게 지정 가능)
    log_cfg : config.yaml 의 logging 섹션 딕셔너리

    Returns
    -------
    logging.Logger
    """
    if log_cfg is None:
        log_cfg = {}

    level_str     = log_cfg.get("level", "INFO").upper()
    log_dir       = log_cfg.get("log_dir", "logs")
    log_file_tpl  = log_cfg.get("log_file", "jira_cli_{date}.log")
    max_size_mb   = log_cfg.get("max_size_mb", 10)
    backup_count  = log_cfg.get("backup_count", 7)
    console_out   = log_cfg.get("console_output", True)
    fmt           = log_cfg.get(
        "format",
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    level = getattr(logging, level_str, logging.INFO)
    logger = logging.getLogger(name)

    # 중복 핸들러 방지
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # ── 파일 핸들러 ──────────────────────────────────────────────────────────
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    date_str  = datetime.now().strftime("%Y%m%d")
    log_file  = os.path.join(log_dir, log_file_tpl.replace("{date}", date_str))

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(file_handler)

    # ── 콘솔 핸들러 ──────────────────────────────────────────────────────────
    if console_out:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(
            ColoredFormatter(fmt)
        )
        logger.addHandler(console_handler)

    logger.debug("Logger initialized → %s", log_file)
    return logger


def get_logger(name: str = "jira_cli") -> logging.Logger:
    """이미 설정된 로거를 이름으로 가져옵니다."""
    return logging.getLogger(name)
