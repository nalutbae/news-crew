"""
뉴스 크롤러 모듈

- NewsCrawler: DB에서 활성 피드 조회 → 파서 선택 → 중복 체크 → DB 저장
- dedup: (feed_id, url) UNIQUE 제약으로 중복 발송 방지
- translation_hash = SHA256(title + content)로 번역 캐시 체크
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from models import Feed, Article, get_session, get_engine
from parsers import get_parser, ParseResult
from config import VALID_CRAWL_INTERVALS, MAX_ARTICLES_PER_FEED
from anti_bot import install_cloudscraper

logger = logging.getLogger(__name__)


def prune_old_articles(session: Session, feed_id: int, keep: int = MAX_ARTICLES_PER_FEED) -> int:
    """
    피드별 오래된 아티클 정리 — 최근 keep개만 유지
    
    Pi 2 SD 마모 방지: 오래된 아티클을 삭제해 DB 크기를 일정하게 유지.
    VACUUM은 자동으로 실행하지 않음 (SD 쓰기 최소화).
    
    Args:
        session: DB 세션
        feed_id: 피드 ID
        keep: 유지할 아티클 수 (기본값: 50)
    
    Returns:
        삭제된 아티클 수
    """
    # 해당 피드의 전체 아티클 수
    total = session.query(Article).filter(Article.feed_id == feed_id).count()
    
    if total <= keep:
        return 0
    
    # keep번째 아티클의 ID = 이 ID 이상은 유지
    keep_from = (
        session.query(Article.id)
        .filter(Article.feed_id == feed_id)
        .order_by(Article.id.desc())
        .offset(keep - 1)
        .first()
    )
    
    if not keep_from:
        return 0
    
    # keep_from 미만 아티클 일괄 삭제
    deleted = session.query(Article).filter(
        Article.feed_id == feed_id,
        Article.id < keep_from[0],
    ).delete(synchronize_session='fetch')
    
    session.commit()
    logger.info(f"피드 ID={feed_id}: 아티클 정리 {deleted}개 삭제 (유지: {keep}개)")
    return deleted


def compute_translation_hash(title: str, content: str) -> str:
    """
    SHA256(title + content) 번역 캐시 키 생성
    
    번역 모듈(translator.py) 및 models.py와 동일한 컨벤션
    """
    raw = f"{title}{content}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class NewsCrawler:
    """
    뉴스 크롤러 - 피드 조회 → 파싱 → 중복 체크 → DB 저장
    
    Usage:
        crawler = NewsCrawler(db_path='news_crew.db')
        new_articles = crawler.crawl_all()
    """
    
    def __init__(self, db_path: str = None, session: Session = None):
        if session:
            self.session = session
            self._owns_session = False
        else:
            engine = get_engine(db_path)
            self.session = get_session(engine)
            self._owns_session = True
    
    def __del__(self):
        if hasattr(self, '_owns_session') and self._owns_session:
            try:
                self.session.close()
            except Exception:
                pass
    
    def get_active_feeds(self) -> List[Feed]:
        """활성화된 피드 목록 조회"""
        feeds = self.session.query(Feed).filter(Feed.is_active == True).all()
        logger.info(f"활성 피드 {len(feeds)}개 조회됨")
        return feeds
    
    def get_due_feeds(self) -> List[Feed]:
        """
        크롤링 주기가 도래한 활성 피드만 조회
        
        조건: last_checked가 없거나, last_checked + crawl_interval(분) <= now
        한국시간 자정(00:00 KST = 15:00 UTC 전일)을 기준으로 간격 계산.
        
        Returns:
            크롤링이 필요한 Feed 리스트
        """
        now = datetime.utcnow()
        
        # 모든 활성 피드 조회
        active_feeds = self.session.query(Feed).filter(Feed.is_active == True).all()
        
        due_feeds = []
        skipped_feeds = []
        
        for feed in active_feeds:
            # crawl_interval 유효성 검증
            interval = feed.crawl_interval
            if interval not in VALID_CRAWL_INTERVALS:
                logger.warning(
                    f"피드 '{feed.name}' 유효하지 않은 crawl_interval={interval}, "
                    f"기본값({VALID_CRAWL_INTERVALS[0]})으로 처리"
                )
                interval = VALID_CRAWL_INTERVALS[0]
            
            if feed.last_checked is None:
                # 한 번도 크롤링하지 않은 피드 → 항상 크롤링
                due_feeds.append(feed)
            else:
                # 마지막 확인 시간 + interval이 현재 시간 이전이면 크롤링 대상
                next_check = feed.last_checked + timedelta(minutes=interval)
                if next_check <= now:
                    due_feeds.append(feed)
                else:
                    remaining = (next_check - now).total_seconds() / 60
                    skipped_feeds.append((feed.name, remaining))
        
        if skipped_feeds:
            logger.debug(
                f"interval 미도래 피드 {len(skipped_feeds)}개 건너뜀: "
                + ", ".join(f"{n}({r:.0f}분 후)" for n, r in skipped_feeds)
            )
        
        logger.info(
            f"크롤링 대상 피드: {len(due_feeds)}/{len(active_feeds)}개 "
            f"(건너뜀: {len(active_feeds) - len(due_feeds)}개)"
        )
        return due_feeds
    
    def crawl_feed(self, feed: Feed) -> List[Article]:
        """
        단일 피드 크롤링
        
        Returns:
            새로 발견된 Article 리스트 (아직 번역/전송되지 않은 것)
        """
        logger.info(f"피드 크롤링 시작: {feed.name} ({feed.feed_type})")
        
        # 파서 선택
        parser = get_parser(
            feed_type=feed.feed_type,
            feed_url=feed.url,
            feed_name=feed.name,
            language=feed.language,
        )
        
        # 파싱
        result = parser.parse()
        
        # 에러 로깅
        for err in result.errors:
            logger.warning(f"파싱 에러 ({feed.name}): {err}")
        
        # DB 저장
        new_articles = []
        for item in result.items:
            try:
                article = self._save_article(feed, item)
                if article:
                    new_articles.append(article)
            except Exception as e:
                logger.error(f"아티클 저장 실패 ({item.get('url', '?')}): {e}")
        
        # 피드 last_checked 업데이트
        feed.last_checked = datetime.utcnow()
        self.session.commit()
        
        # 피드별 아티클 정리 (Pi 2 DB 크기 관리)
        pruned = prune_old_articles(self.session, feed.id)
        if pruned:
            logger.debug(f"피드 {feed.name}: {pruned}개 오래된 아티클 정리됨")
        
        logger.info(f"피드 크롤링 완료: {feed.name} - 신규 {len(new_articles)}개 / 전체 {len(result.items)}개")
        return new_articles
    
    def _save_article(self, feed: Feed, item: dict) -> Optional[Article]:
        """
        아티클을 DB에 저장 (중복 체크)
        
        (feed_id, url) UNIQUE 제약으로 중복 방지
        """
        url = item.get('url', '')
        title = item.get('title', '')
        content = item.get('content', '')
        
        if not url or not title:
            logger.debug(f"URL 또는 제목 누락, 건너뜀")
            return None
        
        # 중복 체크
        existing = self.session.query(Article).filter(
            Article.feed_id == feed.id,
            Article.url == url
        ).first()
        
        if existing:
            logger.debug(f"중복 아티클, 건너뜀: {url[:80]}")
            return None
        
        # translation_hash 계산
        translation_hash = compute_translation_hash(title, content or '')
        
        # 새 아티클 생성
        article = Article(
            feed_id=feed.id,
            url=url,
            title=title,
            content=content,
            summary=item.get('summary', ''),
            published_at=item.get('published_at'),
            translation_hash=translation_hash,
            author=item.get('author', ''),
            category=item.get('category', ''),
        )
        
        self.session.add(article)
        self.session.flush()  # id 할당
        
        logger.info(f"신규 아티클 저장: [{feed.name}] {title[:50]}")
        return article
    
    def crawl_all(self, due_only: bool = True) -> List[Article]:
        """
        활성 피드 크롤링
        
        Args:
            due_only: True면 interval이 도래한 피드만 크롤링 (기본값)
                     False면 모든 활성 피드 크롤링 (첫 실행 등)
        
        Returns:
            새로 발견된 전체 Article 리스트
        """
        all_new = []
        feeds = self.get_due_feeds() if due_only else self.get_active_feeds()
        
        if not feeds:
            logger.info("크롤링 대상 피드가 없습니다")
            return all_new
        
        logger.info(f"=== 크롤링 시작: {len(feeds)}개 피드 ===")
        
        for feed in feeds:
            try:
                new_articles = self.crawl_feed(feed)
                all_new.extend(new_articles)
            except Exception as e:
                logger.error(f"피드 크롤링 실패 ({feed.name}): {e}")
        
        self.session.commit()
        
        logger.info(f"=== 크롤링 완료: 신규 {len(all_new)}개 ===")
        return all_new
    
    def mark_article_sent(self, article_id: int) -> bool:
        """아티클 전송 완료 표시 (sent_at 업데이트)"""
        article = self.session.query(Article).get(article_id)
        if article:
            article.sent_at = datetime.utcnow()
            self.session.commit()
            logger.info(f"아티클 전송 완료 표시: ID={article_id}")
            return True
        return False