"""
설정 관리 모듈 (config.py)

환경변수와 상수를 중앙 관리.
.env 파일과 환경변수를 우선하고, 합리적인 기본값 제공.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# 유효한 crawl_interval 값 (분)
VALID_CRAWL_INTERVALS = [5, 10, 15, 30, 60, 120, 360, 720, 1440]

# 기본 crawl_interval (분)
DEFAULT_CRAWL_INTERVAL = 5


@dataclass
class SchedulerConfig:
    """스케줄러 설정"""
    interval_minutes: int = int(os.getenv('CRAWL_INTERVAL_MINUTES', '5'))
    default_crawl_interval: int = DEFAULT_CRAWL_INTERVAL  # 신규 피드 기본 crawl_interval
    coalesce: bool = True          # 누락된 작업 병합
    misfire_grace_time: int = 60   # 누락 허용 시간(초)
    max_instances: int = 1          # 동시 실행 인스턴스 수


@dataclass
class DatabaseConfig:
    """데이터베이스 설정"""
    path: str = os.getenv('DB_PATH', 'news_crew.db')


@dataclass
class TelegramConfig:
    """텔레그램 설정"""
    bot_token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    channel_id: str = os.getenv('TELEGRAM_CHANNEL_ID', '')


@dataclass
class TranslationConfig:
    """번역 설정 — Google Translate 비공식 API (무료, 한도 없음)"""
    provider: str = os.getenv('TRANSLATION_PROVIDER', 'google')  # google (비공식, 무료)
    target_lang: str = 'ko'
    max_retries: int = 3
    chunk_size: int = 4500  # Google Translate 안전 한도


@dataclass
class CrawlerConfig:
    """크롤러 설정"""
    request_timeout: int = 30       # HTTP 요청 타임아웃(초)
    user_agent: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    max_concurrent: int = 3         # 동시 피드 크롤링 수
    retry_on_network_error: bool = True
    max_retries: int = 2


@dataclass
class LoggingConfig:
    """로깅 설정"""
    level: str = os.getenv('LOG_LEVEL', 'INFO')
    log_file: str = os.getenv('LOG_FILE', 'logs/news_crew.log')
    max_bytes: int = 10 * 1024 * 1024   # 10MB
    backup_count: int = 5
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


@dataclass
class AppConfig:
    """애플리케이션 전체 설정"""
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    crawler: CrawlerConfig = field(default_factory=CrawlerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


# 싱글턴 인스턴스
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """설정 싱글턴 반환"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def reload_config() -> AppConfig:
    """설정 다시 로드 (.env 변경 후 사용)"""
    global _config
    load_dotenv(override=True)
    _config = AppConfig()
    return _config


# 유효성 검증
def validate_config(config: AppConfig = None) -> list:
    """
    설정 유효성 검증
    
    Returns:
        에러 메시지 리스트 (빈 리스트면 유효)
    """
    if config is None:
        config = get_config()
    
    errors = []
    
    if not config.telegram.bot_token:
        errors.append("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다")
    
    if not config.telegram.channel_id:
        errors.append("TELEGRAM_CHANNEL_ID가 설정되지 않았습니다")
    
    if config.scheduler.interval_minutes < 1:
        errors.append("CRAWL_INTERVAL_MINUTES는 1 이상이어야 합니다")
    
    if config.scheduler.default_crawl_interval not in VALID_CRAWL_INTERVALS:
        errors.append(
            f"default_crawl_interval이 유효하지 않음: {config.scheduler.default_crawl_interval}. "
            f"유효값: {VALID_CRAWL_INTERVALS}"
        )
    
    return errors