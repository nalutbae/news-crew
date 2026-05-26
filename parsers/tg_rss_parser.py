"""
tg.i-c-a.su RSS 파서

터키어 이란 뉴스 텔레그램 채널 RSS 피드 전용 파서.
구조가 동일하므로 DB에 Feed 추가만으로 자동 크롤링 가능.
일반 RSSParser와 동일하게 동작하나, 향후 tg.i-c-a.su 전용
전처리/필터링이 필요한 경우 이 클래스에 로직 추가.
"""

import logging

import feedparser

from parsers.base import BaseFeedParser, ParseResult
from parsers.rss_parser import RSSParser

logger = logging.getLogger(__name__)


class TgRssParser(RSSParser):
    """
    tg.i-c-a.su RSS 파서

    일반 RSSParser를 상속하며, 향후 tg.i-c-a.su 전용
    전처리(채널명 정제, 태그 제거 등)가 필요한 경우
    _parse_entry()를 오버라이드하여 구현.
    """

    def _parse_entry(self, entry) -> dict | None:
        """tg.i-c-a.su 전용 엔트리 파싱 (필요시 오버라이드)"""
        item = super()._parse_entry(entry)

        # 향후 tg.i-c-a.su 전용 후처리가 필요하면 여기에 추가
        # 예: 채널명 태그 제거, 텔레그램 링크 정제 등

        return item