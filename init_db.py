"""
데이터베이스 초기화 스크립트

- 테이블 생성
- 초기 피드 데이터 삽입
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

from models import get_engine, get_session, Base, Feed
from config import VALID_CRAWL_INTERVALS, DEFAULT_CRAWL_INTERVAL

logger = logging.getLogger(__name__)


# 기본 피드 목록
DEFAULT_FEEDS = [
    {
        'name': 'IRNA (이란)',
        'url': 'https://en.irna.ir/rss',
        'feed_type': 'rss',
        'language': 'en',
        'hashtag': '이란',
        'crawl_interval': 5,
    },
    {
        'name': 'Press TV (이란)',
        'url': 'https://www.presstv.ir/rss',
        'feed_type': 'rss',
        'language': 'en',
        'hashtag': '이란',
        'crawl_interval': 5,
    },
    {
        'name': 'Xinhua (중국)',
        'url': 'http://www.xinhuanet.com/english/rss/world.xml',
        'feed_type': 'rss',
        'language': 'en',
        'hashtag': '중국',
        'crawl_interval': 5,
    },
    {
        'name': 'CGTN (중국)',
        'url': 'https://news.cgtn.com/news/rss/world.rss',
        'feed_type': 'rss',
        'language': 'en',
        'hashtag': '중국',
        'crawl_interval': 5,
    },
    {
        'name': '중국외교부 대변인 브리핑',
        'url': 'https://www.mfa.gov.cn/fyrbt_673021/jzhsl_673025/',
        'feed_type': 'web',
        'language': 'zh',
        'hashtag': '중국',
        'crawl_interval': 360,  # 하루 1~2회 업데이트
    },
    {
        'name': 'Tasnim (이란)',
        'url': 'https://www.tasnimnews.com/en/rss',
        'feed_type': 'rss',
        'language': 'fa',
        'hashtag': '이란',
        'crawl_interval': 5,
    },
    {
        'name': 'Araghchi (이란외교부)',
        'url': 'https://araghchi.ir/en/rss',
        'feed_type': 'rss',
        'language': 'en',
        'hashtag': '이란',
        'crawl_interval': 30,   # RSS, 적당한 빈도
    },
    {
        'name': 'Fars News (이란)',
        'url': 'https://www.farsnews.ir/en/rss',
        'feed_type': 'rss',
        'language': 'fa',
        'hashtag': '이란',
        'crawl_interval': 10,   # 자주 업데이트
    },
]


def _migrate_crawl_interval(engine):
    """
    기존 DB에 crawl_interval 컬럼이 없으면 ALTER TABLE로 추가.
    
    SQLAlchemy의 create_all()은 새 테이블만 생성하므로,
    이미 존재하는 테이블에 컬럼을 추가하려면 명시적 마이그레이션이 필요.
    """
    from sqlalchemy import inspect as sa_inspect, text
    
    inspector = sa_inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('feeds')]
    
    if 'crawl_interval' not in columns:
        logger.info("마이그레이션: feeds 테이블에 crawl_interval 컬럼 추가")
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE feeds ADD COLUMN crawl_interval INTEGER NOT NULL DEFAULT 5"
            ))
            conn.commit()
        logger.info("crawl_interval 컬럼 추가 완료 (기본값: 5분)")
        
        # 기존 피드의 interval 값 업데이트
        session = get_session(engine)
        try:
            # 피드 이름 기반 interval 매핑
            interval_map = {
                '중국외교부 대변인 브리핑': 360,
                'Araghchi': 30,
                'Fars News': 10,
            }
            
            for feed in session.query(Feed).all():
                new_interval = None
                for key, interval in interval_map.items():
                    if key in feed.name:
                        new_interval = interval
                        break
                
                if new_interval and new_interval in VALID_CRAWL_INTERVALS:
                    feed.crawl_interval = new_interval
                    logger.info(f"피드 interval 설정: {feed.name} → {new_interval}분")
            
            session.commit()
            logger.info("기존 피드 interval 업데이트 완료")
        except Exception as e:
            session.rollback()
            logger.error(f"피드 interval 업데이트 실패: {e}")
        finally:
            session.close()


def init_database(db_path: str = None, insert_defaults: bool = True):
    """
    데이터베이스 초기화
    
    Args:
        db_path: DB 파일 경로 (None이면 환경 변수 또는 기본값 사용)
        insert_defaults: 기본 피드 데이터 삽입 여부
    """
    engine = get_engine(db_path)
    
    # 테이블 생성
    Base.metadata.create_all(engine)
    logger.info("DB 테이블 생성 완료")
    
    # crawl_interval 컬럼 마이그레이션 (기존 DB 대응)
    _migrate_crawl_interval(engine)
    
    if insert_defaults:
        session = get_session(engine)
        try:
            # 기존 피드 수 확인
            existing_count = session.query(Feed).count()
            
            if existing_count == 0:
                for feed_data in DEFAULT_FEEDS:
                    feed = Feed(**feed_data)
                    session.add(feed)
                    logger.info(f"피드 추가: {feed_data['name']}")
                
                session.commit()
                logger.info(f"기본 피드 {len(DEFAULT_FEEDS)}개 삽입 완료")
            else:
                logger.info(f"기존 피드 {existing_count}개 존재, 기본 삽입 건너뜀")
                
        except Exception as e:
            session.rollback()
            logger.error(f"피드 삽입 실패: {e}")
            raise
        finally:
            session.close()
    
    return engine


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    db_path = os.getenv('DB_PATH', 'news_crew.db')
    print(f"데이터베이스 초기화: {db_path}")
    
    engine = init_database(db_path)
    print("초기화 완료!")
    
    # 확인
    session = get_session(engine)
    feeds = session.query(Feed).all()
    print(f"\n등록된 피드 ({len(feeds)}개):")
    for f in feeds:
        print(f"  [{f.id}] {f.name} ({f.feed_type}, {f.language}, interval={f.crawl_interval}분)")
    session.close()