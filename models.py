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
def get_engine(db_path: str = None):
    """SQLite 엔진 생성"""
    if db_path is None:
        import os
        db_path = os.getenv('DB_PATH', 'news_crew.db')
    return create_engine(f'sqlite:///{db_path}', echo=False)


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