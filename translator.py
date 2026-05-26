"""
Google Translate 비공식 API 번역 모듈 (deep-translator)

설계:
- deep-translator GoogleTranslator 사용 (무료, 한도 없음)
- 자동 언어 감지 지원
- 동기 호출 — 스레드 안전
- translation_hash로 DB 중복 번역 방지
- 4500자 초과 텍스트 자동 분할 처리
- fa→ko, zh→ko, en→ko 번역 지원
"""

import logging
from typing import Optional, Tuple

from deep_translator import GoogleTranslator

from models import Article, get_session, get_engine
from translation_cache import TranslationCache
from crawl import compute_translation_hash

logger = logging.getLogger(__name__)

# Google Translate 비공식 API — 한도 없음, 무료
MAX_CHARS_PER_REQUEST = 4500  # Google Translate 안전 한도

# 지원 언어 페어
SUPPORTED_LANGS = {'fa', 'zh', 'en', 'ru', 'ar', 'ko', 'ja'}

# deep-translator 언어 코드 매핑 (Google 코드 → deep-translator 코드)
LANG_CODE_MAP = {
    'fa': 'fa',       # 페르시아어
    'zh': 'zh-CN',    # 중국어 간체
    'en': 'en',       # 영어
    'ru': 'ru',       # 러시아어
    'ar': 'ar',       # 아랍어
    'ja': 'ja',       # 일본어
    'ko': 'ko',       # 한국어
}


def _split_text(text: str, max_chars: int = MAX_CHARS_PER_REQUEST) -> list:
    """
    긴 텍스트를 문단/문장 단위로 분할

    4500자 이상 텍스트 자동 분할 처리
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
                import re
                # 페르시아어/중국어 문장 구분자 포함
                sentences = re.split(r'(?<=[.!?。！？؟。])\s*', para)
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


def translate_text(text: str, source_lang: str, target_lang: str = 'ko') -> Optional[str]:
    """
    Google Translate 비공식 API로 텍스트 번역 (무료, 한도 없음)

    Args:
        text: 원본 텍스트
        source_lang: 원본 언어 코드 (fa, zh, en, ru, ar 등)
        target_lang: 대상 언어 코드 (기본값: ko)

    Returns:
        번역된 텍스트 또는 None
    """
    if not text or not text.strip():
        return ''

    # 언어 코드 매핑
    src = LANG_CODE_MAP.get(source_lang, source_lang)
    tgt = LANG_CODE_MAP.get(target_lang, target_lang)

    if source_lang not in SUPPORTED_LANGS:
        logger.warning(f"지원되지 않는 언어: {source_lang}, 직접 번역 시도")

    chunks = _split_text(text)
    if not chunks:
        return ''

    translator = GoogleTranslator(source=src, target=tgt)
    translated_chunks = []

    for i, chunk in enumerate(chunks):
        try:
            result = translator.translate(chunk)
            if result:
                translated_chunks.append(result)
            else:
                logger.warning(f"청크 {i+1}/{len(chunks)} 번역 결과 없음, 원문 유지")
                translated_chunks.append(chunk)
        except Exception as e:
            logger.error(f"Google Translate 청크 {i+1}/{len(chunks)} 실패: {e}")
            translated_chunks.append(chunk)  # 폴백: 원문 유지

    return '\n'.join(translated_chunks)


def _strip_html(text: str) -> str:
    """HTML 태그를 제거하고 순수 텍스트만 반환 (번역 품질 관리)"""
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