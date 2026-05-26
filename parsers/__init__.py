"""
피드 파서 패키지

타입별로 분리된 파서 모듈:
- base: BaseFeedParser ABC, ParseResult 데이터 클래스
- rss_parser: RSS/Atom 파서 (feedparser 기반)
- tg_rss_parser: tg.i-c-a.su RSS 파서 (터키어 이란 뉴스 전용)
- web_parser: 웹 스크래핑 파서 (2단계: 리스트 → 상세)
"""

from parsers.base import BaseFeedParser, ParseResult
from parsers.rss_parser import RSSParser
from parsers.tg_rss_parser import TgRssParser
from parsers.web_parser import WebParser

# tg.i-c-a.su 도메인 패턴 — 이 패턴에 매칭되면 TgRssParser 사용
TG_RSS_PATTERN = 'tg.i-c-a.su'


def get_parser(feed_type: str, feed_url: str, feed_name: str = '',
               language: str = 'en', **kwargs) -> BaseFeedParser:
    """
    피드 URL과 타입에 따른 적절한 파서 반환

    - feed_type='rss' 이면서 URL에 tg.i-c-a.su 포함 → TgRssParser
    - feed_type='rss' (일반) → RSSParser
    - feed_type='web' / 'web_detail' → WebParser
    - 그 외 → RSSParser 폴백
    """
    if feed_type == 'rss':
        # tg.i-c-a.su RSS 전용 파서
        if TG_RSS_PATTERN in feed_url:
            return TgRssParser(feed_url, feed_name, language)
        return RSSParser(feed_url, feed_name, language)
    elif feed_type in ('web', 'web_detail'):
        return WebParser(feed_url, feed_name, language, **kwargs)
    else:
        import logging
        logging.getLogger(__name__).warning(
            f"알 수 없는 피드 타입 '{feed_type}', RSS로 폴백"
        )
        return RSSParser(feed_url, feed_name, language)