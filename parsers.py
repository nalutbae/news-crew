"""
RSS/Web 피드 파서 모듈

설계:
- BaseFeedParser ABC: parse() → ParseResult 패턴 — 에러는 수집하고 예외를 던지지 않음 (graceful degradation)
- RSSParser: feedparser 라이브러리로 RSS/Atom 파싱 (bozo recovery 지원)
- WebParser: 2단계 스크래핑 (리스트 페이지 → 상세 페이지), CSS 셀렉터 기반
- 인코딩 감지: BOM → meta charset → 도메인 힌트 → UTF-8 폴백
"""

import abc
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime

import requests
import feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ── 도메인별 인코딩 힌트 ──
ENCODING_HINTS: Dict[str, str] = {
    'mfa.gov.cn': 'GB2312',
    'tg.i-c-a.su': 'UTF-8',
}


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


class RSSParser(BaseFeedParser):
    """RSS/Atom 피드 파서 (feedparser 라이브러리 기반)"""
    
    def parse(self) -> ParseResult:
        result = ParseResult(
            source_name=self.feed_name,
            source_url=self.feed_url,
        )
        
        try:
            feed = feedparser.parse(self.feed_url)
            
            # feedparser bozo_handler가 에러를 수집
            if feed.bozo and not feed.entries:
                result.errors.append(f'feedparser bozo error: {feed.bozo_exception}')
                logger.warning(f"RSS 파싱 에러 ({self.feed_url}): {feed.bozo_exception}")
                # bozo여도 entries가 있으면 계속 진행 (graceful degradation)
            
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


class WebParser(BaseFeedParser):
    """
    웹 스크래핑 파서 (2단계: 리스트 페이지 → 상세 페이지)
    
    CSS 셀렉터를 사용해 링크 목록 추출 후 각 상세 페이지 크롤링
    """
    
    # 도메인별 CSS 셀렉터 설정
    DOMAIN_SELECTORS: Dict[str, dict] = {
        'mfa.gov.cn': {
            'list_link': 'a',                          # 모든 <a> 태그에서 후보 수집
            'list_link_pattern': r'^\./\d{6}/',       # ./YYYYMM/ 형식만 매칭 (인덱스 ./ 제외)
            'detail_title': '.news-title h1',           # 기사 제목 (h1 직접 선택)
            'detail_content': '.news-details',          # 기사 본문 클래스
            'detail_date': '.news-title .time span',   # 기사 날짜/시간
        },
    }
    
    # 제목 정제용 정규식 패턴
    _NOISE_PATTERNS = [
        re.compile(r'\s*【[^】]*】\s*'),          # 【中大校】【打印】 등 꺾쇠 괄호 노이즈
        re.compile(r'\s*（\d{4}-\d{2}-\d{2}）\s*'),  # （2026-05-25） 날짜+괄호
        re.compile(r'\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*'),  # 2026-05-25 17:30 날짜+시간
        re.compile(r'\s*打印\s*'),                # "打印" (인쇄) 버튼 텍스트
        re.compile(r'\s*[中大校小]+\s*'),          # 글자크기 버튼 텍스트 (중대소)
    ]
    
    def __init__(self, feed_url: str, feed_name: str = '', language: str = 'en',
                 list_link_selector: str = None, detail_title_selector: str = None,
                 detail_content_selector: str = None):
        super().__init__(feed_url, feed_name, language)
        
        # 도메인별 기본 셀렉터 또는 사용자 지정
        domain = self._extract_domain(feed_url)
        domain_config = {}
        # 서브도메인 포함 매칭 (www.mfa.gov.cn → mfa.gov.cn 설정 사용)
        for config_domain, config in self.DOMAIN_SELECTORS.items():
            if domain == config_domain or domain.endswith('.' + config_domain):
                domain_config = config
                break
        
        self.list_link_selector = list_link_selector or domain_config.get('list_link', 'a')
        self.list_link_pattern = domain_config.get('list_link_pattern')  # 정규식 패턴 (선택사항)
        self.detail_title_selector = detail_title_selector or domain_config.get('detail_title', 'h1')
        self.detail_content_selector = detail_content_selector or domain_config.get('detail_content', 'article, .content, .post')
    
    @classmethod
    def _clean_title(cls, title: str) -> str:
        """
        제목에서 노이즈 제거
        
        - 【中大校】打印 (글자크기/인쇄 버튼 텍스트)
        - （2026-05-25） (리스트 페이지 링크에 포함된 날짜)
        - 2026-05-25 17:30 (상세 페이지에 포함된 날짜+시간)
        """
        cleaned = title
        for pattern in cls._NOISE_PATTERNS:
            cleaned = pattern.sub('', cleaned)
        return cleaned.strip()
    
    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ''
    
    def _detect_encoding(self, response: requests.Response, content: bytes) -> str:
        """
        인코딩 감지: BOM → meta charset → 도메인 힌트 → UTF-8 폴백
        """
        # 1. BOM 확인
        if content.startswith(b'\xef\xbb\xbf'):
            return 'UTF-8-SIG'
        if content.startswith(b'\xff\xfe'):
            return 'UTF-16-LE'
        if content.startswith(b'\xfe\xff'):
            return 'UTF-16-BE'
        
        # 2. meta charset 확인
        content_type = response.headers.get('Content-Type', '')
        if 'charset=' in content_type:
            match = re.search(r'charset=([^\s;]+)', content_type, re.IGNORECASE)
            if match:
                return match.group(1).strip('"').strip("'")
        
        # HTML meta 태그에서 charset 감지
        try:
            # 앞부분만 파싱
            head_content = content[:2048].decode('ascii', errors='ignore')
            charset_match = re.search(
                r'<meta[^>]+charset=["\']?([^"\';\s>]+)', head_content, re.IGNORECASE
            )
            if charset_match:
                return charset_match.group(1)
        except Exception:
            pass
        
        # 3. 도메인 힌트
        domain = self._extract_domain(response.url)
        for hint_domain, encoding in ENCODING_HINTS.items():
            if hint_domain in domain:
                return encoding
        
        # 4. UTF-8 폴백
        return 'UTF-8'
    
    def _fetch_page(self, url: str, timeout: int = 30) -> Optional[BeautifulSoup]:
        """페이지 가져오기 및 BeautifulSoup 파싱"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # 인코딩 감지 후 디코딩
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
                
                # 정규식 패턴 필터링 (예: ./YYYYMM/ 형식만 허용)
                if self.list_link_pattern and not re.match(self.list_link_pattern, href):
                    continue
                
                seen_hrefs.add(href)
                
                # 상대 URL → 절대 URL 변환
                from urllib.parse import urljoin, urlparse
                if href.startswith('./') or href.startswith('/') or not href.startswith('http'):
                    href = urljoin(self.feed_url, href)
                
                # 동일 도메인 검증 (외부 사이트 크롤링 방지, 서브도메인 허용)
                if href.startswith('http'):
                    link_domain = urlparse(href).netloc
                    feed_domain = urlparse(self.feed_url).netloc
                    if link_domain and feed_domain and link_domain != feed_domain:
                        # 서브도메인 관계 확인 (www.mfa.gov.cn ↔ mfa.gov.cn)
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
                
                # 제목: 상세 페이지 .news-title h1 우선, 폴백으로 리스트 제목 사용
                title_el = detail_soup.select_one(self.detail_title_selector)
                if title_el:
                    title = title_el.get_text(strip=True)
                else:
                    title = link_info.get('title', '')
                # 제목 정제: 노이즈(날짜, 글자크기 버튼, 인쇄 버튼) 제거
                title = self._clean_title(title)
                
                # 내용
                content_el = detail_soup.select_one(self.detail_content_selector)
                content = ''
                if content_el:
                    # .news-details 내부 노이즈 태그 제거
                    # - .news-title (제목 중복)
                    # - .action (글자크기/인쇄/공유 버튼)
                    # - .time (날짜/시간 — 본문 아님)
                    # - script, style, nav, footer 일반 노이즈
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


def get_parser(feed_type: str, feed_url: str, feed_name: str = '', 
               language: str = 'en', **kwargs) -> BaseFeedParser:
    """
    피드 타입에 따른 적절한 파서 반환
    
    Args:
        feed_type: 'rss', 'web', 'web_detail'
        feed_url: 피드 URL
        feed_name: 피드 이름
        language: 언어 코드
        **kwargs: WebParser용 추가 셀렉터 설정
    
    Returns:
        BaseFeedParser 인스턴스
    """
    if feed_type == 'rss':
        return RSSParser(feed_url, feed_name, language)
    elif feed_type in ('web', 'web_detail'):
        return WebParser(feed_url, feed_name, language, **kwargs)
    else:
        logger.warning(f"알 수 없는 피드 타입 '{feed_type}', RSS로 폴백")
        return RSSParser(feed_url, feed_name, language)