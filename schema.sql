-- News Crew 데이터베이스 스키마 (참조용 DDL)
-- SQLAlchemy ORM에서 자동 생성되지만, 수동 초기화나 마이그레이션에 사용

CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    feed_type VARCHAR(50) NOT NULL DEFAULT 'rss',
    is_active BOOLEAN DEFAULT 1,
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    hashtag VARCHAR(100),
    last_checked DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    published_at DATETIME,
    translation_hash VARCHAR(64),
    translated_title TEXT,
    translated_content TEXT,
    sent_at DATETIME,
    author VARCHAR(255),
    category VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
    CONSTRAINT uq_feed_url UNIQUE (feed_id, url)
);

CREATE INDEX IF NOT EXISTS ix_articles_translation_hash ON articles(translation_hash);
CREATE INDEX IF NOT EXISTS ix_articles_sent_at ON articles(sent_at);

-- 초기 피드 데이터 (중동/중국 관련 소식)
INSERT OR IGNORE INTO feeds (name, url, feed_type, language, hashtag) VALUES
    ('IRNA (이란)', 'https://en.irna.ir/rss', 'rss', 'en', '이란'),
    ('Press TV (이란)', 'https://www.presstv.ir/rss', 'rss', 'en', '이란'),
    ('Xinhua (중국)', 'http://www.xinhuanet.com/english/rss/world.xml', 'rss', 'en', '중국'),
    ('CGTN (중국)', 'https://news.cgtn.com/news/rss/world.rss', 'rss', 'en', '중국'),
    ('중국외교부', 'https://www.mfa.gov.cn/wjb/wjbzwd/wjbxw/', 'web', 'zh', '중국'),
    ('Tasnim (이란)', 'https://www.tasnimnews.com/en/rss', 'rss', 'fa', '이란');