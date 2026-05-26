"""
MyMemory 번역 서비스 모듈

설계:
- MyMemory free tier 사용 (API key 선택사항)
- async/await 패턴으로 비동기 번역 구현
- translation_hash로 DB 중복 번역 방지
- 1000자 이상 텍스트 자동 분할 처리
- fa→ko, zh→ko 번역 지원
"""

import os
import asyncio
import logging
import re
from typing import Optional, Tuple

import aiohttp
from dotenv import load_dotenv

from models import Article, get_session, get_engine
from translation_cache import TranslationCache
from crawl import compute_translation_hash

load_dotenv()

logger = logging.getLogger(__name__)

# MyMemory API 설정
MYMEMORY_API_URL = 'https://api.mymemory.translated.net/get'
MYMEMORY_API_KEY = os.getenv('MYMEMORY_API_KEY', '')  # 선택사항
MAX_CHARS_PER_REQUEST = 450  # MyMemory 무료 한도 (500자 서버 제한, 안전 마진)

# 지원 언어 페어
SUPPORTED_PAIRS = {
    'fa': 'farsi-to-korean',   # 페르시아어 → 한국어
    'zh': 'chinese-to-korean', # 중국어 → 한국어
    'en': 'english-to-korean', # 영어 → 한국어
    'ru': 'russian-to-korean', # 러시아어 → 한국어
    'ar': 'arabic-to-korean',  # 아랍어 → 한국어
}


def _split_text(text: str, max_chars: int = MAX_CHARS_PER_REQUEST) -> list:
    """
    긴 텍스트를 문단/문장 단위로 분할
    
    1000자 이상 텍스트 자동 분할 처리
    """
    if not text or len(text) <= max_chars:
        return [text] if text else []
    
    # 문단 단위 분할 우선
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ''
    
    for para in paragraphs:
        if len(current_chunk) + len(para) + 1 <= max_chars:
            current_chunk = current_chunk + '\n' + para if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # 단일 문단이 max_chars 초과 시 문장 단위 분할
            if len(para) > max_chars:
                sentences = re.split(r'(?<=[.!?。！？])\s+', para)
                sent_chunk = ''
                for sent in sentences:
                    if len(sent_chunk) + len(sent) + 1 <= max_chars:
                        sent_chunk = sent_chunk + ' ' + sent if sent_chunk else sent
                    else:
                        if sent_chunk:
                            chunks.append(sent_chunk)
                        sent_chunk = sent
                if sent_chunk:
                    current_chunk = sent_chunk
            else:
                current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


async def _translate_chunk(
    session: aiohttp.ClientSession,
    text: str,
    source_lang: str,
    target_lang: str = 'ko',
) -> Optional[str]:
    """
    단일 청크 번역 (MyMemory API 호출)
    
    POST 방식 사용 — GET은 URL 길이 제한(414 URI Too Long)으로 긴 텍스트 실패
    """
    lang_pair = f'{source_lang}|{target_lang}'
    
    data = {
        'q': text,
        'langpair': lang_pair,
    }
    
    if MYMEMORY_API_KEY:
        data['key'] = MYMEMORY_API_KEY
        data['de'] = os.getenv('MYMEMORY_EMAIL', 'news-crew@example.com')
    
    try:
        async with session.post(MYMEMORY_API_URL, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logger.error(f"MyMemory API HTTP {resp.status}")
                return None
            
            data = await resp.json()
            
            status = data.get('responseStatus', 0)
            if status != 200:
                logger.warning(f"MyMemory 응답 에러: {data.get('responseDetails', 'unknown')}")
                return None
            
            translated = data.get('responseData', {}).get('translatedText', '')
            
            # "MYMEMORY WARNING" 등 오류 메시지 처리
            if 'MYMEMORY' in translated.upper() and 'WARNING' in translated.upper():
                logger.warning(f"MyMemory 번역 경고: {translated[:100]}")
                return None
            
            return translated
            
    except asyncio.TimeoutError:
        logger.error("MyMemory API 타임아웃")
        return None
    except Exception as e:
        logger.error(f"MyMemory API 호출 실패: {e}")
        return None


async def translate_text_async(
    text: str,
    source_lang: str,
    target_lang: str = 'ko',
) -> Optional[str]:
    """
    비동기 텍스트 번역 (자동 분할 포함)
    
    Args:
        text: 원본 텍스트
        source_lang: 원본 언어 코드
        target_lang: 대상 언어 코드
    
    Returns:
        번역된 텍스트 또는 None
    """
    if not text or not text.strip():
        return ''
    
    # 지원되지 않는 언어 페어
    if source_lang not in SUPPORTED_PAIRS:
        logger.warning(f"지원되지 않는 언어: {source_lang}, 영어를 경유합니다")
        # 영어를 경유하는 2단계 번역은 복잡하므로 직젵 시도
    
    chunks = _split_text(text)
    if not chunks:
        return ''
    
    translated_chunks = []
    
    async with aiohttp.ClientSession() as session:
        tasks = [
            _translate_chunk(session, chunk, source_lang, target_lang)
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"청크 {i+1}/{len(chunks)} 번역 실패: {result}")
                translated_chunks.append(chunks[i])  # 폴백: 원문 유지
            elif result is None:
                logger.warning(f"청크 {i+1}/{len(chunks)} 번역 결과 없음, 원문 유지")
                translated_chunks.append(chunks[i])
            else:
                translated_chunks.append(result)
    
    return '\n'.join(translated_chunks)


def translate_text(text: str, source_lang: str, target_lang: str = 'ko') -> Optional[str]:
    """
    동기식 번역 래퍼
    
    APScheduler 스케줄러에서 호출하기 위한 동기 인터페이스
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # 이미 실행 중인 루프(예: APScheduler 스레드)에서는 새 루프 생성
        loop = asyncio.new_event_loop()
    
    return loop.run_until_complete(translate_text_async(text, source_lang, target_lang))


def _strip_html(text: str) -> str:
    """HTML 태그를 제거하고 순수 텍스트만 반환 (번역 품질 및 API 한도 관리)"""
    if not text:
        return ''
    if '<' in text and '>' in text:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, 'html.parser')
        # 불필요한 태그 제거
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'head']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        # 연속 공백 정리
        text = ' '.join(text.split())
    return text


def translate_article(article: Article, session=None) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    아티클 번역 (캐시 확인 포함)
    
    HTML 콘텐츠는 번역 전 텍스트로 변환하여 API 한도 관리
    
    Returns:
        (성공여부, 번역제목, 번역내용)
    """
    if not session:
        engine = get_engine()
        session = get_session(engine)
    
    cache = TranslationCache(session)
    
    # 캐시 확인
    if article.translation_hash:
        cached = cache.get(article.translation_hash)
        if cached:
            logger.info(f"번역 캐시 히트: article_id={article.id}")
            return True, cached['translated_title'], cached['translated_content']
    
    # 원문 언어 확인
    feed = article.feed
    source_lang = feed.language if feed else 'en'
    
    # 제목 번역
    translated_title = translate_text(article.title, source_lang)
    if not translated_title:
        logger.error(f"제목 번역 실패: article_id={article.id}")
        return False, None, None
    
    # 내용 번역 — HTML 태그 제거 후 텍스트만 번역
    raw_content = article.content or ''
    plain_content = _strip_html(raw_content)
    if plain_content and len(plain_content) > 50:
        translated_content = translate_text(plain_content, source_lang)
    else:
        translated_content = plain_content
    
    # 캐시 저장
    if translated_content is None:
        translated_content = ''
    
    cache.put(article.id, translated_title, translated_content)
    
    logger.info(f"번역 완료: article_id={article.id} ({source_lang}→ko)")
    return True, translated_title, translated_content