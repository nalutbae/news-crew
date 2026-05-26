"""
RSS/Atom 피드 파서 (feedparser 라이브러리 기반)

일반적인 RSS/Atom 피드 파싱. bozo recovery 지원.
tg.i-c-a.su 패턴은 TgRssParser로 라우팅됨.
"""

import logging
from datetime import datetime
from typing import Optional

import feedparser

from parsers.base import BaseFeedParser, ParseResult

logger = logging.getLogger(__name__)


class RSSParser(BaseFeedParser):
    """RSS/Atom 피드 파서 (feedparser 라이브러리 기반)"""

    def parse(self) -> ParseResult:
        result = ParseResult(
            source_name=self.feed_name,
            source_url=self.feed_url,
        )

        try:
            # anti_bot 지원: cloudscraper 세션으로 RSS 가져오기
            try:
                from anti_bot import fetch_with_rotation
                from config import get_config
                response = fetch_with_rotation(self.feed_url, timeout=30)
                if response and response.content:
                    # Pi 2 메모리 보호: 응답 크기 제한
                    content = response.content
                    max_bytes = get_config().crawler.max_response_bytes
                    if len(content) > max_bytes:
                        logger.warning(
                            f"RSS 응답 크기 초과 ({len(content)} > {max_bytes}): {self.feed_url}"
                        )
                        content = content[:max_bytes]
                    feed = feedparser.parse(content)
                else:
                    # 폴백: 일반 feedparser
                    feed = feedparser.parse(self.feed_url)
            except ImportError:
                feed = feedparser.parse(self.feed_url)

            # feedparser bozo_handler가 에러를 수집
            if feed.bozo and not feed.entries:
                result.errors.append(f'feedparser bozo error: {feed.bozo_exception}')
                logger.warning(f"RSS 파싱 에러 ({self.feed_url}): {feed.bozo_exception}")

            # 피드 메타
            if not result.source_name and hasattr(feed.feed, 'title'):
                result.source_name = feed.feed.get('title', '')

            # 엔트리 파싱
            for entry in feed.entries:
                try:
                    item = self._parse_entry(entry)
                    if item:
                        result.items.append(item)
                except Exception as e:
                    result.errors.append(f'entry parse error: {e}')
                    logger.debug(f"엔트리 파싱 건너뜀: {e}")

            logger.info(f"RSS 파싱 완료: {len(result.items)}개 항목 ({self.feed_url})")

        except Exception as e:
            result.errors.append(f'RSS fetch error: {e}')
            logger.error(f"RSS 가져오기 실패 ({self.feed_url}): {e}")

        return result

    def _parse_entry(self, entry) -> Optional[dict]:
        """feedparser entry를 dict로 변환"""
        url = entry.get('link', '')
        if not url:
            return None

        title = entry.get('title', '')

        # 내용 추출 (우선순위: content → summary_detail → summary)
        content = ''
        if hasattr(entry, 'content') and entry.content:
            content = entry.content[0].get('value', '')
        elif hasattr(entry, 'summary_detail') and entry.summary_detail:
            content = entry.summary_detail.get('value', '')
        elif hasattr(entry, 'summary'):
            content = entry.summary

        # 발행일
        published_at = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        # 작성자
        author = entry.get('author', '')

        return {
            'url': url,
            'title': title,
            'content': content,
            'published_at': published_at,
            'author': author,
        }