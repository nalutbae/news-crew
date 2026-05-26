# Telegram Bot 사용 가이드

## 개요

이 모듈은 python-telegram-bot를 사용하여 번역된 뉴스를 Telegram 채널로 전송합니다.

## 설치

```bash
pip install -r requirements.txt
```

## 환경 변수 설정

`.env` 파일을 생성하고 다음 환경 변수를 설정하세요:

```bash
cp .env.example .env
```

`.env` 파일에 다음 내용을 수정하여 입력:

```bash
# Telegram Bot 토큰 (@BotFather에서 발급)
TELEGRAM_BOT_TOKEN=your_actual_bot_token_here

# Telegram 채널 ID (예: -1001234567890)
TELEGRAM_CHANNEL_ID=your_channel_id
```

### Bot Token 얻는 방법

1. Telegram에서 [@BotFather](https://t.me/botfather) 챗봇을 엽니다
2. `/newbot` 명령어를 입력하여 새 봇을 생성합니다
3. 봇 이름과 사용자 이름을 입력합니다
4. 생성된 Bot Token을 복사합니다 (예: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 채널 ID 얻는 방법

1. 봇을 채널에 관리자로 추가합니다
2. 해당 채널에 메시지를 보냅니다
3. 브라우저에서 `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`에 접속합니다
4. 응답에서 `{"message":{"chat":{"id":-1001234567890}}}` 형식의 ID를 찾습니다
5. `-100`으로 시작하는 숫자가 채널 ID입니다

## 기본 사용

### 함수 API

#### `send_translated_news(channel_id, title, content, url, source_name, hashtag=None)`

번역된 뉴스를 지정한 채널에 전송합니다.

```python
from telegram_bot import send_translated_news

success = send_translated_news(
    channel_id="-1001234567890",
    title="뉴스 제목",
    content="뉴스 내용 (HTML 가능)",
    url="https://example.com/article",
    source_name="연합뉴스",
    hashtag="경제"
)

print(f"전송 성공: {success}")
```

#### `send_to_default_channel(title, content, url, source_name, hashtag=None)`

환경 변수 `TELEGRAM_CHANNEL_ID`로 설정된 기본 채널에 전송합니다.

```python
from telegram_bot import send_to_default_channel

success = send_to_default_channel(
    title="뉴스 제목",
    content="뉴스 내용",
    url="https://example.com/article",
    source_name="연합뉴스",
    hashtag="경제"
)
```

### 메시지 포맷

전송되는 메시지 형식:

```
📰 [번역된 제목]

[번역된 내용 요약]

🔗 [원문 링크](url)

출처: [source_name] | #{hashtag}
```

## 특징

### 1. HTML → 텍스트 변환

HTML 태그가 포함된 content를 자동으로 텍스트로 변환합니다:

```python
content = "<p>테스트 <strong>볼드</strong> 텍스트</p>"
# 자동으로: "테스트 볼드 텍스트"로 변환
```

### 2. MarkdownV2 이스케이프

Telegram의 MarkdownV2 포맷을 사용하며, 특수문자를 자동으로 이스케이프 처리합니다.

### 3. 메시지 길이 제한

Telegram의 4096자 제한을 초과하지 않도록 자동으로 자릅니다:

```python
# 최대 1000자까지 내용 포함
truncated_content = truncate_message(content, max_length=1000)
```

### 4. 네트워크 오류 자동 재시도

네트워크 오류 발생 시 최대 3회까지 재시도하며, 지수 백오프를 적용합니다:

- 1차 시도: 즉시
- 2차 시도: 2초 대기
- 3차 시도: 4초 대기

### 5. 상세 로깅

모든 전송 결과와 오류를 로깅합니다:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## 테스트

```bash
python test_telegram_bot.py
```

테스트 항목:
- MarkdownV2 이스케이프 처리
- HTML → 텍스트 변환
- 메시지 길이 제한 처리
- 메시지 포맷팅

## 통합 예제

```python
import asyncio
from telegram_bot import send_translated_news

async def send_news_example():
    news_data = {
        "title": "한국 경제 성장률 2024년 2.4% 전망",
        "content": "<p>한은이 최근 <strong>경제 전망 보고서</strong>에서 2024년 경제 성장률이 2.4%로 전망된다고 밝혔다.</p>",
        "url": "https://news.example.com/economy-2024",
        "source_name": "연합뉴스",
        "hashtag": "경제"
    }
    
    channel_id = "-1001234567890"
    success = send_translated_news(
        channel_id=channel_id,
        **news_data
    )
    
    if success:
        print("뉴스 전송 성공!")
    else:
        print("뉴스 전송 실패!")

# 실행
asyncio.run(send_news_example())
```

## 주의사항

1. **Bot Token 보안**: `.env` 파일을 Git에 커밋하지 마세요. `.gitignore`에 `.env`가 포함되어 있는지 확인하세요.
2. **채널 권한**: 봇이 채널에 메시지를 보낼 수 있도록 관리자 권한이 필요합니다.
3. **Rate Limit**: Telegram API는 rate limit이 있으므로 너무 많은 메시지를 빠르게 보내면 제한될 수 있습니다. 간격을 두고 전송하세요.
4. **프록시 설정**: 한국에서 사용 시 프록시 설정이 필요할 수 있습니다. HTTPXRequest에서 연결 설정을 조정하세요.

## DB 연동 (별도 스케줄링 코드에서 구현 필요)

전송 성공 시 DB의 `articles.sent_at` 필드에 타임스탬프를 기록하려면, 스케줄링 코드에서 다음과 같이 구현해야 합니다:

```python
from datetime import datetime
from telegram_bot import send_translated_news

# 전송 시도
success = send_translated_news(channel_id, title, content, url, source_name)

# 전송 성공 시 DB 업데이트
if success:
    from database import update_article_sent_time
    update_article_sent_time(article_id, datetime.now())
```

이 부분은 별도의 스케줄링/스크래핑 코드에서 구현해야 합니다.

## 문제 해결

### "Bad Request" 오류

- 채널 ID가 올바른지 확인하세요
- 봇이 채널의 관리자로 추가되었는지 확인하세요

### "Unauthorized" 오류

- Bot Token이 올바른지 확인하세요
- 봇이 활성화 상태인지 확인하세요 (@BotFather에서 확인)

### 네트워크 타임아웃

- 인터넷 연결을 확인하세요
- 한국에서 사용 시 VPN이나 프록시가 필요할 수 있습니다

## 지원

문제가 발생하면 로그를 확인하고, python-telegram-bot 공식 문서를 참조하세요:
- [공식 문서](https://docs.python-telegram-bot.org/)
- [GitHub Repository](https://github.com/python-telegram-bot/python-telegram-bot)