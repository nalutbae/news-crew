"""
로깅 설정 모듈 (logging_config.py)

RotatingFileHandler로 logs/news_crew.log에 회전 로그 저장.
콘솔 + 파일 양쪽 출력.
"""

import os
import logging
from logging.handlers import RotatingFileHandler

from config import get_config


def setup_logging() -> logging.Logger:
    """
    애플리케이션 전체 로깅 설정
    
    - 콘솔 핸들러: INFO 이상
    - 파일 핸들러: DEBUG 이상 (RotatingFileHandler)
    - 로그 파일: logs/news_crew.log
    
    Returns:
        루트 로거
    """
    config = get_config()
    log_config = config.logging
    
    # 로그 디렉토리 생성
    log_dir = os.path.dirname(log_config.log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_config.level.upper(), logging.INFO))
    
    # 기존 핸들러 제거 (중복 방지)
    root_logger.handlers.clear()
    
    # 포매터
    formatter = logging.Formatter(log_config.format)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 파일 핸들러 (RotatingFileHandler)
    file_handler = RotatingFileHandler(
        log_config.log_file,
        maxBytes=log_config.max_bytes,
        backupCount=log_config.backup_count,
        encoding='utf-8',
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 써드파티 라이브러리 로그 레벨 조정
    logging.getLogger('feedparser').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    
    root_logger.info("로깅 설정 완료: level=%s, file=%s", log_config.level, log_config.log_file)
    
    return root_logger