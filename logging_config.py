"""
로깅 설정 모듈 (logging_config.py)

RotatingFileHandler로 로그 저장.
Pi 2 SD 마모 방지:
- /dev/shm(tmpfs)가 있으면 로그를 메모리에 저장 (재부팅 시 삭제됨 - Pi에서 허용)
- /dev/shm이 없으면 기존대로 파일 시스템에 저장
- 콘솔 + 파일 양쪽 출력
"""

import os
import logging
from logging.handlers import RotatingFileHandler

from config import get_config

# Pi 2 SD 보호: tmpfs 경로 우선 사용
# /dev/shm은 Linux에서 항상 존재하는 tmpfs (메모리 파일 시스템)
# 재부팅 시 로그가 사라지지만, 뉴스 크롤러에서는 허용 가능
_SHM_DIR = '/dev/shm'


def _resolve_log_dir(configured_path: str) -> str:
    """
    로그 디렉토리 경로 결정 (Pi 2 SD 보호)

    1. LOG_DIR 환경변수가 설정되면 그대로 사용
    2. /dev/shm(tmpfs)가 존재하면 /dev/shm/news-crew/logs 사용
    3. 그 외 설정된 경로 사용

    Pi 2에서는 로그 파일이 가장 빈번한 SD 쓰기 원인.
    tmpfs로 로그를 메모리에 저장하면 SD 쓰기를 크게 줄일 수 있음.
    """
    # 환경변수로 명시적 오버라이드
    env_dir = os.getenv('LOG_DIR')
    if env_dir:
        return env_dir

    # Pi 2: tmpfs 우선 사용
    if os.path.isdir(_SHM_DIR):
        shm_log_dir = os.path.join(_SHM_DIR, 'news-crew', 'logs')
        return shm_log_dir

    # 기본: 설정된 경로
    log_dir = os.path.dirname(configured_path)
    return log_dir if log_dir else 'logs'


def setup_logging() -> logging.Logger:
    """
    애플리케이션 전체 로깅 설정

    - 콘솔 핸들러: INFO 이상
    - 파일 핸들러: DEBUG 이상 (RotatingFileHandler)
    - Pi 2: /dev/shm(tmpfs)에 로그 저장 -> SD 쓰기 방지

    Returns:
        루트 로거
    """
    config = get_config()
    log_config = config.logging

    # 로그 디렉토리 결정 (Pi 2 SD 보호)
    log_dir = _resolve_log_dir(log_config.log_file)
    log_file = os.path.join(log_dir, os.path.basename(log_config.log_file))

    # 로그 디렉토리 생성
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
        log_file,
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

    # tmpfs 사용 여부 로깅
    is_tmpfs = log_dir.startswith(_SHM_DIR)
    root_logger.info(
        "로깅 설정 완료: level=%s, file=%s%s",
        log_config.level,
        log_file,
        " (tmpfs - SD 쓰기 방지)" if is_tmpfs else "",
    )

    return root_logger