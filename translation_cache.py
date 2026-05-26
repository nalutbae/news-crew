"""
번역 캐시 모듈

translation_hash = SHA256(title + content) 기반 DB 캐시
동일 내용의 재번역을 방지하여 API 호출 최소화
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from models import Article
from crawl import compute_translation_hash

logger = logging.getLogger(__name__)


class TranslationCache:
    """
    DB 기반 번역 캐시
    
    translation_hash로 동일 내용의 재번역을 방지
    """
    
    def __init__(self, session: Session):
        self.session = session
    
    def get(self, translation_hash: str) -> Optional[dict]:
        """
        캐시에서 번역 결과 조회
        
        Returns:
            {'translated_title': ..., 'translated_content': ...} 또는 None
        """
        article = self.session.query(Article).filter(
            Article.translation_hash == translation_hash,
            Article.translated_title.isnot(None),
        ).first()
        
        if article and article.translated_title:
            logger.debug(f"번역 캐시 히트: hash={translation_hash[:12]}...")
            return {
                'translated_title': article.translated_title,
                'translated_content': article.translated_content,
            }
        
        return None
    
    def get_by_text(self, title: str, content: str) -> Optional[dict]:
        """
        원문으로 번역 캐시 조회 (편의 메서드)
        """
        translation_hash = compute_translation_hash(title, content or '')
        return self.get(translation_hash)
    
    def put(self, article_id: int, translated_title: str, translated_content: str) -> bool:
        """
        번역 결과를 DB에 저장
        
        Args:
            article_id: Article ID
            translated_title: 번역된 제목
            translated_content: 번역된 내용
        
        Returns:
            저장 성공 여부
        """
        article = self.session.query(Article).get(article_id)
        if not article:
            logger.warning(f"아티클 ID {article_id} 없음, 캐시 저장 실패")
            return False
        
        article.translated_title = translated_title
        article.translated_content = translated_content
        self.session.commit()
        
        logger.debug(f"번역 캐시 저장: article_id={article_id}")
        return True