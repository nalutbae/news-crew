"""
SQLAlchemy ORM 모델 - News Crew 데이터베이스 스키마

핵심 설계:
- (feed_id, url) UNIQUE 제약으로 중복 아티클 방지
- translation_hash = SHA256(title + content)로 번역 캐시 체크
- FK CASCADE 삭제로 참조 무결성 보장
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.event import listens_for

Base = declarative_base()


class Feed(Base):
    """RSS/Web 피드 설정"""
    __tablename__ = 'feeds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, comment='피드 이름')
    url = Column(Text, nullable=False, comment='피드 URL')
    feed_type = Column(String(50), nullable=False, default='rss',
                       comment='피드 타입: rss, web, web_detail')
    is_active = Column(Boolean, default=True, comment='활성화 여부')
    language = Column(String(10), nullable=False, default='en',
                      comment='원본 언어 코드 (fa, zh, en 등)')
    hashtag = Column(String(100), nullable=True, comment='텔레그램 해시태그')
    crawl_interval = Column(Integer, nullable=False, default=5,
                             comment='크롤링 주기 (분). 유효값: 5,10,15,30,60,120,360,720,1440')
    last_checked = Column(DateTime, nullable=True, comment='마지막 확인 시간')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계
    articles = relationship('Article', back_populates='feed',
                            cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Feed(id={self.id}, name='{self.name}', type='{self.feed_type}')>"


class Article(Base):
    """크롤링된 뉴스 아티클"""
    __tablename__ = 'articles'
    __table_args__ = (
        UniqueConstraint('feed_id', 'url', name='uq_feed_url'),
        Index('ix_articles_translation_hash', 'translation_hash'),
        Index('ix_articles_sent_at', 'sent_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    feed_id = Column(Integer, ForeignKey('feeds.id', ondelete='CASCADE'),
                     nullable=False, comment='피드 FK')
    url = Column(Text, nullable=False, comment='아티클 URL')
    title = Column(Text, nullable=False, comment='원본 제목')
    content = Column(Text, nullable=True, comment='원본 내용')
    summary = Column(Text, nullable=True, comment='원본 요약')
    published_at = Column(DateTime, nullable=True, comment='발행일')
    
    # 번역 관련
    translation_hash = Column(String(64), nullable=True,
                              comment='SHA256(title+content) 번역 캐시 키')
    translated_title = Column(Text, nullable=True, comment='번역된 제목')
    translated_content = Column(Text, nullable=True, comment='번역된 내용')
    
    # 전송 관련
    sent_at = Column(DateTime, nullable=True, comment='텔레그램 전송 시간')
    
    # 메타
    author = Column(String(255), nullable=True, comment='작성자')
    category = Column(String(100), nullable=True, comment='카테고리')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계
    feed = relationship('Feed', back_populates='articles')

    def __repr__(self):
        return f"<Article(id={self.id}, title='{self.title[:30]}...')>"


# 데이터베이스 엔진 및 세션 팩토리

# Pi 2 SD 마모 방지를 위한 SQLite PRAGMA 설정
_SQLITE_PRAGMAS = {
    'journal_mode': 'WAL',        # Write-Ahead Logging: 읽기/쓰기 동시, 체크포인트만 쓰기
    'synchronous': 'NORMAL',     # FULL 대비 쓰기 빈도 감소, 전원 끊김 시 마지막 몇 초만 손실 가능
    'cache_size': '-2000',       # 2MB 캐시 (Pi 2 1GB RAM 고려)
    'temp_store': 'MEMORY',      # 임시 테이블 메모리 처리 (SD 쓰기 방지)
    'busy_timeout': '5000',      # 5초 대기 (동시 접근 시)
    'mmap_size': '8388608',      # 8MB mmap: 디스크 읽기를 메모리 매핑으로 대체 (SD I/O 감소)
    'wal_autocheckpoint': '500', # WAL 체크포인트 500페이지마다 (기본 1000, 낮춰서 쓰기 분산)
}


def get_engine(db_path: str = None):
    """
    SQLite 엔진 생성 (Pi 2 최적화 PRAGMA 포함)
    
    WAL 모드: 읽기/쓰기 동시 처리, 체크포인트만 실제 쓰기 → SD 쓰기 횟수 대폭 감소
    synchronous=NORMAL: fsync 빈도 감소, 전원 끊김 시 마지막 수초 데이터만 손실 가능
    mmap_size=8MB: 일반적인 뉴스 DB 크기(수천 건)를 메모리 매핑으로 처리 (디스크 읽기 최소화)
    wal_autocheckpoint=500: 체크포인트를 더 자주, 더 작게 수행 (SD 쓰기 부하 분산)
    
    Pi 2 특이사항:
    - 전원 끊김 리스크: NORMAL은 마지막 수초의 트랜잭션만 손실. 뉴스 크롤러는
      재시작 시 크롤링 재개하므로 치명적이지 않음.
    - VACUUM은 명시적 호출만: 자동 VACUUM 비활성화로 SD 쓰기 최소화.
      DB가 과도하게 커진 경우에만 수동 실행 권장.
    """
    if db_path is None:
        import os
        db_path = os.getenv('DB_PATH', 'news_crew.db')
    
    engine = create_engine(
        f'sqlite:///{db_path}',
        echo=False,
        connect_args={'check_same_thread': False},
    )
    
    # 연결 시마다 PRAGMA 자동 실행
    @listens_for(engine, 'connect')
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        for pragma_key, value in _SQLITE_PRAGMAS.items():
            cursor.execute(f'PRAGMA {pragma_key}={value}')
        cursor.close()
    
    return engine


def get_session(engine=None):
    """세션 팩토리"""
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def init_db(engine=None):
    """테이블 생성"""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)