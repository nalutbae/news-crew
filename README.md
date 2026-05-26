# News Crew 🗞️

다국어 뉴스 RSS/웹 크롤러 → 한국어 번역 → 텔레그램 채널 자동 발송 시스템

이란(Fars News, Araghchi, IRNA), 중국(외교부), 러시아(외무부) 등의 외교·안보 뉴스를 자동 수집해 한국어로 번역하여 텔레그램 채널에 발송합니다.

## 목차

- [아키텍처](#아키텍처)
- [크롤링 구조와 작동 방식](#크롤링-구조와-작동-방식)
- [스케줄링 구조](#스케줄링-구조)
- [설치 및 설정](#설치-및-설정)
- [프로그램 조작 방법](#프로그램-조작-방법)
- [피드 관리](#피드-관리)
- [프로젝트 구조](#프로젝트-구조)
- [의존성](#의존성)
- [라이선스](#라이선스)

---

## 아키텍처

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   스케줄러    │────▶│    크롤러     │────▶│    번역기     │────▶│  텔레그램 봇  │
│ APScheduler │     │ NewsCrawler  │     │ GoogleTrans  │     │ python-tg-bot│
│  (5분 간격)  │     │              │     │  (deep-trans) │     │              │
└─────────────┘     └──────┬───────┘     └──────────────┘     └──────┬───────┘
                           │                                          │
                    ┌──────▼───────┐                          ┌──────▼───────┐
                    │   파서 패키지  │                          │  SQLite DB   │
                    │   parsers/   │                          │ news_crew.db │
                    └──────────────┘                          └──────────────┘
```

**데이터 흐름:**

1. **스케줄러**가 5분마다 `crawl_job()` 실행
2. **크롤러**가 DB에서 크롤링 주기가 도래한 피드 조회
3. **파서**가 피드 타입에 따라 RSS/Web 파싱 → 새 아티클 추출
4. **번역기**가 원문을 한국어로 번역 (Google Translate 비공식 API, 무료/한도 없음)
5. **텔레그램 봇**이 번역된 아티클을 채널에 발송
6. DB에 `sent_at` 타임스탬프 업데이트

---

## 크롤링 구조와 작동 방식

### 파서 라우팅 (`parsers/`)

URL과 `feed_type`에 따라 자동으로 적절한 파서가 선택됩니다:

```
get_parser(feed_type, feed_url)
│
├── feed_type='rss' + URL에 'tg.i-c-a.su' 포함 → TgRssParser
│   └── 텔레그램 채널 RSS (터키어 이란 뉴스)
│
├── feed_type='rss' (일반) → RSSParser
│   └── feedparser 라이브러리 + cloudscraper 세션
│   └── mid.ru 등 봇 감지 사이트 자동 우회
│
└── feed_type='web' / 'web_detail' → WebParser
    └── 2단계 크롤링 (리스트 페이지 → 상세 페이지)
    └── 도메인별 CSS 셀렉터 자동 매칭
```

### RSS 파서 (`RSSParser`)

- **feedparser** 라이브러리로 RSS/Atom 피드 파싱
- **cloudscraper** 세션으로 봇 감지 사이트 우회 (mid.ru, presstv.ir 등)
- 엔트리에서 제목, URL, 내용, 발행일 추출
- `(feed_id, url)` UNIQUE 제약으로 중복 아티클 방지

### tg.i-c-a.su 파서 (`TgRssParser`)

- `RSSParser` 상속, 기본 동작은 동일
- 향후 텔레그램 채널 전용 전처리(채널명 정제, 태그 제거)를 위해 분리
- DB에 RSS 피드 URL만 추가하면 자동 크롤링

### 웹 스크래핑 파서 (`WebParser`)

2단계 크롤링 구조:

```
1단계: 리스트 페이지 → CSS 셀렉터로 링크 목록 추출
2단계: 각 링크 → 상세 페이지에서 제목/내용 추출
```

- 도메인별 CSS 셀렉터를 `DOMAIN_SELECTORS` 딕셔너리에서 관리
- 새 웹 사이트 추가 시 `DOMAIN_SELECTORS`에 설정만 추가하면 됨
- 인코딩 자동 감지 (BOM, Content-Type, meta charset, 도메인 힌트)
- 제목 노이즈 자동 제거 (【】, 날짜, "打印" 등)

### 봇 감지 회피 (`anti_bot.py`)

| 기능 | 설명 |
|------|------|
| User-Agent 로테이션 | 12개 실제 브라우저 UA 풀에서 매 요청마다 랜덤 선택 |
| cloudscraper | JavaScript 챌린지(F5, Cloudflare) 자동 우회 |
| 세션 캐시 | 도메인별 세션 유지 (쿠키/인증 상태) |
| 폴백 | cloudscraper 미설치 시 일반 `requests`로 자동 전환 |

> **참고:** 러시아 외무부(mid.ru)는 F5 봇 감지가 매우 강력하여 cloudscraper로도 우회 불가. Google News RSS(`site:mid.ru`)를 미러로 사용 중.

### 중복 방지

```
아티클 저장 시: (feed_id, url) UNIQUE 제약 → 동일 URL 재저장 방지
번역 캐시: translation_hash = SHA256(title + content) → 동일 내용 재번역 방지
```

---

## 스케줄링 구조

### APScheduler 구성

```python
# config.py — 스케줄러 설정
SchedulerConfig:
    interval_minutes: 5        # 크롤링 주기 (분)
    coalesce: True             # 누락된 작업 병합
    misfire_grace_time: 60     # 누락 허용 시간 (초)
    max_instances: 1           # 동시 실행 인스턴스 수
```

### 피드별 크롤링 주기

스케줄러는 5분마다 실행되지만, **각 피드의 `crawl_interval`**에 따라 실제 크롤링 여부를 결정합니다:

| 조건 | 동작 |
|------|------|
| `last_checked`가 없음 | 첫 실행 → 무조건 크롤링 |
| `now >= last_checked + crawl_interval` | 크롤링 주기 도래 → 크롤링 |
| `now < last_checked + crawl_interval` | 아직 도래 안 함 → 건너뜀 |

### 유효한 크롤링 주기 (분)

```
5, 10, 15, 30, 60, 120, 360, 720, 1440 (1일)
```

### 기본 피드 및 주기

| 피드 | 타입 | 언어 | 주기 | 활성 |
|------|------|------|------|------|
| Araghchi (이란외교부) | RSS | fa | 30분 | ✅ |
| Fars News (이란) | RSS | fa | 10분 | ✅ |
| 모즈타바 하메네이(이란) | RSS | fa | 10분 | ✅ |
| 중국외교부 대변인 브리핑 | Web | zh | 360분(6시간) | ✅ |
| 러시아 외무부 (MID) | RSS | ru | 30분 | ✅ |
| IRNA (이란) | RSS | en | 5분 | 비활성 |
| Press TV (이란) | RSS | en | 5분 | 비활성 |
| Xinhua (중국) | RSS | en | 5분 | 비활성 |
| CGTN (중국) | RSS | en | 5분 | 비활성 |
| Tasnim (이란) | RSS | fa | 5분 | 비활성 |

---

## 설치 및 설정

### 1. 저장소 클론 및 의존성 설치

```bash
git clone https://github.com/nalutbae/news-crew.git
cd news-crew

# Python 가상환경 (pyenv 권장)
pyenv install 3.12    # 3.12 이상 필요
pyenv local 3.12
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일 수정:

```ini
# 필수 — 텔레그램 봇 (@BotFather에서 발급)
TELEGRAM_BOT_TOKEN=8807365706:AAG...

# 필수 — 텔레그램 채널 ID
TELEGRAM_CHANNEL_ID=-1003902680445

# 선택 — DB 경로 (기본값: news_crew.db)
DB_PATH=news_crew.db

# 선택 — 로그 레벨 (기본값: INFO)
LOG_LEVEL=INFO

# 선택 — 로그 파일 경로 (기본값: logs/news_crew.log)
LOG_FILE=logs/news_crew.log
```

### 3. 데이터베이스 초기화

```bash
python init_db.py
```

기본 피드 9개가 자동 삽입됩니다.

### 4. (선택) cloudscraper 설치

봇 감지 사이트(mid.ru 등) 크롤링에 필요합니다:

```bash
pip install cloudscraper>=1.2.71
```

> 미설치 시 일반 `requests`로 자동 폴백됩니다.

---

## 프로그램 조작 방법

### 시작

```bash
# 가상환경 활성화
source .venv/bin/activate

# 백그라운드 실행 (권장)
nohup python main.py > logs/stdout.log 2>&1 &

# 또는 포그라운드 실행 (디버깅용, Ctrl+C로 종료)
python main.py
```

실행 시 동작:

1. DB 초기화 (테이블 자동 생성, 기본 피드 삽입)
2. **첫 실행: 모든 활성 피드 크롤링** (기존 아티클 건너뛰기)
3. APScheduler 시작 → 5분마다 `crawl_job()` 실행
4. 각 피드의 `crawl_interval`에 따라 실제 크롤링 여부 결정

### 중단

```bash
# 포그라운드 실행 중인 경우
Ctrl+C

# 백그라운드 실행 중인 경우
ps aux | grep "python main.py"   # PID 확인
kill <PID>                        # 정상 종료 (SIGTERM)
kill -9 <PID>                     # 강제 종료 (최후 수단)
```

> APScheduler가 SIGINT/SIGTERM 시그널을 감지하여 정상 종료합니다.

### 상태 체크

```bash
# 1. 프로세스 실행 여부 확인
ps aux | grep "python main.py"

# 2. 최근 로그 확인
tail -50 logs/news_crew.log

# 3. 실시간 로그 모니터링
tail -f logs/news_crew.log

# 4. DB 내 아티클/피드 상태 확인
python -c "
from models import get_engine, get_session, Feed, Article
from datetime import datetime, timedelta

engine = get_engine('news_crew.db')
session = get_session(engine)

# 활성 피드 목록
feeds = session.query(Feed).filter(Feed.is_active == True).all()
print(f'활성 피드: {len(feeds)}개')
for f in feeds:
    print(f'  [{f.id}] {f.name} ({f.feed_type}, {f.language}, interval={f.crawl_interval}분)')

# 최근 24시간 아티클
since = datetime.utcnow() - timedelta(hours=24)
recent = session.query(Article).filter(Article.created_at >= since).all()
print(f'\\n최근 24시간 아티클: {len(recent)}개')

# 전송 대기 아티클
pending = session.query(Article).filter(Article.sent_at == None).all()
print(f'전송 대기: {len(pending)}개')

session.close()
"

# 5. 특정 피드 크롤링 상태
python -c "
from models import get_engine, get_session, Feed
engine = get_engine('news_crew.db')
session = get_session(engine)
for f in session.query(Feed).all():
    print(f'{f.name}: last_checked={f.last_checked}, interval={f.crawl_interval}분, active={f.is_active}')
session.close()
"
```

### 단일 크롤링 테스트

```bash
# 전체 피드 크롤링 (스케줄러 없이 1회만)
python -c "
from crawl import NewsCrawler
crawler = NewsCrawler(db_path='news_crew.db')
new = crawler.crawl_all(due_only=False)
print(f'새 아티클: {len(new)}개')
for a in new[:5]:
    print(f'  {a.title[:60]}')
"

# 특정 피드만 크롤링
python -c "
from parsers import get_parser
parser = get_parser('rss', 'https://www.farsnews.ir/en/rss', 'Fars News', 'fa')
result = parser.parse()
print(f'항목: {len(result.items)}개')
print(f'에러: {len(result.errors)}개')
for item in result.items[:3]:
    print(f'  {item[\"title\"][:60]}')
"
```

---

## 피드 관리

### 새 피드 추가

**방법 1: init_db.py에 영구 추가**

`init_db.py`의 `DEFAULT_FEEDS` 리스트에 항목 추가:

```python
{
    'name': '새 피드 이름',
    'url': 'https://example.com/rss',
    'feed_type': 'rss',       # 'rss' | 'web'
    'language': 'en',          # fa, zh, en, ru, ar, ja
    'hashtag': '해시태그',
    'crawl_interval': 30,      # 분 단위 (유효값: 5,10,15,30,60,120,360,720,1440)
},
```

> DB가 비어 있을 때만 자동 삽입됩니다. 기존 DB에는 직접 추가해야 합니다.

**방법 2: DB에 직접 추가**

```python
from models import get_engine, get_session, Feed

engine = get_engine('news_crew.db')
session = get_session(engine)

new_feed = Feed(
    name='새 피드 이름',
    url='https://example.com/rss',
    feed_type='rss',
    language='en',
    hashtag='해시태그',
    crawl_interval=30,
    is_active=True
)
session.add(new_feed)
session.commit()
session.close()
```

### tg.i-c-a.su 피드 추가

tg.i-c-a.su RSS 피드는 동일한 구조이므로 DB에 URL만 추가하면 자동으로 `TgRssParser`가 선택됩니다:

```python
Feed(
    name='채널 이름',
    url='https://tg.i-c-a.su/rss/farsna',
    feed_type='rss',
    language='fa',
    hashtag='이란',
    crawl_interval=10,
    is_active=True
)
```

### 피드 활성화/비활성화

```python
from models import get_engine, get_session, Feed

engine = get_engine('news_crew.db')
session = get_session(engine)

# 비활성화
feed = session.query(Feed).filter(Feed.name == 'IRNA (이란)').first()
feed.is_active = False
session.commit()

# 활성화
feed.is_active = True
session.commit()

session.close()
```

### 피드 크롤링 주기 변경

```python
from config import VALID_CRAWL_INTERVALS

# 유효한 크롤링 주기: 5, 10, 15, 30, 60, 120, 360, 720, 1440 (분)
feed.crawl_interval = 60  # 1시간마다
session.commit()
```

---

## 프로젝트 구조

```
news-crew/
├── main.py                 # 메인 실행기 (APScheduler, 5분 간격)
├── config.py               # 설정 관리 (환경변수, 데이터클래스)
├── models.py               # SQLAlchemy ORM 모델 (Feed, Article)
├── crawl.py                # 크롤러 코어 (중복 체크, DB 저장)
├── init_db.py              # DB 초기화 + 기본 피드 삽입
├── translator.py           # Google Translate 번역 모듈
├── translation_cache.py    # SHA256 기반 번역 캐시
├── telegram_bot.py          # 텔레그램 메시지 전송
├── anti_bot.py              # 봇 감지 회피 (UA 로테이션, cloudscraper)
├── logging_config.py        # 로깅 설정 (RotatingFileHandler)
├── requirements.txt         # Python 의존성
├── .env                     # 환경변수 (TELEGRAM_BOT_TOKEN, CHANNEL_ID)
│
├── parsers/                 # 📦 파서 패키지 (타입별 분리)
│   ├── __init__.py          # get_parser() 라우팅
│   ├── base.py              # BaseFeedParser ABC, ParseResult
│   ├── rss_parser.py        # RSS/Atom 파서 (feedparser + cloudscraper)
│   ├── tg_rss_parser.py     # tg.i-c-a.su 전용 파서
│   └── web_parser.py        # 웹 스크래핑 파서 (2단계: 리스트→상세)
│
├── logs/                    # 로그 디렉토리 (자동 생성)
│   └── news_crew.log        # 회전 로그 (10MB × 5개)
│
└── news_crew.db             # SQLite 데이터베이스 (자동 생성)
```

---

## 의존성

| 패키지 | 용도 |
|--------|------|
| `feedparser` | RSS/Atom 피드 파싱 |
| `beautifulsoup4` | HTML 파싱 (웹 스크래핑) |
| `requests` | HTTP 요청 |
| `cloudscraper` | 봇 감지(JavaScript 챌린지) 우회 |
| `SQLAlchemy` | ORM, 데이터베이스 |
| `APScheduler` | 크롤링 스케줄러 |
| `python-telegram-bot` | 텔레그램 메시지 전송 |
| `deep-translator` | Google Translate 번역 (무료, 한도 없음) |
| `python-dotenv` | 환경변수 관리 |

---

## 라이선스

Private — nalutbae