"""
웹 스크래핑 파서 (2단계: 리스트 페이지 → 상세 페이지)

CSS 셀렉터를 사용해 링크 목록 추출 후 각 상세 페이지 크롤링.
도메인별 셀렉터 설정을 DOMAIN_SELECTORS에서 관리.
새로운 웹 사이트 추가 시 DOMAIN_SELECTORS에 설정만 추가하면 됨.
"""

import re
import logging
from typing import Optional, Dict
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from parsers.base import BaseFeedParser, ParseResult

logger = logging.getLogger(__name__)

# ── 도메인별 인코딩 힌트 ──
ENCODING_HINTS: Dict[str, str] = {
    'mfa.gov.cn': 'GB2312',
}


class WebParser(BaseFeedParser):
    """
    웹 스크래핑 파서 (2단계: 리스트 페이지 → 상세 페이지)

    CSS 셀렉터를 사용해 링크 목록 추출 후 각 상세 페이지 크롤링.

    새로운 웹 사이트 추가:
        1. DOMAIN_SELECTORS에 도메인 설정 추가
        2. 필요시 인코딩 힌트를 ENCODING_HINTS에 추가
    """

    # 도메인별 CSS 셀렉터 설정
    # 새로운 웹 사이트 추가 시 여기에 설정만 추가
    DOMAIN_SELECTORS: Dict[str, dict] = {
        'mfa.gov.cn': {
            'list_link': 'a',
            'list_link_pattern': r'^\./\d{6}/',
            'detail_title': '.news-title h1',
            'detail_content': '.news-details',
            'detail_date': '.news-title .time span',
        },
    }

    # 제목 정제용 정규식 패턴
    _NOISE_PATTERNS = [
        re.compile(r'\s*【[^】]*】\s*'),
        re.compile(r'\s*（\d{4}-\d{2}-\d{2}）\s*'),
        re.compile(r'\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*'),
        re.compile(r'\s*打印\s*'),
        re.compile(r'\s*[中大校小]+\s*'),
    ]

    def __init__(self, feed_url: str, feed_name: str = '', language: str = 'en',
                 list_link_selector: str = None, detail_title_selector: str = None,
                 detail_content_selector: str = None):
        super().__init__(feed_url, feed_name, language)

        # 도메인별 기본 셀렉터 또는 사용자 지정
        domain = self._extract_domain(feed_url)
        domain_config = {}
        for config_domain, config in self.DOMAIN_SELECTORS.items():
            if domain == config_domain or domain.endswith('.' + config_domain):
                domain_config = config
                break

        self.list_link_selector = list_link_selector or domain_config.get('list_link', 'a')
        self.list_link_pattern = domain_config.get('list_link_pattern')
        self.detail_title_selector = detail_title_selector or domain_config.get('detail_title', 'h1')
        self.detail_content_selector = detail_content_selector or domain_config.get('detail_content', 'article, .content, .post')

    @classmethod
    def _clean_title(cls, title: str) -> str:
        """제목에서 노이즈 제거"""
        cleaned = title
        for pattern in cls._NOISE_PATTERNS:
            cleaned = pattern.sub('', cleaned)
        return cleaned.strip()

    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ''

    def _detect_encoding(self, response: requests.Response, content: bytes) -> str:
        """인코딩 감지: BOM → meta charset → 도메인 힌트 → UTF-8 폴백"""
        # BOM 확인
        if content.startswith(b'\xef\xbb\xbf'):
            return 'UTF-8-SIG'
        if content.startswith(b'\xff\xfe'):
            return 'UTF-16-LE'
        if content.startswith(b'\xfe\xff'):
            return 'UTF-16-BE'

        # Content-Type 헤더 charset
        content_type = response.headers.get('Content-Type', '')
        if 'charset=' in content_type:
            match = re.search(r'charset=([^\s;]+)', content_type, re.IGNORECASE)
            if match:
                return match.group(1).strip('"').strip("'")

        # HTML meta 태그 charset 감지
        try:
            head_content = content[:2048].decode('ascii', errors='ignore')
            charset_match = re.search(
                r'<meta[^>]+charset=["\']?([^"\';\s>]+)', head_content, re.IGNORECASE
            )
            if charset_match:
                return charset_match.group(1)
        except Exception:
            pass

        # 도메인 힌트
        domain = self._extract_domain(response.url)
        for hint_domain, encoding in ENCODING_HINTS.items():
            if hint_domain in domain:
                return encoding

        return 'UTF-8'

    def _fetch_page(self, url: str, timeout: int = 30) -> Optional[BeautifulSoup]:
        """페이지 가져오기 및 BeautifulSoup 파싱 (봇 감지 회피 지원)"""
        try:
            # anti_bot 모듈에서 세션 가져오기 (있으면 cloudscraper, 없으면 requests)
            from anti_bot import get_session
            session = get_session()

            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ko,en-US;q=0.9,en;q=0.8',
            }
            response = session.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()

            # 인코딩 감지 후 디코딩
            encoding = self._detect_encoding(response, response.content)
            html = response.content.decode(encoding, errors='replace')

            return BeautifulSoup(html, 'html.parser')

        except ImportError:
            # anti_bot 없으면 일반 requests 사용
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ko,en-US;q=0.9,en;q=0.8',
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()

            encoding = self._detect_encoding(response, response.content)
            html = response.content.decode(encoding, errors='replace')
            return BeautifulSoup(html, 'html.parser')

        except Exception as e:
            logger.error(f"페이지 가져오기 실패 ({url}): {e}")
            return None

    def parse(self) -> ParseResult:
        result = ParseResult(
            source_name=self.feed_name,
            source_url=self.feed_url,
        )

        # 1단계: 리스트 페이지에서 링크 추출
        try:
            soup = self._fetch_page(self.feed_url)
            if not soup:
                result.errors.append(f'리스트 페이지 가져오기 실패: {self.feed_url}')
                return result

            links = []
            seen_hrefs = set()

            for a_tag in soup.select(self.list_link_selector):
                href = a_tag.get('href', '')
                if not href or href in seen_hrefs:
                    continue

                # 정규식 패턴 필터링
                if self.list_link_pattern and not re.match(self.list_link_pattern, href):
                    continue

                seen_hrefs.add(href)

                # 상대 URL → 절대 URL 변환
                if href.startswith('./') or href.startswith('/') or not href.startswith('http'):
                    href = urljoin(self.feed_url, href)

                # 동일 도메인 검증 (서브도메인 허용)
                if href.startswith('http'):
                    link_domain = urlparse(href).netloc
                    feed_domain = urlparse(self.feed_url).netloc
                    if link_domain and feed_domain and link_domain != feed_domain:
                        if not (link_domain.endswith('.' + feed_domain) or feed_domain.endswith('.' + link_domain)):
                            logger.debug(f"외부 도메인 링크 건너뜀: {href}")
                            continue
                    links.append({
                        'url': href,
                        'title': self._clean_title(a_tag.get_text(strip=True) or ''),
                    })

            logger.info(f"리스트에서 {len(links)}개 링크 발견 ({self.feed_url})")

        except Exception as e:
            result.errors.append(f'리스트 파싱 에러: {e}')
            logger.error(f"리스트 파싱 실패 ({self.feed_url}): {e}")
            return result

        # 2단계: 각 상세 페이지 크롤링
        for link_info in links:
            try:
                detail_soup = self._fetch_page(link_info['url'])
                if not detail_soup:
                    result.errors.append(f"상세 페이지 가져오기 실패: {link_info['url']}")
                    continue

                # 제목: 상세 페이지 셀렉터 우선, 폴백으로 리스트 제목
                title_el = detail_soup.select_one(self.detail_title_selector)
                if title_el:
                    title = title_el.get_text(strip=True)
                else:
                    title = link_info.get('title', '')
                title = self._clean_title(title)

                # 내용
                content_el = detail_soup.select_one(self.detail_content_selector)
                content = ''
                if content_el:
                    # 노이즈 태그 제거
                    for tag in content_el.find_all(['script', 'style', 'nav', 'footer']):
                        tag.decompose()
                    for selector in ['.news-title', '.action', '.time']:
                        noise_el = content_el.select_one(selector)
                        if noise_el:
                            noise_el.decompose()
                    content = str(content_el)

                item = {
                    'url': link_info['url'],
                    'title': title,
                    'content': content,
                    'published_at': None,
                    'author': '',
                }

                result.items.append(item)

            except Exception as e:
                result.errors.append(f"상세 페이지 파싱 에러 ({link_info['url']}): {e}")
                logger.debug(f"상세 페이지 파싱 건너뜀: {e}")

        logger.info(f"Web 파싱 완료: {len(result.items)}개 항목 ({self.feed_url})")
        return result