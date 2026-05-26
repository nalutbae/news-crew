"""
봇 감지 회피 모듈

- User-Agent 로테이션: 매 요청마다 다른 UA 사용
- cloudscraper 지원: JavaScript 챌린지(FCP 등)가 있는 사이트 자동 우회
- 세션 재사용: 쿠키 유지로 연속 요청 시 인증 상태 유지

사용법:
    from anti_bot import get_session
    session = get_session()
    response = session.get('https://example.com')

    # 또는 직접 요청 함수 사용
    from anti_bot import fetch_with_rotation
    response = fetch_with_rotation('https://example.com')
"""

import logging
import random
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── User-Agent 풀 ──
# 실제 브라우저 비율과 유사하게 최신 Chrome/Edge/Firefox/Safari 배치
USER_AGENTS = [
    # Chrome (Windows) — 가장 많은 비율
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    # Chrome (macOS)
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    # Edge
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
    # Firefox
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0',
    # Safari
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
]

# 전역 세션 캐시 (도메인별 세션 유지, TTL 관리)
_sessions = {}          # domain → session
_session_timestamps = {}  # domain → last_used (epoch)
_SESSION_TTL = 1800     # 30분 (Pi 2 메모리 관리)

# cloudscraper 사용 가능 여부
_CLOUDSCRAPER_AVAILABLE = False
try:
    import cloudscraper
    _CLOUDSCRAPER_AVAILABLE = True
    logger.info("cloudscraper 사용 가능 — JavaScript 챌린지 사이트 우회 지원")
except ImportError:
    logger.debug("cloudscraper 미설치 — 일반 requests로 폴백")


def get_random_ua() -> str:
    """User-Agent 풀에서 랜덤 선택"""
    return random.choice(USER_AGENTS)


def get_session(domain: str = None):
    """
    도메인별 세션 반환 (봇 감지 회피 + TTL 만료)

    - cloudscraper가 설치된 경우: JavaScript 챌린지 자동 우회
    - 미설치 시: 일반 requests.Session + User-Agent 로테이션
    - TTL 30분 초과 시 세션 close 후 새로 생성 (Pi 2 메모리 관리)

    Args:
        domain: 세션을 분리할 도메인 (선택). None이면 기본 세션.

    Returns:
        requests.Session 또는 cloudscraper.CloudScraper 세션
    """
    cache_key = domain or '_default'
    now = time.time()
    
    # TTL 만료 세션 정리 (Pi 2 메모리 관리)
    if cache_key in _sessions:
        last_used = _session_timestamps.get(cache_key, 0)
        if now - last_used > _SESSION_TTL:
            logger.debug(f"세션 TTL 만료: domain={domain}, idle={now - last_used:.0f}s")
            try:
                _sessions[cache_key].close()
            except Exception:
                pass
            del _sessions[cache_key]
            _session_timestamps.pop(cache_key, None)
    
    if cache_key in _sessions:
        _session_timestamps[cache_key] = now
        return _sessions[cache_key]

    if _CLOUDSCRAPER_AVAILABLE:
        session = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
    else:
        import requests
        session = requests.Session()

    # 기본 User-Agent 설정 (cloudscraper는 자체 UA 관리)
    if not _CLOUDSCRAPER_AVAILABLE:
        session.headers['User-Agent'] = get_random_ua()

    # 공통 헤더
    session.headers.update({
        'Accept-Language': 'ko,en-US;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })

    _sessions[cache_key] = session
    _session_timestamps[cache_key] = now
    logger.debug(f"새 세션 생성: domain={domain}, cloudscraper={_CLOUDSCRAPER_AVAILABLE}")
    return session


def fetch_with_rotation(url: str, timeout: int = 30, domain: str = None):
    """
    URL 요청 (봇 감지 회피 + User-Agent 로테이션)

    Args:
        url: 요청할 URL
        timeout: 요청 타임아웃 (초)
        domain: 세션 분리용 도메인 키

    Returns:
        requests.Response 또는 None (실패 시)
    """
    session = get_session(domain)

    # cloudscraper 미사용 시 매 요청마다 UA 로테이션
    if not _CLOUDSCRAPER_AVAILABLE:
        session.headers['User-Agent'] = get_random_ua()

    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response
    except Exception as e:
        logger.error(f"fetch_with_rotation 실패 ({url}): {e}")
        return None


def reset_sessions():
    """모든 캐시된 세션 초기화 (새로 시작 시 사용)"""
    global _sessions, _session_timestamps
    for key, session in _sessions.items():
        try:
            session.close()
        except Exception:
            pass
    _sessions = {}
    _session_timestamps = {}
    logger.info("모든 세션 초기화 완료")


def install_cloudscraper():
    """
    cloudscraper 설치 안내

    봇 감지가 있는 사이트(러시아 외무부 등)를 크롤링하려면 필요.
    pip install cloudscraper
    """
    if not _CLOUDSCRAPER_AVAILABLE:
        logger.warning(
            "cloudscraper 미설치! 봇 감지 사이트 우회가 제한됩니다.\n"
            "설치: pip install cloudscraper"
        )
    return _CLOUDSCRAPER_AVAILABLE