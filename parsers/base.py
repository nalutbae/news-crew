"""
피드 파서 기본 클래스 및 데이터 구조

- ParseResult: 파싱 결과 데이터 클래스
- BaseFeedParser: ABC 기반 파서 인터페이스
"""

import abc
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """파싱 결과 데이터 클래스"""
    items: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    source_name: str = ''
    source_url: str = ''


class BaseFeedParser(abc.ABC):
    """피드 파서 추상 기반 클래스"""

    def __init__(self, feed_url: str, feed_name: str = '', language: str = 'en'):
        self.feed_url = feed_url
        self.feed_name = feed_name
        self.language = language

    @abc.abstractmethod
    def parse(self) -> ParseResult:
        """피드를 파싱하여 ParseResult 반환"""
        pass